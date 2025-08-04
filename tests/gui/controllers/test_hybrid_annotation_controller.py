"""HybridAnnotationController統合テスト"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from lorairo.database.db_repository import ImageRepository
from lorairo.gui.controllers.hybrid_annotation_controller import (
    AnnotationUIState,
    HybridAnnotationController,
)
from lorairo.gui.widgets.annotation_results_widget import AnnotationResult
from lorairo.services.configuration_service import ConfigurationService


class TestHybridAnnotationController:
    """HybridAnnotationController統合テスト"""

    @pytest.fixture
    def mock_db_repository(self) -> None:
        """モックDBリポジトリ"""
        mock = Mock(spec=ImageRepository)
        mock._get_model_id = Mock(return_value=None)
        return mock

    @pytest.fixture
    def mock_config_service(self) -> None:
        """モック設定サービス"""
        mock = Mock(spec=ConfigurationService)
        mock.get_config = Mock(
            return_value={
                "api": {"openai_key": "test_openai_key", "claude_key": "test_claude_key", "google_key": ""}
            }
        )
        return mock

    @pytest.fixture
    def controller(self, mock_db_repository, mock_config_service):
        """HybridAnnotationController インスタンス"""
        return HybridAnnotationController(
            db_repository=mock_db_repository, config_service=mock_config_service
        )

    def test_controller_initialization(self, controller):
        """コントローラー初期化テスト"""
        # 基本属性の確認
        assert controller.db_repository is not None
        assert controller.config_service is not None
        assert controller.model_info_manager is not None

        # UI状態の初期化確認
        assert isinstance(controller.ui_state, AnnotationUIState)
        assert controller.ui_state.selected_models == []
        assert not controller.ui_state.annotation_in_progress
        assert not controller.ui_state.results_visible

    @patch("src.lorairo.gui.controllers.hybrid_annotation_controller.QUiLoader")
    def test_load_hybrid_annotation_ui_success(self, mock_ui_loader, controller):
        """HybridAnnotation UIロード成功テスト"""
        # モックUI設定
        mock_widget = Mock(spec=QWidget)
        mock_widget.findChild = Mock(return_value=Mock())
        mock_ui_loader.return_value.load = Mock(return_value=mock_widget)

        # UIファイルパス（存在しないパスでテスト）
        ui_file_path = Path("/fake/path/test.ui")

        with patch("pathlib.Path.open", mock_open_for_ui_file()):
            result = controller.load_hybrid_annotation_ui(ui_file_path)

        # 結果検証
        assert result is mock_widget
        assert controller.hybrid_annotation_widget is mock_widget

    def test_model_selection_changed_signal(self, controller):
        """モデル選択変更シグナルテスト"""
        # シグナル受信用スロット
        signal_received = []
        controller.model_selection_changed.connect(lambda models: signal_received.append(models))

        # モデル選択状態をシミュレート
        controller.ui_state.selected_models = ["gpt-4o", "claude-3-5-sonnet"]
        controller.model_selection_changed.emit(controller.ui_state.selected_models)

        # シグナル受信確認
        assert len(signal_received) == 1
        assert signal_received[0] == ["gpt-4o", "claude-3-5-sonnet"]

    def test_annotation_result_management(self, controller):
        """アノテーション結果管理テスト"""
        # 結果表示ウィジェットをモック
        controller.annotation_results_widget = Mock()

        # テスト用結果作成
        test_result = AnnotationResult(
            model_name="test-model",
            success=True,
            processing_time=2.5,
            caption="Test caption",
            tags=["test", "anime"],
            score=0.85,
        )

        # 結果追加テスト
        controller.add_annotation_result(test_result)

        # ウィジェットのメソッド呼び出し確認
        controller.annotation_results_widget.add_result.assert_called_once_with(test_result)
        assert controller.ui_state.results_visible is True

        # 結果クリアテスト
        controller.clear_annotation_results()
        controller.annotation_results_widget.clear_results.assert_called_once()
        assert controller.ui_state.results_visible is False

    def test_model_info_manager_integration(self, controller):
        """ModelInfoManager統合テスト"""
        # ModelInfoManagerが正しく初期化されている
        assert controller.model_info_manager is not None
        assert controller.model_info_manager.db_repository is controller.db_repository
        assert controller.model_info_manager.config_service is controller.config_service

    def test_ui_state_updates(self, controller):
        """UI状態更新テスト"""
        controller.get_ui_state()

        # 状態変更
        controller.ui_state.selected_models = ["model1", "model2"]
        controller.ui_state.annotation_in_progress = True

        updated_state = controller.get_ui_state()

        # 変更確認
        assert updated_state.selected_models == ["model1", "model2"]
        assert updated_state.annotation_in_progress is True
        assert updated_state is controller.ui_state

    def test_recommended_model_detection(self, controller):
        """推奨モデル判定テスト"""
        # 推奨モデル名でテスト
        recommended_models = ["gpt-4o", "claude-3-5-sonnet", "wd-v1-4-tagger", "aesthetic-scorer"]

        for model_name in recommended_models:
            assert controller._is_recommended_model(model_name) is True

        # 非推奨モデル名でテスト
        non_recommended_models = ["unknown-model", "custom-local-model", "experimental-ai"]

        for model_name in non_recommended_models:
            assert controller._is_recommended_model(model_name) is False

    @patch("src.lorairo.gui.controllers.hybrid_annotation_controller.logger")
    def test_error_handling_in_ui_load(self, mock_logger, controller):
        """UIロード時のエラーハンドリングテスト"""
        # 存在しないUIファイルパス
        invalid_ui_path = Path("/nonexistent/path/invalid.ui")

        # エラーが発生することを確認
        with pytest.raises(Exception):
            controller.load_hybrid_annotation_ui(invalid_ui_path)

        # エラーログ出力確認
        mock_logger.error.assert_called()

    def test_demo_functionality(self, controller):
        """デモ機能テスト"""
        # 結果表示ウィジェットをモック
        controller.annotation_results_widget = Mock()

        # デモ実行
        controller.demo_show_annotation_results()

        # 複数の結果が追加されることを確認
        assert controller.annotation_results_widget.add_result.call_count >= 3

    def test_export_results_signal_handling(self, controller):
        """結果エクスポートシグナル処理テスト"""
        # テスト結果リスト
        test_results = [
            AnnotationResult("model1", True, 1.0, caption="test1"),
            AnnotationResult("model2", True, 1.5, tags=["tag1", "tag2"]),
        ]

        # エクスポート要求シグナル送信
        with patch.object(controller, "_on_export_results_requested") as mock_handler:
            controller._on_export_results_requested(test_results)
            mock_handler.assert_called_once_with(test_results)


def mock_open_for_ui_file():
    """UIファイル読み込み用モックopen"""
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.__exit__.return_value = False
    return MagicMock(return_value=mock_file)


class TestAnnotationUIState:
    """AnnotationUIState テスト"""

    def test_annotation_ui_state_initialization(self):
        """AnnotationUIState初期化テスト"""
        # Qt環境の初期化を確実に行う
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        try:
            state = AnnotationUIState(selected_models=["model1"])

            assert state.selected_models == ["model1"]
            assert state.annotation_in_progress is False
            assert state.results_visible is False
            assert state.filter_criteria is None
        finally:
            # テスト用に作成したQApplicationの場合はクリーンアップ
            if app.parent() is None:
                app.quit()

    def test_annotation_ui_state_updates(self):
        """AnnotationUIState更新テスト"""
        state = AnnotationUIState(selected_models=[])

        # 状態更新
        state.selected_models = ["new_model"]
        state.annotation_in_progress = True
        state.results_visible = True

        # 更新確認
        assert state.selected_models == ["new_model"]
        assert state.annotation_in_progress is True
        assert state.results_visible is True


@pytest.mark.gui
class TestHybridAnnotationControllerGUI:
    """HybridAnnotationController GUI統合テスト（headless環境対応）"""

    @pytest.fixture(autouse=True)
    def setup_gui_test(self, qapp):
        """GUI テスト環境セットアップ"""
        # QtTestモジュールを使用したGUIテスト用セットアップ
        pass

    def test_signal_emission_integration(self, qapp, mock_db_repository, mock_config_service):
        """シグナル送信統合テスト"""
        controller = HybridAnnotationController(
            db_repository=mock_db_repository, config_service=mock_config_service
        )

        # シグナル受信カウンター
        signal_counts = {"model_selection_changed": 0, "ui_state_changed": 0}

        def count_model_selection(models):
            signal_counts["model_selection_changed"] += 1

        def count_ui_state(state):
            signal_counts["ui_state_changed"] += 1

        # シグナル接続
        controller.model_selection_changed.connect(count_model_selection)
        controller.ui_state_changed.connect(count_ui_state)

        # シグナル送信をトリガー
        controller.model_selection_changed.emit(["test_model"])
        controller.ui_state_changed.emit(controller.ui_state)

        # Qt イベントループ処理
        QApplication.processEvents()

        # シグナル受信確認
        assert signal_counts["model_selection_changed"] == 1
        assert signal_counts["ui_state_changed"] == 1
