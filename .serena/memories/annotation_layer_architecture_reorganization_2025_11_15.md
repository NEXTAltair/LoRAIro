# アノテーション層アーキテクチャ再編成計画書

**作成日**: 2025-11-15
**更新日**: 2025-11-16（Phase 6 完了記録）
**Phase**: Phase 6 完了、Phase 7 以降未着手
**Status**: 🟢 Phase 1-6 完了、Phase 7-10 未着手

## 1. 概要

LoRAIroのアノテーション層を3層分離アーキテクチャに再編成。Critical Bug Fix（Phase 6）により、AnnotationWorker/WorkerService統合が完了。

**アーキテクチャ方針**:
- **Data Access Layer**: `annotations/annotator_adapter.py` (AnnotatorLibraryAdapter)
- **Business Logic Layer**: `annotations/annotation_logic.py` (AnnotationLogic)
- **GUI Layer**: `gui/workers/annotation_worker.py`, `gui/controllers/annotation_workflow_controller.py`

**統合方針**: WorkerService-centered architecture（既存パターン踏襲）

## 2. 完了済み作業（Phase 1-6）

### Phase 1: ファイル移動と作成 ✅
- `annotations/annotator_adapter.py` 作成（services/から移動）
- `annotations/annotation_logic.py` 作成（ビジネスロジック抽出）

### Phase 2: AnnotationWorker修正（第1版） ✅
- `gui/workers/annotation_worker.py` を AnnotationLogic 呼び出しに変更
- **注意**: 後にインターフェースミスマッチが判明（Phase 6で修正完了）

### Phase 3: 不要ファイル削除 ✅
- ✅ `services/annotation_service.py` 削除
- ✅ `services/annotation_batch_processor.py` 削除
- ✅ `gui/widgets/annotation_coordinator.py` 削除
- ✅ `annotations/caption_tags.py` 削除
- ✅ `services/__init__.py` 更新（AnnotationService除去）
- ✅ `services/service_container.py` 更新（import修正、BatchProcessor除去）

### Phase 4: AnnotationWorkflowController の WorkerService 化 ✅
- ✅ WorkerService import追加
- ✅ `__init__()` 引数変更: `annotation_service` → `worker_service`（必須引数化）
- ✅ `_validate_services()` に WorkerService NULL チェック追加
- ✅ `_start_batch_annotation()` を WorkerService.start_enhanced_batch_annotation() 呼び出しに変更

### Phase 5: MainWindow の WorkerService 化 ✅
- ✅ `annotation_service` 属性削除（Line 55）
- ✅ `AnnotationService` 初期化コード削除（Line 167）
- ✅ AnnotationService Signal接続削除（Line 322, 454, 462, 465）
- ✅ AnnotationWorkflowController初期化をWorkerService依存に修正
- ✅ WorkerService初期化をクリティカル化（失敗時アプリ起動中止）

### Phase 6: Critical Bug Fix - AnnotationWorker/WorkerService Integration ✅

**実施日**: 2025-11-16

**6.1: WorkerService への AnnotationLogic 統合**
- ✅ AnnotationLogic 遅延初期化プロパティ追加 (worker_service.py:105-126)
- ✅ ServiceContainer 経由で AnnotatorLibraryAdapter, ConfigurationService 取得
- ✅ 依存関係: AnnotatorLibraryAdapter, ConfigurationService, ImageDatabaseManager

**6.2: start_enhanced_batch_annotation() 修正**
- ✅ AnnotationWorker コンストラクタを正しいシグネチャに修正 (worker_service.py:260-264)
  - **修正前**: `AnnotationWorker(image_paths, models, batch_size, operation_mode, api_keys)`
  - **修正後**: `AnnotationWorker(annotation_logic, image_paths, models)`
- ✅ 後方互換性のため `batch_size`, `api_keys` パラメータは保持（未使用）

**6.3: start_model_sync() 完全削除**
- ✅ メソッド本体削除
- ✅ Signal 削除: `model_sync_started`, `model_sync_finished`, `model_sync_error`
- ✅ `_on_worker_started()`, `_on_worker_finished()`, `_on_worker_error()` から model_sync 処理削除

**6.4: MainWindow の WorkerService 初期化をクリティカル化**
- ✅ 初期化失敗時に `None` 設定ではなく `_handle_critical_initialization_failure()` 呼び出し
- ✅ アプリケーション起動を中止する設計に変更

**6.5: AnnotationWorkflowController の _validate_services() 修正**
- ✅ `worker_service` の NULL チェックを追加
- ✅ 適切なエラーメッセージング実装

**6.6: Import エラー修正**
- ✅ `AnnotatorAdapter` → `AnnotatorLibraryAdapter` に修正 (worker_service.py:11)

**6.7: 陳腐化テスト削除**
- ✅ `tests/performance/test_performance.py` - `annotation_batch_processor` import
- ✅ `tests/unit/test_caption_tags.py` - `annotations.caption_tags` import

**修正ファイル**:
1. `src/lorairo/gui/services/worker_service.py` - AnnotationLogic 統合、start_model_sync() 削除
2. `src/lorairo/gui/window/main_window.py` - WorkerService クリティカル化
3. `src/lorairo/gui/controllers/annotation_workflow_controller.py` - WorkerService NULL チェック追加
4. `tests/performance/test_performance.py` - 削除
5. `tests/unit/test_caption_tags.py` - 削除

**検証結果**:
- ✅ MainWindow import 成功
- ✅ pytest コレクション成功（1531 tests collected）
- ✅ NameError, TypeError, ImportError 完全解消

## 3. 残存作業（Phase 7-10）

### Phase 7: test_annotation_workflow_controller.py 修正 （未着手）

**7.1: AnnotationService Mock → WorkerService Mock**

```python
# 修正前
from lorairo.services.annotation_service import AnnotationService

@pytest.fixture
def mock_annotation_service():
    return Mock(spec=AnnotationService)

def test_start_annotation_workflow(mock_annotation_service, ...):
    controller = AnnotationWorkflowController(
        annotation_service=mock_annotation_service,
        ...
    )

# 修正後
from lorairo.gui.services.worker_service import WorkerService

@pytest.fixture
def mock_worker_service():
    return Mock(spec=WorkerService)

def test_start_annotation_workflow(mock_worker_service, ...):
    controller = AnnotationWorkflowController(
        worker_service=mock_worker_service,
        ...
    )
```

**検証ポイント**:
- [ ] test_annotation_workflow_controller.py がパス

### Phase 8: test_annotation_worker.py 修正 （未着手）

**8.1: 新インターフェースに合わせたテストコード書き換え**

```python
# 修正前
worker = AnnotationWorker(
    images=[mock_image],
    phash_list=["test_phash"],
    operation_mode="batch",
    api_keys={"openai": "test_key"},
)

# 修正後
worker = AnnotationWorker(
    annotation_logic=mock_annotation_logic,
    image_paths=["test_image.png"],
    models=["gpt-4o-mini"],
)

# Mock対象をAnnotationLogicに変更
with patch('lorairo.annotations.annotation_logic.AnnotationLogic') as mock_logic:
    mock_logic.execute_annotation.return_value = mock_results
    # テスト実行
```

**検証ポイント**:
- [ ] test_annotation_worker.py がパス

### Phase 9: 不要テストファイル削除 （未着手）

- [ ] `tests/unit/services/test_annotation_service.py` 削除
- [ ] `tests/integration/services/test_annotation_service_integration.py` 削除
- [ ] `tests/integration/gui/test_annotation_ui_integration.py` 削除
- [ ] `tests/integration/gui/test_mainwindow_annotation_integration.py` 削除
- [ ] `tests/integration/test_phase4_integration.py` 削除

**注意**: Phase 3-5 で一部削除済み

### Phase 10: 統合テストと検証 （未着手）

**10.1: 単体テスト実行**
```bash
# AnnotationWorker テスト
uv run pytest tests/unit/gui/workers/test_annotation_worker.py -xvs

# AnnotationWorkflowController テスト
uv run pytest tests/unit/gui/controllers/test_annotation_workflow_controller.py -xvs
```

**10.2: 統合テスト実行**
```bash
# アノテーション関連統合テスト
uv run pytest tests/integration/annotations/ -xvs

# GUI統合テスト（headless）
uv run pytest tests/integration/gui/ -xvs -m gui
```

**10.3: 手動動作確認**
1. MainWindow起動
2. 画像選択
3. アノテーション開始
4. 進捗表示確認
5. 完了通知確認
6. DB保存確認

**検証ポイント**:
- [ ] 全テストパス（カバレッジ75%以上）
- [ ] Pylance/mypy エラーゼロ確認
- [ ] GUI手動テスト（アノテーション実行→完了→DB保存）
- [ ] WorkerService進捗報告・キャンセル動作確認

## 4. リスク評価と対策

### リスク1: テストカバレッジ低下 🟡

**リスク**: インターフェース変更によりテストカバレッジが低下

**対策**:
- Phase 7-8でテスト修正時、カバレッジレポート確認
- 75%未満の場合、不足テストケース追加

### リスク2: AnnotationLogic層分離の破壊 🔴

**リスク**: AnnotationLogic内部生成により層分離が曖昧化

**対策**:
- AnnotationLogicはあくまでビジネスロジック（DB非依存）を維持
- AnnotationWorkerはGUI層（Qt Signal発火、進捗報告）の責務を明確化
- DB保存は別途Repositoryレイヤーで実施（AnnotationLogicには含めない）

## 5. 実装チェックリスト

### Phase 1-6: 完了済み ✅

**Phase 1: ファイル移動と作成**
- [x] `annotations/annotator_adapter.py` 作成
- [x] `annotations/annotation_logic.py` 作成

**Phase 2: AnnotationWorker修正（第1版）**
- [x] `gui/workers/annotation_worker.py` を AnnotationLogic 呼び出しに変更

**Phase 3: 不要ファイル削除**
- [x] `services/annotation_service.py` 削除
- [x] `services/annotation_batch_processor.py` 削除
- [x] `gui/widgets/annotation_coordinator.py` 削除

**Phase 4: AnnotationWorkflowController の WorkerService 化**
- [x] WorkerService import追加
- [x] `__init__()` 引数変更
- [x] `_validate_services()` に WorkerService チェック追加
- [x] `_start_batch_annotation()` を WorkerService 呼び出しに修正

**Phase 5: MainWindow の WorkerService 化**
- [x] `annotation_service` 属性削除
- [x] `AnnotationService` 初期化コード削除
- [x] AnnotationWorkflowController初期化をWorkerService依存に修正
- [x] WorkerService初期化をクリティカル化

**Phase 6: Critical Bug Fix**
- [x] WorkerService への AnnotationLogic 統合
- [x] start_enhanced_batch_annotation() 修正
- [x] start_model_sync() 完全削除
- [x] MainWindow の WorkerService 初期化をクリティカル化
- [x] AnnotationWorkflowController の _validate_services() 修正
- [x] Import エラー修正
- [x] 陳腐化テスト削除
- [x] MainWindow import 成功確認
- [x] pytest コレクション成功確認

### Phase 7-10: 未着手

**Phase 7: test_annotation_workflow_controller.py 修正**
- [ ] AnnotationService Mock → WorkerService Mock
- [ ] pytest実行確認（全パス）

**Phase 8: test_annotation_worker.py 修正**
- [ ] 新インターフェースに合わせたテストコード書き換え
- [ ] Mock対象をAnnotationLogicに変更
- [ ] pytest実行確認（全パス）

**Phase 9: 不要テストファイル削除**
- [ ] `tests/unit/services/test_annotation_service.py` 削除
- [ ] `tests/integration/services/test_annotation_service_integration.py` 削除
- [ ] その他削除対象ファイル確認・削除

**Phase 10: 統合テストと検証**
- [ ] pytest全実行（カバレッジ75%以上）
- [ ] Pylance/mypy エラーゼロ確認
- [ ] GUI手動テスト（アノテーション実行→完了→DB保存）
- [ ] WorkerService進捗報告・キャンセル動作確認

## 6. 完了条件

以下の全条件を満たした時点で本再編成完了とする:

1. ✅ **層分離アーキテクチャ確立**: Data Access / Business Logic / GUI の3層が明確
2. ✅ **WorkerService統合**: AnnotationWorkerがWorkerServiceから正常起動
3. ⏳ **テスト全パス**: 単体・統合テスト全件パス、カバレッジ75%以上（Phase 7-10で実施）
4. ⏳ **型チェック通過**: Pylance/mypy エラーゼロ（Phase 10で実施）
5. ⏳ **実動作確認**: GUI操作でアノテーション実行→DB保存成功（Phase 10で実施）
6. ⏳ **ドキュメント更新**: 本計画書を最終版に更新（Phase 10完了時）

## 7. 参考情報

**関連Memory**:
- `annotator_lib_completion_master_plan.md` - image-annotator-lib統合完了記録
- `phase4_completion_record_2025_11_08.md` - Phase 4完了時の設計判断

**関連ファイル**:
- `gui/services/worker_service.py` - WorkerService実装（統合先）
- `gui/workers/annotation_worker.py` - 修正対象Worker
- `gui/controllers/annotation_workflow_controller.py` - Controller書き換え対象
- `gui/window/main_window.py` - MainWindowクリーンアップ対象
- `services/service_container.py` - ServiceContainer（依存解決）

**設計原則**:
- YAGNI（今必要なものだけ実装）
- Single Responsibility（各層の責務を明確化）
- Dependency Injection（Constructor injection優先）
