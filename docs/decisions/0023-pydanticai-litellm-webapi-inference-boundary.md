# ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary

- **日付**: 2026-05-07
- **ステータス**: Accepted
- **Supersedes**: ADR 0021 (partial — `available_api_models.toml` キャッシュ運用と WebAPI 用 user TOML override 部分)
- **関連 ADR**: [0021 LiteLLM-Driven WebAPI Model Registry](0021-litellm-driven-model-registry.md)
- **関連 ISSUE**:
  [image-annotator-lib#37](https://github.com/NEXTAltair/image-annotator-lib/issues/37),
  [#36](https://github.com/NEXTAltair/image-annotator-lib/issues/36),
  [#35](https://github.com/NEXTAltair/image-annotator-lib/issues/35)

## Context

ADR 0021 で WebAPI モデル一覧と capability metadata の正本を LiteLLM に寄せたが、
Issue #36 の調査で、LiteLLM の `provider/model` ID と PydanticAI の実行モデル指定を混同している
箇所が見つかった。

直接の不具合は `ProviderManager` が PydanticAI `Agent.run_sync()` に `BinaryContent` 単体を渡している
ことだが、これだけを直すと次の問題が残る。

- PydanticAI の画像入力は `["prompt", BinaryContent(...)]` のような sequence を渡す契約である
- PydanticAI の structured output は `AgentRunResult.output` から読む
- LiteLLM は `openai/gpt-5` や `anthropic/...` のような ID を使う一方、PydanticAI は native provider
  object や `openai:gpt-5.2` / `openrouter:...` 形式を使う
- PydanticAI と LiteLLM は retry / fallback / structured output 周辺に重複機能を持つため、
  どちらを主責務にするか決めないと再び責務境界が曖昧になる
- 現状実装は `os.environ` を mutate して PydanticAI auto-detection に任せる副作用パターンや、
  `api_model_id` だけを cache key にして API key 違いを無視する stale agent 問題を抱えている

これらは「実装可能な ADR」になるためには解決が必要で、本 ADR は ADR 0021 の責務境界を
具体化しつつ、ADR 0021 の中で残されていた `available_api_models.toml` キャッシュ運用と
user TOML WebAPI override も再評価して整理する。

## Decision

通常の WebAPI 推論経路では、以下の責務分離を採用する。

> LiteLLM は discovery / capability metadata の正本として使う。
> 推論実行、multimodal input、structured output validation、output retry は PydanticAI native
> provider/model で行う。
> `image-annotator-lib` 独自層は、LiteLLM metadata と PydanticAI 実行 descriptor を接続する
> adapter と、結果の application schema 変換を担う。

### 責務比較

| 機能 | PydanticAI | LiteLLM | 採用方針 |
|---|---|---|---|
| モデル discovery | 実行可能モデル一覧の正本には不向き | 同梱 model DB と `get_model_info`, `supports_vision` が使える | LiteLLM を SSoT にする |
| capability 判定 | 実行時の model/profile 能力は扱えるが一覧化に弱い | Vision, function/tool calling, response schema 等の metadata を持つ | LiteLLM を採用 |
| 推論実行 | Agent / native provider / model settings / TestModel が強い | SDK/Proxy で 100+ provider を OpenAI 互換形式で実行可能 | 通常経路は PydanticAI native provider |
| multimodal input | `["prompt", BinaryContent(...)]` 形式を公式サポート | OpenAI 互換 message 形式へ変換して provider に送れる | PydanticAI に寄せる |
| structured output | `output_type`, Tool/Native/Prompted output, Pydantic validation, `result.output` | `response_format`, `supports_response_schema`, client-side JSON schema validation | Phase 1 は PydanticAI default Tool Output を使う |
| response validation | Pydantic schema / validators / validation context / `ModelRetry` が自然 | JSON schema validation は可能だが application schema の意味検証は薄い | PydanticAI に寄せる |
| output retry | `retries` / `output_retries` で validation failure を同一モデルに再試行 | Router retry は API 呼び出し失敗寄り | PydanticAI を採用 |
| HTTP/API retry | Tenacity transport を provider HTTP client に設定可能 | Router / Proxy retry が強い | PydanticAI HTTP retry のみ採用。LiteLLM Router retry は採用しない |
| fallback / routing | `FallbackModel` あり。Agent 内で明示モデル順を管理 | Router/Proxy の load balancing/fallback が強い | 採用しない。同一モデル retry までに限定する |
| cost / token metadata | `result.usage()` で usage は取得可能 | 価格 metadata / cost helpers がある | Phase 1 では使わない。必要なら別 ADR |
| API key / provider config | native provider に明示注入でき、副作用が小さい | env/config/proxy 経由が得意 | 通常経路は PydanticAI provider に明示注入 |
| testing | `TestModel`, mocked inference と相性がよい | mock response / proxy testing は可能 | PydanticAI を主にする |
| observability / budgets / multi-tenant | Logfire 等と連携 | Proxy が budgets/rate limits/spend tracking に強い | 今回は対象外。必要時に別 ADR |

### ID 境界

`api_model_id` という単一名で LiteLLM ID と PydanticAI 実行 ID を兼用しない。
後続実装では以下の意味を分ける。

| 名前 | 意味 | 例 |
|---|---|---|
| `litellm_model_id` | LiteLLM DB / metadata 用 ID | `openai/gpt-4o`, `anthropic/claude-...`, `gemini/gemini-...` |
| `provider_model_id` | 実 provider 上のモデル名 | `gpt-4o`, `claude-...`, `gemini-...` |
| `pydantic_ai_model_ref` | PydanticAI 実行用 descriptor | native model/provider object または PydanticAI 形式の model string |

`available_api_models.toml` 由来の旧 `api_model_id` は本 ADR で**廃止**する (互換シムを残さない)。
LoRAIro / image-annotator-lib の関連呼び出しは破壊的変更として同 PR でリネームする。

### ID mapping 関数契約

ID 解析と PydanticAI 実行 descriptor 構築は `image-annotator-lib/core/model_id.py` に集約する。

```python
# core/model_id.py
@dataclass(frozen=True)
class PydanticAIModelRef:
    provider: str
    litellm_model_id: str
    provider_model_id: str
    pydantic_model_id: str | None = None

def resolve_model_ref(
    litellm_model_id: str,
    config: dict[str, object] | None = None,
) -> PydanticAIModelRef: ...

_BUILDER_DISPATCH: dict[str, Callable[..., PydanticAIModelRef]] = {
    "openai": _build_openai_ref,
    "anthropic": _build_anthropic_ref,
    "google": _build_google_ref,
    "gemini": _build_google_ref,   # LiteLLM ID prefix の別名
    "openrouter": _build_openrouter_ref,
}
SUPPORTED_PROVIDERS: frozenset[str] = frozenset(_BUILDER_DISPATCH.keys())
```

責務:

- `litellm_model_id` の prefix 解析 (`openai/...`, `anthropic/...`, `gemini/...`, `openrouter/...`)
- 該当 builder 呼び出し → `PydanticAIModelRef` 生成
- LiteLLM ID から provider 上の model name と PydanticAI model string / model object 構築情報を分離
- 未知 provider (allowlist 外) は `UnknownProviderError`
- prefix 解析失敗・空 ID 等は `IdMappingError`

`SUPPORTED_PROVIDERS` は `_BUILDER_DISPATCH.keys()` から導出するため、dispatch table と
allowlist が同一 source となり「allowlist にあるが builder が無い」「builder にあるが
allowlist 除外」の drift が構造的に発生しない。`core/api_model_discovery.py` 側はこの
constant を import して filter に使うだけ。新 provider 追加は dispatch table への 1 entry
追加で完結する。

`PydanticAIModelRef` は旧 provider-specific SDK adapter の class 分割を持ち込まないための
境界である。具体的な PydanticAI provider/model class 名や import path は実装時点の
PydanticAI 公式 API に合わせる。`resolve_model_ref()` の後段で PydanticAI 実行用 model object
または model string を構築するが、ADR では特定 class 名を固定しない。

### Phase 1 の Provider scope

Phase 1 (本 ADR + Issue #36 修正) で正式対応する provider は以下の 4 種:

- OpenAI (`openai/...`)
- Anthropic (`anthropic/...`)
- Google (`gemini/...`, `google/...`)
- OpenRouter (`openrouter/...`)

Vertex AI / xAI / Cohere 等は本 Phase の対象外。`SUPPORTED_PROVIDERS` に含めず
`UnknownProviderError` を返す。必要になった時点で `_BUILDER_DISPATCH` に builder を
1 つ追加するだけで対応可能 (allowlist 編集不要)。

### LiteLLM SSoT スコープ

ADR 0021 の責務分離をさらに進め、`available_api_models.toml` を**廃止**し LiteLLM を
runtime の単一 source にする。

| 用途 | Phase 0 (ADR 0021) | Phase 1 (本 ADR) |
|---|---|---|
| WebAPI モデル一覧 | `available_api_models.toml` (LiteLLM 出力のキャッシュ) | LiteLLM 同梱 DB を runtime 評価 → `SUPPORTED_PROVIDERS` で filter |
| capability 判定 | `_WEBAPI_MODEL_METADATA` / toml フィールド | `litellm.supports_vision()`, `litellm.get_model_info()` を local DB 前提で runtime 呼び出し |
| user カスタム WebAPI | `user_config.toml` の WebAPI section | **廃止** (LiteLLM 未登録モデルは利用不可) |
| ローカル ML モデル | `annotator_config.toml` + `user_config.toml` | 変更なし (本 ADR スコープ外) |

設計判断:

- LiteLLM import 前に `LITELLM_LOCAL_MODEL_COST_MAP=True` を設定し、remote cost map fetch を
  禁止する。LiteLLM 同梱 DB (`model_prices_and_context_window.json`) は capability registry として
  利用するが、Phase 1 では cost / price フィールドを読まない
- toml キャッシュを廃止することで「toml と LiteLLM の drift」「`last_refresh` TTL 管理」
  「LiteLLM 更新後の手動 regenerate」のオペレーション負担をすべて消滅させられる
- OpenRouter fallback fetch / TTL refresh / force refresh / regenerate 系処理は削除する。
  モデル DB 更新は `image-annotator-lib` の LiteLLM 依存更新で行う
- WebAPI 用 user TOML override 経路 (`user_config.toml` の WebAPI section) は本 ADR で廃止
  する。ローカル ML モデル (`annotator_config.toml`) の user override は別経路で維持
- LiteLLM 未登録のモデルをユーザーが追加で使いたいケースは Phase 1 ではサポート対象外。
  必要が顕在化した時点で別 ADR で再検討

### API key 注入契約

API key 注入は **provider object への明示注入のみ** を許可する。

- `ProviderManager.run_inference_with_model()` の `api_keys: dict[str, str]` を**唯一の**入力経路とする
- `pydantic_ai_factory._set_env_api_key()` を削除し、`os.environ` を一切 mutate しない
- env var fallback (`os.environ.get("OPENAI_API_KEY")` 等) も image-annotator-lib 内では行わない。
  LoRAIro 側は既に config から読んだ値を `api_keys` 経由で渡しているため実質影響なし
- API key 解決失敗時は `MissingApiKeyError(provider=..., litellm_model_id=...)` を raise

理由:

- env mutate はプロセスローカルな global state 汚染で、テスト並列実行 (pytest-xdist) や
  同プロセス内の別ライブラリと競合する
- 後始末忘れで API key が別経路に漏れる事故が起きうる
- 「key の出どころ」が 2 経路あると、どちらを使ったかログを見ないと分からずデバッグ困難
- 将来「ユーザー単位で API key を分ける」マルチテナントシナリオに耐える

### Agent ライフサイクル

PydanticAI Agent / Provider / Model object はキャッシュしない。

- `PydanticAIAgentFactory._agents` ClassVar dict および `clear_cache()` メソッドを削除
- 推論呼び出しごとに `resolve_model_ref` → provider 構築 → model 構築 → Agent 構築 → run の
  シーケンスを毎回実行する

性能影響評価:

- Agent object 作成コストは API 推論時間に比べて十分小さいと見込む
- HTTP client / connection pool を毎回捨てるため、HTTP keep-alive の利得は失う
- LoRAIro の Phase 1 ユースケースは低並列の GUI / CLI 実行であり、接続再利用より
  stale agent / API key 混線をなくす方を優先する
- それと引き換えに「stale agent 問題 (Issue #36 系の動いたり動かなかったり)」「cache key
  設計の難度」「cache invalidation ロジック」「ClassVar dict の永続化バグ」を構造的に消滅させられる
- 大量バッチや高並列が必要になったら、API key を含む明示 cache key と lifecycle 管理、
  または Batch API 採用を別 ADR で再検討する

### Capability check

推論実行直前に LiteLLM の capability を検証して fail-fast する。

```python
import litellm

if not litellm.supports_vision(litellm_model_id):
    raise VisionUnsupportedError(litellm_model_id=litellm_model_id)
```

- LiteLLM を SSoT にする以上、registry 構築時のフィルタだけでなく実行時にも同じ source を
  見るのが一貫している
- ユーザーが手で誤った `litellm_model_id` を渡したケース (例: `openai/gpt-3.5-turbo`) でも
  API 課金される前に弾ける
- LiteLLM は同梱 DB のため runtime 呼び出しコストはほぼゼロ

Phase 1 の structured output は PydanticAI default Tool Output を使う。そのため
`supports_response_schema` は NativeOutput 最適化の参考 metadata として扱い、Phase 1 の
実行可否条件にはしない。モデル絞り込みでは `supports_function_calling` を主条件にし、
`supports_tool_choice` は候補優先度や警告に使う。metadata が欠ける provider/model では、
PydanticAI 実行時エラーを `InferenceError` として明示化する。

Phase 1 の最低条件:

- provider が `SUPPORTED_PROVIDERS` に含まれる
- LiteLLM metadata 上で vision 対応
- LiteLLM metadata 上で function/tool calling 対応
- PydanticAI が対象 provider/model を実行可能

### Schema → Result 変換

PydanticAI `AgentRunResult.output` (`AnnotationSchema` 検証済) → `AnnotationResult` への
変換は `image-annotator-lib/core/result_adapter.py` に集約する。

```python
# core/result_adapter.py
def to_annotation_result(
    schema_output: AnnotationSchema | None,
    phash: str,
    error: str | None = None,
) -> AnnotationResult: ...
```

責務:

- `AnnotationSchema.tags` の抽出 / 正規化
- `formatted_output` の組み立て
- error message の正規化
- `phash` mapping の維持

`ProviderManager` は inference 実行のみを担当し、結果変換ロジックは持たない。

### TestModel 注入機構

本番コードからテスト環境検知ロジック (`_is_test_environment()`, env var / sys.modules 判定) を
削除する。テストは依存注入で行う。

```python
# core/provider_manager.py
@classmethod
def run_inference_with_model(
    cls,
    *,
    litellm_model_id: str,
    images_list: list[Image.Image],
    api_keys: dict[str, str] | None = None,
    config: dict[str, object] | None = None,
    _test_agent: Agent | None = None,   # pytest fixture からのみ使用
) -> dict[str, AnnotationResult]:
    if _test_agent is not None:
        agent = _test_agent
    else:
        ref = resolve_model_ref(litellm_model_id, config)
        model = build_pydantic_model(ref, api_key, config)
        agent = Agent(model=model, output_type=AnnotationSchema, ...)
    ...
```

- `_test_agent` は keyword-only / underscore prefix で「テスト専用」を明示
- 本番コードがテスト環境を検知する分岐を**ゼロ**にする
- pytest fixture から `TestModel` ベースの Agent を渡す経路に統一

### Exception 階層

`WebApiError` を root とした sub-exception を新設する。

```
WebApiError (existing)
├── IdMappingError          # litellm_model_id を解析できない / 不正形式
├── UnknownProviderError    # SUPPORTED_PROVIDERS に含まれない provider
├── MissingApiKeyError      # api_keys に該当 provider のキーが無い
├── VisionUnsupportedError  # litellm.supports_vision() == False
├── SafetyRefusalError      # provider safety / content policy refusal
├── ContentPolicyRefusalError # provider content policy refusal
└── InferenceError          # PydanticAI 実行時エラーの wrap (HTTP / validation / timeout 等)
```

LoRAIro 側の `annotator_adapter.py` は `WebApiError` で広く拾い、必要に応じて type で
分岐できる。各 sub-exception は `litellm_model_id` / `provider` 等の context を attribute で
保持する。

### Retry policy

Phase 1 の retry は「構造化出力の validation failure」と「API transient failure」だけを対象にする。

- output / schema validation failure は PydanticAI の `output_retries=1` で 1 回だけ再生成する
- HTTP/API transient failure は PydanticAI provider の HTTP client / transport で initial + 2 retries
  (最大 3 attempts) とする
- retry 対象 HTTP status は `408`, `409`, `429`, `500`, `502`, `503`, `504`
- `Retry-After` がある場合は尊重する。ただし最大待機は 60 秒までとし、それを超える場合は retry せず
  error として返す
- model fallback / routing は実装しない。別モデルへの自動切り替えは行わない
- LiteLLM Router retry は採用しない
- `Agent(retries=...)` を API failure retry として扱わない

toml / 設定ファイルからの上書き口は Phase 1 では提供しない。ユーザー要望が顕在化した時点で
別 ADR で追加検討する。

Retry しないもの:

- safety / content policy refusal
- auth / API key / permission / quota hard failure
- unsupported provider / unsupported capability / invalid model ID
- input error (画像読み込み・BinaryContent 変換・media type・payload/context limit)
- sync wrapper を running event loop 内で呼んだ misuse
- cancellation / user stop / worker shutdown
- PydanticAI API 変更や provider SDK 仕様変更などの想定外バグ

### Output normalization

`AnnotationSchema` validation 時の軽微な正規化は許可する。ただし独自 JSON repair class や
複雑な parser 層は作らない。軽微な正規化で補正できない場合は PydanticAI output retry に任せる。

許可する軽微な正規化:

- `tags` が文字列ならカンマ分割または single item list 化
- `captions` が文字列なら single item list 化
- `score` が数値文字列なら float 化
- tag / caption の前後空白除去
- 空文字 tag / caption の除外

実装しない補正:

- 壊れた JSON の手修復
- free text から regex で強引に schema を復元する処理
- provider ごとの専用 repair class / parser layer

### Safety refusal handling

Safety / content policy refusal は retry しない。prompt wording を変えて通す retry も Phase 1 では
実装しない。拒否された画像は `ErrorRecord` を正本として記録し、以後 WebAPI アノテーション対象から
除外する。`Rating` は意味が違うため使わない。

既存 `error_records` を以下の形で使う。

```text
operation_type = "annotation"
error_type = "SafetyRefusalError" または "ContentPolicyRefusalError"
image_id = 対象画像ID
model_name = 拒否した model / litellm_model_id
resolved_at = NULL
```

送信前の除外条件:

```text
operation_type = "annotation"
error_type in {"SafetyRefusalError", "ContentPolicyRefusalError"}
resolved_at IS NULL
```

この条件に合う `image_id` は WebAPI provider/model に再送しない。将来 refusal reason taxonomy が
必要になった場合は、専用カラムまたは専用テーブルを別 ADR で検討する。

### Async execution

`ProviderManager` は async-first とする。

- 中核実装は `run_inference_with_model_async()` に置く
- `run_inference_with_model()` は CLI / Qt worker / 既存同期呼び出し用の薄い wrapper とする
- sync wrapper は running asyncio event loop 内では使用不可
- running loop を検出した場合は thread fallback せず、async API 利用を促す明示エラーを返す
- 将来問題が出た場合は、呼び出し側の async 化または worker 実行方式を別 issue で調整する

#### サポート対象実行環境とスコープ

`image-annotator-lib` は **LoRAIro 専用 submodule** として運用される前提で設計されている。
LoRAIro は WebAPI annotation を Qt worker (`QRunnable` on `QThreadPool`,
`src/lorairo/gui/workers/`) で実行し、Qt event loop は asyncio とは別系統のため
worker thread には running asyncio loop が存在しない。本 ADR の sync wrapper は
この想定のもと `asyncio.run()` 経由で動作する。

サポート対象の実行環境:

- LoRAIro の Qt worker (`QRunnable` / `QThreadPool`)
- 通常の Python CLI / script (`python -m image_annotator_lib...`)
- pytest 同期テスト (asyncio loop なし)

サポート対象外の実行環境:

- Jupyter notebook / IPython kernel (kernel が asyncio loop を保持する)
- FastAPI handler / asyncio web framework の handler 内
- 既に `asyncio.run()` 内の任意の async コンテキスト

これらの環境で `image_annotator_lib.annotate()` を呼ぶと sync wrapper の running
loop 検出ロジックにより `InferenceError` が raise される。本ライブラリを直接利用する
外部コードがこの制約を超える要件を持った場合は、別 issue で公開 `annotate_async()` の
追加または `nest_asyncio` 等の代替を再評価する。

[Codex review on PR #38](https://github.com/NEXTAltair/image-annotator-lib/pull/38#discussion_r3204194306)
で同問題が指摘されたが、上記の実行環境スコープに基づき現状の `InferenceError`
fail-fast を維持する判断とした。

### 実行経路 (確定版)

1. LiteLLM 同梱 DB を起動時に読み、`SUPPORTED_PROVIDERS` と capability で filter して registry を構築
   (`core/api_model_discovery.py`)
2. 推論直前に vision + function/tool calling capability を fail-fast
3. `resolve_model_ref(litellm_model_id, config)` で `PydanticAIModelRef` を生成
4. API key を provider object に明示注入し、PydanticAI 実行用 model object / model string を構築
   (env mutate なし)
5. `Agent(model=model, output_type=AnnotationSchema, system_prompt=BASE_PROMPT, ...)` を毎回新規作成
6. async core では `result = await agent.run([prompt_text, binary_content])` (sequence で渡す)
7. sync wrapper は `run_inference_with_model_async()` を event loop 非稼働 thread でだけ実行する
8. `result.output` (`AnnotationSchema` 検証済) を `core/result_adapter.py:to_annotation_result()` で
   `AnnotationResult` に変換

### Phase 1.x: WebAPI 経路の device 判定責務分離 (Issue #35)

**契機**: ADR 0023 Phase 1 (Issue #36, PR #38) で `WebApiAnnotator` が新設され、WebAPI
推論経路は構造的にこのクラスに集約されたが、以下 2 つの設計負債が残った。

1. registry が登録するのは `PydanticAIWebAPIAnnotator` (旧クラス) で、`annotation_runner._create_annotator_instance()` が `WebApiAnnotator` に置換するという
   「片付けない」パターン。`_is_webapi_annotator_class` は class 名文字列リストでの照合という fragile 実装。
2. `BaseAnnotator.__init__` が `_validate_device` 経由で `determine_effective_device` を呼ぶ
   構造のため、将来 WebAPI 系クラスが `super().__init__()` を呼ぶと CUDA 判定が走り、
   CPU-only 環境で「CUDA非対応PyTorch」WARNING が出る問題が再発する余地がある (Issue #35)。

**Phase 1.x の決定**: 階層整理 + デッドコード掃除を行う。

- `BaseAnnotator.__init__` から `_validate_device` 呼び出しを削除し、ローカル ML 系 base
  class (`TransformersBaseAnnotator` / `ONNXBaseAnnotator` / `TensorflowBaseAnnotator` /
  `ClipBaseAnnotator` / `PipelineBaseAnnotator`) の `__init__` で個別に `determine_effective_device` を呼ぶ責務に移譲する。
- `BaseAnnotator.device` の型は `str` を維持し、空文字 (`""`) を「サブクラス未上書き」の
  sentinel とする。
- registry が `WebApiAnnotator` を直接登録するように `_register_webapi_models_from_discovery()` を更新。
- `annotation_runner._is_webapi_annotator_class()` を `issubclass(cls, WebApiAnnotator)` 判定にシンプル化。
- `api.py:list_annotator_info()` の class 名照合も `issubclass(model_class, WebApiAnnotator)` に置換。
- 削除する死コード:
  - `core/base/pydantic_ai_annotator.py` (`PydanticAIWebAPIAnnotator`)
  - `core/base/webapi.py` (`WebApiBaseAnnotator`)
  - `core/base/webapi_common.py`
  - `model_class/annotator_webapi/{anthropic_api,google_api,openai_api_chat,openai_api_response,pydantic_ai_unified}.py`
  - `model_class/pydantic_ai_webapi_annotator.py`
  - `core/model_factory_adapters/` (旧 SDK adapter helpers)

**結果**: WebAPI 推論経路は `BaseAnnotator → WebApiAnnotator` 一直線になり、device 判定は
ローカル ML 系 base class でのみ走る。Issue #35 (CPU-only 環境の WARNING) は構造的に
解消される。

**実機検証** (PR-A baseline / post-fix 比較で確認済):

- baseline (PR #38 マージ後 commit `a9861bd`): `gemini-2.0-flash-lite` 実行時に
  `determine_effective_device` の WARNING は **既に出ない** (Phase 1 での `WebApiAnnotator`
  への切替が `BaseAnnotator.__init__` を skip していたため)。
- post-fix (Phase 1.x マージ後): WARNING が出ないことを構造的に保証する regression test
  (`tests/unit/core/test_webapi_annotator.py`) を追加。`BaseAnnotator.__init__` 自体からも
  device 判定が削除されたため、将来 WebAPI 系クラスが `super().__init__()` を呼んでも
  WARNING は発生しなくなる。

### LiteLLMProvider / LiteLLM SDK 推論の扱い

PydanticAI の `LiteLLMProvider` または LiteLLM SDK 直接推論は、通常の直接 API 実行経路では
採用しない。LiteLLM Proxy/Gateway と model fallback / routing も本 ADR の実装対象外とする。

## Rationale

PydanticAI は Agent 実行、画像入力、structured output、Pydantic validation、output retry、
TestModel に強い。画像アノテーションの主要要件は「画像を渡し、`AnnotationSchema` に検証済みの
結果を得る」ことなので、推論実行は PydanticAI に寄せるのが自然である。

LiteLLM は多 provider のモデル DB、capability 判定、Router/Proxy に強い。
ADR 0021 の目的は WebAPI モデル一覧の追従を安定化することであり、推論実行まで LiteLLM に
寄せることではない。本 ADR は ADR 0021 の方針を維持しつつ、ADR 0021 で残された「toml キャッシュを
SSoT 化するか runtime LiteLLM を SSoT 化するか」の選択を後者に倒す。

PydanticAI と LiteLLM の両方を最大限使うのではなく、同じ責務を二重に持たせない。

- capability / lifecycle は LiteLLM local DB (runtime call、toml キャッシュなし)
- cost は Phase 1 では対象外
- execution / validation / output retry は PydanticAI native provider
- mapping / compatibility / application result conversion は image-annotator-lib

この分割により、LiteLLM ID と PydanticAI 実行 descriptor の混同を構造的に防げる。

破壊的変更を選択した理由:

- 互換シム (`api_model_id` keyword 残存、env mutate fallback 等) は責務境界を曖昧にし、
  Issue #36 系の再発を許してしまう
- LoRAIro と image-annotator-lib は同一プロジェクト内で同 PR で切り替え可能なため、
  互換期間を設けるメリットが薄い
- image-annotator-lib は現時点で LoRAIro 内部利用が主であり、外部互換より責務境界の明確化を優先する
- ID 用語の混乱を残すと後続 ADR (Vertex AI 対応、Batch API 対応等) で「`api_model_id` とは
  何だったか」を毎回参照することになる

## Consequences

### 良い影響

- Issue #36 の修正方針が、単発バグ修正ではなく WebAPI 推論設計と整合する
- OpenAI / Anthropic / Gemini / OpenRouter の ID 差分を `core/model_id.py` 一箇所で吸収できる
- API key を `os.environ` に後付けする副作用を排除し、provider object に明示注入できる
- structured output validation と output retry を PydanticAI に集約できる
- LiteLLM の capability metadata は runtime call で常に同梱 DB と一致する
- `available_api_models.toml` の TTL 管理 / regenerate オペレーション / drift 問題が消滅
- テスト環境検知ロジックが本番コードからゼロになり、CI / 開発で「テストコードと本番コードで
  挙動が違う」事故を防げる

### トレードオフ

- provider ごとの PydanticAI provider/model adapter (`_build_<provider>_ref`) を `core/model_id.py`
  に保守する必要がある
- PydanticAI provider API の変更には追従が必要になる
- LiteLLM Router/Proxy の fallback / budget / multi-tenant 機能は使わない
- Agent キャッシュを廃止することで HTTP 接続再利用の利得を失う。Phase 1 では低並列 GUI / CLI
  用途の安全性を優先する
- LoRAIro / image-annotator-lib 双方の `ProviderManager.run_inference_with_model()` 呼び出しを
  同 PR で破壊的に切り替える必要がある (互換期間なし)
- WebAPI 用 user_config.toml override を廃止するため、LiteLLM 未登録モデルを使うユースケースは
  Phase 1 ではサポートできない (顕在化したら別 ADR で復活検討)

### 後続実装

#### Issue #36 (本 ADR が決まり次第着手)

**新設ファイル** (`image-annotator-lib/src/image_annotator_lib/`):

- `core/model_id.py`
  - `PydanticAIModelRef` dataclass
  - `resolve_model_ref(litellm_model_id, config) -> PydanticAIModelRef`
  - `build_pydantic_model(ref, api_key, config)` 等の実行用 model 構築 helper
  - provider 別 builder (`_build_openai_ref`, `_build_anthropic_ref`, `_build_google_ref`, `_build_openrouter_ref`)
  - `_BUILDER_DISPATCH` テーブルと `SUPPORTED_PROVIDERS` constant
- `core/result_adapter.py`
  - `to_annotation_result(schema_output, phash, error=None) -> AnnotationResult`
  - エラー正規化、tag 抽出、formatted_output 詰め
- `core/image_preprocess.py`
  - `preprocess_images_to_binary(images: list[Image.Image]) -> list[BinaryContent]`
  - 旧 `pydantic_ai_factory.preprocess_images_to_binary` を移動

**改修ファイル**:

- `core/provider_manager.py`
  - async core `run_inference_with_model_async()` を追加
  - sync wrapper `run_inference_with_model()` は running loop 内で明示エラー
  - `run_inference_with_model()` 引数を `api_model_id` → `litellm_model_id` にリネーム (破壊的変更)
  - キャッシュ取得を廃止し毎回 `resolve_model_ref` → provider/model/Agent 構築
  - 推論前 vision + function/tool calling capability check を追加
  - `agent.run_sync(binary_content)` → async core の `await agent.run([prompt_text, binary_content])`
  - `response.data` → `result.output`
  - `_get_provider`, `_get_api_key` の ID parsing 部分を `core/model_id.py` 利用に置換
  - `_test_agent` keyword-only arg を追加 (テスト専用)
- `core/api_model_discovery.py`
  - `available_api_models.toml` への書き出しを廃止
  - OpenRouter fallback fetch / TTL refresh / force refresh / regenerate 処理を削除
  - `list_webapi_models()` 等の API を runtime LiteLLM local DB call + `SUPPORTED_PROVIDERS` filter に変更
- `exceptions/errors.py`
  - sub-exception 7 種 (`IdMappingError`, `UnknownProviderError`, `MissingApiKeyError`,
    `VisionUnsupportedError`, `SafetyRefusalError`, `ContentPolicyRefusalError`, `InferenceError`) を追加
- `model_class/annotator_webapi/*.py`
  - 各 annotator の `run_with_model()` を新 `ProviderManager` API に追従
- `AnnotationSaveService` / annotation worker 周辺
  - result error が `SafetyRefusalError` / `ContentPolicyRefusalError` の場合、`error_records` に
    unresolved annotation error として保存する
  - WebAPI 送信前に unresolved safety refusal error を持つ image_id を除外する
  - `ErrorRecord` 検索 helper に `error_type` filter を追加する。schema migration は不要

**削除ファイル**:

- `config/available_api_models.toml` (LoRAIro / image-annotator-lib 双方)
- `core/pydantic_ai_factory.py` (機能を `core/model_id.py` + `core/result_adapter.py` +
  `core/image_preprocess.py` に分散)

#### LoRAIro 側の追従 (Issue #36 と同 PR で完結)

- `src/lorairo/annotations/annotator_adapter.py`
  - `ProviderManager.run_inference_with_model()` 呼び出しを `litellm_model_id=` に変更
  - `available_api_models.toml` 読み込み箇所があれば LiteLLM 直接呼び出しに置換
- `config/lorairo.toml`
  - WebAPI モデル定義に関する記述があれば削除
- ドキュメント
  - ADR 0021 のステータスと supersede 注記を更新
  - README / CHANGELOG / migration docs / integrations docs から `available_api_models.toml` キャッシュ前提を削除
- テスト
  - `tests/unit/annotations/test_annotator_adapter.py` の引数名更新
  - 既存 `available_api_models.toml` を参照する fixture は LiteLLM mock fixture に置換

#### Issue #35 (本 ADR / Issue #36 完了後)

- WebAPI 経路で `determine_effective_device` を呼ばない
- `WebApiBaseAnnotator` 系では device 判定を完全スキップ
- 本 ADR の責務分離が成立した時点で自然に解決可能

### ADR 0021 への影響

ADR 0021 のステータスを `Superseded by ADR 0023 (partial)` に更新する。supersede されるのは
以下の部分のみ:

- ADR 0021 Decision #3: `available_api_models.toml` を「LiteLLM 出力のキャッシュ」として継続 → **廃止**
- ADR 0021 Decision #4: WebAPI モデル metadata の正本は `available_api_models.toml` /
  `_WEBAPI_MODEL_METADATA` に集約 → **runtime LiteLLM call に変更**
- ADR 0021 Decision #5: WebAPI モデルの user TOML は最小限 override → **WebAPI 用は廃止**
  (ローカル ML モデル用 user TOML は ADR 0021 で扱っていないため影響なし)

ADR 0021 のその他の決定 (LiteLLM を SSoT として採用、ライフサイクル API 二系統化等) は
引き続き有効。本 ADR は ADR 0021 の方向性を加速させるものであり、
覆すものではない。

## References

- [PydanticAI Output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [PydanticAI Agent](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [PydanticAI Image, Audio, Video & Document Input](https://ai.pydantic.dev/input/)
- [PydanticAI HTTP Request Retries](https://ai.pydantic.dev/retries/)
- [PydanticAI OpenRouter](https://ai.pydantic.dev/models/openrouter/)
- [LiteLLM Structured Outputs](https://docs.litellm.ai/docs/completion/json_mode)
- [LiteLLM Router Architecture](https://docs.litellm.ai/docs/router_architecture)
- [Issue #36 — BinaryContent object is not iterable](https://github.com/NEXTAltair/image-annotator-lib/issues/36)
- [Issue #35 — WebAPI モデルでも device='cuda' 判定が走る](https://github.com/NEXTAltair/image-annotator-lib/issues/35)
