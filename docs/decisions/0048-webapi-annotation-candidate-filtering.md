---
type: ADR
title: WebAPI Annotation Candidate Filtering (Endpoint / Capability / Suitability)
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0048: WebAPI Annotation Candidate Filtering (Endpoint / Capability / Suitability)

- **関連 Issue**: [NEXTAltair/image-annotator-lib#130](https://github.com/NEXTAltair/image-annotator-lib/issues/130), [NEXTAltair/image-annotator-lib#131](https://github.com/NEXTAltair/image-annotator-lib/issues/131), [NEXTAltair/LoRAIro#589](https://github.com/NEXTAltair/LoRAIro/issues/589)
- **関連 ADR**: [ADR 0021](0021-litellm-driven-model-registry.md), [ADR 0023](0023-pydanticai-litellm-webapi-inference-boundary.md), [ADR 0026](0026-on-demand-runtime-validation-strategy.md), [ADR 0038](0038-provider-batch-api-integration-strategy.md)

## Context

`image-annotator-lib` の WebAPI モデル検出処理(`webapi/api_model_discovery.py`)は、LiteLLM 同梱 DB を実行時の SSoT としている。現在の実装では、`supports_vision`、`supports_function_calling`、`mode ∈ {chat, responses}` を満たすモデルをアノテーション候補として登録する(ADR 0023 Phase 1.6)。LoRAIro はこの候補一覧を信頼し、DB 同期および UI 表示に利用している。

しかし実運用において、現行の同期アノテーション実行基盤では利用できないモデルや、画像アノテーションの用途に適さないモデルが候補へ混入する問題が顕在化した。168 件の検出結果を分類したところ、原因の異なる以下の 3 種類の不適格モデルが存在することが分かった。

- **`mode=responses` 専用モデル(23 件)**:deep-research、codex 系、pro ティアなどが該当する。現行の実行基盤(`webapi/model_id.py:build_pydantic_model`)は OpenAI モデルを常に `OpenAIChatModel`(`v1/chat/completions`)で構築するため、Responses 専用モデルは実行時に 404 エラーとなる。
- **`tools` 非対応モデル**:`gpt-5-search-api` 族などが該当する。LiteLLM は `supports_function_calling=True` と報告するものの、`get_model_info().supported_openai_params` には `tools` や `tool_choice` が含まれていない。LiteLLM の機能フラグが自身のパラメータ一覧と矛盾しており、現行の絞り込み条件をすり抜ける。
- **用途不適モデル**:TTS、computer-use、Web 検索を強制する search-preview などが該当する。`mode=chat` でエンドポイント上は動作するが、出力モダリティや対話方式が画像アノテーションに適さない。LiteLLM のメタデータでは判別できず、`supports_audio_output` には誤報があるうえ、`supports_web_search=True` は優良モデルも持つため判定軸として使えない。

さらに消費側である LoRAIro にも課題がある。`ModelSyncService.sync_available_models()` は登録と更新のみを行い、候補から外れたモデルの無効化(de-list)を行わない。そのため、ライブラリが提供しなくなったモデルが `discontinued_at=NULL` のまま `available=True` として残り続ける(`Model.available = discontinued_at is None`)。

これらは互いに独立した関心事である。単一の「フィルタ強度」設定でまとめて扱おうとすると、優良モデルである pro ティアを不適格として誤排除したり、`mode=chat` の用途不適モデルを取り逃したりする原因になる。

## Decision

WebAPI アノテーション候補の選別を**3 つの直交する軸**に分解し、それぞれを独立に実装する。あわせて消費側(LoRAIro)に無効化の再同期処理を導入する。

### 軸 A:エンドポイント実行可能性(capability gate)

現行の実行基盤が実際に構築・実行できるエンドポイントのモデルだけを候補とする。

- 現行の実行基盤は Chat Completions に一本化されている(ADR 0023 の同期経路および ADR 0038 のバッチ経路がいずれも `/v1/chat/completions` を使用)。そのため、アノテーション候補は `mode == "chat"` に限定する。
- `mode=responses` のモデルは「不適格」ではなく「現行の実行基盤では未対応」として扱う。将来 Responses 実行基盤へ対応した際に、このゲートを反転して利用可能にする(後述の Forward path)。

### 軸 B:機能判定の正確化(tool / function calling)

ADR 0023 Phase 1.6 で定めた「tool / function calling 対応を絞り込みの主条件とする」方針を踏襲しつつ、LiteLLM の `supports_function_calling` 真偽値を盲信しない。

- `get_model_info().supported_openai_params` に値が設定されている場合は、その中に `"tools"` が実際に存在することを要求する(実パラメータ一覧を優先)。
- 当該パラメータ一覧が未設定のプロバイダ(Gemini、Anthropic など)に限り、`supports_function_calling` の真偽値を信頼する。

これにより、`tools` 非対応の search-api 族をモデル名に依存せず除外しつつ、パラメータ一覧を持たないプロバイダを巻き込まないようにする。

### 軸 C:アノテーション適性(suitability denylist)

エンドポイントと機能の条件を満たしていても、画像アノテーションの用途に合わないモデルは LiteLLM のメタデータで判別できない。そこで、精査済みのモデル名部分一致による拒否リスト(denylist)で除外する。

- 対象は TTS、computer-use、Web 検索強制モデル、データソースツール前提の deep-research などとする。
- 軸 A のゲートとは独立した定数および関数として実装し、将来軸 A を反転しても拒否リストは維持する。
- 拒否リストはテストフィクスチャで固定し、LiteLLM DB の月次依存関係レビューで乖離(drift)を確認する。

### 消費側:候補外モデルの無効化(LoRAIro)

ライブラリが提供しなくなった WebAPI モデルを LoRAIro 側で正しく無効化できるようにする。

- `ModelSyncService.sync_available_models()` に再同期(reconcile)ステップを追加する。現在の検出結果に存在しない WebAPI モデル(`requires_api_key=True`)に対し、`discontinued_at` を設定して論理削除(soft-delete)する。
- ローカル ML モデルおよび `MANUAL_EDIT` センチネルは対象外とする。また、すでに `discontinued_at` が設定済みのレコードは再書き込みしない。
- モデルが再び候補へ現れた際の再有効化は、既存の更新経路(`discontinued_at=None`)が担う。

この処理はライブラリ側フィルタとは独立した汎用的な保護機構である。新規 DB はライブラリ側フィルタが保護し、既存 DB の残留レコードは本無効化処理が解消する。

### Forward path:Responses 実行基盤への対応(別軸・次段階)

OpenAI は Responses API を主軸としており、pro ティアや専用ティアを Responses 専用で提供している。将来 `OpenAIResponsesModel` の実行経路を追加して軸 A のゲートを反転すれば、`gpt-5-pro` や `o3-pro` などの pro ティアを実行できるようになる。

ただし、これは ADR 0023 の Chat 一本化方針を見直すアーキテクチャ判断にあたるため、本 ADR の対象外とし、別の Issue および ADR で扱う。その場合でも、軸 C の拒否リスト(deep-research など)は維持する。

## Consequences

### 良い点

- pro ティアを「不適格」と誤って排除せず「実行基盤未対応」として区別できるため、将来の Responses 対応で容易に復活させられる。
- search-api 族を名前非依存のメタデータ判定で除外でき、同種の将来モデルも自動的に弾ける。
- 3 つの軸を分離したことで、Responses 実行基盤へ対応する際の変更範囲を軸 A の反転のみに局所化できる。
- 既存 DB に残っていた古いモデルも、消費側の無効化処理によって UI から消去される。

### トレードオフ

- 軸 C は手動管理の拒否リストであるため、LiteLLM DB の更新に伴い乖離が生じ得る。月次の依存関係レビューとテストフィクスチャ固定によってリスクを緩和する。
- 現時点では OpenAI の pro ティアは利用できない(Responses 実行基盤が未対応のため)。これは Forward path で解消する予定である。

## Alternatives Considered

- **`mode=responses` を一律除外するだけにする案**:pro ティアを「不適格」と誤分類して恒久的に排除してしまううえ、`mode=chat` の用途不適モデルを取り逃す。関心事の混同にあたるため却下した。
- **プロバイダ系列ごとの許可リスト(opt-in allowlist)案**:安全性は高いが、LiteLLM 駆動の自動検出(ADR 0021)の利点を損ない、新モデルのたびに手動追加が必要になるため却下した。
- **`supports_web_search` で検索モデルを除外する案**:`gpt-5` や `gemini-2.5-pro` などの優良モデルも `supports_web_search=True` を持つため、約 60 件規模の誤除外が発生する。そのため却下した。
- **推奨フラグ(soft tier)で表示を抑制する案**:候補一覧そのものには不適格モデルが残るため、根本的な問題が解消しない。そのため却下した。

## Related

- ADR 0021 — LiteLLM-Driven WebAPI Model Registry(自動検出基盤)
- ADR 0023 — PydanticAI / LiteLLM WebAPI Inference Boundary(軸 B の tool 主条件および Chat 一本化の SSoT。Forward path での改訂対象)
- ADR 0026 — On-Demand Runtime Validation Strategy(Responses 実行基盤の実 API 検証方針)
- ADR 0038 — Provider Batch API Integration Strategy(Chat Completions 統一の根拠)
- `.claude/rules/dependency-management.md` — 拒否リストの乖離を確認する月次レビュー運用
