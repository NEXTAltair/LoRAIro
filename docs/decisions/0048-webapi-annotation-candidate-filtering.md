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

`image-annotator-lib` の WebAPI discovery (`webapi/api_model_discovery.py`) は LiteLLM 同梱 DB を runtime SSoT とし、`supports_vision` + `supports_function_calling` + `mode ∈ {chat, responses}` を満たすモデルを annotation 候補として登録する (ADR 0023 Phase 1.6)。LoRAIro はこの候補一覧を信頼して DB sync / UI 表示する。

実運用で、現行の同期 annotation runtime では使えないモデルや、用途が画像 annotation に合わないモデルが候補に紛れ込む問題が表面化した。168 件の discovery 結果を分類した結果、原因の異なる複数の不適格モデルが存在した:

- **`mode=responses` 専用モデル** (23 件: deep-research / codex 直 / pro ティア)。現 runtime (`webapi/model_id.py:build_pydantic_model`) は OpenAI を常に `OpenAIChatModel` (`v1/chat/completions`) で構築するため、Responses 専用モデルは実行時に 404。
- **`tools` 非対応モデル** (例: `gpt-5-search-api` 族)。LiteLLM が `supports_function_calling=True` と報告するが、`get_model_info().supported_openai_params` には `tools` / `tool_choice` が無い。LiteLLM の capability boolean が自身の param リストと矛盾しており、現条件をすり抜ける。
- **用途不適モデル** (TTS / computer-use / web 検索強制の search-preview)。`mode=chat` でエンドポイント上は動くが、出力 modality や対話パラダイムが画像 annotation に合わない。これらは LiteLLM metadata では判別できない (`supports_audio_output` 誤報、`supports_web_search=True` は優良モデルも持つため判定軸に使えない)。

加えて消費側の問題として、LoRAIro `ModelSyncService.sync_available_models()` は register / update のみで de-list を持たず、ライブラリが提供しなくなったモデルが `discontinued_at=NULL` のまま `available=True` で残存し続ける (`Model.available = discontinued_at is None`)。

これらは独立した関心事であり、ひとつの「フィルタ強度」ノブで扱うと優良モデルの巻き添え (pro ティアを「不適格」と誤排除) や本丸の取り逃し (chat-mode の用途不適モデルが残る) を招く。

## Decision

WebAPI annotation 候補の選別を **3 つの直交する軸** に分解し、それぞれ独立に実装する。

### 軸A — エンドポイント実行可能性 (capability gate)
現 runtime が実際に構築・実行できる endpoint のモデルのみを候補にする。現状 runtime は Chat Completions 一本 (ADR 0023 同期経路 / ADR 0038 batch も `/v1/chat/completions`) のため、annotation 候補は `mode == "chat"` に限定する。`mode=responses` は「不適格」ではなく「現 runtime 未対応」として扱い、Responses runtime 対応で gate を反転する (軸の forward path、後述)。

### 軸B — capability 判定の正確化 (tool/function calling)
ADR 0023 Phase 1.6 で確立した「tool/function calling を絞り込み主条件にする」を踏襲しつつ、LiteLLM の `supports_function_calling` boolean を盲信しない。`get_model_info().supported_openai_params` が populate されている場合は `"tools"` の実在を要求し (ground truth 優先)、未populate (Gemini / Anthropic 等) の場合のみ boolean を信頼する。これにより `tools` 非対応の search-api 族を名前非依存で除外しつつ、param を populate しない provider を巻き込まない。

### 軸C — アノテーション適性 (suitability denylist)
エンドポイント・capability が揃っても用途が画像 annotation に合わないモデルは、LiteLLM metadata で判別不能なため curated な名前 substring denylist で除外する (TTS / computer-use / web 検索強制 / data-source tool 前提の deep-research)。軸A の gate とは独立した定数・関数として実装し、軸A を反転しても denylist は維持する。denylist は test fixture で固定し、LiteLLM DB の月次 dependency review で drift を確認する。

### 消費側 — de-list reconcile (LoRAIro)
ライブラリが提供しなくなった WebAPI モデルを LoRAIro が正しく無効化できるようにする。`ModelSyncService.sync_available_models()` に reconcile ステップを追加し、現在の discovery に存在しない WebAPI モデル (`requires_api_key=True`) を soft-delete (`discontinued_at` 設定) する。ローカル ML モデルと MANUAL_EDIT sentinel は対象外。既 discontinued 行は再書き込みしない。再出現時の reactivation は既存 update 経路 (`discontinued_at=None`) が担う。これはライブラリ側フィルタとは独立した汎用的な堅牢性であり、新規 DB はライブラリ側フィルタが、既存 DB は本 de-list がカバーする。

### Forward path — Responses runtime (別軸 / 次段階)
OpenAI は Responses API を主軸化し pro / 専用ティアを Responses 専用で提供する。将来 `OpenAIResponsesModel` 経路を追加し軸A の gate を反転すれば pro ティア (gpt-5-pro / o3-pro 等) が実行可能になる。これは ADR 0023 の Chat 一本化を見直すアーキテクチャ判断であり、本 ADR のスコープ外 (別 Issue / 別 ADR)。その際も軸C denylist (deep-research 等) は維持する。

## Consequences

**Positive**
- pro ティアを「不適格」と誤排除せず「runtime 未対応」として正しく区別 — 将来の Responses 対応で復活させられる。
- search-api 族を名前非依存・metadata 駆動で除外。将来の同種モデルも自動的に弾ける。
- 軸の分離により Responses runtime 対応時に軸A だけを反転でき、変更範囲が局所化する。
- 既存 DB に残った stale モデルも消費側 de-list で UI から消える。

**Negative / Trade-off**
- 軸C は curated denylist のため LiteLLM DB 更新で drift し得る。月次 dependency review + test fixture 固定で緩和する。
- 現状 OpenAI pro ティアは利用不可 (Responses runtime 未対応のため)。Forward path で解消予定。

## Alternatives Considered

- **`mode=responses` を一律除外するだけ**: pro ティアを「不適格」と誤ラベルし恒久排除、かつ chat-mode の用途不適モデルを取り逃す。軸の混同。却下。
- **provider family allowlist (opt-in)**: 安全だが LiteLLM 駆動 auto-discovery (ADR 0021) の利点を殺し、新モデルごとに手動追加が必要。却下。
- **`supports_web_search` で search モデルを除外**: gpt-5 / gemini-2.5-pro 等の優良モデルも `supports_web_search=True` を持つため 60 件規模の誤除外。却下。
- **soft tier (recommended フラグ) で表示抑制**: 候補一覧には残るため「不適格モデルがリストアップされる」問題を解消しない。却下。

## Related

- ADR 0021 — LiteLLM-Driven WebAPI Model Registry (auto-discovery 基盤)
- ADR 0023 — PydanticAI / LiteLLM WebAPI Inference Boundary (軸B の tool 主条件 / Chat 一本化の SSoT、Forward path で改訂対象)
- ADR 0026 — On-Demand Runtime Validation Strategy (Responses runtime の実 API 検証方針)
- ADR 0038 — Provider Batch API Integration Strategy (Chat Completions 統一の根拠)
- `.claude/rules/dependency-management.md` — denylist drift の月次 review