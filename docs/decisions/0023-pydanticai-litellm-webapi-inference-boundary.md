# ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary

- **日付**: 2026-05-07
- **ステータス**: Accepted
- **Supersedes**: ADR 0021 (partial — `available_api_models.toml` キャッシュ運用と WebAPI 用 user TOML override 部分)
- **関連 ADR**: [0021 LiteLLM-Driven WebAPI Model Registry](0021-litellm-driven-model-registry.md)
- **関連 ISSUE**:
  [image-annotator-lib#37](https://github.com/NEXTAltair/image-annotator-lib/issues/37),
  [#36](https://github.com/NEXTAltair/image-annotator-lib/issues/36),
  [#35](https://github.com/NEXTAltair/image-annotator-lib/issues/35),
  [#45](https://github.com/NEXTAltair/image-annotator-lib/issues/45),
  [#47](https://github.com/NEXTAltair/image-annotator-lib/issues/47),
  [#46](https://github.com/NEXTAltair/image-annotator-lib/issues/46)

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

## Phase 1.5 完了 (Issue #42 — SafetyRefusal / ContentPolicyRefusal 統合)

本 ADR line 285-294 で確定済みの `SafetyRefusalError` / `ContentPolicyRefusalError`
を WebApiError 階層に追加し、line 347-372 の error_records 統合契約と送信前 filter
を実装した (2026-05 完了)。

### 実装サマリー

- **image-annotator-lib PR-A2**: `exceptions/errors.py` に 2 sub-exception 追加 +
  `provider_manager.py` の `_classify_refusal()` で PydanticAI / provider SDK 例外
  を検出して分類 (case-insensitive な type 名 / message signature 部分マッチ)。
- **LoRAIro PR-B2**: `AnnotationSaveService._process_model_result` で
  `UnifiedAnnotationResult.error` の prefix を decode して `error_records` に記録。
  `filter_refused_image_paths()` を `WorkerService.start_enhanced_batch_annotation`
  で呼び、unresolved refusal を持つ画像を送信前に除外。

### 連携契約 (lib ↔ LoRAIro)

image-annotator-lib は `UnifiedAnnotationResult.error` に
`f"{type(refusal_exc).__name__}: {refusal_exc}"` 形式の prefix 付き文字列を乗せる。
LoRAIro 側はこの prefix を `startswith` で判定して error_type を切り出す。型を直接
import せず文字列 prefix のみで連携することで、submodule pinning 戦略と整合させ、
bidirectional version coupling を回避する。

```text
lib側  UnifiedAnnotationResult.error = "SafetyRefusalError: blocked by safety filter"
                ↓
LoRAIro側  error.startswith("SafetyRefusalError:") → error_records.error_type = "SafetyRefusalError"
                ↓
LoRAIro側  filter_refused_image_paths() で次回送信時に除外
```

### 送信前 filter

`AnnotationSaveService.filter_refused_image_paths(image_paths)` が
`get_error_image_ids(operation_type="annotation", resolved=False,
error_types=["SafetyRefusalError", "ContentPolicyRefusalError"])` で取得した
image_id 集合を WebAPI annotation 対象から除外する。`get_error_image_ids` には
本 PR で `error_types` 引数を追加した (schema migration 不要、既存 column 利用)。

### 検証

- image-annotator-lib unit test: 12 case (`_classify_refusal` 分類精度 / attribute 反映 / truncation)
- LoRAIro integration test: 13 case (refusal → error_records 記録 / filter 除外 / resolved 通過 / 他 error_type 通過 / unknown path 通過 / error_types filter)

将来の refusal reason taxonomy (専用カラム / 専用テーブル) は別 ADR で検討。

## Phase 2 完了 (Issue #41 — `api_model_id` field 廃止)

ADR 0023 line 73「``available_api_models.toml`` 由来の旧 ``api_model_id`` は本 ADR
で廃止する (互換シムを残さない)」を public API レベルで実現する一括破壊的変更
(Option A) を実施した (2026-05 完了)。

- **image-annotator-lib PR-A1**: `AnnotatorInfo.api_model_id` field を
  `litellm_model_id` にリネーム + registry.py の関連箇所更新。
- **LoRAIro PR-B1**: `Model.api_model_id` column を `litellm_model_id` にリネーム
  (Alembic migration `c4d5e6f7a8b9` で SQLite 互換 `batch_alter_table` 経由)、
  TypedDict / Protocol / 6 file refs を新名称に追従。

これにより lib と LoRAIro 双方で SSoT として `litellm_model_id` を使い、命名上の
分裂が解消した。後方互換期間は設けず一括移行 (LoRAIro 専用 submodule のため
外部 consumer なし)。

## Phase 1.6 完了 (Issue #45 — capability check の discovery 集約 + direct dispatch 廃止)

ADR 0023 line 216-220 で確定済みの「`supports_function_calling` を主条件にする」を
実装すると同時に、capability 判定の責務を **discovery / registry SSoT に完全集約**
するリファクタを実施した (2026-05 完了)。

### 実装サマリー (image-annotator-lib PR #48)

1. **絞り込み条件切替**: `core/api_model_discovery.py:_is_litellm_model_annotation_compatible()`
   の必須条件を `supports_response_schema is True` から `supports_function_calling is True`
   に置換。registry 側の重複ロジック (dead code `_is_annotation_compatible_webapi_model()`)
   は削除。
2. **metadata 純化**: `_format_litellm_metadata()` および
   `_register_webapi_models_from_discovery()` の登録 metadata から
   `supports_response_schema` キーを削除。NativeOutput / Tool Output の切替戦略は
   将来別 ADR で扱うため、現時点では metadata に残さない。
3. **推論直前 capability fail-fast の削除**:
   `core/provider_manager.py` の `litellm.supports_vision()` 直前 check を削除。
   `VisionUnsupportedError` クラスも削除。capability 責務は discovery / registry に
   一本化。
4. **direct LiteLLM ID dispatch 経路廃止**:
   `core/annotation_runner.py:_create_annotator_instance()` の Step 2 (registry に
   存在しない `provider/model` 形式を `WebApiAnnotator` に直接渡す経路) を削除。
   registry に該当しないモデル名は `KeyError` で弾く。`api.py:list_annotator_info()`
   の direct discovery 列挙 (section 2) と registry helper
   `_build_annotator_info_for_direct_model()` も dead code として削除。

### 設計上の本決定 (Decision section の更新差分)

ADR 0023 本文の以下の記述は **Phase 1.6 (Issue #45) で更新** された:

| ADR 本文 | 旧方針 | Phase 1.6 で更新後の方針 |
|---|---|---|
| line 199-220 "Capability check" | 推論実行直前に LiteLLM `supports_vision()` で fail-fast | capability 判定は discovery / registry SSoT に集約。推論層は capability 前提で動作する純化設計。runtime fail-fast は冗長として削除 |
| line 217 "supports_response_schema は ... 参考 metadata として扱い" | metadata に保持 (NativeOutput 最適化用) | metadata からも削除 (NativeOutput / Tool Output 切替を実装する際に別 ADR で再追加) |
| line 415-417 "実行経路 #2 推論直前 vision + function/tool calling capability fail-fast" | 推論直前 fail-fast あり | 廃止 (discovery で完結) |
| (新規) | (記述なし) | **direct LiteLLM ID dispatch 経路の廃止**: `_create_annotator_instance()` は registry のみ参照。registry に未登録の `provider/model` を `WebApiAnnotator` に直接渡す経路は廃止。LiteLLM 同梱 DB の WebAPI モデルは起動時 discovery で registry に自動登録されるため、通常運用への影響なし |

### 根拠

- **discovery / registry SSoT 方針との整合**: ADR 0023 全体で「capability 判定は LiteLLM
  metadata の SSoT」と決定済み。registry 経由の通常パスでは登録時点で capability check
  が完了するため、推論層で再 check するのは冗長 (機能的重複)。
- **direct dispatch 経路と SSoT の不整合**: `_create_annotator_instance()` の direct
  dispatch path は registry を経由しないため capability check が抜ける構造的問題があった
  (Codex P1 指摘)。capability check を再導入するのではなく、SSoT 方針に従い経路自体を
  廃止することで根本解決。
- **`supports_response_schema` metadata 削除**: PydanticAI default Tool Output で実行
  する Phase 1 設計では参照しないため。LoRAIro 側にも該当 column / 参照は存在しないため
  schema migration 不要。

### 検証

- image-annotator-lib unit test: 9 case (`_is_litellm_model_annotation_compatible` の各
  境界条件 / `_format_litellm_metadata` の `supports_response_schema` キー欠落確認)
  + 既存 test 含む全 502 件 PASS (1 件 pre-existing failure 除く)
- LoRAIro 側影響なし (`supports_response_schema` / `VisionUnsupportedError` への直接参照は
  事前調査で「無し」を確認)

将来 NativeOutput 切替や registry-bypass capability check が必要になった場合は別 ADR で
扱う。

## Phase 1.7 完了 (Issue #47 — PydanticAI output 処理での軽微正規化集約)

ADR 0023 line 50-55 / line 595-600 で確定済みの「structured output validation /
軽微正規化を PydanticAI に寄せる」方針に従い、軽微正規化を **AnnotationSchema
validation の前** の output function 内に集約するリファクタを実施した
(2026-05 完了)。

### 背景: drift の構造的発生

`BASE_PROMPT` (`image_annotator_lib/model_class/annotator_webapi/webapi_shared.py`)
は LLM に対して以下の形式を指示している:

- `tags: 30-50 comma-separated words` (**文字列**)
- `caption: Single 1-2 sentence ... description` (**文字列**, 単数)
- `score: Single decimal number between 1.00 and 10.00` (数値)

一方 `AnnotationSchema` は `tags: list[str]` / `captions: list[str]` /
`score: float` を期待する。`output_type=AnnotationSchema` 直指定では LLM が
prompt 通りの文字列形式を返すと validation 失敗 → `output_retries=1` での再生成
頼みになり、再生成も失敗すると inference 全体が失敗する構造だった。

### 実装サマリー (image-annotator-lib PR #49)

1. **output function による正規化集約**: `core/output_normalization.py` に
   `normalize_annotation_output(tags, captions, score) -> AnnotationSchema`
   を新設し、PydanticAI `Agent.output_type` に渡す。PydanticAI は callable を
   tool 化して LLM に公開するため、関数の **docstring を LLM-facing description**
   として記述する (内部実装説明は module docstring に分離)。許可する正規化:
   - `tags`: 文字列 (カンマ分割または single item) → `list[str]`、各要素 trim、空除外
   - `captions`: 文字列 (single) → `list[str]`、trim、空除外 (カンマ分割しない)
   - `score`: 数値文字列 → `float` (`bool` は明示拒否)
   補正不能 (None / dict / list 内非文字列 等) は `ModelRetry` を raise し、
   PydanticAI `output_retries=1` 経由で LLM 再生成へ流す。
2. **provider_manager の output_type 切替**:
   `Agent(output_type=AnnotationSchema, ...)` →
   `Agent(output_type=normalize_annotation_output, ...)`。`output_retries=1` は
   維持し、normalize 内 `ModelRetry` 経由で再生成に流す。
3. **result_adapter の純化**: 旧 `_normalize_string_list()` / `_normalize_score()`
   (pre-validation 補正) を削除し、`_clean_string_list()` 最終防衛のみ残す。
   `to_annotation_result()` は検証済み `AnnotationSchema` → `AnnotationResult`
   変換専任。

### 設計上の本決定 (Decision section の更新差分)

ADR 0023 本文の以下の記述は **Phase 1.7 (Issue #47) で更新**:

| ADR 本文 | 旧方針 | Phase 1.7 で更新後の方針 |
|---|---|---|
| line 595-600 "Schema → Result 変換 (`core/result_adapter.py`)" | `result_adapter.py` で軽微正規化 + 変換 | 軽微正規化を `core/output_normalization.py` (validation 前) に分離。`result_adapter.py` は変換専任 + 最終防衛 trim/drop empty のみ |
| (新規) | (記述なし) | **PydanticAI output function 経路の確定**: `Agent.output_type` には callable を渡し、その内部で軽微正規化 + `AnnotationSchema` validation を行う。drift は `ModelRetry` 経由で `output_retries=1` 再生成に流す |
| (補強) | "output retry" 行 | 「output normalization の `ModelRetry` も `output_retries=1` の対象」を明記 |

### 実装しない補正

- 壊れた JSON の手修復
- free text からの regex 強制復元
- provider 別 parser layer
- Issue #46 (HTTP/API transport retry) — 別 issue / 別 PR

### 根拠

- **drift 補正経路の構造的解決**: `output_type=AnnotationSchema` 直指定では drift
  全件が validation 失敗 → retry になり、retry 失敗時は inference 全体が失敗
  していた。output function 経由なら drift をコード側で補正してそのまま valid 化
  できるため、retry 消費を「真に補正不能なケース」だけに限定できる。
- **責務分離**: validation 前正規化を `output_normalization.py`、検証済 → 結果
  変換を `result_adapter.py` に分離することで、各 module の責務が単一化。
- **LLM 側の guidance**: PydanticAI が callable を tool 化する仕様上、関数の
  docstring が LLM への description として使われる。`Args:` 構造で各 field の
  期待形状を例示することで、`Any` 型 schema でも LLM が適切な構造化出力を生成
  できる (BASE_PROMPT の prompt-level 指示と二重化された安全網)。

### 検証

- image-annotator-lib unit test: 新規 16 ケース (output_normalization 9 +
  provider_manager_output_normalization 1 + result_adapter 6) PASS。既存
  refusal / capability / annotation_runner / webapi_annotator test 64 ケース
  PASS。全 unit test 512 PASS (1 件 pre-existing failure 除く)
- LoRAIro 側影響なし (`AnnotationSchema` / `to_annotation_result` への直接参照は
  事前 grep で「無し」確認)

将来 score range constraint や Issue #46 の transport retry 集約は別 issue で扱う。

## Phase 1.8 完了 (Issue #46 — PydanticAI HTTP transport retry の集約)

ADR 0023 line 304-329 で確定済の HTTP/API transient failure retry policy を
`pydantic_ai.retries.AsyncTenacityTransport` を介して provider HTTP client 層に
組み込む実装を完了した (2026-05 完了)。Phase 1 残タスクの最後の項目。

### 実装サマリー (image-annotator-lib PR #50)

1. **transport retry 経路の新設**: `core/http_retry.py` に
   `build_retry_transport()` / `build_retry_http_client()` を新設し、
   PydanticAI `AsyncTenacityTransport` + `RetryConfig` でラップした
   `httpx.AsyncClient` を返す。retry 対象は status code 7 種 (`408`, `409`, `429`,
   `500`, `502`, `503`, `504`) と httpx の transient 例外
   (`TimeoutException` 階層 = `ConnectTimeout` / `ReadTimeout` / `WriteTimeout` /
   `PoolTimeout` および `ConnectError` / `RemoteProtocolError`)。`RetryConfig(reraise=True)`
   で原因例外をそのまま伝搬させ、`_classify_refusal()` の判定経路を保つ。
2. **provider object への http_client 注入**: `core/model_id.py:build_pydantic_model()`
   に keyword-only `http_client: httpx.AsyncClient | None = None` を追加し、
   OpenAI / Anthropic / Google / OpenRouter の 4 provider 全てで
   `*Provider(api_key=..., http_client=http_client)` 形式で注入する。
3. **AsyncClient lifecycle**: `provider_manager.run_inference_with_model_async()` で
   `build_retry_http_client()` を毎回新規生成し、`try/finally` で
   `await http_client.aclose()` する。Agent / Provider / Model キャッシュなし方針
   (Agent ライフサイクル節) と一貫させる。
4. **HTTP timeout の明示**: `httpx.Timeout(timeout=120.0, connect=10.0, read=120.0,
   write=30.0, pool=10.0)` を `HTTP_CLIENT_TIMEOUT` constant として定義し
   `build_retry_http_client()` 内で AsyncClient に渡す。WebAPI vision model は
   応答に数十秒かかるため read=120s を取り、connect/pool は短く 10s で fail-fast する。
   timeout 発火時は retry tuple の `TimeoutException` 経由で 3 attempts まで救済される。
5. **依存の明示化**: `pyproject.toml` の `dependencies` に `tenacity>=9.0` を
   transitive 経由から explicit 依存に昇格 (`pydantic_ai.retries` モジュールが要求)。

### 設計上の本決定 (Decision section の更新差分)

ADR 0023 本文の以下の記述は **Phase 1.8 (Issue #46) で更新**:

| ADR 本文 | 旧方針 | Phase 1.8 で更新後 |
|---|---|---|
| line 308 「最大待機は 60 秒までとし」 | 60s が magic number | **60s 採用根拠を明示**: OpenAI / Anthropic の token bucket は分単位で補充され、典型 Retry-After は 60s 以内 (Anthropic 公式 "continuously replenished" 記述、OpenAI RPM/ITPM/OTPM)。3 attempts × 60s = worst 120s 待機後に error 伝播 → Qt batch worker のキャンセル応答性を確保。pydantic-ai default 300s は CLI 想定で Qt UI には過大 |
| line 308-310 「それを超える場合は retry せず error として返す」 | halt-on-exceed | Phase 1 では **cap-only** (PydanticAI 標準 `wait_retry_after(max_wait=60)`)。halt-on-exceed は Phase 2 に繰り延べ。`Retry-After > 60s` のケースは daily quota 超過が主で、3 attempts 後の error 経路で実質同等の運用結果になるため Phase 1 では実装しない |
| line 309 「retry 対象 HTTP status は 408, 409, 429, 500, 502, 503, 504」 | status code のみ | **network 例外も追加**: `httpx.TimeoutException` 階層 (`ConnectTimeout` / `ReadTimeout` / `WriteTimeout` / `PoolTimeout`) と `httpx.ConnectError` / `httpx.RemoteProtocolError`。一時的な接続切断・DNS 一時障害・connect 段階の TLS timeout も transient failure として扱う (Codex P1 review で `ConnectTimeout` が漏れていた点を修正済) |
| (新規) | (記述なし) | **AsyncClient lifecycle**: 推論呼び出しごとに `httpx.AsyncClient(transport=AsyncTenacityTransport(...), timeout=HTTP_CLIENT_TIMEOUT)` を新規生成し try/finally で `aclose()`。Agent/Provider/Model のキャッシュなし方針と一致 |
| (新規) | (記述なし) | **HTTP timeout 明示**: `connect=10s` / `read=120s` / `write=30s` / `pool=10s` を constant `HTTP_CLIENT_TIMEOUT` で定義。WebAPI vision model の応答は数十秒オーダーなので read を長めに、connect / pool は fail-fast |
| (新規) | (記述なし) | **依存**: `tenacity>=9.0` を `image-annotator-lib` の `dependencies` に明示追加 (PydanticAI `retries` モジュールが要求) |

### 実装しない補正 (Phase 1.8 スコープ外)

- model fallback / routing (ADR line 313-314 で採用しない決定)
- LiteLLM Router retry (同上)
- halt-on-exceed (Retry-After > max_wait なら retry せず即 error) — Phase 2
- 推論を跨いだ HTTP connection pool 共有 — Agent キャッシュなし方針 (Agent ライフサイクル節) と整合させるため

### 根拠

- **transient failure の包括的救済**: ADR line 305 の「HTTP/API transient failure」を
  status code だけでなく network 例外 (timeout / connect / protocol) も含めて解釈し、
  実運用で頻発する DNS 一時障害 / TLS handshake 一時失敗 / read timeout / pool 枯渇を
  retry で吸収する。`HTTPStatusError` だけ retry すると connection 段階で
  落ちるケースで救済機構が機能せず、ユーザの手動再実行が必要になる。
- **`HTTP_CLIENT_TIMEOUT` の値設計**: `connect=10s` は TCP 接続が 10s で確立しなければ
  上流障害と判断して fail-fast (リトライで救済)。`read=120s` は WebAPI vision model
  (例: GPT-4o, Claude Sonnet) の典型応答時間 (5-30s) の余裕を持たせた値。`pool=10s`
  は pool acquire 段階の hang を fail-fast。`write=30s` は image upload (数 MB) の余裕。
- **`tenacity` 明示依存の理由**: PydanticAI の `pydantic_ai.retries` は `tenacity` を
  optional `[retries]` group としてのみ提供する。transitive で入っていても暗黙依存は
  壊れる余地があるため、image-annotator-lib 側で `dependencies` に直接列挙する。

### 検証

- image-annotator-lib unit test: 新規 51 ケース (`test_http_retry.py` 27 ケース +
  `test_http_retry_transport.py` 24 ケース) PASS。`ConnectTimeout` / `PoolTimeout` /
  `ReadTimeout` / `WriteTimeout` の 4 timeout subclass の retry 振る舞いを parametrize
  で網羅。既存 unit test は 559 PASS / 1 件 deselect (pre-existing failure)。
- LoRAIro 側影響なし (`InferenceError` / `WebApiError` の直接 import なし、retry
  exhaustion error は既存 `UnifiedAnnotationResult.error` 文字列 prefix mechanism
  でそのまま LoRAIro 側に伝搬する。Phase 1.5 / Issue #42 と同じ疎結合契約)。

将来 halt-on-exceed (Retry-After > max_wait の即 error 化) や session-scoped
HTTP connection pool は別 ADR で扱う。

## Phase 1.9 完了 (Issue #51 — LiteLLM 完全 ID を registry SSoT に統一)

ADR 0023 line 65-77 の ID 境界規定に基づき、`api_model_discovery._format_litellm_metadata()`
が返す `model_name_short` を **LiteLLM 同梱 DB のオリジナルキーと同一の完全 ID** に
揃える修正を実施した (2026-05 完了)。

### 背景

旧実装は `model_id.split("/", 1)[1]` で provider prefix を剥がした文字列を
`model_name_short` としていたため、`openrouter/z-ai/glm-4.7` のような nested
LiteLLM ID では `model_name_short = "z-ai/glm-4.7"` となり、registry キー /
CLI 表示 / LoRAIro DB `litellm_model_id` 列に prefix 欠落形が伝播していた。
推論時の `resolve_model_ref()` は `_BUILDER_DISPATCH` にない `z-ai` を未知
provider として `UnknownProviderError` で弾く構造だった。

### 実装サマリー (image-annotator-lib PR #51 系)

1. **`_format_litellm_metadata()` の修正**: `core/api_model_discovery.py:55-82`
   の `model_name_short` を `model_id` (= LiteLLM オリジナルキー) そのものに変更。
   `display_name` も同一値となるが既存呼び出し側互換のため両 field を残す
   (将来の Phase で field 統合は別 ADR で検討)。
2. **registry / CLI / LoRAIro DB の SSoT 統一**: `_register_webapi_models_from_discovery()`
   は変更不要。`model_name_short` を辞書値からそのままキーとして登録するため、
   `_MODEL_CLASS_OBJ_REGISTRY` / `_WEBAPI_MODEL_METADATA` のキーが完全 ID
   (`openai/gpt-4o`, `openrouter/z-ai/glm-4.7` 等) に揃う。`AnnotatorInfo.name` /
   LoRAIro CLI の `info.name` も同一値となる。
3. **discovery filter は無変更**: `is_allowed_provider()` は line 126-138 通り
   `_BUILDER_DISPATCH.keys()` (= `SUPPORTED_PROVIDERS`) の第 1 要素照合のみで
   判定。`openrouter/<inner>/<model>` の inner provider 別フィルタは行わない
   (Issue #51 本文「discovery フィルタ: `openrouter/` 配下は全て表示」を遵守)。
   未知 inner provider (`z-ai`, `qwen`, `mistralai`, `moonshotai` 等) も
   そのまま OpenRouter 経由で推論ルーティングされる。

### Decision section の更新差分

ADR 0023 本文の以下の記述は **Phase 1.9 (Issue #51) で更新**:

| ADR 本文 | 旧方針 | Phase 1.9 で更新後 |
|---|---|---|
| line 70-74 ID 用語表 (`litellm_model_id` の例) | `openai/gpt-4o`, `anthropic/claude-...`, `gemini/gemini-...` | **OpenRouter nested 形式 `openrouter/<inner>/<model>` (例: `openrouter/openai/gpt-4.1`, `openrouter/z-ai/glm-4.7`, `openrouter/qwen/qwen3.5-...`) も `litellm_model_id` の有効形式である** ことを明記。inner provider が `_BUILDER_DISPATCH` の直接プロバイダー集合に無い場合 (`z-ai`, `qwen` 等) でも `openrouter/` プレフィックスにより OpenRouter 経由でルーティング可能 |
| (新規) | (記述なし) | **registry SSoT**: `_format_litellm_metadata()` が返す `model_name_short` は LiteLLM オリジナルキーと同一の完全 ID。registry キー / CLI 表示 / LoRAIro DB `litellm_model_id` 列に同一値が伝播する |

なお ADR 0023 の **本文 line 70-74 の ID 用語表自体は書き換えない**。
Phase 1.5〜1.8 の前例に倣い、本 Phase 1.9 完了セクションの「Decision section
の更新差分」表で解釈拡張を文書化するのみ。本文を歴史的記録として保つことで
ADR の trace 性を維持する。

### 検証

- 新規 unit test 5 件:
  - `tests/unit/core/test_api_model_discovery_filter.py:TestFormatLitellmMetadata`
    に 3 ケース追加 (openrouter/<inner>/<model>, openrouter/openai/<model>,
    openai/<model> 直接形式)
  - `tests/unit/core/test_model_id.py::TestResolveModelRef` の parametrize に
    2 ケース追加 (`openrouter/z-ai/glm-4.7`, `openrouter/qwen/qwen2-vl-72b-instruct`)
- 全既存テスト PASS (603 passed, 18 skipped)。残る 1 件 failure
  (`test_tagger_transformers.py::test_toriigate_tagger_format_with_assistant_prefix`)
  および 5 件 BDD features failure は main ブランチでも再現する pre-existing
  failure であり、本修正とは無関係 (transformers ライブラリ版の互換性問題)
- `lorairo-cli models list` 手動確認: `openrouter/z-ai/glm-4.7`,
  `openrouter/qwen/qwen3.5-...`, `openrouter/anthropic/claude-opus-4.6`
  などが完全 ID で 71 件表示。旧 prefix 欠落形 (`z-ai/glm-4.7` 単体等) は消失

### LoRAIro 側影響

- `Model.litellm_model_id` 列に格納される文字列が完全 ID に揃う (DB 既存
  データの扱いは LoRAIro Issue #238 のスキーマ変更時に migration で扱う)
- LoRAIro CLI (`lorairo/cli/commands/models.py`) の `is_model_deprecated(info.name)`
  は `info.name` が完全 ID になることで自動的に LiteLLM 内部キーと一致するため、
  LoRAIro 側の追加変更は不要

### 関連 (未対応)

- Issue #39 (image-annotator-lib): OpenRouter 経由の `openai/...` `anthropic/...`
  と直接プロバイダー版が両方 registry に登録される重複問題。本 Phase で
  完全 ID 表示が確定したことで重複が CLI 上で可視化された。別 Issue で対応
- 新規 Issue (image-annotator-lib): LiteLLM JSON の bare Anthropic 名
  (`claude-opus-4-6` 等、`/` 無し) が `is_allowed_provider()` で全除外される
  問題。Anthropic 直接モデル経路の復活は Phase 1.10 として連動 PR で対応予定
- LoRAIro Issue #238: `schema.Model` の `name` UNIQUE 制約撤去 +
  `litellm_model_id` UNIQUE NOT NULL 化 + Alembic migration

## Phase 1.10 完了 (Issue #52 — Anthropic bare 名を `anthropic/<bare>` に正規化)

ADR 0023 line 109 の prefix 解析対象規定の解釈拡張として、LiteLLM 同梱 DB の bare
Anthropic 名 (`claude-*`、計 19 件) を `anthropic/<bare>` 形式に正規化して
`litellm_model_id` の有効形式として扱う修正を実施した (2026-05 完了)。

### 背景

LiteLLM 同梱 DB は Anthropic 直接モデルを `claude-opus-4-6`, `claude-sonnet-4-6`,
`claude-haiku-4-5` 等の bare 名 (`/` 無し) で格納している。Issue #51 (Phase 1.9)
で完全 ID 保持に修正後も、`is_allowed_provider()` の `if "/" not in model_id:
return False` チェックが bare 名を全除外していたため、Anthropic 直接プロバイダー
経路が registry に登録されず、`lorairo-cli models list` には OpenRouter 経由
(`openrouter/anthropic/claude-*`) のみ表示されていた。`_BUILDER_DISPATCH["anthropic"]`
(= `_build_anthropic_ref`) は既に `anthropic/<model>` 形式をサポートしていたため、
discovery 段階での正規化のみで Anthropic 直接経路を復活できる構造だった。

### 実装サマリー (image-annotator-lib PR #YY)

1. **`_canonicalize_litellm_id()` ヘルパーを新設** (`core/api_model_discovery.py`):
   `_ANTHROPIC_BARE_PREFIXES = ("claude-",)` で始まる bare ID を `anthropic/<bare>`
   に補完。slash 入り ID は素通り。スコープ外の bare 名 (例: `gpt-4o`,
   Bedrock 形式 `anthropic.claude-*`) は None を返す
2. **`is_allowed_provider()` を refactor**: ヘルパー経由で判定。bare `claude-*`
   が SUPPORTED_PROVIDERS 通過するようになる
3. **`_format_litellm_metadata()` を修正**: ヘルパーで正規化後の ID を
   `model_name_short` / `display_name` に格納。`provider` は capitalize 規則で
   `"Anthropic"` になる (Phase 1.9 で確立した規則)
4. **`_collect_models()` の dict キーを正規化後 ID に統一**:
   `metadata[model_id] = formatted` → `metadata[formatted["model_name_short"]] =
   formatted`。これにより `discover_available_vision_models()` の戻り値
   `{"models": [...], "metadata": {...}}` も正規化後 ID で一貫する
5. **変更不要箇所** (確認済): `is_model_deprecated()` は `litellm.get_model_info()`
   が bare/slash 両形式で同一 metadata を返すためそのまま動作。`_BUILDER_DISPATCH` /
   `core/model_id.py` も `anthropic/<model>` 形式を既存サポート

### Decision section の更新差分

ADR 0023 本文の以下の記述は **Phase 1.10 (Issue #52) で更新**:

| ADR 本文 | 旧方針 | Phase 1.10 で更新後 |
|---|---|---|
| line 109 prefix 解析対象 (`openai/...`, `anthropic/...`, `gemini/...`, `openrouter/...`) | `provider/model` 形式の slash 入り ID のみ | LiteLLM 同梱 DB の bare Anthropic 名 (`claude-*`、19 件) は `anthropic/` プレフィックスを補完して `litellm_model_id` の有効形式として扱う。registry / CLI / DB SSoT には正規化後 ID で乗せる |
| (新規) | (記述なし) | スコープは `claude-*` プレフィックスのみ。Bedrock/Vertex 経由の `anthropic.*` 形式 bare 名 (約 178 件、`_BUILDER_DISPATCH` に builder 無し) は除外維持。これらの追加対応は新 builder の追加が必要なため別 ADR で扱う |

本文 line 109 自体は書き換えず Phase 1.10 完了セクション内の表で文書化
(Phase 1.5〜1.9 と同じ運用)。

### 検証

- 新規 unit test 10 件 (`tests/unit/core/test_api_model_discovery_filter.py`):
  - `TestCanonicalizeLitellmId` 4 ケース (slash passthrough / claude bare / 非 claude bare / 空文字)
  - `TestIsAllowedProviderBareName` 3 ケース (bare claude allow / 非 claude bare reject / slash unchanged)
  - `TestFormatLitellmMetadata` に 3 ケース追加 (bare claude / 日付 suffix / 非 claude bare)
- 全既存テスト PASS (Phase 1.9 と同じ pre-existing failures は除く)。
  全 lib test: 613 passed, 18 skipped, 1 failure (pre-existing `test_tagger_transformers`)
- `lorairo-cli models list` 手動確認: registry 登録 webapi モデル 71 件 → 90 件
  (+19 件)、総モデル数 104 → 123 件。`anthropic/claude-opus-4-6`,
  `anthropic/claude-sonnet-4-6`, `anthropic/claude-haiku-4-5` 等が完全 ID で
  追加表示されることを確認

### LoRAIro 側影響

- `Model.litellm_model_id` 列に `anthropic/claude-*` の新規行が追加される (DB
  既存データへの影響なし、新規モデル追加と等価)
- LoRAIro CLI / GUI / annotator_adapter のコード変更は不要
- Anthropic 直接モデル経由の推論には `api_keys["anthropic"]` が必要。LoRAIro 側
  config の Anthropic API key 設定経路 (`config/lorairo.toml [api] claude_key`) は
  既存のまま機能する

### 関連 (未対応)

- Issue #39 (image-annotator-lib): Anthropic 直接 (`anthropic/claude-opus-4-6`)
  と OpenRouter 経由 (`openrouter/anthropic/claude-opus-4-6`) の重複登録。
  Phase 1.10 で重複が CLI 上で更に可視化されるが本 Issue では触らない。
  運用上の選択 (低レイテンシの直接経路 vs マルチプロバイダー一元化の OpenRouter
  経路) は LoRAIro 側で解決する設計余地として残す
- LoRAIro Issue #238: `schema.Model.litellm_model_id` 列 UNIQUE NOT NULL 化 +
  Alembic migration
- 他プロバイダー bare 名対応 (Bedrock/Vertex 経由 `anthropic.*` 等 約 178 件):
  `_BUILDER_DISPATCH` に builder 追加が必要なため別 ADR で扱う

## Phase 1.11 完了 (LoRAIro Issue #238 — `schema.Model.litellm_model_id` を UNIQUE NOT NULL 化、`name` を表示名に降格)

> **注意 (2026-05-23 追記)**: 本 Phase で導入した `__legacy_<id>__` sentinel の
> 「履歴行として保持」運用契約は **[ADR 0033](0033-annotation-worker-batch-execution-contract.md) Decision 7 で撤回**された。
> 撤回理由: LoRAIro は開発フェーズで過去 DB 互換性が不要、かつ sentinel 行が
> name 一致経由のクエリで推論経路に流入する脆弱性を抱えていた。
> sentinel 行は migration `a3b4c5d6e7f8` で削除済 (2026-05-23)。
> `__manual_edit__` sentinel (推論経路に乗らない正規利用) は引き続き保持する。

Phase 1.9 / 1.10 (Issue #51, #52) で registry が「同一論理モデル × 経路違い」のエントリを
完全 LiteLLM ID で並列保持するようになったことを受け、LoRAIro DB schema を SSoT 規約に
整合させた (2026-05 完了)。`schema.Model` の責務を以下に再構成:

| カラム | 値の例 | 役割 |
|---|---|---|
| `name` | `gpt-4.1` | 表示名 (非 UNIQUE) |
| `provider` | `openrouter` / `openai` / `anthropic` | ルーティング元 (非 UNIQUE) |
| `litellm_model_id` | `openrouter/openai/gpt-4.1` | **ルーティングキー (UNIQUE NOT NULL)** |

### 背景

ADR 0023 line 109 / 138 (`SUPPORTED_PROVIDERS` 規定) と Phase 1.9 / 1.10 の SSoT
拡張により、registry には `anthropic/claude-3-5-sonnet-20241022` (直接) と
`openrouter/anthropic/claude-3-5-sonnet-20241022` (OpenRouter 経由) が **別エントリ**
として並列登録される。LoRAIro `schema.Model` の旧定義は:

- `name` UNIQUE → 同一モデル名の複数経路を DB に保存できない (重複 INSERT で IntegrityError)
- `litellm_model_id` nullable / 非 UNIQUE → ルーティングキーとして信頼できず、
  `model_sync_service` は `name` を一意キーとして lookup していたため経路違いを区別できない
- `provider` の意味が緩く、`name="openai/gpt-4.1"` のスラッシュ込み形式が混在する余地

Phase 1.10 完了後の registry は 123 件のモデルを返すが、LoRAIro DB に流し込もうとすると
直接版と OpenRouter 版の `name` 衝突で sync が破綻する。

### 実装サマリー (LoRAIro PR #ZZZ)

1. **`schema.Model` 定義変更**:
   - `name` の `unique=True` を削除 (非 UNIQUE NOT NULL 表示名)
   - `litellm_model_id` を `Mapped[str]` (NOT NULL) + `unique=True` に昇格
   - `provider`, `discontinued_at`, `estimated_size_gb`, `requires_api_key`, relationships は据え置き
2. **Alembic migration 新規作成**:
   - `MANUAL_EDIT` 行: `litellm_model_id = '__manual_edit__'` (sentinel) を埋める
   - スラッシュ込み `name` 行: `name` をそのまま `litellm_model_id` にコピーし、
     `provider` / 表示名を `instr(name, '/')` で先頭 `/` 区切りに分離
     (例: `openrouter/openai/gpt-4o` → `provider='openrouter'`, `name='openai/gpt-4o'`)
   - スラッシュなし `name` で `provider IS NOT NULL` 行: `litellm_model_id = provider || '/' || name` で補完
   - 残存 NULL 行は `__legacy_<id>__` sentinel で fallback して NOT NULL 化失敗を防ぐ
     (**ADR 0033 Decision 7 で撤回**: sentinel 行は migration `a3b4c5d6e7f8` で削除済)
   - `batch_alter_table` で `name` UNIQUE drop + `litellm_model_id` NOT NULL UNIQUE 化
3. **`model_sync_service` の同期キーを `litellm_model_id` に切替**:
   - `register_new_models_to_db` / `update_existing_models` の lookup を
     `get_model_by_name` → `get_model_by_litellm_id` に変更
   - 旧 `metadata["litellm_model_id"]` None フォールバックを削除 (Phase 1.10 完了で不要)
   - 経路違いの並列登録は UNIQUE 制約に委譲 (DB 側 IntegrityError をログのみで握る)
4. **`db_repository` の lookup API 改修**:
   - `get_model_by_litellm_id`, `get_models_by_litellm_ids` を新設
   - `get_model_by_name`, `get_models_by_names` は重複可能性のため削除し、呼び出し元を移行
   - `_get_or_create_manual_edit_model` を sentinel `__manual_edit__` 経由に変更
5. **MANUAL_EDIT の扱い**: `name="MANUAL_EDIT"`, `provider="user"`,
   `litellm_model_id="__manual_edit__"` の sentinel 値で UNIQUE NOT NULL 制約を満たす。
   推論経路には乗らないため副作用なし

### Decision section の更新差分

ADR 0023 本文の以下の記述は **Phase 1.11 (LoRAIro Issue #238) で更新**:

| ADR 本文 | 旧方針 | Phase 1.11 で更新後 |
|---|---|---|
| line 137-150 「LoRAIro DB との責務境界」 (ADR 0021 由来) の `models` テーブル保存項目 | `name` (UNIQUE 想定), `provider`, `api_model_id`, ... | `litellm_model_id` を UNIQUE NOT NULL のルーティングキー、`name` を非 UNIQUE 表示名、`provider` を非 UNIQUE ルーティング元に再定義。registry → DB sync キーは `litellm_model_id` 一本 |
| (新規) | (記述なし) | MANUAL_EDIT 行は sentinel `litellm_model_id="__manual_edit__"` で UNIQUE NOT NULL に整合 |

本文 line 137-150 自体は書き換えず Phase 1.11 完了セクション内の表で文書化
(Phase 1.5〜1.10 と同じ運用)。

### 検証

- 新規 unit test:
  - `get_model_by_litellm_id` (通常モデル / MANUAL_EDIT sentinel / 不在 ID)
  - migration data backfill 検証 (旧形式データ `name='openai/gpt-4.1', litellm_model_id=NULL` を含む test DB に upgrade を流して期待値検証)
- 既存テスト修正:
  - `test_manual_rating_unification.py` の `filter_by(name="MANUAL_EDIT")` を sentinel ベースに更新
  - `tests/bdd/steps/test_database_management.py` の name lookup を `litellm_model_id` ベースに書き換え
  - `test_model_sync_service.py` の lookup mock を更新
- Alembic upgrade/downgrade ラウンドトリップ確認
- `lorairo-cli models refresh` → `lorairo-cli models list` で 123 件 (Phase 1.10 後の registry 全件) が DB に並列登録されることを確認

### 関連 (未対応)

- LoRAIro Issue #241: API key 状況に応じたモデル表示フィルタ
  (`openrouter/` prefix 有無で経路判別、CLI/GUI 表示制御を追加)
- image-annotator-lib Issue #39 (close 済み): OpenRouter / 直接プロバイダーの
  経路選択ロジックは prefix 文字列マッチで機械的に判別可能と確定。ライブラリ側
  修正なしで close、表示制御は呼び出し側 (LoRAIro #241) で扱う

## Phase 1.12 方針 (LoRAIro Issue #241 — モデル route 表示の畳み込みと実行時 route 確定)

Phase 1.9 / 1.10 / 1.11 で registry と LoRAIro DB は「同一論理モデル × 経路違い」
を完全 `litellm_model_id` で並列保持できるようになった。一方で、GUI / CLI のモデル一覧で
直接プロバイダー経路と OpenRouter 経由がそのまま複数行に並ぶと、ユーザーがどちらを選ぶべきか
判断しづらい。

Issue #241 では、**実行時の SSoT は `litellm_model_id` のまま維持しつつ、表示時だけ route を
畳み込む** 方針を採用する。

### 責務境界

1. **image-annotator-lib 側**:
   - registry には direct / OpenRouter route を dedup せず並列登録する
   - `image_annotator_lib.annotate(..., model_name_list=...)` は完全 `litellm_model_id` を受け取る
   - OpenRouter / direct の経路判別は `openrouter/` prefix を持つ ID mapping で機械的に行う
2. **LoRAIro 側**:
   - GUI / CLI 一覧では同一論理モデルの route 候補を 1 行に畳み込む
   - ユーザー選択値は最終的に完全 `Model.litellm_model_id` に解決してから annotation library に渡す
   - API key 状況に応じて preferred route を選ぶ
   - 実行直前に `litellm_model_id` が要求する provider key の有無を検証し、不足時は
     library に投げる前に LoRAIro 側で分かりやすく失敗させる

### canonical model key

表示用の同一論理モデル判定では、`openrouter/` prefix を route として取り除いた
canonical key を使う。

| `litellm_model_id` | 表示用 canonical key |
|---|---|
| `anthropic/claude-3-5-sonnet-20241022` | `anthropic/claude-3-5-sonnet-20241022` |
| `openrouter/anthropic/claude-3-5-sonnet-20241022` | `anthropic/claude-3-5-sonnet-20241022` |
| `openai/gpt-4o` | `openai/gpt-4o` |
| `openrouter/openai/gpt-4o` | `openai/gpt-4o` |

`openrouter/<inner>/<model>` の `<inner>` が direct provider として LoRAIro で扱えない場合
(`openrouter/z-ai/...` 等) は、その canonical key に direct 候補が存在しないため
OpenRouter route が主候補になる。

### route 優先順位

永続設定は汎用 enum (`auto | direct | openrouter | all`) ではなく、
`prefer_openrouter: bool` の 1 つだけにする。デフォルトは `false` で、
direct provider route を優先する。

| `prefer_openrouter` | direct key | OpenRouter key | direct route | OpenRouter route | 選択 |
|---|---:|---:|---:|---:|---|
| `false` | yes | yes | yes | yes | direct |
| `true` | yes | yes | yes | yes | OpenRouter |
| 任意 | yes | no | yes | yes/no | direct |
| 任意 | no | yes | yes/no | yes | OpenRouter |
| 任意 | yes | yes | yes | no | direct |
| 任意 | yes | yes | no | yes | OpenRouter |
| 任意 | no | no | yes/no | yes/no | preferred fallback を disabled / unavailable 表示 |

永続設定を boolean に絞る理由:

- ユーザーが現時点で決めたいのは「直接 provider API に寄せるか、OpenRouter API に寄せるか」
  であり、モデル別 route preference は過剰設計になりやすい
- GUI では checkbox 1 個で表現でき、dropdown と補足説明が不要
- `all` は選択 policy ではなく表示/debug mode に近いため、永続設定に混ぜると責務が曖昧になる
- モデル別 preference は canonical key の安定性、モデル廃止、DB sync との整合、GUI 設定 UI、
  テストケースを大きく増やすため、実需要が出るまで採用しない

ただし実行時には選択済み `selected_litellm_model_id` をそのまま渡すため、表示上 direct を
優先しても route 情報は失われない。

### API key 設定

LoRAIro の `config/lorairo.toml [api]` に OpenRouter key を追加する。

```toml
[api]
openai_key = ""
claude_key = ""
google_key = ""
openrouter_key = ""
```

annotation library に渡す `api_keys` は provider 名を key にする。

```python
{
    "openai": "...",
    "anthropic": "...",
    "google": "...",
    "openrouter": "...",
}
```

`ConfigurationService.get_api_keys()` が設定ファイル上の key 名 (`openai_key`,
`claude_key` 等) を返す経路と、annotation library 用の provider key dict を返す経路は
混同しない。実装時は provider 名ベースの helper を用意し、`AnnotatorLibraryAdapter` /
`cli annotate` / 実行直前 validation で同じ helper を使う。

### 表示設定

永続設定は `[model_selection]` に分離し、OpenRouter API を優先するかだけを持つ。

```toml
[model_selection]
prefer_openrouter = false
```

`[api]` は credential のみ、`[model_selection]` は UI/CLI route 選択ポリシーのみを持つ。
route 詳細をすべて見る debug / display option (`--show-routes` 等) は永続設定とは分離する。

### LoRAIro 実装方針

- `src/lorairo/services/model_route_service.py` を追加し、pure helper と view model を集約する
  - `get_provider_route(litellm_model_id)`
  - `get_required_api_provider(litellm_model_id)`
  - `get_canonical_model_key(litellm_model_id)`
  - `group_model_routes(...)`
  - `select_preferred_route(...)`
- `ModelSelectionService` は GUI / CLI 共通の表示用畳み込みを提供する
- `lorairo-cli models list` の default は route を畳んだ一覧とする
  - config の `prefer_openrouter` を使う
  - 一時上書きが必要なら `--prefer-openrouter` / `--no-prefer-openrouter`
  - route 詳細表示が必要なら永続設定ではなく `--show-routes` 等の表示 option として扱う
- GUI `ModelSelectionWidget` は通常 1 モデル 1 行表示とし、route badge (`direct` /
  `openrouter`) を提供する。設定 UI は dropdown ではなく「OpenRouter API を優先する」
  checkbox とする
- `AnnotatorLibraryAdapter._prepare_api_keys()` と `cli annotate` は `openrouter` key を含める
- annotation 実行直前に選択済み `litellm_model_id` の required provider key を検証する

### Decision section の更新差分

ADR 0023 本文の以下の記述は **Phase 1.12 (LoRAIro Issue #241) で解釈拡張**:

| ADR 本文 | 既存方針 | Phase 1.12 で追加する解釈 |
|---|---|---|
| ID 境界: `litellm_model_id` は LiteLLM DB / metadata 用 ID | registry / DB / 実行指定の SSoT | LoRAIro GUI / CLI の表示上は route 候補を canonical key で畳むが、annotation library へ渡す実行指定は完全 `litellm_model_id` のまま維持する |
| API key / provider config は明示注入 | `api_keys` dict を唯一の入力経路とする | `openrouter/*` の required provider は `openrouter`。LoRAIro は `[api].openrouter_key` を provider key dict に含め、実行前 validation で不足を検出する |
| OpenRouter / direct route は prefix で判別可能 | lib 側は dedup しない | route 選択・表示畳み込みは LoRAIro 側の責務とする。永続設定は `prefer_openrouter` boolean のみで、モデル別 preference / 4値 enum は採用しない |

### スコープ外

- image-annotator-lib 側の registry dedup
- モデル別 / provider 別 route preference
- `route_preference = auto | direct | openrouter | all` の永続化
- `show_route_alternatives` の永続化
- 経路ごとのコスト / レイテンシ自動推奨
- LiteLLM Router / Proxy を使った runtime fallback
- direct provider が存在しない OpenRouter inner provider (`z-ai`, `qwen` 等) を direct route 化すること

## Phase 1.13 完了 (LoRAIro Issue #265 — discovery で `litellm_provider` を SSoT にして provider 推論を廃止)

### 問題

`lorairo-cli status` / `lorairo-cli models list --type webapi` 実行時に、LiteLLM の
provider 推論失敗で `Provider List: https://docs.litellm.ai/docs/providers` が多数回出力
されていた。

原因は `api_model_discovery.py` の `_collect_models()` / `is_model_deprecated()` が
`litellm.get_model_info(model_id)` を bare ID のみで呼んでいたこと。LiteLLM 内部の
`get_llm_provider_logic.py:505` は `custom_llm_provider` が無い場合に provider 推論を
試み、推論失敗時に `Provider List:` を print() して `BadRequestError` を raise する。

### 修正方針

`litellm.model_cost` の各 entry は `litellm_provider` field を既に持つ。discovery は
LiteLLM DB を走査しているため、provider の決定は `litellm_provider` field で完結する。
`litellm.get_model_info()` 等の LiteLLM API 呼び出しには `custom_llm_provider=provider`
を明示し、provider 推論経路に入らないようにする。

```python
# _collect_models() 修正前
info = litellm.get_model_info(model_id)

# _collect_models() 修正後
provider = info_cost.get("litellm_provider")   # info_cost = litellm.model_cost のループ変数
info = litellm.get_model_info(model_id, custom_llm_provider=provider)
```

```python
# is_model_deprecated() 修正後
info_cost = litellm.model_cost.get(model_id) or {}
provider = info_cost.get("litellm_provider")
info = litellm.get_model_info(model_id, custom_llm_provider=provider)
```

`litellm.suppress_debug_info = True` は global state 変更であるため採用しない。

### Decision section の更新差分

| ADR 本文 | 旧方針 | Phase 1.13 で更新後の方針 |
|---|---|---|
| `api_model_discovery.py` — LiteLLM 同梱 DB の runtime query | `litellm.get_model_info(model_id)` で provider は LiteLLM に推論させる | `litellm.model_cost[model_id]["litellm_provider"]` を SSoT として取得し、`litellm.get_model_info(model_id, custom_llm_provider=provider)` を明示渡しする |

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
- [Issue #41 — AnnotatorInfo.api_model_id を litellm_model_id field にリネーム](https://github.com/NEXTAltair/image-annotator-lib/issues/41)
- [Issue #42 — Phase 1.5 SafetyRefusalError / ContentPolicyRefusalError 統合](https://github.com/NEXTAltair/image-annotator-lib/issues/42)
- [Issue #45 — Phase 1.6 capability check 集約 + direct LiteLLM ID dispatch 廃止](https://github.com/NEXTAltair/image-annotator-lib/issues/45)
- [Issue #47 — Phase 1.7 PydanticAI output 処理での軽微正規化集約](https://github.com/NEXTAltair/image-annotator-lib/issues/47)
- [Issue #46 — Phase 1.8 PydanticAI HTTP transport retry の集約](https://github.com/NEXTAltair/image-annotator-lib/issues/46)
- [Issue #51 — Phase 1.9 LiteLLM 完全 ID を registry SSoT に統一](https://github.com/NEXTAltair/image-annotator-lib/issues/51)
- [Issue #52 — Phase 1.10 Anthropic bare 名を `anthropic/<bare>` に正規化](https://github.com/NEXTAltair/image-annotator-lib/issues/52)
- [LoRAIro Issue #238 — Phase 1.11 `schema.Model.litellm_model_id` を UNIQUE NOT NULL 化、`name` を表示名に降格](https://github.com/NEXTAltair/LoRAIro/issues/238)
- [LoRAIro Issue #241 — モデル route 表示の畳み込みと実行時 route 確定 (Phase 1.12)](https://github.com/NEXTAltair/LoRAIro/issues/241)
- [LoRAIro Issue #265 — discovery で `litellm_provider` を SSoT にして provider 推論廃止 (Phase 1.13)](https://github.com/NEXTAltair/LoRAIro/issues/265)
