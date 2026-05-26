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
| [0031](0031-ai-rating-mapping.md) | AI Rating Mapping to Canonical Rating | 2026-05-21 | Accepted |
| [0032](0032-copyable-readonly-text-display.md) | Copyable Read-Only Text Display Policy | 2026-05-23 | Accepted |
| [0033](0033-annotation-worker-batch-execution-contract.md) | AnnotationWorker Batch Execution Contract | 2026-05-23 | Accepted |
| [0034](0034-worker-operation-pipeline-lifecycle.md) | Worker / Operation / Pipeline Lifecycle Boundary | 2026-05-24 | Accepted |
| [0035](0035-repository-aggregate-split-policy.md) | Repository Aggregate分割方針 | 2026-05-25 | Accepted |
| [0036](0036-gui-compound-widget-split-policy.md) | GUI Compound Widget 分割方針 | 2026-05-25 | Accepted |
| [0037](0037-api-facade-wiring-policy.md) | api/ Public Facade Wiring Policy | 2026-05-25 | Accepted |
| [0038](0038-provider-batch-api-integration-strategy.md) | Provider Batch API Integration Strategy | 2026-05-25 | Accepted |
| [0039](0039-agent-pr-maintenance-automation.md) | Agent PR Maintenance Automation | 2026-05-25 | Accepted |
| [0040](0040-agent-pr-maintenance-workflow-runner.md) | Agent PR Maintenance Workflow Runner | 2026-05-26 | Accepted |

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
