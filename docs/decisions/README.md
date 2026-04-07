# Architecture Decision Records

LoRAIro の重要な設計判断を記録するドキュメント群。

| ADR | タイトル | 日付 | ステータス |
|-----|---------|------|-----------|
| [0001](0001-two-tier-service-architecture.md) | Two-Tier Service Architecture | 2025-08-16 | Accepted |
| [0002](0002-database-schema-decisions.md) | Database Schema Decisions | 2025-10-01 | Accepted |
| [0003](0003-annotator-config-management.md) | Annotator Config Management | 2025-11-15 | Accepted |
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
