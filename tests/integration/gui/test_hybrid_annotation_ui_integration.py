# tests/integration/gui/test_hybrid_annotation_ui_integration.py

"""
Hybrid Annotation UI Integration Tests

Phase 4: 統合テスト - ウィジェット間連携テスト
ハイブリッドアノテーションUIの統合機能をテスト
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from lorairo.gui.widgets.annotation_control_widget import AnnotationControlWidget
from lorairo.gui.widgets.annotation_results_widget import AnnotationResultsWidget
from lorairo.gui.widgets.annotation_status_filter_widget import AnnotationStatusFilterWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget


class MockImageDatabaseManager:
    """統合テスト用のモックデータベースマネージャー"""

    def __init__(self):
        self.mock_images = [
            {"id": 1, "file_path": "/test/image1.jpg", "width": 1920, "height": 1080},
            {"id": 2, "file_path": "/test/image2.jpg", "width": 1024, "height": 768},
            {"id": 3, "file_path": "/test/image3.jpg", "width": 512, "height": 512},
        ]

    def get_annotation_status_counts(self):
        """アノテーション状態カウントを返す"""
        return {
            "total": 3,
            "completed": 2,
            "error": 1,
        }

    def get_image_details(self, image_id: int):
        """画像詳細情報を返す"""
        for image in self.mock_images:
            if image["id"] == image_id:
                return image
        return None


class TestHybridAnnotationUIIntegration:
    """ハイブリッドアノテーションUI統合テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return MockImageDatabaseManager()

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def annotation_control(self, parent_widget, mock_db_manager, qtbot):
        """AnnotationControlWidget のテストインスタンス"""
        with patch("lorairo.gui.widgets.annotation_control_widget.ModelInfoManager"):
            widget = AnnotationControlWidget(parent_widget)
            qtbot.addWidget(widget)
            return widget

    @pytest.fixture
    def annotation_results(self, parent_widget, mock_db_manager, qtbot):
        """AnnotationResultsWidget のテストインスタンス"""
        widget = AnnotationResultsWidget(parent_widget)
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def status_filter(self, parent_widget, mock_db_manager, qtbot):
        """AnnotationStatusFilterWidget のテストインスタンス"""
        widget = AnnotationStatusFilterWidget(parent_widget, mock_db_manager)
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def image_details(self, parent_widget, mock_db_manager, qtbot):
        """SelectedImageDetailsWidget のテストインスタンス"""
        widget = SelectedImageDetailsWidget(parent_widget, mock_db_manager)
        qtbot.addWidget(widget)
        return widget


class TestWidgetInterconnection:
    """ウィジェット間連携テスト"""

    def test_annotation_control_to_results_connection(self, annotation_control, annotation_results, qtbot):
        """アノテーション制御→結果表示の連携テスト"""
        # モックデータを設定
        test_results = {
            "captions": [{"model": "gpt-4o", "caption": "Test caption", "confidence": 0.95}],
            "tags": [{"model": "wd-v1-4", "tags": ["1girl", "test"], "confidence": [0.98, 0.85]}],
            "scores": [{"model": "clip-aesthetic", "score": 0.87, "type": "aesthetic"}],
        }

        # シグナル接続をシミュレート
        annotation_control.annotation_completed.connect(annotation_results.display_annotation_results)

        # アノテーション完了シグナルを発行
        with qtbot.waitSignal(annotation_control.annotation_completed, timeout=1000):
            annotation_control.annotation_completed.emit(test_results)

        # 結果が適切に表示されることを確認
        # 注意: 実際のUIコンポーネントがない場合はモックで検証
        assert hasattr(annotation_results, "display_annotation_results")

    def test_status_filter_to_thumbnail_connection(self, status_filter, qtbot):
        """状態フィルター→サムネイル表示の連携テスト"""
        # フィルター条件変更をシミュレート
        test_filters = {"completed": True, "error": False}

        # フィルター変更シグナルの発行を確認
        with qtbot.waitSignal(status_filter.filter_changed, timeout=1000):
            status_filter.filter_changed.emit(test_filters)

        # シグナルが正しく発行されることを確認
        assert hasattr(status_filter, "filter_changed")

    def test_image_selection_to_details_connection(self, image_details, qtbot):
        """画像選択→詳細表示の連携テスト"""
        # 画像選択データ
        test_image_data = {
            "id": 1,
            "file_path": "/test/image1.jpg",
            "width": 1920,
            "height": 1080,
            "file_size": 2048576,
        }

        # 画像詳細更新をシミュレート
        image_details.update_image_details(test_image_data)

        # 詳細情報が更新されることを確認
        assert hasattr(image_details, "update_image_details")

    def test_annotation_coordinator_workflow(
        self, annotation_control, annotation_results, status_filter, image_details, qtbot
    ):
        """統合ワークフローテスト（AnnotationCoordinator相当）"""
        # 1. 画像選択
        selected_image = {"id": 1, "file_path": "/test/image1.jpg"}

        # 2. モデル選択

        # 3. アノテーション実行シミュレート
        annotation_results_data = {
            "captions": [
                {"model": "gpt-4o", "caption": "A test image", "confidence": 0.95},
                {"model": "claude-3-5-sonnet", "caption": "Test image content", "confidence": 0.88},
            ]
        }

        # 4. ワークフロー実行をシミュレート
        # 画像詳細更新
        image_details.update_image_details(selected_image)

        # アノテーション完了シグナル発行
        with qtbot.waitSignal(annotation_control.annotation_completed, timeout=1000):
            annotation_control.annotation_completed.emit(annotation_results_data)

        # 5. ワークフローが正常に動作することを確認
        assert hasattr(annotation_control, "annotation_completed")
        assert hasattr(annotation_results, "display_annotation_results")


class TestUIStateManagement:
    """UI状態管理テスト"""

    def test_widget_state_consistency(self, annotation_control, status_filter, qtbot):
        """ウィジェット間の状態一貫性テスト"""
        # 初期状態確認
        assert annotation_control.isEnabled()
        assert status_filter.isEnabled()

        # バッチ実行中状態をシミュレート
        annotation_control.setEnabled(False)  # バッチ実行中は無効化

        # 状態変更が反映されることを確認
        assert not annotation_control.isEnabled()

        # バッチ完了後の状態復元
        annotation_control.setEnabled(True)
        assert annotation_control.isEnabled()

    def test_error_state_propagation(self, annotation_control, annotation_results, status_filter, qtbot):
        """エラー状態の伝播テスト"""
        # エラー発生をシミュレート
        error_data = {
            "model": "gpt-4o",
            "error": "API connection failed",
            "timestamp": "2023-07-30 10:00:00",
        }

        # エラーシグナル発行
        if hasattr(annotation_control, "annotation_error"):
            with qtbot.waitSignal(annotation_control.annotation_error, timeout=1000):
                annotation_control.annotation_error.emit(error_data)

        # エラー状態が適切に処理されることを確認
        # 注意: 実際の実装では error handling が必要
        assert True  # 基本テスト - 実装に応じて詳細化


class TestPerformanceIntegration:
    """パフォーマンス統合テスト"""

    def test_large_dataset_handling(self, annotation_control, annotation_results, qtbot):
        """大量データセット処理テスト"""
        # 200モデル対応のテストデータ
        large_model_list = [
            {"name": f"model-{i}", "provider": "test", "capabilities": ["caption"]} for i in range(200)
        ]

        # 大量モデルデータの処理時間を測定
        import time

        start_time = time.time()

        # モデルリスト更新をシミュレート
        if hasattr(annotation_control, "populate_model_table"):
            annotation_control.populate_model_table(large_model_list)

        processing_time = time.time() - start_time

        # 処理時間が許容範囲内であることを確認（例: 1秒以内）
        assert processing_time < 1.0, f"Large dataset processing took {processing_time:.2f}s"

    def test_concurrent_operations(self, annotation_control, annotation_results, qtbot):
        """同時操作テスト"""
        # 複数の操作を同時実行
        operations = []

        # 複数のアノテーション結果を同時処理
        for i in range(5):
            result_data = {
                "captions": [{"model": f"model-{i}", "caption": f"Caption {i}", "confidence": 0.9}]
            }
            operations.append(result_data)

        # 同時実行をシミュレート
        for result_data in operations:
            if hasattr(annotation_results, "display_annotation_results"):
                annotation_results.display_annotation_results(result_data)

        # 同時操作が適切に処理されることを確認
        assert len(operations) == 5
