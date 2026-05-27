# Plan: Issue #507 残り実装 — E2E smoke + Issue close (Agent Teams 並列)

- **対象**: NEXTAltair/LoRAIro#507 (OpenAI Moderations preflight rating integration)
- **策定日**: 2026-05-27
- **前提**: T1 (iam-lib #119/#121)、T2 (iam-lib #120/#122)、T3 (LoRAIro #505/#509)、T4 (LoRAIro #506/#510)、final submodule pin (LoRAIro #511) はすべて merged 済み
- **スコープ**: ADR 0026 (On-Demand Runtime Validation) に従う E2E smoke と Issue close 整理のみ。Backfill / Anthropic / Google batch 拡張は本タスク対象外。

## 1. ultrathink 設計プロセス

### 1.1 状況認識

`/v1/moderations` rating preflight pipeline は**コード上は完成**している:

| レイヤー | 実装 | 検証状況 |
|---|---|---|
| iam-lib converter (`category_scores → RatingPrediction`) | ✅ #121 merged | ユニットテスト済 |
| iam-lib OpenAI Batch adapter (submit/retrieve/cancel/fetch + JSONL parse) | ✅ #122 merged | adapter 単体ユニットテスト済 (mocked OpenAI client) |
| LoRAIro provider batch workflow (`task_type=rating_preflight` 透過 + `model_id` 必須化) | ✅ #509 merged | ユニットテスト + targeted integration ✅ |
| LoRAIro annotation save 側 rating eligibility filter | ✅ #510 merged | ユニットテスト + targeted integration ✅ |
| ADR 0031 amendment + ADR 0038 | ✅ #503, #466 merged | docs 整合 |

**未検証ギャップ**:
1. 実 OpenAI key で `/v1/moderations` Batch API を回したときの artifact JSONL shape が iam-lib `_parse_output_lines` / `_extract_moderation_response` の仮定と整合するか
2. LoRAIro の `submit_images → refresh → download_results → import_results` 通しが provider 実 batch を相手に動くか
3. rating preflight 結果が `ratings.normalized_rating` に正しく落ち、後続 `AnnotationWorker` の `filter_excluded_by_rating()` で X/XXX 画像が annotation API 送信対象から除外されるか
4. Issue #505 (LoRAIro) と #120 (iam-lib) が PR `closes` reference 抜けで OPEN のまま放置

### 1.2 検証境界 (ADR 0026)

| 検証対象 | 配置 | marker |
|---|---|---|
| 実 OpenAI Batch API の submit/poll/fetch contract | iam-lib `tests/runtime_validation/test_real_webapi_runtime.py` | `calls_real_webapi` |
| LoRAIro adapter / config / DB 保存 / annotation save flow の wiring | LoRAIro `tests/integration/` (fake `ProviderBatchAdapter` 注入) | `integration` + 既存 marker |
| Issue close / docs follow-up | docs / GitHub | n/a |

LoRAIro 側に実 WebAPI test を増やさない (ADR 0026 amendment 2026-05-18)。

## 2. 解決策ソリューション比較

| 案 | 内容 | 評価 |
|---|---|---|
| A. iam-lib runtime smoke のみ追加し、LoRAIro 側は既存 unit/integration で代替 | iam-lib に `omni-moderation-latest` happy-path を追加、LoRAIro は変更なし | ❌ workflow_service の `download_results → import_results → annotation_save` チェーン全体の wiring が deterministic E2E でカバーされない |
| B. LoRAIro deterministic E2E のみ追加し、iam-lib 側 smoke は手動メモで運用 | LoRAIro 側 fake adapter で workflow 全体を通す | △ artifact JSONL shape の確認漏れリスク (まさに ADR 0026 が解こうとした問題) |
| **C. (推奨)** iam-lib runtime smoke + LoRAIro deterministic E2E + docs/Issue close を Agent Teams で並列 | 4 worktree 同時進行、各タスク独立 | ✅ ADR 0026 と一致、検証ギャップを全部埋める、並列で速い |
| D. PydanticAI / LiteLLM 経由で /v1/moderations を叩く統一抽象 | 共通化を進める | ❌ ADR 0038 §8 で却下済み (provider artifact lifecycle が PydanticAI 抽象と合わない) |

**選択: C** — ADR 0026 boundary を保ち、ギャップを並列で埋める。

## 3. アーキテクチャ設計

```
[T1: iam-lib happy]                [T2: iam-lib error/cancel]
     ↓                                   ↓
tests/runtime_validation/         tests/runtime_validation/
test_real_webapi_runtime.py       test_real_webapi_runtime.py
(`calls_real_webapi` marker)      (`calls_real_webapi` marker)
     ↓                                   ↓
     └─────────────┬──────────────────────┘
                   ↓ (LoRAIro 側 bridge)
     scripts/run_runtime_webapi_tests.py
                   ↓
[T3: LoRAIro deterministic E2E]
tests/integration/test_provider_batch_rating_preflight_e2e.py
(fake ProviderBatchAdapter 注入、annotation save flow まで通し検証)
                   ↓
[T4: docs & Issue close]
- docs/lessons-learned.md (rating preflight 実装知見)
- ADR 0031 amendment: Implementation Status: Merged 追記
- LoRAIro #505 / iam-lib #120 を手動 close (PR linking comment 付き)
```

各タスクは独立した worktree (`/tmp/worktrees/issue-507-*`) で実行し、共有 venv (`UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv`) を利用 (ADR 0024 / parallel-execution.md)。

## 4. 実装計画 (T1-T4 並列分担)

### Agent Teams roster

- **karo (家老)**: 全体統合 / final report / 全 T 完了確認後の Issue #507 close 判断
- **ashigaru1**: T1 担当
- **ashigaru2**: T2 担当
- **ashigaru3**: T3 担当
- **ashigaru4**: T4 担当
- **gunshi (軍師)**: 各 T の QC レビュー (PR merge 前)

### T1: iam-lib runtime smoke (happy path)

**Worktree**: `/tmp/worktrees/issue-507-smoke-iam-happy` (iam-lib repo)
**Branch**: `feat/issue-120-runtime-smoke-happy`
**Files**:
- `local_packages/image-annotator-lib/tests/runtime_validation/test_real_webapi_runtime.py` (既存ファイルに append)
- 必要に応じて `tests/runtime_validation/conftest.py` に moderation 用 fixture

**実装内容**:
- `@pytest.mark.calls_real_webapi` で `omni-moderation-latest` を `litellm_model_id="openai/omni-moderation-latest"` として submit
- 入力: 安全画像 2-3 枚 (`tests/resources/` 既存 fixture を流用、低リスク safe-illustration)
- 検証:
  - `submit_batch()` が `BatchSubmitResult.provider_job_id` を返す
  - `retrieve_batch()` を最大 5 分 polling (timeout=300s) し、`completed` に遷移
  - `fetch_batch_results()` が `BatchFetchResult.items` を返し、各 item の `annotation.ratings[0]` が `source_scheme="openai_moderation_v1"` を持つ
  - `raw_label` が `pg` / `pg13` のいずれか (安全画像なので)

**Acceptance**:
- `cd local_packages/image-annotator-lib && OPENAI_API_KEY=... uv run pytest -m calls_real_webapi tests/runtime_validation/test_real_webapi_runtime.py::test_openai_moderations_batch_happy_path` が pass
- LoRAIro 側からは `make test-runtime-webapi` で起動可能 (scripts/run_runtime_webapi_tests.py 経由)

### T2: iam-lib runtime smoke (error/cancel/expire path)

**Worktree**: `/tmp/worktrees/issue-507-smoke-iam-error` (iam-lib repo)
**Branch**: `feat/issue-120-runtime-smoke-error`
**Files**:
- `local_packages/image-annotator-lib/tests/runtime_validation/test_real_webapi_runtime.py`

**実装内容**:
- **cancel path**: 最小 submit → 数秒内に `cancel_batch()` → `retrieve_batch()` が `canceled` を返すこと
- **invalid model path**: 存在しない model_id (`openai/omni-moderation-fake`) で submit → `BatchJobError` (`code=invalid_model_id` or `unsupported_model_provider`) が raise
- **missing api key path**: `api_keys={}` で submit → `BatchJobError(code="missing_api_key")` が raise (これは mocked でも検証可能、SHOULD be unit-level)

**実行時コスト配慮**: cancel path はファイル upload なしの最小 submit (1 item) で実行。invalid model path はネットワーク呼び出し前に fail (`_resolve_model_ref` 内)。

**Acceptance**:
- `pytest -m calls_real_webapi ... test_openai_moderations_batch_cancel_path` が pass
- 既存 `test_openai_adapter.py` の mocked test と矛盾しない

### T3: LoRAIro deterministic E2E (rating preflight → annotation skip)

**Worktree**: `/tmp/worktrees/issue-507-smoke-lorairo-e2e`
**Branch**: `feat/issue-505-deterministic-e2e`
**Files**:
- `tests/integration/test_provider_batch_rating_preflight_e2e.py` (新規)

**実装内容**:

deterministic fake `ProviderBatchAdapter` を注入し、以下のシナリオを通し検証:

```
1. LoRAIro DB に test image を 3 枚登録 (image_id=1,2,3)
2. fake adapter が next submit で `provider_job_id="job-xxx"` を返す
3. workflow_service.submit_images(task_type="rating_preflight", model_id=<omni-moderation-latest model>, image_ids=[1,2,3]) を呼ぶ
4. provider_batch_jobs + provider_batch_items が DB に作成され task_type="rating_preflight" を持つことを確認
5. fake adapter が `retrieve` で `completed` を返すよう setup
6. fake adapter が `fetch_batch_results` で各 image に対応する RatingPrediction (image_id=1→PG, image_id=2→R, image_id=3→XXX) を返すよう setup
7. workflow_service.download_results(job_id) → workflow_service.import_results(job_id)
8. ratings テーブルに 3 行作られ、`normalized_rating` が PG/R/XXX であることを確認
9. annotation_save_service.filter_excluded_by_rating([1,2,3]) を呼び、image_id=3 (XXX) だけ除外されることを確認
10. (オプション) annotation_worker への chain で WebAPI submit 対象画像が [1,2] のみであることを確認
```

**Marker**: `@pytest.mark.integration` (CI 実行対象)

**Acceptance**:
- CI-equivalent filter で `tests/integration/test_provider_batch_rating_preflight_e2e.py` が pass
- 既存 LoRAIro test suite に regression なし: `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60`

### T4: Documentation & Issue close

**Worktree**: `/tmp/worktrees/issue-507-docs-close`
**Branch**: `docs/issue-507-final-followup`
**Files**:
- `docs/lessons-learned.md` (Integration セクションに rating preflight 知見追記)
- `docs/decisions/0031-ai-rating-mapping.md` 末尾 (Amendment 2026-05-27 セクションに `Implementation Status: Merged via #509/#510/#122/#121` を追記)
- 必要なら `docs/services.md` の rating preflight 経路への参照

**Issue close** (PR merge 後、別作業として):
- `gh issue close NEXTAltair/LoRAIro#505 --comment "Merged via #509 + smoke validated by #<T1 PR> / #<T3 PR>"`
- `gh issue close NEXTAltair/image-annotator-lib#120 --comment "Merged via #122 + smoke validated by #<T1 PR> / #<T2 PR>"`
- `gh issue close NEXTAltair/LoRAIro#507 --comment "All subtasks done"` (karo 判断後)

**Acceptance**:
- ADR amendment が docs/decisions/0031 に追記済
- lessons-learned.md に integration 観点で 1 セクション追記
- T1/T2/T3 完了後に Issue #505, #120 を close
- karo が全 T の QC pass を確認した後 Issue #507 を close

## 5. テスト戦略

| Phase | Filter | 期待結果 |
|---|---|---|
| Unit (各 T 内で実装新規 test) | `pytest <file>` | 全 pass |
| iam-lib CI-equivalent (T1/T2 前後) | `cd local_packages/image-annotator-lib && uv run pytest -m "not downloads_and_runs_model and not calls_real_webapi"` | regression なし (現状 757 passed) |
| iam-lib runtime smoke (T1/T2 検証時) | `OPENAI_API_KEY=... uv run pytest -m calls_real_webapi` | 新規 test pass |
| LoRAIro CI-equivalent (T3/T4 前後) | `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60` | regression なし (現状 3435 passed / 2 skipped) |

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| 実 OpenAI Batch API が 24h SLA 内に completed に遷移しない | T1 で timeout=300s (5分)、超過時 skip + warning。Acceptance には影響させない (Batch SLA は OpenAI 側責務) |
| OpenAI Batch artifact JSONL shape が iam-lib `_parse_output_lines` の仮定とズレる | T1 で発覚した場合、別 PR で adapter 修正 → submodule pin 更新 → LoRAIro 側 regression 確認の 3-step で対応 |
| iam-lib runtime test が課金を発生させる | `omni-moderation-latest` は text moderation pricing なし (image moderation は free tier 内)。安全画像 2-3 枚なら無視できるコスト |
| T3 fake adapter が現実の adapter contract と乖離 | `ProviderBatchLibraryAdapter` の `submit_batch/retrieve_batch/fetch_batch_results/cancel_batch` シグネチャを Protocol として抽出し、fake は同 Protocol を満たすこと (T3 内で確認) |
| T4 ドキュメント更新が他の進行中の docs PR と conflict | T4 の docs 更新は ADR amendment と lessons-learned 追記のみに絞り、user_guide / spec の大規模改修は対象外 |
| Issue close race (T1/T2/T3 が完了する前に #505/#120 を close してしまう) | T4 の Issue close 作業は karo の merge 確認後にのみ実行 (karo が ashigaru4 に明示指示) |

## 7. 引き継ぎ事項 (implement フェーズへ)

実装開始時に確認すべき項目:

1. **API key 準備**: T1/T2 実行者は `.env.local` または `config/lorairo.toml` の `[api].openai_key` に有効な OpenAI key を設定。CI には含めない。
2. **fixture**: T1 用安全画像は既存 `local_packages/image-annotator-lib/tests/resources/` から選定。T2 cancel path は最小 1 枚で可。
3. **PR 起票順序**: T1 → submodule pin update → T3 の順に依存。T2/T4 は独立並列可能。
4. **karo が判断する終了条件**:
   - T1 PR が iam-lib に merge され、LoRAIro 側 submodule pin が更新されている
   - T2 PR が iam-lib に merge されている
   - T3 PR が LoRAIro に merge されている
   - T4 PR が LoRAIro に merge されている
   - LoRAIro #505 / iam-lib #120 が close されている
   - 上記すべての CI-equivalent filter が green

karo は上記を満たした後、LoRAIro #507 を close する。

## 8. 次のステップ

1. 本 plan のレビュー → ユーザー承認
2. `/implement` または agent teams 起動で T1-T4 並列分担開始
3. 各 ashigaru は自分の worktree を作成 (`git worktree add /tmp/worktrees/issue-507-*`)
4. 完了後、karo が QC + final report

## 関連

- ADR 0026 (On-Demand Runtime Validation Strategy)
- ADR 0031 amendment (OpenAI Moderations preflight rating)
- ADR 0038 (Provider Batch API Integration Strategy)
- LoRAIro #505 / #506 / #509 / #510 / #511
- iam-lib #119 / #120 / #121 / #122
- `.claude/rules/parallel-execution.md` (worktree 分離 / 共有 venv)
- `.claude/rules/testing.md` (CI-equivalent filter)
- `scripts/run_runtime_webapi_tests.py` (LoRAIro 側 bridge script)
