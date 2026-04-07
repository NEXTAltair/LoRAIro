# ADR 0005: Annotation Layer Reorganization

- **日付**: 2025-11-15
- **ステータス**: Accepted

## Context

AnnotationService が GUI ロジック・ビジネスロジック・データアクセスを混在させており、WorkerService との責任境界が不明確だった。HybridAnnotationController の除去が必要だった。

## Decision

**3層分離アーキテクチャ**:
- **Data Access Layer**: `annotations/annotator_adapter.py` (AnnotatorLibraryAdapter) — image-annotator-lib との境界
- **Business Logic Layer**: `annotations/annotation_logic.py` (AnnotationLogic) — Qt 非依存
- **GUI Layer**: `gui/workers/annotation_worker.py` + `gui/controllers/annotation_workflow_controller.py`

**WorkerService-centered architecture**: 既存の WorkerService パターンを踏襲し、AnnotationLogic を WorkerService 経由で遅延初期化。

## Rationale

AnnotationService の完全削除 (Phase 3) で以下を削除:
- `services/annotation_service.py`
- `services/annotation_batch_processor.py`
- `gui/widgets/annotation_coordinator.py`

PydanticAI 統合で全機能がカバー済みのため完全削除を選択（段階的廃止より明確）。

## Consequences

- AnnotationWorker コンストラクタ変更: `(image_paths, models, batch_size, operation_mode, api_keys)` → `(annotation_logic, image_paths, models)`
- MainWindow から `annotation_service` 属性・import・初期化コードを完全削除
- WorkerService が失敗するとアプリ起動が中止される（クリティカル化）
- GUI テストでは AnnotationLogic をモックして AnnotationWorker を独立テスト可能
