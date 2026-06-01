# Plan: Responses API runtime 対応 (iam-lib #131)

- **親 Issue**: [image-annotator-lib#131](https://github.com/NEXTAltair/image-annotator-lib/issues/131) — Responses API runtime 対応: pro/専用ティア (gpt-5-pro, o3-pro 等) を実行可能にする
- **前段**: [iam-lib#130](https://github.com/NEXTAltair/image-annotator-lib/issues/130) (merged, PR #132) — discovery endpoint-gate を `chat` のみに絞った sub#1。本計画は plan_130 の sub#2。
- **連動**: [LoRAIro#589](https://github.com/NEXTAltair/LoRAIro/issues/589) — de-list (ModelSyncService reconcile で吸収済)
- **作成日**: 2026-06-01

## Context

OpenAI は Responses API を主軸化し、pro ティア (`gpt-5-pro`, `o3-pro`, `o1-pro`, `gpt-5.x-pro`)
は **Responses 専用** (`mode=responses`) で、Chat Completions には載らない。iam-lib の WebAPI runtime は
`webapi/model_id.py:build_pydantic_model()` が OpenAI を**無条件に `OpenAIChatModel` (`v1/chat/completions`)**
で構築するため、`mode=responses` モデルは実行時に必ず 404 になる。#130 では暫定対応として discovery の
endpoint-gate を `chat` のみに絞り responses 系を候補から除外した。本 Issue は **gate を反転し
`OpenAIResponsesModel` 経路を実装** して pro ティアを実行可能にする。

設計の核 (plan_130 で確定済): **エンドポイント互換性 (軸A)** と **アノテーション適性 (軸B)** を
コード上分離する。#131 では軸A gate のみ反転し、軸B denylist (deep-research / codex) は維持/拡張する。

### 確定した方針 (planning セッションで user 確認済)
- **codex は一律除外**: openai-direct responses codex 8件 + 現在 chat で有効な `openrouter/openai/gpt-5.1-codex-max`
  も denylist substring `codex` で除外する (plan_130 の「openrouter codex は残す」を上書き、ADR に記録)。
- **ADR**: LoRAIro ADR 0023 を改訂 + iam-lib に新規 ADR 0007 を作成。
- **smoke**: 実 API smoke 手順を計画に含める (実行は実装後に user 判断、ADR 0026)。

### gate 反転で復活/除外される openai モデル (litellm 同梱 DB 実測, 2026-06-01)
- **復活 (pro ティア, 11件)**: `openai/gpt-5-pro`(+dated), `gpt-5.2-pro`(+dated), `gpt-5.4-pro`(+dated),
  `gpt-5.5-pro`(+dated), `o1-pro`(+dated), `o3-pro`(+dated)。全て vision=True / function_calling=True。
- **除外維持 (deep-research, 4件)**: `openai/o3-deep-research*`, `openai/o4-mini-deep-research*`。
- **新規除外 (codex)**: `openai/gpt-5*-codex*`, `openai/codex-mini-latest`, `openrouter/openai/gpt-5.1-codex-max`。

---

## 実装 (iam-lib: `local_packages/image-annotator-lib`)

すべて iam-lib 単一 repo の変更。worktree: `/tmp/worktrees/iam-131-responses` (iam-lib branch
`feat/issue-131-responses-endpoint`)。mode threading は 1 本の連鎖変更なので並列化せず逐次実装。

### 1. 軸A gate 反転 + 軸B codex 追加 — `webapi/api_model_discovery.py`
- `_SUPPORTED_LITELLM_MODES = frozenset({"chat", "responses"})` (← `responses` を再追加)。
  docstring/コメントを「#131 で gate 反転、`OpenAIResponsesModel` で responses を実行可能」に更新。
- `_ANNOTATION_UNSUITABLE_SUBSTR` に `"codex"` を追加 (deep-research は維持):
  ```python
  _ANNOTATION_UNSUITABLE_SUBSTR = ("-tts", "computer-use", "-search-preview", "deep-research", "codex")
  ```
  コメントで「codex はコーディング特化で annotation 不適、provider/endpoint 問わず一律除外」と明記。

### 2. endpoint 情報を mode から導出 — `webapi/model_id.py`
- `PydanticAIModelRef` に `endpoint: str = "chat"` フィールド追加 (値: `"chat"` | `"responses"`)。
- `resolve_model_ref(litellm_model_id, config=None, *, mode: str = "chat")`: 既存 dispatch で ref 構築後、
  `provider == "openai" and mode == "responses"` の場合のみ `dataclasses.replace(ref, endpoint="responses")`。
  anthropic/google/openrouter は常に `chat` (builder 群は無変更)。
- `build_pydantic_model()` の `openai` 分岐: `ref.endpoint == "responses"` なら `OpenAIResponsesModel`、
  それ以外は従来どおり `OpenAIChatModel`。provider object (`OpenAIProvider(api_key=..., http_client=...)`) は共通。
  import は分岐内 lazy (`from pydantic_ai.models.openai import OpenAIResponsesModel`)。
  - 検証済: pydantic_ai 1.100.0 に `OpenAIResponsesModel(model_name, *, provider=...)` が存在し、
    `OpenAIProvider` (= `Provider[AsyncOpenAI]`) を受け付ける。Agent / output_type(callable) / BinaryContent は同一抽象で動作。

### 3. mode を推論経路に配線 (現状 mode 非伝播の解消)
mode は既に `registry._WEBAPI_MODEL_METADATA[model_name_short]["mode"]` に格納済 (registry.py:756)。
これを annotator → provider_manager → resolve_model_ref へ通す。
- `core/annotation_runner.py:_create_annotator_instance()`: registry の既存 getter
  `get_webapi_model_metadata(actual_model_name)` から `mode` を取得し、`WebApiAnnotator(..., mode=mode)` に渡す
  (litellm_model_id を引く `_resolve_litellm_model_id` の隣)。
- `webapi/annotator.py:WebApiAnnotator.__init__`: 引数 `mode: str = "chat"` を追加し `self.mode` に保持。
  `_run_inference()` の `ProviderManager.run_inference_with_model(...)` 呼び出しに `mode=self.mode` を追加。
- `webapi/provider_manager.py`: `run_inference_with_model_async()` と sync wrapper `run_inference_with_model()`
  に `mode: str = "chat"` を追加し、`resolve_model_ref(litellm_model_id, config, mode=mode)` へ渡す。
  moderation 早期 return 経路 (`_run_openai_moderation_inference`) は chat のまま (mode 不要)。

### 4. refusal / 構造化出力
- refusal: ADR 0006 (iam-lib) の refusal contract は body 再帰 walk + type 名 + regex で provider 横断。
  Responses API の refusal も `exc.body` の `finish_reason`/`refusal` を拾うため既存経路で吸収。**コード変更なし**
  (smoke で確認、リスク欄参照)。
- 構造化出力: Agent.output_type は callable (Tool Output)。Responses API でも tool calling 経路は同一。
  Chat と response shape 差異 (plan_518 指摘) は pydantic_ai が吸収する想定だが smoke で確認。

---

## テスト (iam-lib, package-local pytest セッション)

- `tests/unit/core/test_model_id.py` に追記:
  - `resolve_model_ref("openai/gpt-5-pro", mode="responses").endpoint == "responses"`。
  - default mode / `mode="chat"` → `endpoint == "chat"`。
  - 非 openai + `mode="responses"` (例 anthropic) → `endpoint == "chat"` (responses は openai 限定)。
  - `build_pydantic_model(ref(endpoint="responses"), "k")` が `OpenAIResponsesModel`、chat が `OpenAIChatModel`
    の instance を返す (network 不要、provider 構築のみ)。
- `tests/unit/core/test_api_model_discovery_filter.py` に追記/更新:
  - `mode=responses` + vision + fc が compatible になる (gate 反転)。
  - discovery 結果に **含む**: `openai/gpt-5-pro`, `openai/o3-pro`, `openai/o1-pro`, `openai/gpt-5.5-pro`。
  - discovery 結果に **含まない**: `openai/o3-deep-research*`, `openai/o4-mini-deep-research*`,
    `*codex*` 全般 (`openai/gpt-5-codex`, `openai/codex-mini-latest`, `openrouter/openai/gpt-5.1-codex-max`)。
  - 回帰ガード: `openai/gpt-4o`, `openai/gpt-5`, `anthropic/...`, `google/gemini-2.5-pro` が残る。
  - litellm は `LITELLM_LOCAL_MODEL_COST_MAP=True` で同梱 DB のみ (network 不要)。
- mode 配線の薄い test: `WebApiAnnotator(litellm_model_id="openai/gpt-5-pro", mode="responses")` →
  `ProviderManager.run_inference_with_model` を monkeypatch して `mode` が伝わることを assert。
  `annotation_runner._create_annotator_instance` が responses モデルで `mode="responses"` を注入することを assert。

---

## ADR / ドキュメント更新 (user 指摘)

- **LoRAIro `docs/decisions/0023-...md` 改訂**: 「Chat Completions 一本化」→「Chat + Responses dual-endpoint」。
  Decision/Consequences に: (a) openai `mode=responses` は `OpenAIResponsesModel` で構築、(b) endpoint は
  litellm `mode` 由来で per-model 選択、(c) **batch は chat 専用のまま (ADR 0038 不変)**、(d) codex/deep-research は
  軸B denylist で除外、(e) plan_525 の「PydanticAI 2.0 forced-responses 不採用」との整合 (こちらは per-model
  endpoint 選択であり全 chat 強制切替とは別) を明記。Related に #131 追加。
- **iam-lib `docs/decisions/0007-webapi-dual-endpoint-runtime.md` 新規**: runtime 構築 contract
  (mode threading 経路、`OpenAIResponsesModel` 分岐、軸A/軸B 分離、codex 一律除外の根拠) を記録。
  `docs/decisions/README.md` の表に 1 行追加。
- (任意) iam-lib `CLAUDE.md` の discovery/責務コメントに responses endpoint 対応を 1 行追記。

---

## 統合 (LoRAIro 本体)

1. iam-lib branch を PR・merge。
2. LoRAIro 側 submodule pin (`local_packages/image-annotator-lib`) を当該 commit に bump + `uv.lock` 更新
   (ADR 0025 / dependency-management.md、pin 変更 PR は両 lockfile)。
3. LoRAIro コード変更は**不要**: #130 sub#1B の `ModelSyncService` reconcile/de-list が discovery 増減を吸収し、
   pro ティアは次回 sync で自動登録 (過去 de-list 済なら `discontinued_at=NULL` 復活)。
4. CI-equivalent filter を PR 前に両側実行 (submodule pin 変更 → Hook gate 対象)。

---

## Agent Teams 実行体制

> memory: Agent tool の `isolation="worktree"` はこの repo で壊れている → **手動 worktree + 共有 venv**
> で並列ディスパッチ。worktree 内 `uv` は `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` 明示。
> 並列 `uv sync` 禁止 (Issue #222)。推奨チームサイズ 3〜4。

mode threading (Track B) は 1 本の連鎖なので 1 人が所有して分割しない。Track A/B/C は
互いに独立 (disjoint ファイル / 別ドキュメント) なので並列可。統合は A+B 完了後に直列化。

| Track | 担当 | 担当ファイル (競合回避) | 依存 |
|---|---|---|---|
| **A: discovery** | gate 反転 + codex denylist + 回帰 test | `webapi/api_model_discovery.py`, `tests/unit/core/test_api_model_discovery_filter.py` | なし (並列開始可) |
| **B: runtime 配線** | endpoint 導出 + mode threading + test | `webapi/model_id.py`, `webapi/provider_manager.py`, `webapi/annotator.py`, `core/annotation_runner.py`, `tests/unit/core/test_model_id.py` + mode 配線 test | なし (unit は `mode=` 明示で discovery 非依存、並列開始可) |
| **C: ADR/docs** | LoRAIro 0023 改訂 + iam-lib 0007 新規 + README | LoRAIro `docs/decisions/0023-*.md`; iam-lib `docs/decisions/0007-*.md` + `docs/decisions/README.md` | 本計画を spec に並列可 |
| **統合 (lead)** | A+B を iam-lib branch に集約 → CI-equiv → PR/merge → LoRAIro submodule pin bump + `uv.lock` → discovery/CI-equiv 検証 → smoke 調整 | iam-lib branch, LoRAIro `local_packages/image-annotator-lib` pin, `uv.lock` | A, B 完了後 |

- worktree 運用: iam-lib branch `feat/issue-131-responses-endpoint` の単一 worktree
  `/tmp/worktrees/iam-131-responses` を A/B で共有し、**disjoint ファイル所有**で競合回避 (同一 branch を
  複数 worktree に同時 checkout できないため)。commit は lead が track 単位で逐次。
  Track C の LoRAIro ADR は本体 checkout (`/workspaces/LoRAIro`) または別 worktree で編集。
- A/B/C 並列ディスパッチ → 全完了後に lead が統合フェーズを直列実行。
- 小〜中規模のため単独逐次実装でも可。並列化する場合のみ上記体制を採る。

---

## 検証

```bash
# iam-lib unit + CI-equivalent filter (package root)
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
uv run pytest -m "not downloads_and_runs_model and not calls_real_webapi"

# discovery 反映確認 (pro ティア出現 / codex・deep-research 不在)
cd /workspaces/LoRAIro && LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONPATH=local_packages/image-annotator-lib/src \
  python -c "from image_annotator_lib.webapi.api_model_discovery import get_available_models; \
  m=get_available_models(); print('gpt-5-pro' , 'openai/gpt-5-pro' in m); \
  print('o3-pro', 'openai/o3-pro' in m); print('deep-research', any('deep-research' in x for x in m)); \
  print('codex', any('codex' in x for x in m))"

# LoRAIro 本体 CI-equivalent filter
cd /workspaces/LoRAIro
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"
```

期待: `gpt-5-pro True / o3-pro True / deep-research False / codex False`。

### 手動 smoke (ADR 0026, 実行は user 判断・API 課金発生)
- `tools/webapi_annotate.py` 等で `openai/gpt-5-pro` または `openai/o3-pro` に画像1枚を annotation 実行。
- 確認: 404 が出ず `OpenAIResponsesModel` 経路で tags/captions/scores が返る (構造化出力 = Tool Output 成立)。
- refusal 系画像で `SafetyRefusalError`/`ContentPolicyRefusalError` の error 文字列が従来同様に伝搬するか確認。

---

## リスクと対策
| リスク | 対策 |
|---|---|
| Responses API で Tool Output (output_type callable) / BinaryContent 画像が pydantic_ai で正しく動かない | 同一 Agent 抽象だが未実証。手動 smoke で確認。差異があれば `model_id.py` 構築時に `OpenAIResponsesModelSettings` を補う |
| refusal contract が Responses の response shape で機能しない | `_classify_refusal` は body 再帰 walk で provider 横断。smoke で実画像確認、必要なら body 抽出を補強 |
| codex 一律除外で plan_130 の openrouter codex 判断を上書き | ADR 0007 / 0023 に経緯を記録、discovery test で `openrouter/openai/gpt-5.1-codex-max` 不在を固定 |
| litellm DB 月次更新で pro/codex/deep-research の mode が drift | discovery test を fixture 固定、月次 dependency review で確認 |
| submodule pin 変更で CI 漏れ | CI-equivalent filter を PR 前必須 (Hook gate) |

## Related
- iam-lib #131 (本体), #130 (前段, merged PR #132), LoRAIro #589 (de-list 連動)
- LoRAIro ADR 0023 (改訂対象), ADR 0038 (batch chat 維持), ADR 0026 (smoke), ADR 0025 (lockfile)
- iam-lib ADR 0006 (refusal contract), 新規 ADR 0007
- plan_130 (sub#2 として本計画に接続), plan_518 (Chat vs Responses shape), plan_525 (PydanticAI 2.0 不採用)
