---
type: ADR
title: Annotation Layer Reorganization
status: Accepted
timestamp: 2025-11-15
tags: []
---
# ADR 0005: Annotation Layer Reorganization

## Context

`AnnotationService` に GUI ロジック、ビジネスロジック、データアクセスが混在しており、`WorkerService` との責務境界が不明確だった。また、不要になった `HybridAnnotationController` を除去する必要があった。

## Decision

アノテーション処理に**3 層分離アーキテクチャ**を採用する。

- **データアクセス層(Data Access Layer)**: `annotations/annotator_adapter.py`(`AnnotatorLibraryAdapter`)に配置し、`image-annotator-lib` との境界を担う。
- **ビジネスロジック層(Business Logic Layer)**: `annotations/annotation_logic.py`(`AnnotationLogic`)に配置し、Qt に依存しない構成とする。
- **GUI 層(GUI Layer)**: `gui/workers/annotation_worker.py` と `gui/controllers/annotation_workflow_controller.py` が担当する。

あわせて、既存の `WorkerService` 中心のアーキテクチャを踏襲し、`AnnotationLogic` は `WorkerService` 経由で遅延初期化する。

## Rationale

Phase 3 における `AnnotationService` の完全削除に伴い、次の 3 ファイルを削除した。

- `services/annotation_service.py`
- `services/annotation_batch_processor.py`
- `gui/widgets/annotation_coordinator.py`

PydanticAI の統合によって既存機能はすべて代替済みであったため、段階的な廃止ではなく完全削除を選択し、構成を明確にした。

## Consequences

- `AnnotationWorker` のコンストラクタ引数を `(image_paths, models, batch_size, operation_mode, api_keys)` から `(annotation_logic, image_paths, models)` へ変更した。
- `MainWindow` から `annotation_service` 属性、インポート文、および初期化コードを完全に削除した。
- `WorkerService` の初期化に失敗した場合はアプリケーションの起動を中止する設計とし、必須コンポーネントとして位置づけた。
- GUI テストでは `AnnotationLogic` をモック化することで、`AnnotationWorker` を独立してテストできるようになった。
