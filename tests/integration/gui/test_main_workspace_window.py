# tests/integration/gui/test_main_workspace_window.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.lorairo.gui.state.workflow_state import WorkflowStep
from src.lorairo.gui.window.main_workspace_window import MainWorkspaceWindow


class TestMainWorkspaceWindowIntegration:
    """MainWorkspaceWindow の統合テスト"""

    @pytest.fixture
    def app(self):
        """QApplication インスタンス"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
        # テスト後にクリーンアップは不要（他のテストで共有）

    @pytest.fixture
    def main_window(self, app):
        """テスト用メインウィンドウ"""
        with patch("src.lorairo.gui.window.main_workspace_window.DefaultSessionLocal"):
            window = MainWorkspaceWindow()
            yield window
            window.close()

    def test_window_initialization(self, main_window):
        """ウィンドウ初期化テスト"""
        # ウィンドウが正常に作成されることを確認
        assert main_window is not None
        assert main_window.windowTitle() == "LoRAIro - ワークスペース"

        # 状態管理オブジェクトが作成されることを確認
        assert main_window.dataset_state is not None
        assert main_window.workflow_state is not None
        assert main_window.worker_service is not None

        # 初期ワークフローステップの確認
        assert main_window.workflow_state.current_step == WorkflowStep.DATASET_SELECTION

    def test_ui_components_creation(self, main_window):
        """UIコンポーネント作成テスト"""
        # カスタムウィジェットが作成されることを確認
        assert hasattr(main_window, "workflow_navigator")
        assert hasattr(main_window, "filter_search_panel")
        assert hasattr(main_window, "thumbnail_selector")

        # レイアウトが設定されることを確認
        assert main_window.workflow_navigator.parent() is not None
        assert main_window.filter_search_panel.parent() is not None
        assert main_window.thumbnail_selector.parent() is not None

    def test_menu_actions_exist(self, main_window):
        """メニューアクション存在テスト"""
        # 必要なアクションが存在することを確認
        assert main_window.actionOpenDataset is not None
        assert main_window.actionExit is not None
        assert main_window.actionSelectAll is not None
        assert main_window.actionDeselectAll is not None
        assert main_window.actionToggleFilterPanel is not None
        assert main_window.actionTogglePreviewPanel is not None
        assert main_window.actionAnnotation is not None
        assert main_window.actionExport is not None
        assert main_window.actionSettings is not None

    def test_state_management_integration(self, main_window):
        """状態管理統合テスト"""
        # データセット状態とワークフロー状態の連携確認
        dataset_state = main_window.dataset_state
        workflow_state = main_window.workflow_state

        # 初期状態確認
        assert not dataset_state.has_images()
        assert workflow_state.current_step == WorkflowStep.DATASET_SELECTION

        # 状態変更シグナルが接続されていることを確認
        # (実際のシグナル発行は他のテストで確認)
        assert dataset_state.receivers(dataset_state.dataset_loaded) > 0
        assert workflow_state.receivers(workflow_state.step_changed) > 0

    def test_worker_service_integration(self, main_window):
        """ワーカーサービス統合テスト"""
        worker_service = main_window.worker_service

        # ワーカーサービスが正常に初期化されることを確認
        assert worker_service is not None
        assert worker_service.get_active_worker_count() == 0

        # シグナル接続確認
        assert worker_service.receivers(worker_service.batch_registration_finished) > 0

    @patch("src.lorairo.gui.window.main_workspace_window.QFileDialog.getExistingDirectory")
    def test_dataset_selection_dialog(self, mock_dialog, main_window):
        """データセット選択ダイアログテスト"""
        # モックダイアログ設定
        test_path = "/test/dataset/path"
        mock_dialog.return_value = test_path

        # データセット選択実行
        main_window.select_dataset()

        # ダイアログが呼び出されることを確認
        mock_dialog.assert_called_once()

        # パスが設定されることを確認
        assert main_window.lineEditDatasetPath.text() == test_path

    def test_thumbnail_size_slider_integration(self, main_window):
        """サムネイルサイズスライダー統合テスト"""
        slider = main_window.sliderThumbnailSize
        dataset_state = main_window.dataset_state

        # 初期値確認
        assert slider.value() == 128
        assert dataset_state.thumbnail_size == 150  # DatasetStateManagerのデフォルト

        # スライダー値変更
        slider.setValue(200)

        # 状態管理に反映されることを確認
        assert dataset_state.thumbnail_size == 200

    def test_layout_mode_button_integration(self, main_window):
        """レイアウトモードボタン統合テスト"""
        button = main_window.pushButtonLayoutMode
        dataset_state = main_window.dataset_state

        # 初期状態確認
        assert dataset_state.layout_mode == "grid"
        assert button.text() == "Grid"

        # ボタンクリック（リストモードに切り替え）
        button.setChecked(False)
        button.toggled.emit(False)

        # 状態変更確認
        assert dataset_state.layout_mode == "list"
        assert button.text() == "List"

    def test_panel_visibility_toggle(self, main_window):
        """パネル表示切り替えテスト"""
        # 初期状態確認
        assert main_window.frameFilterSearchPanel.isVisible()
        assert main_window.framePreviewDetailPanel.isVisible()

        # フィルターパネル非表示
        main_window.actionToggleFilterPanel.setChecked(False)
        main_window.toggle_filter_panel(False)
        assert not main_window.frameFilterSearchPanel.isVisible()

        # プレビューパネル非表示
        main_window.actionTogglePreviewPanel.setChecked(False)
        main_window.toggle_preview_panel(False)
        assert not main_window.framePreviewDetailPanel.isVisible()

    def test_workflow_navigation_integration(self, main_window):
        """ワークフローナビゲーション統合テスト"""
        workflow_navigator = main_window.workflow_navigator
        workflow_state = main_window.workflow_state

        # 初期ステップ確認
        assert workflow_state.current_step == WorkflowStep.DATASET_SELECTION

        # ワークフロー開始
        workflow_state.start_workflow()

        # ナビゲーターが状態を反映することを確認
        current_step = workflow_navigator.get_current_step()
        assert current_step == WorkflowStep.DATASET_SELECTION

    def test_status_updates_integration(self, main_window):
        """ステータス更新統合テスト"""
        dataset_state = main_window.dataset_state

        # 初期ステータス確認
        assert main_window.labelStatus.text() == "準備完了"

        # 選択変更によるステータス更新
        dataset_state.set_selected_images([1, 2, 3])

        # ステータスが更新されることを確認
        assert "3件の画像を選択中" in main_window.labelStatus.text()

    def test_window_state_summary(self, main_window):
        """ウィンドウ状態サマリーテスト"""
        summary = main_window.get_window_state_summary()

        # サマリーに必要な情報が含まれることを確認
        assert "dataset_loaded" in summary
        assert "workflow_step" in summary
        assert "active_workers" in summary
        assert "selected_images" in summary
        assert "filter_panel_visible" in summary
        assert "preview_panel_visible" in summary

        # 初期値確認
        assert summary["dataset_loaded"] is False
        assert summary["workflow_step"] == "dataset_selection"
        assert summary["active_workers"] == 0
        assert summary["selected_images"] == 0

    @patch("src.lorairo.gui.window.main_workspace_window.QMessageBox.question")
    def test_close_event_with_active_workers(self, mock_question, main_window):
        """アクティブワーカー有りでのクローズイベントテスト"""
        # アクティブワーカーをシミュレート
        with patch.object(main_window.worker_service, "get_active_worker_count", return_value=1):
            # ユーザーがキャンセルを選択
            mock_question.return_value = False  # QMessageBox.StandardButton.No

            # クローズイベント作成
            from PySide6.QtGui import QCloseEvent

            close_event = QCloseEvent()

            # クローズイベント処理
            main_window.closeEvent(close_event)

            # イベントが無視されることを確認
            assert close_event.isAccepted() is False

    def test_keyboard_shortcuts(self, main_window):
        """キーボードショートカットテスト"""
        # ショートカットが設定されていることを確認
        assert main_window.actionOpenDataset.shortcut().toString() == "Ctrl+O"
        assert main_window.actionSelectAll.shortcut().toString() == "Ctrl+A"
        assert main_window.actionDeselectAll.shortcut().toString() == "Ctrl+D"
        assert main_window.actionAnnotation.shortcut().toString() == "Ctrl+T"
        assert main_window.actionExport.shortcut().toString() == "Ctrl+E"
        assert main_window.actionSettings.shortcut().toString() == "Ctrl+,"
        assert main_window.actionExit.shortcut().toString() == "Ctrl+Q"
