---
type: ADR
title: PydanticAI / LiteLLM WebAPI Inference Boundary
status: Accepted
timestamp: 2026-05-07
tags: []
---
# ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary

- **Supersedes**: ADR 0021(一部 — `available_api_models.toml` キャッシュ運用および WebAPI 用ユーザー TOML 上書き部分)
- **関連 ADR**: [0021 LiteLLM-Driven WebAPI Model Registry](0021-litellm-driven-model-registry.md)、image-annotator-lib ADR 0007(WebAPI Dual-Endpoint Runtime — Chat + Responses、ランタイム構築の具体契約)
- **関連 ISSUE**:
  [image-annotator-lib#37](https://github.com/NEXTAltair/image-annotator-lib/issues/37),
  [#36](https://github.com/NEXTAltair/image-annotator-lib/issues/36),
  [#35](https://github.com/NEXTAltair/image-annotator-lib/issues/35),
  [#45](https://github.com/NEXTAltair/image-annotator-lib/issues/45),
  [#47](https://github.com/NEXTAltair/image-annotator-lib/issues/47),
  [#46](https://github.com/NEXTAltair/image-annotator-lib/issues/46),
  [#131](https://github.com/NEXTAltair/image-annotator-lib/issues/131)

## Context

ADR 0021 で WebAPI モデル一覧と機能メタデータの正本を LiteLLM へ寄せた。しかし Issue #36 の調査で、LiteLLM の `provider/model` ID と PydanticAI の実行モデル指定を混同している箇所が見つかった。

直接の不具合は、`ProviderManager` が PydanticAI の `Agent.run_sync()` へ `BinaryContent` 単体を渡している点にある。ただし、これだけを修正しても以下の問題が残る。

- PydanticAI の画像入力は、`["prompt", BinaryContent(...)]` のようなシーケンスを渡す契約である。
- PydanticAI の構造化出力(structured output)は `AgentRunResult.output` から読み取る。
- LiteLLM は `openai/gpt-5` や `anthropic/...` のような ID を使う一方、PydanticAI はネイティブプロバイダーオブジェクトや `openai:gpt-5.2` / `openrouter:...` 形式を使う。
- PydanticAI と LiteLLM はリトライ・フォールバック・構造化出力の周辺で重複機能を持つため、主責務を決めないと再び責務境界が曖昧になる。
- 現状の実装は `os.environ` を書き換えて PydanticAI の自動検出に任せる副作用パターンや、`api_model_id` のみをキャッシュキーにして API キーの違いを無視する古いエージェント再利用(stale agent)問題を抱えている。

これらを解決しなければ「実装可能な ADR」にならない。本 ADR では ADR 0021 の責務境界を具体化しつつ、残されていた `available_api_models.toml` のキャッシュ運用とユーザー TOML による WebAPI 上書きも再評価して整理する。

## Decision

通常の WebAPI 推論経路では、以下の責務分離を採用する。

> LiteLLM はモデル探索(discovery)と機能メタデータの正本として使う。
> 推論実行、マルチモーダル入力、構造化出力の検証、出力リトライは PydanticAI のネイティブプロバイダーおよびモデルで行う。
> `image-annotator-lib` 独自層は、LiteLLM メタデータと PydanticAI 実行記述子をつなぐアダプターと、結果のアプリケーションスキーマ変換を担う。

### 責務比較

| 機能 | PydanticAI | LiteLLM | 採用方針 |
|---|---|---|---|
| モデル探索 | 実行可能モデル一覧の正本には不向き | 同梱モデル DB と `get_model_info`・`supports_vision` が使える | LiteLLM を SSoT とする |
| 機能判定 | 実行時のモデル・プロファイル能力は扱えるが一覧化に弱い | Vision・function/tool calling・response schema 等のメタデータを持つ | LiteLLM を採用する |
| 推論実行 | Agent・ネイティブプロバイダー・モデル設定・`TestModel` が強い | SDK / Proxy で 100 以上のプロバイダーを OpenAI 互換形式で実行可能 | 通常経路は PydanticAI ネイティブプロバイダーを使う |
| マルチモーダル入力 | `["prompt", BinaryContent(...)]` 形式を公式サポート | OpenAI 互換メッセージ形式へ変換してプロバイダーへ送れる | PydanticAI へ寄せる |
| 構造化出力 | `output_type`、Tool/Native/Prompted 出力、Pydantic 検証、`result.output` | `response_format`、`supports_response_schema`、クライアント側 JSON スキーマ検証 | Phase 1 では PydanticAI 既定の Tool Output を使う |
| レスポンス検証 | Pydantic スキーマ・バリデーター・検証コンテキスト・`ModelRetry` が自然 | JSON スキーマ検証は可能だがアプリケーションスキーマの意味検証が弱い | PydanticAI へ寄せる |
| 出力リトライ | `retries` / `output_retries` で検証失敗を同一モデルへ再試行 | Router リトライは API 呼び出し失敗寄り | PydanticAI を採用する |
| HTTP / API リトライ | Tenacity transport をプロバイダー HTTP クライアントへ設定可能 | Router / Proxy リトライが強い | PydanticAI HTTP リトライのみ採用し、LiteLLM Router リトライは採用しない |
| フォールバック・ルーティング | `FallbackModel` があり、Agent 内で明示的なモデル順を管理できる | Router / Proxy の負荷分散やフォールバックが強い | 採用しない。同一モデルのリトライまでに限定する |
| コスト・トークンメタデータ | `result.usage()` で使用量を取得可能 | 価格メタデータとコスト補助関数がある | Phase 1 では使わない。必要なら別 ADR で検討する |
| API キー・プロバイダー設定 | ネイティブプロバイダーへ明示注入でき、副作用が小さい | 環境変数・設定・プロキシ経由が得意 | 通常経路は PydanticAI プロバイダーへ明示注入する |
| テスト | `TestModel` やモック推論と相性が良い | モックレスポンスやプロキシテストが可能 | PydanticAI を主軸にする |
| 可観測性・予算・マルチテナント | Logfire 等と連携可能 | Proxy が予算・レート制限・支出追跡に強い | 今回は対象外とし、必要時に別 ADR で検討する |

### ID 境界

`api_model_id` という単一名で LiteLLM ID と PydanticAI 実行 ID を兼用しない。後続実装では以下の 3 つを明確に分ける。

| 名前 | 意味 | 例 |
|---|---|---|
| `litellm_model_id` | LiteLLM DB・メタデータ用 ID | `openai/gpt-4o`, `anthropic/claude-...`, `gemini/gemini-...` |
| `provider_model_id` | 実プロバイダー上のモデル名 | `gpt-4o`, `claude-...`, `gemini-...` |
| `pydantic_ai_model_ref` | PydanticAI 実行用記述子 | ネイティブモデル・プロバイダーオブジェクト、または PydanticAI 形式のモデル文字列 |

`available_api_models.toml` 由来の旧 `api_model_id` は本 ADR で**廃止**する(互換シムを残さない)。LoRAIro と image-annotator-lib の関連呼び出しは破壊的変更として同一 PR でリネームする。

### ID マッピング関数契約

ID 解析と PydanticAI 実行記述子の構築は `image-annotator-lib/core/model_id.py` に集約する。

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

責務は以下のとおりである。

- `litellm_model_id` のプレフィックス解析(`openai/...`、`anthropic/...`、`gemini/...`、`openrouter/...`)
- 該当ビルダーを呼び出して `PydanticAIModelRef` を生成する
- LiteLLM ID から、プロバイダー上のモデル名と PydanticAI 用の構築情報を分離する
- 許可リスト外の未知プロバイダーには `UnknownProviderError` を送出する
- プレフィックス解析失敗や空 ID 等には `IdMappingError` を送出する

`SUPPORTED_PROVIDERS` は `_BUILDER_DISPATCH.keys()` から導出する。これによりディスパッチ表と許可リストの出典が同一となり、「許可リストにあるがビルダーがない」「ビルダーはあるが許可リストから漏れている」という乖離が構造的に発生しない。`core/api_model_discovery.py` はこの定数をインポートしてフィルタに使うだけとなり、新プロバイダー追加もディスパッチ表への 1 エントリ追加で完結する。

`PydanticAIModelRef` は、旧プロバイダー別 SDK アダプターのクラス分割を持ち込まないための境界である。具体的な PydanticAI プロバイダー・モデルクラス名やインポートパスは実装時点の公式 API に合わせる。`resolve_model_ref()` の後段で実行用モデルオブジェクトまたはモデル文字列を構築するが、本 ADR では特定クラス名を固定しない。

### Phase 1 のプロバイダー範囲

Phase 1(本 ADR と Issue #36 修正)で正式対応するプロバイダーは以下の 4 種である。

- OpenAI(`openai/...`)
- Anthropic(`anthropic/...`)
- Google(`gemini/...`、`google/...`)
- OpenRouter(`openrouter/...`)

Vertex AI・xAI・Cohere 等は本フェーズの対象外とし、`SUPPORTED_PROVIDERS` に含めず `UnknownProviderError` を返す。必要になった時点で `_BUILDER_DISPATCH` にビルダーを 1 つ追加するだけで対応できる(許可リストの個別編集は不要)。

### LiteLLM SSoT スコープ

ADR 0021 の責務分離をさらに進め、`available_api_models.toml` を**廃止**して LiteLLM を実行時の単一情報源とする。

| 用途 | Phase 0(ADR 0021) | Phase 1(本 ADR) |
|---|---|---|
| WebAPI モデル一覧 | `available_api_models.toml`(LiteLLM 出力のキャッシュ) | LiteLLM 同梱 DB を実行時評価し、`SUPPORTED_PROVIDERS` で絞り込む |
| 機能判定 | `_WEBAPI_MODEL_METADATA` / TOML フィールド | `litellm.supports_vision()` と `litellm.get_model_info()` をローカル DB 前提で実行時呼び出し |
| ユーザーカスタム WebAPI | `user_config.toml` の WebAPI セクション | **廃止**(LiteLLM 未登録モデルは利用不可) |
| ローカル ML モデル | `annotator_config.toml` + `user_config.toml` | 変更なし(本 ADR のスコープ外) |

設計判断は以下のとおりである。

- LiteLLM のインポート前に `LITELLM_LOCAL_MODEL_COST_MAP=True` を設定し、リモートのコストマップ取得を禁止する。LiteLLM 同梱 DB(`model_prices_and_context_window.json`)は機能レジストリとして利用するが、Phase 1 ではコスト・価格フィールドを読まない。
- TOML キャッシュを廃止することで、TOML と LiteLLM の乖離、`last_refresh` の TTL 管理、LiteLLM 更新後の手動再生成といった運用負担をすべてなくせる。
- OpenRouter フォールバック取得、TTL リフレッシュ、強制リフレッシュ、再生成系の処理を削除する。モデル DB の更新は `image-annotator-lib` の LiteLLM 依存更新で行う。
- WebAPI 用のユーザー TOML 上書き経路(`user_config.toml` の WebAPI セクション)は本 ADR で廃止する。ローカル ML モデル(`annotator_config.toml`)のユーザー上書きは別経路で維持する。
- LiteLLM 未登録モデルをユーザーが追加利用するケースは Phase 1 の対象外とし、必要性が顕在化した時点で別 ADR で再検討する。

### API キー注入契約

API キーの注入は、**プロバイダーオブジェクトへの明示注入のみ**を許可する。

- `ProviderManager.run_inference_with_model()` の `api_keys: dict[str, str]` を唯一の入力経路とする。
- `pydantic_ai_factory._set_env_api_key()` を削除し、`os.environ` を一切書き換えない。
- 環境変数フォールバック(`os.environ.get("OPENAI_API_KEY")` 等)も image-annotator-lib 内では行わない。LoRAIro 側はすでに設定から読んだ値を `api_keys` 経由で渡しているため実質的な影響はない。
- API キー解決に失敗した場合は `MissingApiKeyError(provider=..., litellm_model_id=...)` を送出する。

理由は以下のとおりである。

- 環境変数の書き換えはプロセス全体のグローバル状態汚染であり、テストの並列実行(pytest-xdist)や同一プロセス内の別ライブラリと競合する。
- 後始末漏れによって API キーが別経路へ漏れる事故が起き得る。
- キーの出所が 2 経路あると、どちらを使ったかログを見ないと分からずデバッグが困難になる。
- 将来「ユーザー単位で API キーを分ける」マルチテナント構成にも耐えられる。

### Agent ライフサイクル

PydanticAI の Agent・Provider・Model オブジェクトはキャッシュしない。

- `PydanticAIAgentFactory._agents` の `ClassVar` 辞書および `clear_cache()` メソッドを削除する。
- 推論呼び出しごとに、`resolve_model_ref` → プロバイダー構築 → モデル構築 → Agent 構築 → 実行の一連を毎回実行する。

性能への影響評価は以下のとおりである。

- Agent オブジェクトの生成コストは API 推論時間に比べて十分小さいと見込む。
- HTTP クライアントとコネクションプールを毎回破棄するため、HTTP keep-alive の利得は失われる。
- LoRAIro の Phase 1 ユースケースは低並列の GUI / CLI 実行であり、接続再利用よりも古いエージェントの再利用や API キー混線の防止を優先する。
- キャッシュ廃止により、Issue #36 系の不安定な挙動、キャッシュキー設計の難度、キャッシュ無効化ロジック、`ClassVar` 辞書の永続化バグを構造的に解消できる。
- 大量バッチや高並列が必要になった場合は、API キーを含む明示キャッシュキーとライフサイクル管理、または Batch API の採用を別 ADR で再検討する。

### 機能チェック(Capability check)

推論実行の直前に LiteLLM の機能を検証して早期失敗(fail-fast)させる。

```python
import litellm

if not litellm.supports_vision(litellm_model_id):
    raise VisionUnsupportedError(litellm_model_id=litellm_model_id)
```

- LiteLLM を SSoT とする以上、レジストリ構築時のフィルタだけでなく実行時にも同一の情報源を参照する方が一貫している。
- ユーザーが誤った `litellm_model_id`(例: `openai/gpt-3.5-turbo`)を直接渡した場合でも、API 課金される前に弾ける。
- LiteLLM は同梱 DB を参照するため、実行時呼び出しのコストはほぼゼロである。

Phase 1 の構造化出力は PydanticAI 既定の Tool Output を使用する。そのため `supports_response_schema` は NativeOutput 最適化の参考メタデータにとどめ、Phase 1 の実行可否条件にはしない。モデル絞り込みでは `supports_function_calling` を主条件とし、`supports_tool_choice` は候補優先度や警告に使う。メタデータが欠けるプロバイダー・モデルでは、PydanticAI の実行時エラーを `InferenceError` として明示化する。

Phase 1 の最低条件は以下のとおりである。

- プロバイダーが `SUPPORTED_PROVIDERS` に含まれる
- LiteLLM メタデータ上で vision に対応している
- LiteLLM メタデータ上で function/tool calling に対応している
- PydanticAI が対象プロバイダー・モデルを実行できる

### Schema から Result への変換

PydanticAI の `AgentRunResult.output`(`AnnotationSchema` 検証済み)から `AnnotationResult` への変換は `image-annotator-lib/core/result_adapter.py` に集約する。

```python
# core/result_adapter.py
def to_annotation_result(
    schema_output: AnnotationSchema | None,
    phash: str,
    error: str | None = None,
) -> AnnotationResult: ...
```

責務は以下のとおりである。

- `AnnotationSchema.tags` の抽出と正規化
- `formatted_output` の組み立て
- エラーメッセージの正規化
- `phash` マッピングの維持

`ProviderManager` は推論実行のみを担当し、結果変換ロジックは持たない。

### `TestModel` 注入機構

本番コードからテスト環境検知ロジック(`_is_test_environment()`、環境変数や `sys.modules` による判定)を削除し、テストは依存注入で行う。

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

- `_test_agent` はキーワード専用かつ先頭アンダースコアによりテスト専用であることを明示する。
- 本番コードがテスト環境を検知する分岐をゼロにする。
- pytest フィクスチャから `TestModel` ベースの Agent を渡す経路へ統一する。

### 例外階層

`WebApiError` を基底クラスとするサブ例外を新設する。

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

LoRAIro 側の `annotator_adapter.py` は `WebApiError` で広く捕捉し、必要に応じて例外型で分岐できる。各サブ例外は `litellm_model_id` や `provider` などのコンテキストを属性で保持する。

### リトライ方針

Phase 1 のリトライ対象は「構造化出力の検証失敗」と「API の一時的障害」のみに限定する。

- 出力およびスキーマ検証の失敗は、PydanticAI の `output_retries=1` で 1 回だけ再生成する。
- HTTP / API の一時的障害は、PydanticAI プロバイダーの HTTP クライアント・トランスポート層で初回+リトライ 2 回(最大 3 回試行)とする。
- リトライ対象の HTTP ステータスコードは `408`、`409`、`429`、`500`、`502`、`503`、`504` とする。
- `Retry-After` ヘッダーがある場合は尊重する。ただし最大待機時間は 60 秒までとし、それを超える場合はリトライせずエラーとして返す。
- モデルフォールバックやルーティングは実装せず、別モデルへの自動切り替えは行わない。
- LiteLLM Router のリトライは採用しない。
- `Agent(retries=...)` を API 失敗時のリトライとして扱わない。

TOML や設定ファイルからの上書き口は Phase 1 では提供しない。ユーザー要望が顕在化した時点で別 ADR で検討する。

リトライ対象外とするものは以下のとおりである。

- 安全性・コンテンツポリシーによる拒否(refusal)
- 認証・API キー・権限・クォータの恒久的失敗
- 未対応プロバイダー、未対応機能、不正モデル ID
- 入力エラー(画像読み込み、`BinaryContent` 変換、メディアタイプ、ペイロード・コンテキスト上限)
- 稼働中のイベントループ内から同期ラッパーを呼んだ誤用
- キャンセル、ユーザー停止、ワーカー終了
- PydanticAI の API 変更やプロバイダー SDK 仕様変更などの想定外バグ

### 出力正規化

`AnnotationSchema` 検証時の軽微な正規化は許可する。ただし独自の JSON 修復クラスや複雑なパーサー層は作らず、軽微な正規化で補正できない場合は PydanticAI の出力リトライに委ねる。

許可する軽微な正規化:

- `tags` が文字列ならカンマ分割または単一要素リスト化する
- `captions` が文字列なら単一要素リスト化する
- `score` が数値文字列なら float 化する
- タグおよびキャプションの前後空白を除去する
- 空文字のタグおよびキャプションを除外する

実装しない補正:

- 壊れた JSON の手修復
- 自由記述テキストからの正規表現による強制復元
- プロバイダーごとの専用修復クラスやパーサー層

### 安全性拒否(Safety refusal)の扱い

安全性・コンテンツポリシーによる拒否はリトライしない。プロンプト文言を変えて再試行する仕組みも Phase 1 では実装しない。拒否された画像は `ErrorRecord` を正本として記録し、以後の WebAPI アノテーション対象から除外する。なお、`Rating` は意味が異なるため使わない。

既存の `error_records` を以下の形式で使う。

```text
operation_type = "annotation"
error_type = "SafetyRefusalError" または "ContentPolicyRefusalError"
image_id = 対象画像ID
model_name = 拒否した model / litellm_model_id
resolved_at = NULL
```

送信前の除外条件は以下のとおりである。

```text
operation_type = "annotation"
error_type in {"SafetyRefusalError", "ContentPolicyRefusalError"}
resolved_at IS NULL
```

この条件に一致する `image_id` は WebAPI プロバイダー・モデルへ再送しない。将来、拒否理由の分類体系が必要になった場合は、専用カラムまたは専用テーブルを別 ADR で検討する。

### 非同期実行(Async execution)

`ProviderManager` は非同期ファーストとする。

- 中核実装は `run_inference_with_model_async()` に置く。
- `run_inference_with_model()` は CLI・Qt ワーカー・既存同期呼び出し用の薄いラッパーとする。
- 同期ラッパーは稼働中の asyncio イベントループ内では使用不可とする。
- 稼働中ループを検出した場合はスレッドへ逃がさず、非同期 API の利用を促す明示エラーを返す。
- 将来問題が生じた場合は、呼び出し側の非同期化またはワーカー実行方式を別 Issue で調整する。

#### サポート対象実行環境とスコープ

`image-annotator-lib` は **LoRAIro 専用サブモジュール** として運用される前提で設計している。LoRAIro は WebAPI アノテーションを Qt ワーカー(`QThreadPool` 上の `QRunnable`、`src/lorairo/gui/workers/`)で実行する。Qt イベントループは asyncio とは別系統であるため、ワーカースレッドには稼働中の asyncio ループが存在しない。本 ADR の同期ラッパーはこの前提のもと `asyncio.run()` 経由で動作する。

サポート対象の実行環境:

- LoRAIro の Qt ワーカー(`QRunnable` / `QThreadPool`)
- 通常の Python CLI およびスクリプト(`python -m image_annotator_lib...`)
- pytest 同期テスト(asyncio ループなし)

サポート対象外の実行環境:

- Jupyter notebook / IPython カーネル(カーネルが asyncio ループを保持する)
- FastAPI ハンドラーおよび asyncio Web フレームワークのハンドラー内
- すでに `asyncio.run()` 内にある任意の非同期コンテキスト

これらの環境で `image_annotator_lib.annotate()` を呼ぶと、同期ラッパーの稼働中ループ検出ロジックにより `InferenceError` が送出される。外部コードから直接利用する要件が生じた場合は、別 Issue で公開 `annotate_async()` の追加や `nest_asyncio` などの代替を再評価する。

[Codex review on PR #38](https://github.com/NEXTAltair/image-annotator-lib/pull/38#discussion_r3204194306) でも同点が指摘されたが、上記の実行環境スコープに基づき、現行の `InferenceError` による早期失敗を維持する判断とした。

### 実行経路(確定版)

1. 起動時に LiteLLM 同梱 DB を読み込み、`SUPPORTED_PROVIDERS` と機能条件で絞り込んでレジストリを構築する(`core/api_model_discovery.py`)。
2. 推論直前に vision と function/tool calling 機能を検証して早期失敗させる。
3. `resolve_model_ref(litellm_model_id, config)` で `PydanticAIModelRef` を生成する。
4. API キーをプロバイダーオブジェクトへ明示注入し、PydanticAI 実行用モデルオブジェクトまたはモデル文字列を構築する(環境変数の書き換えなし)。なお OpenAI プロバイダーのエンドポイントは当初 Chat Completions 固定であったが、#131 Amendment で LiteLLM の `mode` に基づくデュアルエンドポイントへ拡張した(後述の `Amendment (2026-06-01, iam-lib #131)` を参照)。
5. `Agent(model=model, output_type=AnnotationSchema, system_prompt=BASE_PROMPT, ...)` を毎回新規作成する。
6. 非同期コアでは `result = await agent.run([prompt_text, binary_content])` としてシーケンスで渡す。
7. 同期ラッパーは、イベントループ非稼働スレッドでのみ `run_inference_with_model_async()` を実行する。
8. `result.output`(`AnnotationSchema` 検証済み)を `core/result_adapter.py:to_annotation_result()` で `AnnotationResult` に変換する。

### Phase 1.x: WebAPI 経路のデバイス判定責務分離(Issue #35)

**契機**: ADR 0023 Phase 1(Issue #36、PR #38)で `WebApiAnnotator` を新設し、WebAPI 推論経路は構造的にこのクラスへ集約された。しかし次の 2 つの設計負債が残った。

1. レジストリが旧クラス `PydanticAIWebAPIAnnotator` を登録し、`annotation_runner._create_annotator_instance()` が `WebApiAnnotator` へ置換する場当たり的な構造であった。`_is_webapi_annotator_class` もクラス名文字列リストで照合する脆弱な実装になっていた。
2. `BaseAnnotator.__init__` が `_validate_device` 経由で `determine_effective_device` を呼ぶ構造のため、将来 WebAPI 系クラスが `super().__init__()` を呼ぶと CUDA 判定が走り、CPU のみ環境で「CUDA非対応PyTorch」警告が再発する余地があった(Issue #35)。

**Phase 1.x の決定**: クラス階層の整理とデッドコード削除を実施する。

- `BaseAnnotator.__init__` から `_validate_device` 呼び出しを削除し、ローカル ML 系基底クラス(`TransformersBaseAnnotator` / `ONNXBaseAnnotator` / `TensorflowBaseAnnotator` / `ClipBaseAnnotator` / `PipelineBaseAnnotator`)の `__init__` で個別に `determine_effective_device` を呼ぶ責務へ移譲する。
- `BaseAnnotator.device` の型は `str` を維持し、空文字(`""`)を「サブクラス未上書き」の番兵値とする。
- レジストリが `WebApiAnnotator` を直接登録するよう `_register_webapi_models_from_discovery()` を更新する。
- `annotation_runner._is_webapi_annotator_class()` を `issubclass(cls, WebApiAnnotator)` 判定へ簡素化する。
- `api.py:list_annotator_info()` のクラス名照合も `issubclass(model_class, WebApiAnnotator)` に置換する。
- 以下のデッドコードを削除する。
  - `core/base/pydantic_ai_annotator.py`(`PydanticAIWebAPIAnnotator`)
  - `core/base/webapi.py`(`WebApiBaseAnnotator`)
  - `core/base/webapi_common.py`
  - `model_class/annotator_webapi/{anthropic_api,google_api,openai_api_chat,openai_api_response,pydantic_ai_unified}.py`
  - `model_class/pydantic_ai_webapi_annotator.py`
  - `core/model_factory_adapters/`(旧 SDK アダプター補助群)

**結果**: WebAPI 推論経路は `BaseAnnotator → WebApiAnnotator` の一本道となり、デバイス判定はローカル ML 系基底クラスでのみ実行される。これにより Issue #35(CPU のみ環境の警告)は構造的に解消される。

**実機検証(PR-A 修正前後の比較で確認済み)**:

- 修正前ベースライン(PR #38 マージ後コミット `a9861bd`): `gemini-2.0-flash-lite` 実行時に `determine_effective_device` の警告はすでに出ていなかった(Phase 1 の `WebApiAnnotator` 切替が `BaseAnnotator.__init__` を経由していなかったため)。
- 修正後(Phase 1.x マージ後): 警告が出ないことを構造的に保証する回帰テスト(`tests/unit/core/test_webapi_annotator.py`)を追加した。`BaseAnnotator.__init__` 自体からデバイス判定を削除したため、将来 WebAPI 系クラスが `super().__init__()` を呼んでも警告は発生しない。

### `LiteLLMProvider` / LiteLLM SDK 推論の扱い

PydanticAI の `LiteLLMProvider` および LiteLLM SDK による直接推論は、通常の直接 API 実行経路では採用しない。LiteLLM Proxy / Gateway とモデルフォールバック・ルーティングも本 ADR の実装対象外とする。

## Rationale

PydanticAI は Agent 実行、画像入力、構造化出力、Pydantic 検証、出力リトライ、`TestModel` に強い。画像アノテーションの主要件は「画像を渡して `AnnotationSchema` に適合した検証済み結果を得る」ことであり、推論実行は PydanticAI へ寄せるのが自然である。

一方、LiteLLM は多プロバイダーのモデル DB、機能判定、Router / Proxy に強い。ADR 0021 の目的は WebAPI モデル一覧の追従を安定化することであり、推論実行まで LiteLLM へ寄せることではない。本 ADR は ADR 0021 の方針を維持しつつ、残されていた「TOML キャッシュを SSoT とするか、実行時 LiteLLM を SSoT とするか」という選択を後者へ確定させる。

PydanticAI と LiteLLM の両方を最大限に使うのではなく、同一責務を二重に持たせない。

- 機能・ライフサイクル管理: LiteLLM ローカル DB(実行時呼び出し、TOML キャッシュなし)
- コスト管理: Phase 1 では対象外
- 推論実行・検証・出力リトライ: PydanticAI ネイティブプロバイダー
- ID マッピング・互換吸収・結果変換: image-annotator-lib

この分割により、LiteLLM ID と PydanticAI 実行記述子の混同を構造的に防げる。

破壊的変更を選択した理由は以下のとおりである。

- 互換シム(`api_model_id` 引数の残存、環境変数書き換えフォールバック等)を残すと責務境界が曖昧になり、Issue #36 系の不具合が再発し得る。
- LoRAIro と image-annotator-lib は同一プロジェクト内で同 PR により切り替えられるため、互換期間を設ける利点が薄い。
- image-annotator-lib は現時点で LoRAIro 内部利用が主であり、外部互換性より責務境界の明確化を優先する。
- ID 用語の混乱を残すと、後続 ADR(Vertex AI 対応、Batch API 対応等)で `api_model_id` の意味を毎回確認する手間が生じる。

## Consequences

### 良い影響

- Issue #36 の修正方針が、単発のバグ修正ではなく WebAPI 推論設計全体と整合する。
- OpenAI・Anthropic・Gemini・OpenRouter の ID 差分を `core/model_id.py` 一箇所で吸収できる。
- API キーを `os.environ` へ後付けする副作用を排除し、プロバイダーオブジェクトへ明示注入できる。
- 構造化出力の検証と出力リトライを PydanticAI に集約できる。
- LiteLLM の機能メタデータが実行時呼び出しにより常に同梱 DB と一致する。
- `available_api_models.toml` の TTL 管理、再生成運用、乖離問題が消滅する。
- 本番コードからテスト環境検知ロジックがゼロになり、CI と開発環境で本番と挙動が異なる事故を防げる。

### トレードオフ

- プロバイダーごとの PydanticAI アダプター(`_build_<provider>_ref`)を `core/model_id.py` で保守する必要がある。
- PydanticAI プロバイダー API の変更に対する追従が必要になる。
- LiteLLM Router / Proxy のフォールバック・予算管理・マルチテナント機能は利用しない。
- Agent キャッシュを廃止するため HTTP 接続再利用の利得を失う(Phase 1 では低並列 GUI / CLI 用途の安全性を優先する)。
- LoRAIro と image-annotator-lib 双方の `ProviderManager.run_inference_with_model()` 呼び出しを同 PR で破壊的に切り替える必要がある(互換期間なし)。
- WebAPI 用の `user_config.toml` 上書きを廃止するため、LiteLLM 未登録モデルを使うユースケースは Phase 1 では扱えない(必要性が顕在化したら別 ADR で復活を検討する)。

### 後続実装

#### Issue #36(本 ADR 確定後に着手)

**新設ファイル(`image-annotator-lib/src/image_annotator_lib/`)**:

- `core/model_id.py`
  - `PydanticAIModelRef` dataclass
  - `resolve_model_ref(litellm_model_id, config) -> PydanticAIModelRef`
  - `build_pydantic_model(ref, api_key, config)` 等の実行用モデル構築ヘルパー
  - プロバイダー別ビルダー(`_build_openai_ref`、`_build_anthropic_ref`、`_build_google_ref`、`_build_openrouter_ref`)
  - `_BUILDER_DISPATCH` テーブルと `SUPPORTED_PROVIDERS` 定数
- `core/result_adapter.py`
  - `to_annotation_result(schema_output, phash, error=None) -> AnnotationResult`
  - エラー正規化、タグ抽出、`formatted_output` の組み立て
- `core/image_preprocess.py`
  - `preprocess_images_to_binary(images: list[Image.Image]) -> list[BinaryContent]`
  - 旧 `pydantic_ai_factory.preprocess_images_to_binary` を移動

**改修ファイル**:

- `core/provider_manager.py`
  - 非同期コア `run_inference_with_model_async()` を追加する。
  - 同期ラッパー `run_inference_with_model()` は稼働中イベントループ内で明示エラーを返す。
  - `run_inference_with_model()` の引数を `api_model_id` から `litellm_model_id` へリネームする(破壊的変更)。
  - キャッシュ取得を廃止し、毎回 `resolve_model_ref` からプロバイダー・モデル・Agent を構築する。
  - 推論前の vision および function/tool calling 機能チェックを追加する。
  - `agent.run_sync(binary_content)` を非同期コアの `await agent.run([prompt_text, binary_content])` へ変更する。
  - `response.data` を `result.output` へ変更する。
  - `_get_provider` と `_get_api_key` の ID 解析部分を `core/model_id.py` 利用へ置換する。
  - テスト専用のキーワード専用引数 `_test_agent` を追加する。
- `core/api_model_discovery.py`
  - `available_api_models.toml` への書き出しを廃止する。
  - OpenRouter フォールバック取得、TTL リフレッシュ、強制リフレッシュ、再生成処理を削除する。
  - `list_webapi_models()` 等の API を実行時 LiteLLM ローカル DB 呼び出しと `SUPPORTED_PROVIDERS` フィルタへ変更する。
- `exceptions/errors.py`
  - サブ例外 7 種(`IdMappingError`、`UnknownProviderError`、`MissingApiKeyError`、`VisionUnsupportedError`、`SafetyRefusalError`、`ContentPolicyRefusalError`、`InferenceError`)を追加する。
- `model_class/annotator_webapi/*.py`
  - 各アノテーターの `run_with_model()` を新 `ProviderManager` API へ追従させる。
- `AnnotationSaveService` およびアノテーションワーカー周辺
  - 結果エラーが `SafetyRefusalError` または `ContentPolicyRefusalError` の場合、`error_records` に未解決のアノテーションエラーとして保存する。
  - WebAPI 送信前に未解決の安全性拒否エラーを持つ `image_id` を除外する。
  - `ErrorRecord` 検索ヘルパーに `error_type` フィルタを追加する(スキーママイグレーション不要)。

**削除ファイル**:

- `config/available_api_models.toml`(LoRAIro と image-annotator-lib の双方)
- `core/pydantic_ai_factory.py`(機能を `core/model_id.py`・`core/result_adapter.py`・`core/image_preprocess.py` へ分散)

#### LoRAIro 側の追従(Issue #36 と同 PR で完結)

- `src/lorairo/annotations/annotator_adapter.py`
  - `ProviderManager.run_inference_with_model()` 呼び出しを `litellm_model_id=` へ変更する。
  - `available_api_models.toml` 読み込み箇所があれば LiteLLM 直接呼び出しへ置換する。
- `config/lorairo.toml`
  - WebAPI モデル定義に関する記述があれば削除する。
- ドキュメント
  - ADR 0021 のステータスと置き換え注記を更新する。
  - README・CHANGELOG・移行ガイド・統合ドキュメントから `available_api_models.toml` キャッシュ前提を削除する。
- テスト
  - `tests/unit/annotations/test_annotator_adapter.py` の引数名を更新する。
  - 既存 `available_api_models.toml` を参照するフィクスチャは LiteLLM モックフィクスチャへ置換する。

#### Issue #35(本 ADR および Issue #36 完了後)

- WebAPI 経路で `determine_effective_device` を呼ばない。
- `WebApiBaseAnnotator` 系ではデバイス判定を完全にスキップする。
- 本 ADR の責務分離が成立した時点で自然に解決できる。

### ADR 0021 への影響

ADR 0021 のステータスを `Superseded by ADR 0023 (partial)` に更新する。置き換えられるのは以下の部分のみである。

- ADR 0021 Decision #3: `available_api_models.toml` を LiteLLM 出力のキャッシュとして継続 → **廃止**
- ADR 0021 Decision #4: WebAPI モデルメタデータの正本を `available_api_models.toml` / `_WEBAPI_MODEL_METADATA` に集約 → **実行時 LiteLLM 呼び出しへ変更**
- ADR 0021 Decision #5: WebAPI モデルのユーザー TOML を最小限の上書きに留める → **WebAPI 用は廃止**(ローカル ML モデル用ユーザー TOML は ADR 0021 の対象外のため影響なし)

ADR 0021 のその他の決定(LiteLLM を SSoT とする方針、ライフサイクル API の二系統化等)は引き続き有効である。本 ADR は ADR 0021 の方向性をさらに進めるものであり、覆すものではない。

## Phase 1.5 完了(Issue #42 — `SafetyRefusal` / `ContentPolicyRefusal` 統合)

本 ADR line 285-294 で確定済みの `SafetyRefusalError` と `ContentPolicyRefusalError` を `WebApiError` 階層に追加し、line 347-372 の `error_records` 統合契約と送信前フィルタを実装した(2026-05 完了)。

### 実装サマリ

- **image-annotator-lib PR-A2**: `exceptions/errors.py` に 2 つのサブ例外を追加し、`provider_manager.py` の `_classify_refusal()` で PydanticAI およびプロバイダー SDK の例外を検出・分類した(大文字小文字を区別しない型名およびメッセージ文字列の部分一致)。
- **LoRAIro PR-B2**: `AnnotationSaveService._process_model_result` で `UnifiedAnnotationResult.error` のプレフィックスを解釈して `error_records` に記録した。また、`WorkerService.start_enhanced_batch_annotation` から `filter_refused_image_paths()` を呼び、未解決の拒否エラーを持つ画像を送信前に除外した。

### 連携契約(lib ↔ LoRAIro)

image-annotator-lib は `UnifiedAnnotationResult.error` に `f"{type(refusal_exc).__name__}: {refusal_exc}"` 形式のプレフィックス付き文字列を設定する。LoRAIro 側はこのプレフィックスを `startswith` で判定して `error_type` を切り出す。例外型を直接インポートせず文字列プレフィックスのみで連携することで、サブモジュールのピン固定戦略と整合させ、双方向のバージョン結合を回避する。

```text
lib側  UnifiedAnnotationResult.error = "SafetyRefusalError: blocked by safety filter"
                ↓
LoRAIro側  error.startswith("SafetyRefusalError:") → error_records.error_type = "SafetyRefusalError"
                ↓
LoRAIro側  filter_refused_image_paths() で次回送信時に除外
```

### 送信前フィルタ

`AnnotationSaveService.filter_refused_image_paths(image_paths)` は、`get_error_image_ids(operation_type="annotation", resolved=False, error_types=["SafetyRefusalError", "ContentPolicyRefusalError"])` で取得した `image_id` 集合を WebAPI アノテーション対象から除外する。`get_error_image_ids` には本 PR で `error_types` 引数を追加した(既存カラム利用のためスキーママイグレーション不要)。

### 検証

- image-annotator-lib ユニットテスト: 12 ケース(`_classify_refusal` の分類精度、属性反映、切り詰め)
- LoRAIro 統合テスト: 13 ケース(拒否時の `error_records` 記録、フィルタ除外、解決済み通過、他 `error_type` 通過、未知パス通過、`error_types` フィルタ)

将来の拒否理由分類体系(専用カラム・専用テーブル)は別 ADR で検討する。

## Phase 1.5 amendment(Issue #599 — `error_code` ルーティング)

iam-lib #134 によるアノテーション結果契約(Annotation Outcome Contract)の構造化に合わせ、LoRAIro 消費側は `UnifiedAnnotationResult.error` のプレフィックス解釈から `UnifiedAnnotationResult.error_code` ベースのルーティングへ移行する。

### 意味論の境界

`SAFETY_REFUSAL`・`CONTENT_POLICY_REFUSAL`・`EMPTY_ANNOTATION` は iam-lib にとってライブラリエラーではない。推論自体は完了しており、利用可能なアノテーション出力が得られなかった結果(outcome)である。一方 LoRAIro では、同じ結果をアノテーション対象から除外すべき状態として扱い、`error_records` に記録して以後の WebAPI 送信から除外する。これは無駄な API 課金と拒否・空出力ループを防ぐための LoRAIro 側ポリシーである。

### 連携契約(lib ↔ LoRAIro)

iam-lib は同期 WebAPI アノテーションの縮退結果を `UnifiedAnnotationResult(error_code=<code>, retryable=<bool>, error=<message>)` として返す。LoRAIro は例外クラス名やエラーメッセージのプレフィックスを実行時判定に使わず、`error_code` のみで分岐する。

```text
lib側  UnifiedAnnotationResult.error_code = "EMPTY_ANNOTATION"
                ↓
LoRAIro側  error_records.error_type = "EMPTY_ANNOTATION"
                ↓
LoRAIro側  filter_refused_image_paths() で次回送信時に除外
```

記録対象コードは以下に限定する。

- `SAFETY_REFUSAL`
- `CONTENT_POLICY_REFUSAL`
- `EMPTY_ANNOTATION`

`PROVIDER_ERROR` などのリトライ可能・通信系の結果は従来どおり警告付きスキップとし、`error_records` には記録しない。ワーカーレベルの致命例外記録経路とは分離して扱う。

### 既存データ

既存 DB に残る `SafetyRefusalError` および `ContentPolicyRefusalError` の `error_type` は、Alembic のデータマイグレーションで `SAFETY_REFUSAL` / `CONTENT_POLICY_REFUSAL` へ正規化する。実行時フィルタは旧例外名を許容せず、コード文字列のみを SSoT とする。

## Phase 2 完了(Issue #41 — `api_model_id` フィールド廃止)

ADR 0023 line 73 の「`available_api_models.toml` 由来の旧 `api_model_id` は本 ADR で廃止する(互換シムを残さない)」を公開 API レベルで実現する一括破壊的変更(Option A)を実施した(2026-05 完了)。

- **image-annotator-lib PR-A1**: `AnnotatorInfo.api_model_id` フィールドを `litellm_model_id` へリネームし、`registry.py` の関連箇所を更新した。
- **LoRAIro PR-B1**: `Model.api_model_id` カラムを `litellm_model_id` へリネームし(Alembic マイグレーション `c4d5e6f7a8b9` で SQLite 互換 `batch_alter_table` を使用)、`TypedDict`・`Protocol`・6 ファイルの参照を新名称へ追従させた。

これにより、ライブラリと LoRAIro の双方で `litellm_model_id` を SSoT とする構成が整い、命名上の分裂が解消された。LoRAIro 専用サブモジュールで外部利用者がいないため、後方互換期間は設けず一括移行した。

## Phase 1.6 完了(Issue #45 — 機能チェックの探索層集約と直接ディスパッチ廃止)

ADR 0023 line 216-220 で確定済みの「`supports_function_calling` を主条件にする」を実装すると同時に、機能判定の責務を**探索・レジストリ SSoT へ完全集約**するリファクタリングを実施した(2026-05 完了)。

### 実装サマリ(image-annotator-lib PR #48)

1. **絞り込み条件の切替**: `core/api_model_discovery.py:_is_litellm_model_annotation_compatible()` の必須条件を `supports_response_schema is True` から `supports_function_calling is True` へ置換した。レジストリ側の重複ロジック(未使用の `_is_annotation_compatible_webapi_model()`)は削除した。
2. **メタデータの純化**: `_format_litellm_metadata()` および `_register_webapi_models_from_discovery()` の登録メタデータから `supports_response_schema` キーを削除した。NativeOutput と Tool Output の切替戦略は将来別 ADR で扱うため、現時点ではメタデータに残さない。
3. **推論直前の機能チェック削除**: `core/provider_manager.py` の `litellm.supports_vision()` 直前チェックと `VisionUnsupportedError` クラスを削除し、機能判定責務を探索・レジストリへ一本化した。
4. **直接 LiteLLM ID ディスパッチ経路の廃止**: `core/annotation_runner.py:_create_annotator_instance()` の Step 2(レジストリに存在しない `provider/model` 形式を `WebApiAnnotator` へ直接渡す経路)を削除し、未登録モデル名は `KeyError` で弾くようにした。あわせて `api.py:list_annotator_info()` の直接探索列挙(section 2)とレジストリ補助関数 `_build_annotator_info_for_direct_model()` もデッドコードとして削除した。

### 設計上の本決定(Decision セクションの更新差分)

ADR 0023 本文の以下の記述は **Phase 1.6(Issue #45)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.6 更新後の方針 |
|---|---|---|
| line 199-220 「Capability check」 | 推論実行直前に LiteLLM `supports_vision()` で早期失敗させる | 機能判定は探索・レジストリ SSoT に集約し、推論層は機能検証済み前提で動作する純化設計とする。実行時の直前チェックは冗長なため削除する |
| line 217 「`supports_response_schema` は参考 metadata として扱い」 | メタデータに保持する(NativeOutput 最適化用) | メタデータからも削除する(NativeOutput / Tool Output 切替を実装する際に別 ADR で再追加する) |
| line 415-417 「実行経路 #2 推論直前 vision + function/tool calling capability fail-fast」 | 推論直前の早期失敗チェックあり | 廃止(探索段階で完結させる) |
| (新規) | (記述なし) | **直接 LiteLLM ID ディスパッチ経路の廃止**: `_create_annotator_instance()` はレジストリのみ参照する。未登録の `provider/model` を直接渡す経路は廃止する。LiteLLM 同梱 DB の WebAPI モデルは起動時探索でレジストリに自動登録されるため通常運用への影響はない |

### 根拠

- **探索・レジストリ SSoT 方針との整合**: ADR 0023 全体で機能判定の正本は LiteLLM メタデータと決定済みである。レジストリ経由の通常経路では登録時点で機能チェックが完了しているため、推論層での再チェックは機能的重複となる。
- **直接ディスパッチ経路と SSoT の不整合**: `_create_annotator_instance()` の直接ディスパッチ経路はレジストリを経由しないため機能チェックが抜ける構造的問題があった(Codex P1 指摘)。チェックを再導入するのではなく、SSoT 方針に従って経路自体を廃止することで根本解決した。
- **`supports_response_schema` メタデータ削除**: PydanticAI 既定の Tool Output で実行する Phase 1 設計では参照しないため削除した。LoRAIro 側にも該当カラムや参照は存在しないため、スキーママイグレーションは不要である。

### 検証

- image-annotator-lib ユニットテスト: 9 ケース(`_is_litellm_model_annotation_compatible` の境界条件、`_format_litellm_metadata` での `supports_response_schema` キー非存在確認)を含め、既存テスト全 502 件が PASS した(既存の 1 件失敗を除く)。
- LoRAIro 側への影響はない(`supports_response_schema` および `VisionUnsupportedError` への直接参照がないことを事前調査で確認済み)。

将来 NativeOutput 切替やレジストリ迂回時の機能チェックが必要になった場合は、別 ADR で扱う。

## Phase 1.7 完了(Issue #47 — PydanticAI 出力処理での軽微正規化集約)

ADR 0023 line 50-55 および line 595-600 で確定済みの「構造化出力の検証と軽微正規化を PydanticAI 側へ寄せる」方針に従い、軽微正規化を **`AnnotationSchema` 検証前** の出力関数内へ集約するリファクタリングを実施した(2026-05 完了)。

### 背景: 形式乖離の構造的発生

`BASE_PROMPT`(`image_annotator_lib/model_class/annotator_webapi/webapi_shared.py`)は LLM に対して以下の形式を指示している。

- `tags: 30-50 comma-separated words`(**文字列**)
- `caption: Single 1-2 sentence ... description`(**文字列**、単数)
- `score: Single decimal number between 1.00 and 10.00`(数値)

一方、`AnnotationSchema` は `tags: list[str]`・`captions: list[str]`・`score: float` を期待する。`output_type=AnnotationSchema` を直接指定する構成では、LLM がプロンプトどおりの文字列形式で返すと検証失敗となり、`output_retries=1` による再生成頼みになっていた。再生成も失敗すると推論全体が失敗する構造であった。

### 実装サマリ(image-annotator-lib PR #49)

1. **出力関数による正規化集約**: `core/output_normalization.py` に `normalize_annotation_output(tags, captions, score) -> AnnotationSchema` を新設し、PydanticAI の `Agent.output_type` に渡す。PydanticAI は呼び出し可能オブジェクトをツール化して LLM へ公開するため、関数の docstring は LLM 向けの説明として記述し、内部実装説明はモジュール docstring へ分離した。許可する正規化は以下のとおりである。
   - `tags`: 文字列(カンマ分割または単一要素)を `list[str]` に変換し、各要素の前後空白除去と空文字除外を行う。
   - `captions`: 文字列(単一要素)を `list[str]` に変換し、前後空白除去と空文字除外を行う(カンマ分割はしない)。
   - `score`: 数値文字列を `float` に変換する(`bool` は明示的に拒否する)。
   - 補正不能な値(`None`、辞書、リスト内の非文字列など)は `ModelRetry` を送出し、PydanticAI の `output_retries=1` 経由で LLM 再生成へ流す。
2. **`provider_manager` の `output_type` 切替**: `Agent(output_type=AnnotationSchema, ...)` を `Agent(output_type=normalize_annotation_output, ...)` へ切り替えた。`output_retries=1` は維持し、正規化内の `ModelRetry` 経由で再生成へ流す。
3. **`result_adapter` の純化**: 旧 `_normalize_string_list()` と `_normalize_score()`(検証前補正)を削除し、最終防衛の `_clean_string_list()` のみを残した。`to_annotation_result()` は検証済み `AnnotationSchema` から `AnnotationResult` への変換専任とした。

### 設計上の本決定(Decision セクションの更新差分)

ADR 0023 本文の以下の記述は **Phase 1.7(Issue #47)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.7 更新後の方針 |
|---|---|---|
| line 595-600 「Schema → Result 変換(`core/result_adapter.py`)」 | `result_adapter.py` で軽微正規化と変換の両方を行う | 軽微正規化を検証前の `core/output_normalization.py` へ分離し、`result_adapter.py` は変換専任と最終防衛の空白・空文字除去のみとする |
| (新規) | (記述なし) | **PydanticAI 出力関数経路の確定**: `Agent.output_type` には関数を渡し、内部で軽微正規化と `AnnotationSchema` 検証を行う。補正不能な乖離は `ModelRetry` 経由で `output_retries=1` による再生成へ流す |
| (補強) | 「output retry」行 | 出力正規化の `ModelRetry` も `output_retries=1` の対象であることを明記する |

### 実装しない補正

- 壊れた JSON の手修復
- 自由記述テキストからの正規表現による強制復元
- プロバイダー別パーサー層
- Issue #46(HTTP / API トランスポートリトライ)— 別 Issue・別 PR で扱う

### 根拠

- **形式乖離の構造的解決**: `output_type=AnnotationSchema` の直指定では乖離の全件が検証失敗からリトライへ落ち、再生成失敗時に推論全体が失敗していた。出力関数経由にすればコード側で軽微な乖離を補正して有効化でき、リトライ消費を真に補正不能なケースのみに限定できる。
- **責務分離**: 検証前正規化を `output_normalization.py`、検証済みオブジェクトからの結果変換を `result_adapter.py` へ分離することで、各モジュールの責務が単一になる。
- **LLM 側への案内**: PydanticAI が関数をツール化する仕様上、関数の docstring が LLM への説明として渡される。`Args:` 構造で各フィールドの期待形状を例示することで、`Any` 型スキーマでも LLM が適切な構造化出力を生成しやすくなり、`BASE_PROMPT` の指示と二重の安全網になる。

### 検証

- image-annotator-lib ユニットテスト: 新規 16 ケース(`output_normalization` 9 件、`provider_manager_output_normalization` 1 件、`result_adapter` 6 件)が PASS した。既存の拒否・機能チェック・`annotation_runner`・`webapi_annotator` テスト 64 ケースも PASS し、全ユニットテストは 512 件 PASS した(既存の 1 件失敗を除く)。
- LoRAIro 側への影響はない(`AnnotationSchema` および `to_annotation_result` への直接参照がないことを事前検索で確認済み)。

将来のスコア範囲制約や Issue #46 のトランスポートリトライ集約は別 Issue で扱う。

## Phase 1.8 完了(Issue #46 — PydanticAI HTTP トランスポートリトライの集約)

ADR 0023 line 304-329 で確定済みの HTTP / API 一時的障害リトライ方針を、`pydantic_ai.retries.AsyncTenacityTransport` を介してプロバイダー HTTP クライアント層へ組み込む実装を完了した(2026-05 完了)。Phase 1 残タスクの最終項目である。

### 実装サマリ(image-annotator-lib PR #50)

1. **トランスポートリトライ経路の新設**: `core/http_retry.py` に `build_retry_transport()` と `build_retry_http_client()` を新設し、PydanticAI の `AsyncTenacityTransport` と `RetryConfig` でラップした `httpx.AsyncClient` を返すようにした。リトライ対象は 7 種のステータスコード(`408`、`409`、`429`、`500`、`502`、`503`、`504`)および httpx の一時的例外(`TimeoutException` 階層の `ConnectTimeout` / `ReadTimeout` / `WriteTimeout` / `PoolTimeout`、`ConnectError`、`RemoteProtocolError`)である。`RetryConfig(reraise=True)` により原因例外をそのまま伝搬させ、`_classify_refusal()` の判定経路を保持した。
2. **プロバイダーオブジェクトへの `http_client` 注入**: `core/model_id.py:build_pydantic_model()` にキーワード専用引数 `http_client: httpx.AsyncClient | None = None` を追加し、OpenAI・Anthropic・Google・OpenRouter の全 4 プロバイダーで `*Provider(api_key=..., http_client=http_client)` 形式の注入を行うようにした。
3. **`AsyncClient` ライフサイクル**: `provider_manager.run_inference_with_model_async()` で `build_retry_http_client()` を毎回新規生成し、`try/finally` で `await http_client.aclose()` を呼ぶようにした。Agent・Provider・Model のキャッシュなし方針(Agent ライフサイクル節)と一貫させている。
4. **HTTP タイムアウトの明示**: `httpx.Timeout(timeout=120.0, connect=10.0, read=120.0, write=30.0, pool=10.0)` を定数 `HTTP_CLIENT_TIMEOUT` として定義し、`build_retry_http_client()` 内で `AsyncClient` へ渡す。WebAPI のビジョンモデルは応答に数十秒かかるため `read=120s` とし、`connect` と `pool` は 10 秒で早期失敗させる。タイムアウト発生時は `TimeoutException` 経由で最大 3 回試行まで救済される。
5. **依存の明示化**: `pyproject.toml` の `dependencies` に `tenacity>=9.0` を間接依存から明示依存へ昇格させた(`pydantic_ai.retries` モジュールが要求するため)。

### 設計上の本決定(Decision セクションの更新差分)

ADR 0023 本文の以下の記述は **Phase 1.8(Issue #46)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.8 更新後 |
|---|---|---|
| line 308 「最大待機は 60 秒までとし」 | 60 秒の根拠が未記載 | **60 秒採用の根拠を明示**: OpenAI と Anthropic のトークンバケットは分単位で補充され、典型的な `Retry-After` は 60 秒以内である(Anthropic 公式の "continuously replenished" 記述、OpenAI の RPM / ITPM / OTPM)。3 回試行 × 60 秒 = 最悪 120 秒待機後にエラー伝搬することで、Qt バッチワーカーのキャンセル応答性を確保する。pydantic-ai 既定の 300 秒は CLI 想定であり Qt UI には過大である |
| line 308-310 「それを超える場合は retry せず error として返す」 | 上限超過時の即時打ち切り(halt-on-exceed) | Phase 1 では **上限キャップのみ**(PydanticAI 標準の `wait_retry_after(max_wait=60)`)とし、即時打ち切りは Phase 2 へ繰り延べる。`Retry-After > 60s` は日次クォータ超過が主であり、3 回試行後のエラー経路で実質同等の運用結果になるため Phase 1 では実装しない |
| line 309 「retry 対象 HTTP status は `408`, `409`, `429`, `500`, `502`, `503`, `504`」 | ステータスコードのみ | **ネットワーク例外も追加**: `httpx.TimeoutException` 階層(`ConnectTimeout` / `ReadTimeout` / `WriteTimeout` / `PoolTimeout`)と `httpx.ConnectError` / `httpx.RemoteProtocolError` を対象に含める。一時的な接続切断・DNS 障害・接続段階の TLS タイムアウトも一時的障害として扱う(Codex P1 レビューで `ConnectTimeout` の漏れを修正済み) |
| (新規) | (記述なし) | **`AsyncClient` ライフサイクル**: 推論呼び出しごとに `httpx.AsyncClient(transport=AsyncTenacityTransport(...), timeout=HTTP_CLIENT_TIMEOUT)` を新規生成し、`try/finally` で `aclose()` する。Agent / Provider / Model のキャッシュなし方針と一致させる |
| (新規) | (記述なし) | **HTTP タイムアウト明示**: `connect=10s` / `read=120s` / `write=30s` / `pool=10s` を定数 `HTTP_CLIENT_TIMEOUT` で定義する。ビジョンモデルの応答は数十秒かかるため `read` を長めに取り、`connect` と `pool` は早期失敗させる |
| (新規) | (記述なし) | **依存**: `tenacity>=9.0` を `image-annotator-lib` の `dependencies` へ明示追加する(PydanticAI の `retries` モジュールが要求) |

### 実装しない補正(Phase 1.8 スコープ外)

- モデルフォールバック・ルーティング(ADR line 313-314 で不採用と決定済み)
- LiteLLM Router リトライ(同上)
- 上限超過時の即時エラー化(`Retry-After > max_wait` でリトライせず即エラーとする処理、Phase 2 対象)
- 推論を跨いだ HTTP コネクションプール共有(Agent キャッシュなし方針と整合させるため)

### 根拠

- **一時的障害の包括的救済**: ADR line 305 の「HTTP / API 一時的障害」をステータスコードだけでなくネットワーク例外(タイムアウト・接続・プロトコル)まで含めて解釈し、実運用で頻発する DNS 一時障害、TLS ハンドシェイク一時失敗、読み取りタイムアウト、プール枯渇をリトライで吸収する。`HTTPStatusError` のみでは接続段階で落ちた際に救済が働かず、手動再実行が必要になる。
- **`HTTP_CLIENT_TIMEOUT` の値設計**: `connect=10s` は TCP 接続が 10 秒で確立しなければ上流障害と判断して早期失敗させリトライへ回す。`read=120s` はビジョンモデル(GPT-4o、Claude Sonnet 等)の典型応答時間(5〜30 秒)に余裕を持たせた値である。`pool=10s` はプール取得段階のハングを早期検出し、`write=30s` は数 MB の画像アップロードに余裕を持たせている。
- **`tenacity` を明示依存にする理由**: PydanticAI の `pydantic_ai.retries` は `tenacity` をオプションの `[retries]` グループとしてのみ提供している。間接依存のままだと壊れる余地があるため、image-annotator-lib 側の `dependencies` へ直接列挙する。

### 検証

- image-annotator-lib ユニットテスト: 新規 51 ケース(`test_http_retry.py` 27 ケース、`test_http_retry_transport.py` 24 ケース)が PASS した。`ConnectTimeout`・`PoolTimeout`・`ReadTimeout`・`WriteTimeout` の 4 種のタイムアウトサブクラスのリトライ挙動を parametrize で網羅している。既存ユニットテストは 559 件 PASS、1 件除外(既存の失敗)であった。
- LoRAIro 側への影響はない(`InferenceError` や `WebApiError` の直接インポートはなく、リトライ上限超過エラーは既存の `UnifiedAnnotationResult.error` 文字列プレフィックス機構でそのまま伝搬する。Phase 1.5 / Issue #42 と同じ疎結合契約である)。

将来の上限超過時即時エラー化やセッション単位の HTTP コネクションプール共有は別 ADR で扱う。

## Phase 1.9 完了(Issue #51 — LiteLLM 完全 ID をレジストリ SSoT に統一)

ADR 0023 line 65-77 の ID 境界規定に基づき、`api_model_discovery._format_litellm_metadata()` が返す `model_name_short` を **LiteLLM 同梱 DB のオリジナルキーと同一の完全 ID** に揃える修正を実施した(2026-05 完了)。

### 背景

旧実装では `model_id.split("/", 1)[1]` によりプロバイダープレフィックスを削った文字列を `model_name_short` にしていた。そのため `openrouter/z-ai/glm-4.7` のようなネスト形式の LiteLLM ID では `model_name_short = "z-ai/glm-4.7"` となり、レジストリキー・CLI 表示・LoRAIro DB の `litellm_model_id` 列へプレフィックス欠落形が伝播していた。推論時の `resolve_model_ref()` は `_BUILDER_DISPATCH` にない `z-ai` を未知プロバイダーとみなし、`UnknownProviderError` で弾く構造になっていた。

### 実装サマリ(image-annotator-lib PR #51 系)

1. **`_format_litellm_metadata()` の修正**: `core/api_model_discovery.py:55-82` の `model_name_short` を `model_id`(LiteLLM オリジナルキー)そのものに変更した。`display_name` も同一値になるが、既存呼び出し側との互換のため両フィールドを残した(将来のフェーズでのフィールド統合は別 ADR で検討する)。
2. **レジストリ・CLI・LoRAIro DB の SSoT 統一**: `_register_webapi_models_from_discovery()` は変更不要であった。`model_name_short` をそのままキー登録するため、`_MODEL_CLASS_OBJ_REGISTRY` と `_WEBAPI_MODEL_METADATA` のキーが完全 ID(`openai/gpt-4o`、`openrouter/z-ai/glm-4.7` 等)に揃い、`AnnotatorInfo.name` および LoRAIro CLI の `info.name` も同一値となる。
3. **探索フィルタは無変更**: `is_allowed_provider()` は line 126-138 のとおり `_BUILDER_DISPATCH.keys()`(`SUPPORTED_PROVIDERS`)の第 1 要素照合のみで判定する。`openrouter/<inner>/<model>` の内部プロバイダー別フィルタは行わない(Issue #51 本文の「`openrouter/` 配下はすべて表示」を遵守)。未知の内部プロバイダー(`z-ai`、`qwen`、`mistralai`、`moonshotai` 等)もそのまま OpenRouter 経由で推論ルーティングされる。

### Decision セクションの更新差分

ADR 0023 本文の以下の記述は **Phase 1.9(Issue #51)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.9 更新後 |
|---|---|---|
| line 70-74 ID 用語表(`litellm_model_id` の例) | `openai/gpt-4o`, `anthropic/claude-...`, `gemini/gemini-...` | **OpenRouter ネスト形式 `openrouter/<inner>/<model>`(例: `openrouter/openai/gpt-4.1`、`openrouter/z-ai/glm-4.7`、`openrouter/qwen/qwen3.5-...`)も `litellm_model_id` の有効形式である**ことを明記する。内部プロバイダーが `_BUILDER_DISPATCH` の直接プロバイダー集合にない場合(`z-ai`、`qwen` 等)でも、`openrouter/` プレフィックスにより OpenRouter 経由でルーティングできる |
| (新規) | (記述なし) | **レジストリ SSoT**: `_format_litellm_metadata()` が返す `model_name_short` は LiteLLM オリジナルキーと同一の完全 ID とし、レジストリキー・CLI 表示・LoRAIro DB `litellm_model_id` 列へ同一値を伝播させる |

なお、ADR 0023 本文 line 70-74 の ID 用語表自体は書き換えない。Phase 1.5〜1.8 の前例に倣い、本セクションの「Decision セクションの更新差分」表で解釈拡張を文書化するのみとし、本文を歴史的記録として保つことで追跡性を維持する。

### 検証

- 新規ユニットテスト 5 件:
  - `tests/unit/core/test_api_model_discovery_filter.py:TestFormatLitellmMetadata` に 3 ケース追加(`openrouter/<inner>/<model>`、`openrouter/openai/<model>`、`openai/<model>` 直接形式)。
  - `tests/unit/core/test_model_id.py::TestResolveModelRef` の parametrize に 2 ケース追加(`openrouter/z-ai/glm-4.7`、`openrouter/qwen/qwen2-vl-72b-instruct`)。
- 全既存テストが PASS した(603 passed、18 skipped)。残る 1 件の失敗(`test_tagger_transformers.py::test_toriigate_tagger_format_with_assistant_prefix`)と 5 件の BDD feature 失敗は main ブランチでも再現する既存の失敗であり、本修正とは無関係である(transformers ライブラリ版の互換性問題)。
- `lorairo-cli models list` を手動確認し、`openrouter/z-ai/glm-4.7`、`openrouter/qwen/qwen3.5-...`、`openrouter/anthropic/claude-opus-4.6` などが完全 ID で 71 件表示され、旧プレフィックス欠落形(`z-ai/glm-4.7` 単体等)が消失していることを確認した。

### LoRAIro 側への影響

- `Model.litellm_model_id` 列に格納される文字列が完全 ID に揃う(DB 既存データの扱いは LoRAIro Issue #238 のスキーマ変更時にマイグレーションで対応する)。
- LoRAIro CLI(`lorairo/cli/commands/models.py`)の `is_model_deprecated(info.name)` は、`info.name` が完全 ID になることで自動的に LiteLLM 内部キーと一致するため、LoRAIro 側の追加変更は不要である。

### 関連(未対応)

- Issue #39(image-annotator-lib): OpenRouter 経由の `openai/...` / `anthropic/...` と直接プロバイダー版が両方レジストリに登録される重複問題。本フェーズで完全 ID 表示が確定したことで CLI 上でも重複が可視化された。別 Issue で対応する。
- 新規 Issue(image-annotator-lib): LiteLLM JSON のベア Anthropic 名(`claude-opus-4-6` 等、`/` なし)が `is_allowed_provider()` で全除外される問題。Anthropic 直接モデル経路の復活は Phase 1.10 として連動 PR で対応する。
- LoRAIro Issue #238: `schema.Model` の `name` UNIQUE 制約撤去、`litellm_model_id` の UNIQUE NOT NULL 化、Alembic マイグレーション。

## Phase 1.10 完了(Issue #52 — Anthropic ベア名を `anthropic/<bare>` に正規化)

ADR 0023 line 109 のプレフィックス解析対象規定の解釈拡張として、LiteLLM 同梱 DB のベア Anthropic 名(`claude-*`、計 19 件)を `anthropic/<bare>` 形式へ正規化し、`litellm_model_id` の有効形式として扱う修正を実施した(2026-05 完了)。

### 背景

LiteLLM 同梱 DB は Anthropic 直接モデルを `claude-opus-4-6`、`claude-sonnet-4-6`、`claude-haiku-4-5` などのベア名(`/` なし)で格納している。Issue #51(Phase 1.9)で完全 ID 保持へ修正した後も、`is_allowed_provider()` の `if "/" not in model_id: return False` チェックがベア名を全除外していた。そのため Anthropic 直接プロバイダー経路がレジストリに登録されず、`lorairo-cli models list` には OpenRouter 経由(`openrouter/anthropic/claude-*`)のみが表示されていた。`_BUILDER_DISPATCH["anthropic"]`(`_build_anthropic_ref`)はすでに `anthropic/<model>` 形式に対応していたため、探索段階の正規化のみで Anthropic 直接経路を復活できる構造であった。

### 実装サマリ(image-annotator-lib PR #YY)

1. **`_canonicalize_litellm_id()` ヘルパーを新設(`core/api_model_discovery.py`)**: `_ANTHROPIC_BARE_PREFIXES = ("claude-",)` で始まるベア ID を `anthropic/<bare>` へ補完する。スラッシュ入り ID はそのまま通し、スコープ外のベア名(例: `gpt-4o`、Bedrock 形式の `anthropic.claude-*`)は `None` を返す。
2. **`is_allowed_provider()` をリファクタリング**: 新設ヘルパー経由で判定するようにし、ベア `claude-*` が `SUPPORTED_PROVIDERS` を通過できるようにした。
3. **`_format_litellm_metadata()` を修正**: 正規化後の ID を `model_name_short` と `display_name` に格納する。`provider` は先頭大文字化規則により `"Anthropic"` となる(Phase 1.9 で確立した規則)。
4. **`_collect_models()` の辞書キーを正規化後 ID に統一**: `metadata[model_id] = formatted` を `metadata[formatted["model_name_short"]] = formatted` へ変更した。これにより `discover_available_vision_models()` の戻り値 `{"models": [...], "metadata": {...}}` も正規化後 ID で一貫する。
5. **変更不要箇所(確認済み)**: `is_model_deprecated()` は `litellm.get_model_info()` がベア形式・スラッシュ形式の両方で同一メタデータを返すためそのまま動作する。`_BUILDER_DISPATCH` と `core/model_id.py` も `anthropic/<model>` 形式をすでにサポートしている。

### Decision セクションの更新差分

ADR 0023 本文の以下の記述は **Phase 1.10(Issue #52)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.10 更新後 |
|---|---|---|
| line 109 プレフィックス解析対象(`openai/...`、`anthropic/...`、`gemini/...`、`openrouter/...`) | `provider/model` 形式のスラッシュ入り ID のみ | LiteLLM 同梱 DB のベア Anthropic 名(`claude-*`、19 件)は `anthropic/` プレフィックスを補完して `litellm_model_id` の有効形式として扱う。レジストリ・CLI・DB SSoT には正規化後 ID を乗せる |
| (新規) | (記述なし) | スコープは `claude-*` プレフィックスのみとする。Bedrock / Vertex 経由の `anthropic.*` 形式ベア名(約 178 件、`_BUILDER_DISPATCH` にビルダーなし)は除外を維持する。追加対応には新ビルダーが必要なため別 ADR で扱う |

本文 line 109 自体は書き換えず、Phase 1.10 完了セクション内の表で文書化する(Phase 1.5〜1.9 と同じ運用)。

### 検証

- 新規ユニットテスト 10 件(`tests/unit/core/test_api_model_discovery_filter.py`):
  - `TestCanonicalizeLitellmId` 4 ケース(スラッシュ透過、`claude` ベア、非 `claude` ベア、空文字)
  - `TestIsAllowedProviderBareName` 3 ケース(ベア `claude` 許可、非 `claude` ベア拒否、スラッシュ無変更)
  - `TestFormatLitellmMetadata` に 3 ケース追加(ベア `claude`、日付サフィックス、非 `claude` ベア)
- 全既存テストが PASS した(Phase 1.9 と同じ既存失敗を除く)。ライブラリ全テスト結果は 613 passed、18 skipped、1 failure(既存の `test_tagger_transformers`)であった。
- `lorairo-cli models list` を手動確認し、レジストリ登録 WebAPI モデルが 71 件から 90 件(+19 件)、総モデル数が 104 件から 123 件へ増え、`anthropic/claude-opus-4-6`、`anthropic/claude-sonnet-4-6`、`anthropic/claude-haiku-4-5` 等が完全 ID で追加表示されることを確認した。

### LoRAIro 側への影響

- `Model.litellm_model_id` 列に `anthropic/claude-*` の新規行が追加される(DB 既存データへの影響はなく、新規モデル追加と等価である)。
- LoRAIro CLI・GUI・`annotator_adapter` のコード変更は不要である。
- Anthropic 直接モデル経由の推論には `api_keys["anthropic"]` が必要だが、LoRAIro 設定の Anthropic API キー経路(`config/lorairo.toml [api] claude_key`)が既存のまま機能する。

### 関連(未対応)

- Issue #39(image-annotator-lib): Anthropic 直接(`anthropic/claude-opus-4-6`)と OpenRouter 経由(`openrouter/anthropic/claude-opus-4-6`)の重複登録。Phase 1.10 で重複が CLI 上でさらに可視化されたが本 Issue では触らない。低レイテンシの直接経路とマルチプロバイダー一元化の OpenRouter 経路の選択は、LoRAIro 側で解決する設計余地として残す。
- LoRAIro Issue #238: `schema.Model.litellm_model_id` 列の UNIQUE NOT NULL 化と Alembic マイグレーション。
- 他プロバイダーのベア名対応(Bedrock / Vertex 経由 `anthropic.*` 等 約 178 件): `_BUILDER_DISPATCH` へのビルダー追加が必要なため別 ADR で扱う。

## Phase 1.11 完了(LoRAIro Issue #238 — `schema.Model.litellm_model_id` を UNIQUE NOT NULL 化し、`name` を表示名へ降格)

> **注意(2026-05-23 追記)**: 本フェーズで導入した `__legacy_<id>__` 番兵値の「履歴行として保持する」運用契約は、**[ADR 0033](0033-annotation-worker-batch-execution-contract.md) Decision 7 で撤回**された。LoRAIro は開発フェーズで過去 DB 互換性が不要であり、番兵行が `name` 一致経由のクエリで推論経路へ流入する脆弱性を抱えていたためである。該当番兵行はマイグレーション `a3b4c5d6e7f8` で削除済みである(2026-05-23)。なお、推論経路に乗らない正規利用の `__manual_edit__` 番兵値は引き続き保持する。

Phase 1.9 / 1.10(Issue #51、#52)により、レジストリが「同一論理モデル × 経路違い」のエントリを完全 LiteLLM ID で並列保持するようになった。これを受け、LoRAIro の DB スキーマを SSoT 規約へ整合させた(2026-05 完了)。`schema.Model` の責務を以下のとおり再構成する。

| カラム | 値の例 | 役割 |
|---|---|---|
| `name` | `gpt-4.1` | 表示名(非 UNIQUE) |
| `provider` | `openrouter` / `openai` / `anthropic` | ルーティング元(非 UNIQUE) |
| `litellm_model_id` | `openrouter/openai/gpt-4.1` | **ルーティングキー(UNIQUE NOT NULL)** |

### 背景

ADR 0023 line 109 / 138(`SUPPORTED_PROVIDERS` 規定)および Phase 1.9 / 1.10 の SSoT 拡張により、レジストリには `anthropic/claude-3-5-sonnet-20241022`(直接経路)と `openrouter/anthropic/claude-3-5-sonnet-20241022`(OpenRouter 経由)が別エントリとして並列登録される。LoRAIro の旧 `schema.Model` 定義には以下の問題があった。

- `name` に UNIQUE 制約があるため、同一モデル名の複数経路を DB に保存できず重複 INSERT で `IntegrityError` が発生する。
- `litellm_model_id` が NULL 許容かつ非 UNIQUE であったためルーティングキーとして信頼できず、`model_sync_service` が `name` を一意キーとして検索していた。
- `provider` の意味が緩く、`name="openai/gpt-4.1"` のようなスラッシュ込み形式が混在する余地があった。

Phase 1.10 完了後のレジストリは 123 件のモデルを返すが、そのまま LoRAIro DB へ投入すると直接版と OpenRouter 版の `name` 衝突で同期が破綻していた。

### 実装サマリ(LoRAIro PR #ZZZ)

1. **`schema.Model` 定義変更**:
   - `name` の `unique=True` を削除し、非 UNIQUE・NOT NULL の表示名とした。
   - `litellm_model_id` を `Mapped[str]`(NOT NULL)かつ `unique=True` へ昇格させた。
   - `provider`、`discontinued_at`、`estimated_size_gb`、`requires_api_key`、リレーション定義は据え置いた。
2. **Alembic マイグレーション新設**:
   - `MANUAL_EDIT` 行に番兵値 `litellm_model_id = '__manual_edit__'` を設定した。
   - スラッシュ込み `name` 行は `name` をそのまま `litellm_model_id` にコピーし、`instr(name, '/')` で先頭 `/` 区切りにより `provider` と表示名へ分離した(例: `openrouter/openai/gpt-4o` → `provider='openrouter'`、`name='openai/gpt-4o'`)。
   - スラッシュなし `name` かつ `provider IS NOT NULL` の行は `litellm_model_id = provider || '/' || name` で補完した。
   - 残存 NULL 行は NOT NULL 化失敗を防ぐため `__legacy_<id>__` 番兵値で埋めた(**ADR 0033 Decision 7 で撤回**、マイグレーション `a3b4c5d6e7f8` で削除済み)。
   - `batch_alter_table` により `name` の UNIQUE 制約を削除し、`litellm_model_id` を NOT NULL・UNIQUE 化した。
3. **`model_sync_service` の同期キーを `litellm_model_id` へ切替**:
   - `register_new_models_to_db` および `update_existing_models` の検索を `get_model_by_name` から `get_model_by_litellm_id` へ変更した。
   - 旧 `metadata["litellm_model_id"]` の `None` フォールバックを削除した(Phase 1.10 完了により不要)。
   - 経路違いの並列登録は UNIQUE 制約へ委譲し、DB 側 `IntegrityError` はログ出力のみで吸収する。
4. **`db_repository` の検索 API 改修**:
   - `get_model_by_litellm_id` と `get_models_by_litellm_ids` を新設した。
   - 重複の恐れがある `get_model_by_name` と `get_models_by_names` を削除し、呼び出し元を移行した。
   - `_get_or_create_manual_edit_model` を番兵値 `__manual_edit__` 経由へ変更した。
5. **`MANUAL_EDIT` の扱い**: `name="MANUAL_EDIT"`、`provider="user"`、`litellm_model_id="__manual_edit__"` の番兵値で UNIQUE NOT NULL 制約を満たす。推論経路には乗らないため副作用はない。

### Decision セクションの更新差分

ADR 0023 本文の以下の記述は **Phase 1.11(LoRAIro Issue #238)で更新** された。

| ADR 本文 | 旧方針 | Phase 1.11 更新後 |
|---|---|---|
| line 137-150 「LoRAIro DB との責務境界」(ADR 0021 由来)の `models` テーブル保存項目 | `name`(UNIQUE 想定)、`provider`、`api_model_id` など | `litellm_model_id` を UNIQUE NOT NULL のルーティングキー、`name` を非 UNIQUE 表示名、`provider` を非 UNIQUE ルーティング元へ再定義する。レジストリから DB への同期キーは `litellm_model_id` に一本化する |
| (新規) | (記述なし) | `MANUAL_EDIT` 行は番兵値 `litellm_model_id="__manual_edit__"` で UNIQUE NOT NULL 制約に整合させる |

本文 line 137-150 自体は書き換えず、Phase 1.11 完了セクション内の表で文書化する(Phase 1.5〜1.10 と同じ運用)。

### 検証

- 新規ユニットテスト:
  - `get_model_by_litellm_id`(通常モデル、`MANUAL_EDIT` 番兵値、不在 ID)
  - マイグレーションのデータ補完検証(旧形式データ `name='openai/gpt-4.1', litellm_model_id=NULL` を含むテスト DB でアップグレードを実行し期待値を確認)
- 既存テスト修正:
  - `test_manual_rating_unification.py` の `filter_by(name="MANUAL_EDIT")` を番兵値ベースへ更新
  - `tests/bdd/steps/test_database_management.py` の名前検索を `litellm_model_id` ベースへ書き換え
  - `test_model_sync_service.py` の検索モックを更新
- Alembic のアップグレード・ダウングレード往復を確認した。
- `lorairo-cli models refresh` から `lorairo-cli models list` を実行し、Phase 1.10 後のレジストリ全 123 件が DB に並列登録されることを確認した。

### 関連(未対応)

- LoRAIro Issue #241: API キー状況に応じたモデル表示フィルタ(`openrouter/` プレフィックス有無で経路を判別し、CLI / GUI 表示制御を追加)。
- image-annotator-lib Issue #39(クローズ済み): OpenRouter と直接プロバイダーの経路選択ロジックはプレフィックス文字列一致で機械的に判別可能と確定したため、ライブラリ側の修正なしでクローズし、表示制御は呼び出し側(LoRAIro #241)で扱う。

## Phase 1.12 方針(LoRAIro Issue #241 — モデル経路表示の畳み込みと実行時経路確定)

Phase 1.9 / 1.10 / 1.11 により、レジストリと LoRAIro DB は「同一論理モデル × 経路違い」を完全 `litellm_model_id` で並列保持できるようになった。一方で、GUI や CLI のモデル一覧で直接プロバイダー経路と OpenRouter 経由がそのまま複数行に並ぶと、ユーザーがどれを選ぶべきか判断しづらい。

Issue #241 では、**実行時の SSoT は `litellm_model_id` のまま維持しつつ、表示時のみ経路を畳み込む**方針を採用する。

### 責務境界

1. **image-annotator-lib 側**:
   - レジストリには直接経路と OpenRouter 経路を重複排除せず並列登録する。
   - `image_annotator_lib.annotate(..., model_name_list=...)` は完全 `litellm_model_id` を受け取る。
   - OpenRouter と直接経路の判別は `openrouter/` プレフィックスを持つ ID マッピングで機械的に行う。
2. **LoRAIro 側**:
   - GUI / CLI 一覧では同一論理モデルの経路候補を 1 行に畳み込む。
   - ユーザー選択値は最終的に完全 `Model.litellm_model_id` へ解決してからアノテーションライブラリへ渡す。
   - API キーの状況に応じて優先経路を選択する。
   - 実行直前に `litellm_model_id` が要求するプロバイダーキーの有無を検証し、不足時はライブラリへ渡す前に LoRAIro 側で分かりやすく失敗させる。

### 正規モデルキー(canonical model key)

表示用の同一論理モデル判定では、`openrouter/` プレフィックスを経路情報として取り除いた正規キーを使う。

| `litellm_model_id` | 表示用正規キー |
|---|---|
| `anthropic/claude-3-5-sonnet-20241022` | `anthropic/claude-3-5-sonnet-20241022` |
| `openrouter/anthropic/claude-3-5-sonnet-20241022` | `anthropic/claude-3-5-sonnet-20241022` |
| `openai/gpt-4o` | `openai/gpt-4o` |
| `openrouter/openai/gpt-4o` | `openai/gpt-4o` |

`openrouter/<inner>/<model>` の `<inner>` が直接プロバイダーとして LoRAIro で扱えない場合(`openrouter/z-ai/...` 等)は、その正規キーに直接経路候補が存在しないため、OpenRouter 経路が主候補となる。

### 経路優先順位

永続設定は汎用列挙型(`auto | direct | openrouter | all`)ではなく、`prefer_openrouter: bool` の 1 項目のみとする。既定値は `false` とし、直接プロバイダー経路を優先する。

| `prefer_openrouter` | 直接キー | OpenRouter キー | 直接経路 | OpenRouter 経路 | 選択 |
|---|---:|---:|---:|---:|---|
| `false` | yes | yes | yes | yes | direct |
| `true` | yes | yes | yes | yes | OpenRouter |
| 任意 | yes | no | yes | yes/no | direct |
| 任意 | no | yes | yes/no | yes | OpenRouter |
| 任意 | yes | yes | yes | no | direct |
| 任意 | yes | yes | no | yes | OpenRouter |
| 任意 | no | no | yes/no | yes/no | 優先候補を無効・利用不可表示 |

永続設定を真偽値に絞る理由は以下のとおりである。

- ユーザーが現時点で決めたいのは「直接プロバイダー API に寄せるか、OpenRouter API に寄せるか」であり、モデル別の経路優先設定は過剰設計になりやすい。
- GUI ではチェックボックス 1 個で表現でき、ドロップダウンや補足説明が不要になる。
- `all` は選択ポリシーではなく表示・デバッグモードに近いため、永続設定へ混ぜると責務が曖昧になる。
- モデル別の優先設定は、正規キーの安定性、モデル廃止、DB 同期との整合、GUI 設定 UI、テストケースを大きく増やすため、実需要が出るまで採用しない。

なお、実行時には選択済みの `selected_litellm_model_id` をそのまま渡すため、表示上で直接経路を優先しても経路情報は失われない。

### API キー設定

LoRAIro の `config/lorairo.toml [api]` に OpenRouter キーを追加する。

```toml
[api]
openai_key = ""
claude_key = ""
google_key = ""
openrouter_key = ""
```

アノテーションライブラリへ渡す `api_keys` はプロバイダー名をキーとする。

```python
{
    "openai": "...",
    "anthropic": "...",
    "google": "...",
    "openrouter": "...",
}
```

`ConfigurationService.get_api_keys()` が設定ファイル上のキー名(`openai_key`、`claude_key` 等)を返す経路と、ライブラリ用のプロバイダーキー辞書を返す経路は混同しない。実装時はプロバイダー名ベースのヘルパーを用意し、`AnnotatorLibraryAdapter`、`cli annotate`、実行直前検証で共通利用する。

### 表示設定

永続設定は `[model_selection]` セクションへ分離し、OpenRouter API を優先するかのみを保持する。

```toml
[model_selection]
prefer_openrouter = false
```

`[api]` は認証情報のみ、`[model_selection]` は UI / CLI の経路選択ポリシーのみを持つ。経路詳細をすべて確認するデバッグ・表示オプション(`--show-routes` 等)は永続設定から分離する。

### LoRAIro 実装方針

- `src/lorairo/services/model_route_service.py` を追加し、純粋関数ヘルパーとビューモデルを集約する。
  - `get_provider_route(litellm_model_id)`
  - `get_required_api_provider(litellm_model_id)`
  - `get_canonical_model_key(litellm_model_id)`
  - `group_model_routes(...)`
  - `select_preferred_route(...)`
- `ModelSelectionService` で GUI / CLI 共通の表示用畳み込みを提供する。
- `lorairo-cli models list` の既定表示は経路を畳み込んだ一覧とする。
  - 設定ファイルの `prefer_openrouter` を参照する。
  - 一時上書きには `--prefer-openrouter` / `--no-prefer-openrouter` を用いる。
  - 経路詳細表示は永続設定ではなく `--show-routes` 等の表示オプションで扱う。
- GUI の `ModelSelectionWidget` は通常 1 モデル 1 行表示とし、経路バッジ(`direct` / `openrouter`)を表示する。設定 UI はドロップダウンではなく「OpenRouter API を優先する」チェックボックスとする。
- `AnnotatorLibraryAdapter._prepare_api_keys()` と `cli annotate` に `openrouter` キーを含める。
- アノテーション実行直前に、選択済み `litellm_model_id` が要求するプロバイダーキーを検証する。

### Decision セクションの更新差分

ADR 0023 本文の以下の記述は **Phase 1.12(LoRAIro Issue #241)で解釈拡張** された。

| ADR 本文 | 既存方針 | Phase 1.12 で追加する解釈 |
|---|---|---|
| ID 境界: `litellm_model_id` は LiteLLM DB / メタデータ用 ID | レジストリ・DB・実行指定の SSoT | LoRAIro GUI / CLI の表示上は経路候補を正規キーで畳み込むが、アノテーションライブラリへ渡す実行指定は完全 `litellm_model_id` のまま維持する |
| API キー・プロバイダー設定は明示注入 | `api_keys` 辞書を唯一の入力経路とする | `openrouter/*` の必須プロバイダーは `openrouter` である。LoRAIro は `[api].openrouter_key` をプロバイダーキー辞書に含め、実行前検証で不足を検出する |
| OpenRouter / 直接経路はプレフィックスで判別可能 | ライブラリ側は重複排除しない | 経路選択と表示畳み込みは LoRAIro 側の責務とする。永続設定は `prefer_openrouter` 真偽値のみとし、モデル別優先設定や 4 値列挙型は採用しない |

### スコープ外

- image-annotator-lib 側のレジストリ重複排除
- モデル別・プロバイダー別の経路優先設定
- `route_preference = auto | direct | openrouter | all` の永続化
- `show_route_alternatives` の永続化
- 経路ごとのコスト・レイテンシ自動推奨
- LiteLLM Router / Proxy を用いた実行時フォールバック
- 直接プロバイダーが存在しない OpenRouter 内部プロバイダー(`z-ai`、`qwen` 等)の直接経路化

## Phase 1.13 完了(LoRAIro Issue #265 — 探索処理で `litellm_provider` を SSoT としプロバイダー推論を廃止)

### 問題

`lorairo-cli status` および `lorairo-cli models list --type webapi` の実行時、LiteLLM のプロバイダー推論失敗により `Provider List: https://docs.litellm.ai/docs/providers` が多数回出力されていた。

原因は、`api_model_discovery.py` の `_collect_models()` と `is_model_deprecated()` が `litellm.get_model_info(model_id)` をモデル ID のみで呼んでいた点にある。LiteLLM 内部の `get_llm_provider_logic.py:505` は `custom_llm_provider` が未指定の場合にプロバイダー推論を試み、失敗すると `Provider List:` を標準出力へ出力したうえで `BadRequestError` を送出する。

### 修正方針

`litellm.model_cost` の各エントリはすでに `litellm_provider` フィールドを持っている。探索処理は LiteLLM DB を走査しているため、プロバイダーの決定は `litellm_provider` フィールドで完結する。`litellm.get_model_info()` 等の LiteLLM API 呼び出しには `custom_llm_provider=provider` を明示し、プロバイダー推論経路に入らないようにする。

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

`litellm.suppress_debug_info = True` はグローバル状態の変更を伴うため採用しない。

### Decision セクションの更新差分

| ADR 本文 | 旧方針 | Phase 1.13 更新後の方針 |
|---|---|---|
| `api_model_discovery.py` — LiteLLM 同梱 DB の実行時参照 | `litellm.get_model_info(model_id)` でプロバイダーを LiteLLM に推論させる | `litellm.model_cost[model_id]["litellm_provider"]` を SSoT として取得し、`litellm.get_model_info(model_id, custom_llm_provider=provider)` を明示渡しする |

## Amendment(2026-06-01、iam-lib #131): Chat + Responses Dual-Endpoint

当初の本 ADR では、WebAPI 同期推論経路の OpenAI エンドポイントを Chat Completions(`OpenAIChatModel` / `/v1/chat/completions`)に固定していた。iam-lib #131 により、これを **LiteLLM の `mode` に基づくモデル別エンドポイント選択** へ拡張する。ランタイム構築の具体契約は image-annotator-lib ADR 0007(WebAPI Dual-Endpoint Runtime)に記録し、本改訂では上位方針(SSoT)を記述する。

### 背景

OpenAI は Responses API を主軸化しており、pro ティア(`gpt-5-pro`、`o3-pro`、`o1-pro`、`gpt-5.x-pro` 系)は `mode=responses` 専用で Chat Completions には載っていない。OpenAI を無条件に Chat 経路で構築していたため、これら Responses 専用モデルは実行時に 404 エラーとなっていた。iam-lib #130(PR #132)で暫定的に探索ゲートを `mode=chat` のみに絞って Responses 系を除外していたが、#131 でゲートを反転し `OpenAIResponsesModel` 経路を実装して pro ティアを実行可能にする。

### 拡張内容

- **モデル別のエンドポイント選択**: LiteLLM レジストリメタデータの `mode` を情報源とし、`annotator → provider_manager → resolve_model_ref(mode=...) → PydanticAIModelRef.endpoint → build_pydantic_model` の分岐へ配線する。OpenAI かつ `mode=responses` のときのみ `OpenAIResponsesModel` を使い、それ以外の OpenAI モデルは `OpenAIChatModel` とする。Anthropic・Google・OpenRouter は常に Chat 系とする(OpenRouter 経由の OpenAI モデルも Chat)。
- **軸 A(エンドポイント互換性)と軸 B(アノテーション適性)のコード上分離**: #131 では軸 A のゲートのみ反転して chat と responses の両方を許可し、軸 B の除外リスト(denylist)は維持・拡張する。
- **`codex` の一律除外**: OpenAI 直接の Responses `codex` に加え、従来 Chat で有効だった `openrouter/openai/gpt-5.1-codex-max` も除外部分文字列 `codex` で除外する(plan_130 の「openrouter codex は残す」判断を #131 で上書き)。`codex` はコーディング特化で画像アノテーションに不向きなため、プロバイダーやエンドポイントを問わず一律除外する。
- **`deep-research` の除外維持**: データソースツール前提のため、ゲート反転後も除外リストで除外し続ける。
- **バッチ経路は Chat 専用のまま維持(ADR 0038 不変)**: #131 の対象は同期ランタイムのみであり、ADR 0038 の OpenAI バッチ経路(`/v1/chat/completions`)は変更しない。LoRAIro Issue #518 の教訓(バッチを Chat に固定し、同期経路とエンドポイント・ツールスキーマ・レスポンス形状を一致させてフィクスチャや拒否判定を再利用する)と整合させるためである。Responses 専用 pro ティアは同期ランタイム限定で実行可能となる。
- **拒否判定契約は不変**: Phase 1.5 の拒否分類契約(例外ボディの再帰走査・型名・正規表現によるプロバイダー横断判定)は Responses 経路でもそのまま機能する想定である。コード変更は行わず、実 API スモークテストで確認する([ADR 0026](0026-on-demand-runtime-validation-strategy.md))。
- **plan_525 との整合**: plan_525 では PydanticAI 2.0 beta の「Responses への強制全切替」を不採用とした。#131 は全切替ではなく LiteLLM の `mode` に基づくモデル別選択であるため矛盾しない。

### LiteLLM 同梱 DB 実測(2026-06-01)

- ゲート反転で復活する OpenAI pro ティア: 11 件(`gpt-5-pro` と日付付き、`gpt-5.2/5.4/5.5-pro` と日付付き、`o1-pro` と日付付き、`o3-pro` と日付付き。すべて `vision` と `function_calling` が `True`)。
- 除外維持: `deep-research` 4 件。
- 新規除外: `codex`(OpenAI 直接 8 件および `openrouter/openai/gpt-5.1-codex-max`)。

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
- [image-annotator-lib Issue #131 — WebAPI Chat + Responses dual-endpoint runtime (Amendment 2026-06-01)](https://github.com/NEXTAltair/image-annotator-lib/issues/131)
- [image-annotator-lib Issue #130 — 暫定 chat-only discovery gate (PR #132)](https://github.com/NEXTAltair/image-annotator-lib/issues/130)
- image-annotator-lib ADR 0007 — WebAPI Dual-Endpoint Runtime(Chat + Responses、ランタイム構築の具体契約)