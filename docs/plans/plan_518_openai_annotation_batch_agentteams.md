# Plan: Issue #518 — OpenAI Batch API for standard annotation (Agent Teams 並列)

- **対象**: NEXTAltair/LoRAIro#518 (OpenAI Batch API for standard annotation via `/v1/responses` or `/v1/chat/completions`)
- **策定日**: 2026-05-27
- **前提**: Moderations Batch (#507 / #122 / #509 / #510 / #511 / #515 / #123) は merged 済み。本 Issue は ADR 0038 Phase 1 OpenAI MVP の "annotation 用 `/v1/responses` JSONL 生成" (Implementation 草案 §3) を実装する。
- **スコープ**: OpenAI 通常 annotation (gpt-4o-mini 等) を Batch API 経由で実行できるようにする。Anthropic / Google Batch は本 Issue 対象外 (ADR 0038 Phase 2/3 で別タスク)。

## 1. ultrathink 設計プロセス

### 1.1 現状認識

`/v1/moderations` Batch 経路 (Issue #507) が稼働済み。通常 annotation は同期 `annotate()` のみで、Batch は未対応。

| レイヤー | 現状 |
|---|---|
| iam-lib `webapi/batch/preparation.py` | `build_openai_moderations_jsonl` のみ。annotation 用 JSONL builder なし |
| iam-lib `webapi/batch/adapters/openai.py` | `_SUPPORTED_ENDPOINTS = frozenset({"/v1/moderations", ...})` で制限。`_SUPPORTED_CAPABILITIES = frozenset({TaskCapability.RATINGS})` で rating のみ |
| iam-lib `core/types.py:AnnotationSchema` | Pydantic BaseModel (tags / captions / score / ratings) は既に SSoT として完成 |
| iam-lib `webapi/output_normalization.py` | 同期で PydanticAI tool として publish される callable + `_build_normalizer_signature` で capability-based required/optional 判定済み |
| iam-lib `webapi/provider_manager.py` | refusal exception 階層 (`SafetyRefusalError` / `ContentPolicyRefusalError`)、`_classify_refusal()` で `finish_reason=safety` / `stop_reason=refusal` 等を regex 検出 |
| LoRAIro `provider_batch_workflow_service` | `task_type="annotation"` は **default 値、既に routing 済み** (#509)。本 Issue で LoRAIro 側コアロジック変更は不要 |
| LoRAIro CLI `batch.py` | `_TASK_TYPE_ENDPOINTS` の `"annotation"` キーに OpenAI endpoint を追加するのみ |

### 1.2 設計境界

ADR 0023 / 0038 と整合させる:

- **PydanticAI は Batch では使わない** (ADR 0038 §8): Batch は submit/poll/fetch lifecycle で PydanticAI の sync agent execution 抽象とは責務が違う
- **Schema SSoT は Pydantic `AnnotationSchema`**: 同期は PydanticAI runtime が tool 化 / Batch は `model_json_schema()` 直で OpenAI function schema 生成
- **converter / normalizer は両経路で共有**: `webapi/output_normalization.py:normalize_annotation_output` を Batch result parse 後にも適用 (validation 前の drift 補正)
- **LoRAIro 側は `UnifiedAnnotationResult` contract 経由で透過**: Batch で構築した `UnifiedAnnotationResult` がそのまま既存 annotation save path に流れる

## 2. 解決策ソリューション比較

### 2.1 Endpoint 選択

| 案 | 内容 | 評価 |
|---|---|---|
| **A. `/v1/responses` (推奨)** | OpenAI 新 API、structured output / multimodal を native サポート。ADR 0038 §3 MVP で計画済み | ✅ ADR 0038 計画一致、LiteLLM Batch pricing fields も対応、structured output が綺麗 |
| B. `/v1/chat/completions` | Legacy API、PydanticAI native 経路と一致 | △ legacy、`tools` field 構造は同等だが image input 形式が古い |
| C. 両方サポート | ユーザーが選択 | ❌ 実装コスト倍、MVP に不要 |

**選択: A (`/v1/responses`)** — ADR 0038 計画と一致し、新 API のほうが image input + structured output の組み合わせが綺麗。

### 2.2 Schema 経路

| 案 | 内容 | 評価 |
|---|---|---|
| **A. `AnnotationSchema.model_json_schema()` 直 (推奨)** | Pydantic だけで OpenAI function tool schema を生成 | ✅ 同期/Batch で同じ schema、DRY |
| B. PydanticAI で agent を組んで tool schema を抽出 | 同期経路の Agent 構築を流用 | ❌ agent runtime を Batch で使わない原則違反 |
| C. 手書きで OpenAI function schema を書く | Pydantic を使わない | ❌ AnnotationSchema 変更時に drift |

**選択: A** — Pydantic schema を SSoT、`model_json_schema()` で直接生成。

### 2.3 Capability 範囲

| 案 | 内容 | 評価 |
|---|---|---|
| **A. `{TAGS, CAPTIONS, SCORES}` 対象 (推奨)** | Moderations 経路で `RATINGS` をカバー済み、本 Issue は通常 annotation focus | ✅ scope 明確、`_build_normalizer_signature` の capability-based required を流用 |
| B. `{TAGS, CAPTIONS, SCORES, RATINGS}` 全部 | rating も含めた汎用 | ❌ Moderations 経路と重複、test 範囲膨らむ |
| C. `{TAGS}` のみ MVP | tagger 用途のみ先行 | ❌ caption / score も同じ schema で動くため絞る理由なし |

**選択: A** — `{TAGS, CAPTIONS, SCORES}`。`RATINGS` は Moderations 経路でカバー、混在は別 Issue。

### 2.4 Refusal handling

| 案 | 内容 | 評価 |
|---|---|---|
| **A. Batch result 内 `finish_reason` を post-fetch 検出 (推奨)** | 既存 `provider_manager._classify_refusal()` の regex pattern を Batch result 用に reuse | ✅ 既存 lessons (Issue #42) と整合、両経路で同じ refusal 検出 logic |
| B. Batch では refusal を扱わない | LoRAIro 側 `error_records` に「Batch 由来 unknown error」として保存 | ❌ 同期との一貫性なし、後続 `filter_refused_image_paths` が効かない |
| C. 同期側の exception 階層をそのまま使う | `_classify_refusal()` を呼んで例外を raise → adapter で catch | △ adapter 内で exception flow が複雑、retryable 判定の整合性が崩れる |

**選択: A** — `_classify_refusal()` の regex pattern を helper 化し、Batch result parse でも使う。失敗 item には `BatchItemError(code="provider_safety_refusal", ...)` を設定。

## 3. アーキテクチャ設計

```
[T1: iam-lib JSONL builder]
webapi/batch/preparation.py
  + build_openai_responses_jsonl(items, *, endpoint, litellm_model_id, capabilities, prompt_profile)
  - AnnotationSchema.model_json_schema() で OpenAI function tool schema 生成
  - capability に応じた required filter を _build_normalizer_signature 経由 or 同等ロジックで再現
  - JSONL に { custom_id, method, url, body: { model, input: [{image_url}], tools: [{function: {parameters: <schema>}}], tool_choice: required } }

[T2: iam-lib adapter endpoint 拡張]
webapi/batch/adapters/openai.py
  - _SUPPORTED_ENDPOINTS に "/v1/responses" を追加
  - submit_batch: endpoint = "/v1/responses" 時に build_openai_responses_jsonl を呼ぶ
  - _normalize_result_item: endpoint 別に dispatch (moderations / responses)
  - _parse_responses_output: tool_calls[0].function.arguments → JSON parse →
    normalize_annotation_output(**args) → AnnotationSchema → _to_unified()
  - refusal detection helper を provider_manager 側から共通化 (_classify_refusal_from_response)

[T3: LoRAIro deterministic E2E]
tests/integration/test_provider_batch_annotation_e2e.py
  - fake adapter で 3 image submit → tags/captions/scores が DB に保存される flow
  - 1 image を refusal response にして error_records に保存される flow
  - filter_refused_image_paths が後続 annotation worker で除外することを確認

[T4: iam-lib runtime smoke + docs]
local_packages/image-annotator-lib/tests/runtime_validation/test_openai_responses_batch_runtime.py
  - submit + retrieve + cancel lifecycle (実 API、calls_real_webapi marker)
docs/decisions/0038-provider-batch-api-integration-strategy.md
  - Implementation Status: "annotation 用 /v1/responses MVP merged" を追記
docs/lessons-learned.md
  - Batch 側 schema 生成は Pydantic で完結、PydanticAI は Batch ライフサイクル外
```

各タスクは独立 worktree (`/tmp/worktrees/issue-518-*`) で実行、共有 venv (`UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv`) を利用 (ADR 0024 / parallel-execution.md)。

## 4. 実装計画 (T1-T4 並列分担)

### Agent Teams roster

- **karo (家老)**: 全体統合 / final report / submodule pin 更新 / Issue #518 close 判断
- **ashigaru1**: T1 担当 (iam-lib JSONL builder)
- **ashigaru2**: T2 担当 (iam-lib adapter 拡張)
- **ashigaru3**: T3 担当 (LoRAIro deterministic E2E)
- **ashigaru4**: T4 担当 (iam-lib runtime smoke + docs)
- **gunshi (軍師)**: 各 T の QC レビュー (PR merge 前)

### T1: iam-lib `build_openai_responses_jsonl` + AnnotationSchema tool embedding

**Worktree**: `/tmp/worktrees/issue-518-t1-jsonl-builder` (iam-lib repo)
**Branch**: `feat/issue-518-t1-responses-jsonl-builder`
**Files**:
- `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/batch/preparation.py` (append new function)
- `local_packages/image-annotator-lib/tests/unit/webapi/batch/test_preparation_responses.py` (新規)

**実装内容**:
```python
# preparation.py に追加
from image_annotator_lib.core.types import AnnotationSchema, TaskCapability
from image_annotator_lib.webapi.output_normalization import _build_normalizer_signature

_DEFAULT_RESPONSES_CAPABILITIES = frozenset({
    TaskCapability.TAGS,
    TaskCapability.CAPTIONS,
    TaskCapability.SCORES,
})

def build_openai_responses_jsonl(
    items: list[PreparedBatchItem],
    *,
    endpoint: str,
    litellm_model_id: str,
    capabilities: frozenset[TaskCapability] = _DEFAULT_RESPONSES_CAPABILITIES,
    prompt_profile: str = "default",
) -> str:
    """Build OpenAI batch input JSONL for /v1/responses with structured output tool."""
    schema = AnnotationSchema.model_json_schema()
    # capability に応じて required fields を filter
    schema = _filter_schema_required(schema, capabilities)
    tool = {
        "type": "function",
        "function": {
            "name": "normalize_annotation_output",
            "description": "Provide image annotation results.",
            "parameters": schema,
            "strict": True,
        },
    }
    system_prompt = _build_system_prompt(capabilities)  # 同期側 helper を再利用
    lines: list[str] = []
    for item in items:
        encoded = base64.b64encode(item.image_path.read_bytes()).decode("ascii")
        lines.append(json.dumps({
            "custom_id": item.custom_id,
            "method": "POST",
            "url": endpoint,
            "body": {
                "model": litellm_model_id,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "input_image",
                         "image_url": f"data:{item.image_mime_type};base64,{encoded}"},
                    ]},
                ],
                "tools": [tool],
                "tool_choice": {"type": "function", "function": {"name": "normalize_annotation_output"}},
            },
        }, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)
```

**Acceptance**:
- [ ] `build_openai_responses_jsonl()` が valid JSONL を返し、各 line が `{custom_id, method, url, body: {model, input, tools, tool_choice}}` 構造を持つ
- [ ] tool.function.parameters が `AnnotationSchema.model_json_schema()` 由来で、capability に応じた required fields を持つ
- [ ] image input が `input_image` type で data URL を埋め込む
- [ ] unit test: 3 capability subset (TAGS only / TAGS+CAPTIONS / TAGS+CAPTIONS+SCORES) で required fields が正しく出る
- [ ] unit test: image MIME 非対応時に `BatchJobError(code="unsupported_image_format")` が raise される (既存 `prepare_items` を経由する形)
- [ ] CI-equivalent filter pass (iam-lib `-m "not downloads_and_runs_model and not calls_real_webapi"`)

### T2: iam-lib `OpenAIBatchAdapter` endpoint 拡張 + responses result parse

**Worktree**: `/tmp/worktrees/issue-518-t2-adapter-responses` (iam-lib repo)
**Branch**: `feat/issue-518-t2-adapter-responses-endpoint`
**Files**:
- `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/batch/adapters/openai.py` (modify)
- `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/batch/refusal_detection.py` (新規 helper)
- `local_packages/image-annotator-lib/tests/unit/webapi/batch/test_openai_adapter_responses.py` (新規)

**実装内容**:
- `_SUPPORTED_ENDPOINTS` に `/v1/responses` を追加
- `_SUPPORTED_CAPABILITIES_BY_ENDPOINT` mapping (新規):
  ```python
  _CAPABILITIES_BY_ENDPOINT = {
      "/v1/moderations": frozenset({TaskCapability.RATINGS}),
      "/v1/responses": frozenset({TaskCapability.TAGS, TaskCapability.CAPTIONS, TaskCapability.SCORES}),
  }
  ```
- `submit_batch` 内で endpoint に応じて `build_openai_moderations_jsonl` / `build_openai_responses_jsonl` を分岐
- `_normalize_result_item` 内で endpoint 別 parser dispatch:
  - moderations: 既存経路
  - responses: 新規 `_parse_responses_item`
- `_parse_responses_item`:
  - response.body から refusal 検出 (`refusal_detection.classify_refusal_from_response()`)
  - refusal → `_failed_result_item(code="provider_safety_refusal", ...)`
  - tool_calls[0].function.arguments → JSON parse → `normalize_annotation_output(**args)` → `AnnotationSchema`
  - `_to_unified_annotation(schema, model_name, capabilities)` で `UnifiedAnnotationResult` 構築
- `refusal_detection.py`: `provider_manager.py` の `_FINISH_REASON_SAFETY_RE` / `_STOP_REASON_REFUSAL_RE` を共通 helper に切り出し (provider_manager 側もこの helper を import するよう refactor)

**Acceptance**:
- [ ] `_SUPPORTED_ENDPOINTS` に `/v1/responses` 追加
- [ ] submit が `/v1/responses` endpoint で input file upload + batch create を完走
- [ ] fetch_batch_results が `/v1/responses` の output JSONL を parse して `UnifiedAnnotationResult` を構築
- [ ] refusal response (`finish_reason=content_filter` 等) を `BatchItemError(code="provider_safety_refusal")` に正規化
- [ ] 既存 Moderations adapter test に regression なし
- [ ] unit test: 成功 output / refusal output / tool_calls missing / invalid JSON args の各 path
- [ ] CI-equivalent filter pass

### T3: LoRAIro deterministic E2E (annotation Batch)

**Worktree**: `/tmp/worktrees/issue-518-t3-deterministic-e2e`
**Branch**: `feat/issue-518-t3-annotation-batch-e2e`
**Files**:
- `tests/integration/test_provider_batch_annotation_e2e.py` (新規)
- `src/lorairo/cli/commands/batch.py` (`_TASK_TYPE_ENDPOINTS["annotation"]["openai"]` に `/v1/responses` を追加、必要なら)

**実装内容**:

`#515` の deterministic E2E pattern を流用:

```python
# fake adapter が submit → completed → fetch で 3 image の UnifiedAnnotationResult を返す
# - image_id=1: tags=["1girl", "blue_eyes"], captions=["A girl with blue eyes."], score=8.0
# - image_id=2: tags=["sunset"], captions=["A sunset scene."], score=7.2
# - image_id=3: refusal (safety_refusal) → error_records に保存

# シナリオ:
1. workflow_service.submit_images(task_type="annotation", model_id=<gpt-4o-mini>, image_ids=[1,2,3])
2. provider_batch_jobs / items が task_type="annotation" + model_id 設定で作成
3. fake adapter が completed + fetch で上記 3 結果を返す
4. import_results → tags/captions/scores が annotations に保存、refusal は error_records に
5. annotation_save_service.filter_refused_image_paths([1,2,3]) で image_id=3 のみ除外
```

**Acceptance**:
- [ ] new test 1 つで成功 path / refusal path 両方を検証
- [ ] tags / captions / scores が DB に保存されることを確認
- [ ] refusal が error_records に SafetyRefusalError として保存され、後続 filter で除外
- [ ] CI-equivalent filter regression なし (LoRAIro 本体 + iam-lib)
- [ ] `_TASK_TYPE_ENDPOINTS["annotation"]["openai"]` が `/v1/responses` を返すこと (CLI default 経路)

### T4: iam-lib runtime smoke + docs amendment

**Worktree**: `/tmp/worktrees/issue-518-t4-smoke-docs`
**Branch**: `feat/issue-518-t4-responses-smoke-docs` (iam-lib + LoRAIro 両方を扱うため worktree 2 つに分ける案もあるが、smoke は iam-lib 内 / docs は LoRAIro 親 repo)
**Files**:
- `local_packages/image-annotator-lib/tests/runtime_validation/test_openai_responses_batch_runtime.py` (新規、`#123` と同じ pattern)
- `docs/decisions/0038-provider-batch-api-integration-strategy.md` (Implementation Status に "annotation 用 /v1/responses MVP merged" 追記)
- `docs/lessons-learned.md` (Integration セクションに Batch / Pydantic schema 関連知見追記)

**実装内容**:
- iam-lib smoke: `omni-moderation-latest` runtime smoke (#123) と同じ pattern で `gpt-4o-mini` の `/v1/responses` batch を submit + retrieve + cancel
- ADR 0038 末尾に Phase 1 完了状況 + Phase 2 (Anthropic) への引き継ぎ事項
- lessons-learned に「Schema SSoT = Pydantic、PydanticAI は同期 agent runtime のみ、Batch は Pydantic schema 直接利用」を明文化

**Acceptance**:
- [ ] runtime smoke test が `calls_real_webapi` marker で動作、billing limit 等の environment 失敗は skip
- [ ] ADR 0038 amendment が docs にマージされる
- [ ] lessons-learned に 1 段落追記

## 5. テスト戦略

| Phase | Filter | 期待 |
|---|---|---|
| Unit (T1/T2 内で実装新規 test) | `cd local_packages/image-annotator-lib && uv run pytest tests/unit/webapi/batch/test_preparation_responses.py tests/unit/webapi/batch/test_openai_adapter_responses.py` | 全 pass |
| iam-lib CI-equivalent (T1/T2 PR 前後) | `cd local_packages/image-annotator-lib && uv run pytest -m "not downloads_and_runs_model and not calls_real_webapi"` | regression なし |
| iam-lib runtime smoke (T4 検証時) | `OPENAI_API_KEY=... cd local_packages/image-annotator-lib && uv run pytest -m calls_real_webapi tests/runtime_validation/test_openai_responses_batch_runtime.py` | submit + retrieve + cancel 通り、または billing skip |
| LoRAIro CI-equivalent (T3 PR 前後) | `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60` | regression なし (現状 3443 passed) |

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| `/v1/responses` の Batch サポートが LiteLLM Batch pricing DB に未収録 | LiteLLM DB を T1 開始前に確認、未収録なら `input_cost_per_token` (同期と同 fields) を fallback として認める |
| `AnnotationSchema.model_json_schema()` が OpenAI strict mode と非互換 (e.g. `additionalProperties: false` 欠如) | T1 で `strict=True` 対応の post-processing helper を追加 (`additionalProperties: false` 注入、`$defs` 解決) |
| Refusal detection が provider_manager 側と Batch 側で drift | refusal_detection.py に regex pattern を集約、provider_manager 側からも import (T2 内で refactor) |
| Batch result の `tool_calls` shape が `/v1/responses` で `/v1/chat/completions` と異なる | T2 開始前に OpenAI Batch API docs で `/v1/responses` の response shape を確認、unit test で fixture 作成 |
| capability に応じた required schema が PydanticAI と Batch で drift | `_build_normalizer_signature` を呼ぶか、共通の `_filter_schema_required(schema, capabilities)` helper を T1 で実装 |
| 大量画像 (1000+) Batch で 200 MB / 50,000 requests 制限を越える | T1 で `_MAX_LIBRARY_ITEMS = 500` を再評価。LoRAIro 側で chunk split は本 Issue scope 外 (将来 Issue) |
| LoRAIro deterministic E2E (T3) が iam-lib API 変更で壊れる | T3 は T1/T2 merge + submodule pin 更新後に進める (依存順序を明示) |

## 7. 引き継ぎ事項 (implement フェーズへ)

### PR 起票順序

1. **iam-lib #T1** (preparation.py) → merged
2. **iam-lib #T2** (adapter.py) → merged (T1 の API に依存)
3. **LoRAIro submodule pin update** (chore PR、T1+T2 merge commit を pin)
4. **LoRAIro #T3** (deterministic E2E) → merged (submodule pin 後)
5. **iam-lib #T4-a** (runtime smoke) → merged (T1+T2 merge 後)
6. **LoRAIro #T4-b** (docs amendment) → merged (T3 完了後)
7. **Issue #518 close** (全 PR merge 後)

### karo の終了条件

- T1 / T2 PR が iam-lib に merge
- LoRAIro submodule pin が T1+T2 merge commit に更新
- T3 PR が LoRAIro に merge
- T4-a / T4-b PR が両 repo に merge
- 上記すべての CI-equivalent filter が green
- Issue #518 を close

### API key 準備

T4-a (runtime smoke) 実行時に `OPENAI_API_KEY` を `.env.local` または `config/lorairo.toml` の `[api].openai_key` に設定。CI には含めない (ADR 0026)。

## 8. 次のステップ

1. 本 plan のレビュー → ユーザー承認
2. Agent Teams 起動で T1-T4 並列分担開始
3. 各 ashigaru は自分の worktree を作成 (`git worktree add /tmp/worktrees/issue-518-*`)
4. 完了後、karo が QC + final report + Issue #518 close

## 関連

- ADR 0023 Phase 1 (PydanticAI / LiteLLM WebAPI Inference Boundary)
- ADR 0026 (On-Demand Runtime Validation Strategy)
- ADR 0038 (Provider Batch API Integration Strategy) — §3 Phase 1 OpenAI MVP §1 `/v1/responses` 対応の計画
- LoRAIro #507 (umbrella, closed) / #515 (deterministic E2E pattern)
- iam-lib #119 / #121 / #122 / #123 (Moderations Batch infrastructure)
- iam-lib #42 (refusal exception hierarchy) / #47 (output normalization)
- `.claude/rules/parallel-execution.md` (worktree 分離 / 共有 venv)
- `.claude/rules/testing.md` (CI-equivalent filter)
