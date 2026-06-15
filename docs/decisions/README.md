# Architecture Decision Records

LoRAIro の重要な設計判断を記録するドキュメント群。

| ADR | タイトル | 日付 | ステータス |
|-----|---------|------|-----------|
| [0001](0001-two-tier-service-architecture.md) | Two-Tier Service Architecture | 2025-08-16 | Accepted |
| [0002](0002-database-schema-decisions.md) | Database Schema Decisions | 2025-10-01 | Accepted |
| [0003](0003-annotator-config-management.md) | Annotator Config Management | 2025-11-15 | Superseded by 0021 (partial) |
| [0004](0004-annotator-lib-architecture.md) | Annotator-Lib Architecture | 2025-11-15 | Accepted |
| [0005](0005-annotation-layer-reorganization.md) | Annotation Layer Reorganization | 2025-11-15 | Accepted |
| [0006](0006-pagination-approach.md) | Pagination Approach | 2026-02-05 | Accepted |
| [0007](0007-batch-tag-annotation-ux.md) | Batch Tag Annotation UX | 2026-02-09 | Accepted |
| [0008](0008-claude-md-resilience-architecture.md) | CLAUDE.md Resilience Architecture | 2026-01-01 | Accepted |
| [0009](0009-qt-decoupling-design.md) | Qt Decoupling Design | 2026-02-16 | Accepted |
| [0010](0010-torch-import-design.md) | Torch Import Design | 2025-10-28 | Accepted |
| [0011](0011-mainwindow-ui-redesign.md) | MainWindow UI Redesign | 2026-01-04 | Accepted |
| [0012](0012-batch-tag-atomic-transaction.md) | Batch Tag Atomic Transaction Fix | 2026-01-06 | Accepted |
| [0013](0013-legacy-tag-db-cleanup.md) | Legacy Tag DB Cleanup | 2026-01-02 | Accepted |
| [0014](0014-agent-teams-integration.md) | Agent Teams Integration | 2026-04-09 | Accepted |
| [0015](0015-manual-rating-storage-unification.md) | Manual Rating Storage Unification | 2026-04-18 | Accepted |
| [0016](0016-coverage-threshold-policy.md) | Coverage Threshold Policy | 2026-04-20 | Accepted (amended) |
| [0017](0017-project-db-normalization.md) | Project DB Normalization | 2026-04-22 | Implemented |
| [0018](0018-project-storage-unification.md) | Project Storage Unification | 2026-04-22 | Implemented |
| [0019](0019-export-filter-required-design.md) | Export Filter Required Design | 2026-04-22 | Implemented |
| [0020](0020-cli-message-language-policy.md) | CLI Message Language Policy | 2026-04-27 | Accepted |
| [0021](0021-litellm-driven-model-registry.md) | LiteLLM-Driven WebAPI Model Registry | 2026-04-28 | Superseded by 0023 (partial) |
| [0022](0022-aesthetic-score-predictor-survey.md) | Aesthetic Score Predictor Model Survey | 2025-02-06 | Accepted |
| [0023](0023-pydanticai-litellm-webapi-inference-boundary.md) | PydanticAI / LiteLLM WebAPI Inference Boundary | 2026-05-07 | Accepted |
| [0024](0024-pytest-test-responsibility-separation.md) | pytest Test Responsibility Separation by Package | 2026-05-13 | Accepted |
| [0025](0025-uv-lock-version-control-policy.md) | uv.lock Version Control Policy | 2026-05-14 | Accepted |
| [0026](0026-on-demand-runtime-validation-strategy.md) | On-Demand Runtime Validation Strategy | 2026-05-17 | Accepted |
| [0027](0027-score-labels-db-storage.md) | Score Labels DB Storage | 2026-05-17 | Accepted |
| [0028](0028-score-labels-usage-and-display.md) | Score Labels Usage and Display Strategy | 2026-05-18 | Accepted |
| [0029](0029-unified-dataset-quality-tier.md) | Unified Dataset Quality Tier | 2026-05-19 | Accepted |
| [0030](0030-batch-annotation-model-selection-ui.md) | Batch Annotation Model Selection UI | 2026-05-20 | Accepted |
| [0031](0031-ai-rating-mapping.md) | AI Rating Mapping to Canonical Rating | 2026-05-21 | Accepted (amended) |
| [0032](0032-copyable-readonly-text-display.md) | Copyable Read-Only Text Display Policy | 2026-05-23 | Accepted |
| [0033](0033-annotation-worker-batch-execution-contract.md) | AnnotationWorker Batch Execution Contract | 2026-05-23 | Accepted |
| [0034](0034-worker-operation-pipeline-lifecycle.md) | Worker / Operation / Pipeline Lifecycle Boundary | 2026-05-24 | Accepted |
| [0035](0035-repository-aggregate-split-policy.md) | Repository Aggregate分割方針 | 2026-05-25 | Accepted |
| [0036](0036-gui-compound-widget-split-policy.md) | GUI Compound Widget 分割方針 | 2026-05-25 | Accepted |
| [0037](0037-api-facade-wiring-policy.md) | api/ Public Facade Wiring Policy | 2026-05-25 | Accepted |
| [0038](0038-provider-batch-api-integration-strategy.md) | Provider Batch API Integration Strategy | 2026-05-25 | Accepted |
| [0039](0039-agent-pr-maintenance-automation.md) | Agent PR Maintenance Automation | 2026-05-25 | Accepted |
| [0040](0040-local-ml-model-config-ownership.md) | Local ML Model Config Ownership | 2026-05-24 | Accepted |
| [0041](0041-provider-batch-execution-ui-unification.md) | Provider Batch 実行 UI の個別実行フロー統一 | 2026-05-29 | Accepted |
| [0042](0042-batch-annotation-db-save-io.md) | Batch Annotation DB Save I/O | 2026-05-30 | Accepted |
| [0043](0043-db-core-logging-loguru-unification.md) | db_core Logging Loguru Unification | 2026-05-31 | Accepted |
| [0044](0044-provider-batch-submit-threading.md) | Provider Batch Submit Threading | 2026-05-31 | Accepted |
| [0045](0045-large-search-result-log-level.md) | Large Search Result Log Level | 2026-05-31 | Accepted |
| [0046](0046-loguru-placeholder-format.md) | Loguru Placeholder Format | 2026-05-31 | Accepted |
| [0047](0047-trace-level-for-per-item-diagnostics.md) | TRACE Level for Per-Item Diagnostics | 2026-05-31 | Accepted |
| [0048](0048-webapi-annotation-candidate-filtering.md) | WebAPI Annotation Candidate Filtering (Endpoint / Capability / Suitability) | 2026-05-31 | Accepted |
| [0049](0049-cli-images-list-db-limit.md) | Apply CLI Image List Limit in the Repository Query | 2026-06-01 | Accepted |
| [0050](0050-cli-tag-db-lazy-initialization.md) | CLI Tag DB Lazy Initialization | 2026-06-01 | Accepted |
| [0051](0051-codex-worktree-shared-uv-environment.md) | Codex Worktree Shared uv Environment | 2026-06-01 | Accepted |
| [0052](0052-model-selection-auto-reconcile.md) | ModelSelectionWidget 初回表示時の model reconcile | 2026-06-01 | Accepted |
| [0053](0053-cli-streaming-annotation-memory-bounded-contract.md) | CLI Streaming Annotation Memory-Bounded Execution Contract | 2026-05-29 | Accepted (amended by 0057) |
| [0054](0054-gui-tag-language-reader-initialization.md) | GUI tag language reader initialization | 2026-06-03 | Accepted |
| [0055](0055-workspace-export-target-staging-unification.md) | Workspace Export Target = Staging Set / Selection-Source Unification | 2026-06-04 | Accepted |
| [0056](0056-exact-set-selector-id-count-guard.md) | exact-set selector の大量ID集合ガード / count-only 軽量化方針 | 2026-06-05 | Accepted |
| [0057](0057-cli-jsonl-output-and-error-contract.md) | CLI Machine-Readable (JSONL) Output and Error Contract | 2026-06-05 | Accepted (amended by 0060) |
| [0058](0058-cli-output-mode-trigger-and-entrypoint-policy.md) | CLI Output Mode Trigger and Entry-Point Policy | 2026-06-05 | Accepted |
| [0059](0059-cli-command-introspection.md) | CLI Command Introspection Contract | 2026-06-06 | Accepted |
| [0060](0060-cli-bounded-pagination-contract.md) | CLI Bounded Pagination and Count-First Contract | 2026-06-06 | Accepted |
| [0061](0061-phash-duplicate-variant-classification.md) | 登録パイプライン再設計 — pHash 候補の重複/別版分類 | 2026-06-05 | Accepted |
| [0062](0062-batch-custom-id-phash-long-edge.md) | Provider Batch custom_id を pHash + 長辺解像度基準へ統一 | 2026-06-05 | Accepted |
| [0063](0063-cli-batch-submit-image-ids-csv.md) | CLI Batch Submit Image IDs CSV Contract | 2026-06-07 | Accepted |
| [0064](0064-cli-original-image-annotation-guard.md) | CLI Original Image Annotation Guard | 2026-06-07 | Accepted |
| [0065](0065-tag-caption-soft-reject.md) | Tag/Caption Soft-Reject And Export Resolution | 2026-06-11 | Accepted |
| [0066](0066-unified-jobs-lifecycle-view.md) | Unified Jobs Lifecycle View | 2026-06-12 | Accepted |
| [0067](0067-sqlite-concurrency-busy-timeout.md) | SQLite Concurrency: busy_timeout + Lock Error Classification | 2026-06-15 | Accepted |

## ADR テンプレート

```markdown
# ADR XXXX: タイトル

- **日付**: YYYY-MM-DD
- **ステータス**: Proposed | Accepted | Deprecated | Superseded by [XXXX]

## Context

なぜこの決定が必要だったか。問題の背景と制約。

## Decision

何を決定したか。

## Rationale

なぜこの選択をしたか。他の選択肢との比較。

## Consequences

この決定による影響。良い点・悪い点・トレードオフ。
```
