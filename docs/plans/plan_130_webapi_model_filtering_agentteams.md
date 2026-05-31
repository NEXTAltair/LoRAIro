# Plan: WebAPI discovery のモデル絞り込み是正 + Responses エンドポイント対応 (iam-lib #130 / LoRAIro #589)

- **親 Issue**: [image-annotator-lib#130](https://github.com/NEXTAltair/image-annotator-lib/issues/130) — WebAPI discovery が annotation 不適合な OpenAI Responses/deep-research 系モデルを候補に含める
- **連動 Issue**: [LoRAIro#589](https://github.com/NEXTAltair/LoRAIro/issues/589) — deep-research モデル選択で 404
- **作成日**: 2026-05-31
- **方針 (user 確定)**: 絡まった複数問題を **repo 所有権で別Issue に切り分ける**。
  - **Issue X = iam-lib #130 (更新済, 優先)**: deep-research 等、用途外モデルがリストアップされる = **ライブラリ側の問題**。discovery の絞り込み条件を変更。
  - **Issue Y = LoRAIro #589 (更新済)**: 提供されなくなったモデルを LoRAIro がうまく保存・参照できていない = **LoRAIro 側の問題**。de-list/discontinued 追跡。#130 クリーンアップに留まらない**汎用的な堅牢性 Issue**として単独で価値がある。
  - **Issue Z = iam-lib #131 (新規作成済, 次段階)**: Responses エンドポイント対応 (優先度低)。
- **設計原則**: エンドポイント互換性 (軸A) と アノテーション適性 (軸B) は **別軸**。両者をコード上も分離して実装し、Issue Z で軸A の gate だけを反転できるようにする。
- **#589 (deep-research 404) の解消責務分担**: Issue X は **新規/fresh DB** (deep-research が二度と sync されない) を、Issue Y は **既存 DB** (sync 済 stale 行の de-list) をカバー。両方で完全解消。

---

## 1. 調査で確定した事実 (Evidence)

### 1.1 根本原因 (軸A: エンドポイント)
- `webapi/model_id.py:build_pydantic_model()` は OpenAI を**無条件に `OpenAIChatModel` (`v1/chat/completions`)** で構築 (model_id.py:168-173)。
- `webapi/api_model_discovery.py:_is_litellm_model_annotation_compatible()` は `mode in {"chat", "responses"}` を許可 (api_model_discovery.py:111)。
- → `mode=responses` 専用モデルは実行時に必ず 404 (`This model is only supported in v1/responses`)。
- runtime は `resolve_model_ref(litellm_model_id, config)` → `build_pydantic_model(ref, ...)` の経路で、**`mode`/endpoint 情報を一切受け取らない** (provider_manager.py:156-163)。

### 1.2 在庫 litellm DB の実測分類 (168件中)
| 区分 | mode | 件数 | 代表 |
|---|---|---|---|
| 標準 chat (適格) | chat | 大多数 | gpt-4o, gpt-5, gpt-5.1, gpt-5.5(無印), o3, o4-mini, claude-*, gemini-2.5-pro |
| **responses 専用** | responses | **23** | deep-research×4, codex(OpenAI直)×5, **pro ティア**(gpt-5-pro, gpt-5.2/5.4/5.5-pro, o1-pro, o3-pro +日付版) |
| TTS (音声出力) | chat | 1 | `gemini/gemini-2.5-pro-preview-tts` |
| computer-use (PC操作) | chat | 1 | `gemini/gemini-2.5-computer-use-preview-10-2025` |
| search 専用 (web検索強制) | chat | 6 | `gpt-4o-search-preview`系, `gpt-5-search-api`系 |
| moderation (rating用、別扱い) | moderation | 2 | `openai/omni-moderation-*` (ADR 0042、capabilities=["ratings"]) |

- **OpenRouter 経由 codex** (`openrouter/openai/gpt-5.1-codex-max`) は `mode=chat` で**実際に動作可能**。→ 名前で "codex" 一律除外は軸A的には誤り。
- litellm メタデータは TTS/computer-use/search を**クリーンに判別できない** (実証: `supports_audio_output=False` 誤報、`supports_web_search=True` は gpt-5 等 60件の優良モデルも持つため判定軸に使えない)。→ 軸B は curated denylist に頼らざるを得ない。

### 1.3 OpenAI 上流 / プロジェクト現状の整合 (軸Aの戦略的背景)
- OpenAI は Responses API を主軸化、Chat Completions はレガシー互換維持。pro/専用ティアは Responses 専用で Chat には載らない。
- プロジェクトは意図的に Chat Completions 一本化: ADR 0023 (同期) / ADR 0038 line 511,514 (batch も `/v1/chat/completions` 選択) / plan_525 line 45 (PydanticAI 2.0 beta の Responses 強制切替は**不採用**、`griffe<2` pin)。
- iam-lib に `OpenAIResponsesModel` 経路は**未実装** (grep 確認済)。pydantic_ai 1.100.0 に `OpenAIResponsesModel` クラスは**存在**する。
- → 現アーキテクチャでは responses 専用モデルの除外は **"用途不適" ではなく "Chat runtime が実行不能"** という endpoint 理由。サブ#2 完了でこの gate は反転すべき対象。

### 1.4 消費側 (LoRAIro) の de-list 欠落 (サブ#1 が iam-lib だけで完結しない根拠)
- `Model.available` プロパティ = `discontinued_at is None` (schema.py:148-150)。
- `ModelSyncService.sync_available_models()` は **register_new + update_existing のみ。de-list (削除/無効化) ステップが無い** (model_sync_service.py:258-290)。
- → iam-lib が deep-research を discovery から外しても、**既に DB 登録済みの行は `discontinued_at=NULL` のまま `available=True`** で UI に残存・選択可能。これがログで `o4-mini-deep-research` が選択・送信できた事象の consumer 側原因。
- 同期は `litellm_model_id` を key とする (ADR 0023 Phase 1.11 / #238)。

---

## 2. 軸の分解 (設計の骨格)

| 軸 | 関心事 | サブ#1 で対応 | サブ#2 で対応 |
|---|---|---|---|
| **A: エンドポイント** | Chat runtime が実行可能か | responses を **endpoint-gate で除外** (mode=chat のみ許可)。"Responses 待ち" として位置づけ | `OpenAIResponsesModel` 対応で gate 反転、pro ティア復活 |
| **B: アノテーション適性** | 用途が画像 annotation に合うか | TTS/computer-use/search/deep-research を **suitability denylist で除外** | 変更なし (denylist は維持) |
| **C: 消費側 de-list** | 旧 sync 済モデルを DB から消すか | `ModelSyncService` に **reconcile/de-list** 追加 | 変更なし |

実装上の制約: **軸A の gate と軸B の denylist をコード上分離する** (別関数 / 別定数)。サブ#2 では軸A の gate だけを反転し、軸B の denylist (deep-research 等) は残す。

---

## 3. サブ#1 — モデル絞り込み条件の変更 (優先)

### 3.1 サブ#1A (= iam-lib #130): discovery 変更 【方針 user 確定済】
**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/api_model_discovery.py`

設計原則: **#45 / ADR 0023 で確定済の「tool/function calling を絞り込み主条件にする」を踏襲し、litellm `supports_function_calling` boolean が `supported_openai_params` と矛盾する不正確さを是正する。** 新機構の追加ではなく既存条件の精度向上。

1. **軸A endpoint-gate**: `_SUPPORTED_LITELLM_MODES = frozenset({"chat"})` (← `responses` 削除)。
   - docstring を「Chat Completions runtime が実行可能な mode」に更新。`responses` は #131 (Responses runtime) 待ちである旨コメント + link。
   - 効果: responses 23件除外 (deep-research / codex-direct / pro ティア)。
2. **軸B tool 対応の正確化** (`_is_litellm_model_annotation_compatible` を改修):
   ```python
   mode == "chat"
   and info.get("supports_vision") is True
   and info.get("supports_function_calling") is True
   and (
       not info.get("supported_openai_params")          # 未populate (Gemini/Anthropic等) は boolean 信頼
       or "tools" in info["supported_openai_params"]     # populate時 (OpenAI) は tools 実在を要求
   )
   ```
   - `gpt-5-search-api` 族は `supported_openai_params` に `tools` 無し → **名前非依存で metadata 駆動除外**(将来の search-api も自動)。
   - 「未populate なら boolean 信頼」ガードで Gemini/Anthropic を巻き込まない。
3. **軸B 残余 name denylist** (metadata が嘘 or 未populate のみ、endpoint-gate とは独立した定数/関数):
   ```python
   _ANNOTATION_UNSUITABLE_SUBSTR = (
       "-tts",            # 音声出力 (Gemini, params 未populate)
       "computer-use",    # PC操作特化 (params 未populate)
       "-search-preview", # tools を申告するが web検索強制 (gpt-4o-search-preview)
       "deep-research",   # data-source tool 前提。#131 で gate 反転後も除外維持 (forward-compat)
   )
   ```
   - `-search-api` は手順2の metadata 条件で除外済のため denylist 不要。
   - **codex は denylist に入れない (確定)**: OpenAI直 codex は軸A gate で除外、OpenRouter chat codex (`openrouter/openai/gpt-5.1-codex-max`) は動作可能なため残す。
4. moderation モデルは現状維持 (ADR 0042、capabilities=["ratings"]、別経路)。
5. **実装分離**: 軸A gate と軸B (tool 条件 + denylist) を別関数/別定数に分離 → #131 で軸A gate のみ反転、軸B denylist は維持。
6. **ADR**: 判定根拠を ADR 0023 改訂 or 新規 ADR に記録。denylist は test fixture 固定 + 月次 dependency review で drift 確認。

**テスト**: `tests/unit/webapi/test_api_model_discovery.py` (既存に追記 or 新規)
- 除外 assert: `o3-deep-research*`, `o4-mini-deep-research*`, `gpt-5-pro`, `o3-pro`, `*-tts`, `computer-use*`, `*-search-preview*`, `*-search-api*` が discovery 結果に**出ない**。
- 回帰ガード assert: `gpt-4o`, `gpt-5`, `gpt-5.5`, `claude-sonnet-4-5`, `gemini-2.5-pro` が**残る** (過剰除外していない)。
- `mode=responses` 全件除外を fixture で固定。
- litellm は `LITELLM_LOCAL_MODEL_COST_MAP=True` で同梱 DB のみ参照 (network 不要)。

### 3.2 サブ#1B: LoRAIro ModelSyncService de-list (reconcile)
**ファイル**: `src/lorairo/services/model_sync_service.py`, `src/lorairo/database/repository/model.py`

1. `sync_available_models()` に **第4ステップ「reconcile/de-list」** を追加:
   - 現在の lib discovery set (litellm_model_id) を取得。
   - DB の **API モデル** (requires_api_key=True かつ litellm_model_id 保有、ローカル ML / 合成 moderation は除外) のうち、discovery set に**無い**行に `discontinued_at = now()` を設定 (soft-delete)。
   - 再出現時は `discontinued_at = NULL` に戻す (update_existing 経路で復活)。
2. `ModelSyncResult` に `delisted_count` を追加、summary に反映。
3. Repository に de-list 用メソッド (例: `mark_discontinued(litellm_model_ids: set[str])` / 再活性化) を追加。

**テスト**:
- unit: DB に存在し lib discovery に無い API モデル → `discontinued_at` 設定 → `available==False`。
- unit: ローカル ML / moderation 合成モデルは de-list 対象外。
- regression: `openai/o4-mini-deep-research-2025-06-26` が sync 後 `available==False` (#589 再現防止)。
- BDD (任意): 「discovery から外れたモデルは選択候補に出ない」シナリオ。

### 3.3 統合
1. サブ#1A を iam-lib branch で実装・PR・merge。
2. LoRAIro 側 submodule pin を A の commit に bump (`local_packages/image-annotator-lib`)。
3. サブ#1B を同 PR or 後続 PR で実装。
4. **CI-equivalent filter** 実行 (submodule pin 変更を含むため Hook gate 対象):
   - iam-lib: `-m "not downloads_and_runs_model and not calls_real_webapi"`
   - LoRAIro: `-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`
5. 検証: アプリ起動 → discovery 168→~131件、UI に deep-research/tts/computer-use/search が出ない、既存 DB の stale 行が de-list される。

### 3.4 サブ#1 受け入れ条件
- [ ] discovery が OpenAI `mode=responses` を候補に含めない (unit test)。
- [ ] `o3-deep-research*` / `o4-mini-deep-research*` が候補に出ない (unit test)。
- [ ] tts / computer-use / search-preview / search-api が候補に出ない (unit test)。
- [ ] 標準モデル (gpt-4o, gpt-5, claude, gemini-2.5-pro) は残る (回帰 test)。
- [ ] 軸A gate と軸B denylist がコード上分離されている (サブ#2 で gate 反転可能)。
- [ ] LoRAIro: discovery から消えた API モデルが DB で `available==False` になる (de-list test)。
- [ ] `o4-mini-deep-research` が LoRAIro UI 選択候補に出ない (#589 regression)。
- [ ] CI-equivalent filter 全 pass。

---

## 4. サブ#2 — Responses エンドポイント対応 (次段階、別Issue)

> 優先度低。サブ#1 完了後に別 Issue / 別 ADR で着手。OpenAI の Responses 主軸化に追従し pro ティア (gpt-5-pro, o3-pro 等) を実行可能にする。

**概要 (詳細はサブ#2 起票時に planning)**:
- `model_id.py`: OpenAI `mode=responses` を `OpenAIResponsesModel` で構築する分岐を追加。`mode`/endpoint を discovery metadata → registry → `resolve_model_ref`/`build_pydantic_model` に配線 (現状 mode 非伝播)。
- `api_model_discovery.py`: 軸A endpoint-gate を反転し responses を再許可 (軸B denylist の deep-research 等は除外維持)。
- ADR 0023 改訂: Chat Completions 一本化 → Chat + Responses dual-endpoint。plan_525 の PydanticAI 2.0 不採用判断との整合を再評価。
- refusal: ADR 0006 (iam-lib) が Responses refusal contract を既にカバー。
- 構造化出力: Chat と Responses で tool schema / response shape 差異 (plan_518 で指摘済) を fixture 化。deep-research は data-source tool 配線が別途必要なため軸B で除外継続。
- 検証: ADR 0026 On-Demand Runtime Validation に従い実 API smoke。

---

## 5. Agent Teams 実行体制 (サブ#1)

> memory: Agent worktree isolation は壊れている → **手動 worktree + 共有 venv** で並列ディスパッチ。`UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` 明示。並列 `uv sync` 禁止 (Issue #222)。

| Track | 担当 | worktree | 担当ファイル (競合回避) |
|---|---|---|---|
| **A: iam-lib discovery** | discovery filter + unit test | `/tmp/worktrees/iam-130-discovery` (iam-lib branch) | `webapi/api_model_discovery.py`, `tests/unit/webapi/test_api_model_discovery.py` |
| **B: LoRAIro de-list** | ModelSyncService reconcile + test | `/tmp/worktrees/lorairo-130-delist` (LoRAIro branch) | `services/model_sync_service.py`, `database/repository/model.py`, 対応 test |
| **統合 (本体)** | submodule pin bump, CI-equiv, 起動検証 | 共有 checkout | `local_packages/image-annotator-lib` pin, `uv.lock` |

- A と B は別 repo / 別ファイル → 独立並列可能。
- B の end-to-end 検証は A の pin 後に実施 (依存は統合フェーズで吸収)。
- 各 Track の調査は並列で先行可、実装後に統合フェーズで直列化。

---

## 6. リスクと対策
| リスク | 対策 |
|---|---|
| litellm DB 月次更新で denylist が drift (新 tts/search モデル追加) | denylist を test fixture で固定、月次 dependency review で確認 (dependency-management.md) |
| codex 除外可否の判断ミス | サブ#1 では endpoint-gate のみで自然除外 (OpenRouter codex は残す)、サブ#2 で再検討 |
| de-list が local ML / moderation を誤って無効化 | de-list 対象を「API モデル かつ litellm_model_id 保有 かつ discovery 所有」に限定、合成 moderation を除外 test |
| 過剰除外で優良モデルが消える | 回帰 test で標準モデル残存を assert |
| submodule pin 変更で CI 漏れ | CI-equivalent filter を PR 前に必須実行 (Hook gate) |

## 7. Related
- iam-lib #130 (親), LoRAIro #589 (連動)
- ADR 0023 (PydanticAI/LiteLLM WebAPI Inference Boundary) — サブ#2 で改訂対象
- ADR 0038 (Provider Batch API Integration Strategy) — Chat Completions 統一の根拠
- ADR 0042 (OpenAI Moderation WebAPI Preflight) — moderation モデル別扱い
- plan_525 (CLI dependency drift) — PydanticAI 2.0 Responses 強制切替 不採用の記録
- plan_518 (OpenAI annotation batch) — Chat vs Responses endpoint 選択経緯
