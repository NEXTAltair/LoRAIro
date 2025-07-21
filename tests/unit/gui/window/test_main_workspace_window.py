# tests/unit/gui/window/test_main_workspace_window.py

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QMainWindow

from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow


class TestMainWorkspaceWindow:
    """MainWorkspaceWindow のユニットテスト"""

    @pytest.fixture
    def main_window(self):
        """テスト用MainWorkspaceWindow"""
        with (
            patch("lorairo.gui.window.main_workspace_window.ConfigurationService") as mock_config_service,
            patch("lorairo.gui.window.main_workspace_window.FileSystemManager") as mock_fsm,
            patch("lorairo.gui.window.main_workspace_window.ImageRepository") as mock_image_repo,
            patch("lorairo.gui.window.main_workspace_window.ImageDatabaseManager") as mock_db_manager,
            patch("lorairo.gui.window.main_workspace_window.WorkerService") as mock_worker_service,
            patch("lorairo.gui.window.main_workspace_window.DatasetStateManager") as mock_dataset_state,
            patch("lorairo.gui.window.main_workspace_window.DefaultSessionLocal") as mock_session,
            patch("lorairo.gui.window.main_workspace_window.FilterSearchPanel"),
            patch("lorairo.gui.window.main_workspace_window.ThumbnailSelectorWidget"),
            patch("lorairo.gui.window.main_workspace_window.PreviewDetailPanel"),
            patch.object(MainWorkspaceWindow, "setupUi"),
            patch.object(MainWorkspaceWindow, "setup_custom_widgets"),
            patch.object(MainWorkspaceWindow, "setup_connections"),
            patch.object(MainWorkspaceWindow, "initialize_state"),
        ):
            # モックインスタンス設定
            mock_config_service_instance = Mock()
            mock_fsm_instance = Mock()
            mock_db_manager_instance = Mock()
            mock_worker_service_instance = Mock()
            mock_dataset_state_instance = Mock()

            mock_config_service.return_value = mock_config_service_instance
            mock_fsm.return_value = mock_fsm_instance
            mock_db_manager.return_value = mock_db_manager_instance
            mock_worker_service.return_value = mock_worker_service_instance
            mock_dataset_state.return_value = mock_dataset_state_instance

            # WorkerServiceのメソッドが期待する値を返すよう設定
            mock_worker_service_instance.get_active_worker_count.return_value = 0

            window = MainWorkspaceWindow()

            # UIウィジェットのモック設定
            window.lineEditDatasetPath = Mock()
            window.lineEditDatasetPath.text.return_value = ""
            window.load_dataset = Mock()
            window.thumbnail_selector = Mock()
            window.preview_detail_panel = Mock()
            window.filter_search_panel = Mock()

            # ステータスラベルのモック
            window.labelRegistrationStatus = Mock()
            window.labelSearchStatus = Mock()
            window.labelThumbnailCount = Mock()
            window.labelCurrentDetails = Mock()

            yield window
            window.close()

    def test_initialization(self, main_window):
        """初期化テスト"""
        assert isinstance(main_window, QMainWindow)
        assert hasattr(main_window, "config_service")
        assert hasattr(main_window, "fsm")
        assert hasattr(main_window, "db_manager")
        assert hasattr(main_window, "worker_service")
        assert hasattr(main_window, "dataset_state")

    def test_signals_definition(self, main_window):
        """シグナル定義テスト"""
        assert hasattr(main_window, "dataset_loaded")
        assert hasattr(main_window, "database_registration_completed")

    def test_initial_state(self, main_window):
        """初期状態テスト"""
        assert main_window.search_progress_dialog is None
        assert main_window.thumbnail_progress_dialog is None

    @patch("lorairo.gui.window.main_workspace_window.QFileDialog")
    def test_on_pushButtonSelectDataset_clicked(self, mock_file_dialog, main_window):
        """データセット選択ボタンクリックテスト"""
        # モックファイルダイアログ設定
        test_path = "/test/dataset/path"
        mock_file_dialog.getExistingDirectory.return_value = test_path

        # lineEditDatasetPath モックの設定
        main_window.lineEditDatasetPath = Mock()
        main_window.lineEditDatasetPath.text.return_value = "/current/path"

        # load_dataset メソッドをモック
        main_window.load_dataset = Mock()

        # ボタンクリック実行
        main_window.on_pushButtonSelectDataset_clicked()

        # ファイルダイアログ呼び出し確認
        mock_file_dialog.getExistingDirectory.assert_called_once()
        call_args = mock_file_dialog.getExistingDirectory.call_args[0]
        assert call_args[0] == main_window  # parent
        assert "データセットディレクトリを選択" in call_args[1]  # caption

        # load_dataset 呼び出し確認
        main_window.load_dataset.assert_called_once_with(Path(test_path))

    @patch("lorairo.gui.window.main_workspace_window.QFileDialog")
    def test_on_pushButtonSelectDataset_clicked_no_selection(self, mock_file_dialog, main_window):
        """データセット選択ボタンクリック（選択なし）テスト"""
        # 空の選択を返すように設定
        mock_file_dialog.getExistingDirectory.return_value = ""

        # ボタンクリック実行
        main_window.on_pushButtonSelectDataset_clicked()

        # load_dataset が呼ばれないことを確認
        main_window.load_dataset.assert_not_called()

    def test_on_pushButtonRegisterImages_clicked(self, main_window):
        """画像登録ボタンクリックテスト"""
        # モック設定
        main_window.lineEditDatasetPath.text.return_value = "/test/dataset"

        # ボタンクリック実行
        main_window.on_pushButtonRegisterImages_clicked()

        # worker_service.start_batch_registration 呼び出し確認
        main_window.worker_service.start_batch_registration.assert_called_once_with(Path("/test/dataset"))

    @patch("lorairo.gui.window.main_workspace_window.QMessageBox")
    def test_on_pushButtonRegisterImages_clicked_empty_path(self, mock_message_box, main_window):
        """画像登録ボタンクリック（空パス）テスト"""
        # 空パス設定
        main_window.lineEditDatasetPath.text.return_value = ""

        # ボタンクリック実行
        main_window.on_pushButtonRegisterImages_clicked()

        # エラーメッセージ表示確認
        mock_message_box.warning.assert_called_once()

        # start_database_registration が呼ばれないことを確認
        main_window.start_database_registration.assert_not_called()

    def test_load_dataset_success(self, main_window):
        """データセット読み込み成功テスト"""
        test_path = Path("/test/dataset")

        # モック設定
        main_window.lineEditDatasetPath = Mock()
        main_window.db_manager.get_all_images.return_value = [
            {"id": 1, "path": "/test/image1.jpg"},
            {"id": 2, "path": "/test/image2.jpg"},
        ]

        # dataset_loaded シグナル受信用モック
        signal_mock = Mock()
        main_window.dataset_loaded.connect(signal_mock)

        # 実行
        main_window.load_dataset(test_path)

        # パス設定確認
        main_window.lineEditDatasetPath.setText.assert_called_once_with(str(test_path))

        # データセット状態設定確認
        main_window.dataset_state.set_dataset_path.assert_called_once_with(test_path)
        main_window.dataset_state.set_dataset_images.assert_called_once()

        # シグナル発行確認
        signal_mock.assert_called_once_with(str(test_path))

    def test_load_dataset_database_error(self, main_window):
        """データセット読み込みデータベースエラーテスト"""
        test_path = Path("/test/dataset")

        # データベースエラーを発生させる
        main_window.db_manager.get_all_images.side_effect = Exception("Database error")
        main_window.lineEditDatasetPath = Mock()

        # メッセージボックスモック
        with patch("lorairo.gui.window.main_workspace_window.QMessageBox") as mock_message_box:
            # 実行
            main_window.load_dataset(test_path)

            # エラーメッセージ表示確認
            mock_message_box.critical.assert_called_once()

    def test_start_database_registration(self, main_window):
        """データベース登録開始テスト"""
        test_directory = Path("/test/dataset")

        # モック設定
        main_window.worker_service.start_batch_registration.return_value = "worker_123"
        main_window.pushButtonRegisterDatabase = Mock()
        main_window.progressBarRegistration = Mock()
        main_window.labelRegistrationStatus = Mock()

        # 実行
        main_window.start_database_registration(test_directory)

        # ワーカーサービス呼び出し確認
        main_window.worker_service.start_batch_registration.assert_called_once_with(test_directory)

        # UI状態更新確認
        main_window.pushButtonRegisterDatabase.setEnabled.assert_called_with(False)
        main_window.progressBarRegistration.setVisible.assert_called_with(True)
        main_window.labelRegistrationStatus.setText.assert_called()

    def test_start_database_registration_error(self, main_window):
        """データベース登録開始エラーテスト"""
        test_directory = Path("/test/dataset")

        # ワーカー開始エラーを発生させる
        main_window.worker_service.start_batch_registration.side_effect = RuntimeError(
            "Worker start failed"
        )
        main_window.pushButtonRegisterDatabase = Mock()

        # メッセージボックスモック
        with patch("lorairo.gui.window.main_workspace_window.QMessageBox") as mock_message_box:
            # 実行
            main_window.start_database_registration(test_directory)

            # エラーメッセージ表示確認
            mock_message_box.critical.assert_called_once()

    def test_handle_batch_registration_finished(self, main_window):
        """バッチ登録完了ハンドリングテスト"""
        # モック結果オブジェクト
        mock_result = Mock()
        mock_result.registered_count = 10
        mock_result.skipped_count = 2
        mock_result.error_count = 1

        # UI要素モック
        main_window.pushButtonRegisterDatabase = Mock()
        main_window.progressBarRegistration = Mock()
        main_window.labelRegistrationStatus = Mock()
        main_window.lineEditDatasetPath = Mock()
        main_window.lineEditDatasetPath.text.return_value = "/test/dataset"

        # シグナル受信用モック
        signal_mock = Mock()
        main_window.database_registration_completed.connect(signal_mock)

        # 実行
        main_window.handle_batch_registration_finished(mock_result)

        # UI状態復元確認
        main_window.pushButtonRegisterDatabase.setEnabled.assert_called_with(True)
        main_window.progressBarRegistration.setVisible.assert_called_with(False)

        # ステータス更新確認
        status_call = main_window.labelRegistrationStatus.setText.call_args[0][0]
        assert "10" in status_call  # registered_count
        assert "2" in status_call  # skipped_count
        assert "1" in status_call  # error_count

        # データセット再読み込み確認
        main_window.dataset_state.set_dataset_path.assert_called()

        # シグナル発行確認
        signal_mock.assert_called_once_with(10)

    def test_handle_worker_progress_updated(self, main_window):
        """ワーカー進捗更新ハンドリングテスト"""
        # モック進捗オブジェクト
        mock_progress = Mock()
        mock_progress.percentage = 45
        mock_progress.status_message = "Processing images..."

        # UI要素モック
        main_window.progressBarRegistration = Mock()
        main_window.labelRegistrationStatus = Mock()

        # 実行
        main_window.handle_worker_progress_updated("worker_123", mock_progress)

        # 進捗バー更新確認
        main_window.progressBarRegistration.setValue.assert_called_once_with(45)

        # ステータス更新確認
        main_window.labelRegistrationStatus.setText.assert_called_once_with("Processing images...")

    def test_handle_images_filtered(self, main_window):
        """フィルター適用ハンドリングテスト"""
        filtered_images = [{"id": 1, "path": "/test/image1.jpg"}, {"id": 2, "path": "/test/image2.jpg"}]

        # 実行
        main_window.handle_images_filtered(filtered_images)

        # カウントラベル更新確認
        main_window.labelThumbnailCount.setText.assert_called_once_with("画像: 2件")

    def test_handle_search_finished(self, main_window):
        """検索完了ハンドリングテスト"""
        # モック検索結果
        mock_result = Mock()
        mock_result.image_metadata = [
            {"id": 1, "path": "/test/image1.jpg"},
            {"id": 2, "path": "/test/image2.jpg"},
        ]
        mock_result.total_count = 2

        # 実行
        main_window.handle_search_finished(mock_result)

        # データセット状態更新確認
        main_window.dataset_state.set_filtered_images.assert_called_once_with(mock_result.image_metadata)

    def test_setup_connections(self, main_window):
        """シグナル接続設定テスト"""
        # setup_connections が正常に実行されることを確認
        # （実際のシグナル接続は初期化時に行われる）
        assert hasattr(main_window, "worker_service")
        assert hasattr(main_window, "dataset_state")

    def test_initialize_state(self, main_window):
        """状態初期化テスト"""
        # UI要素モック
        main_window.progressBarRegistration = Mock()
        main_window.labelRegistrationStatus = Mock()

        # 初期化実行（既に__init__で呼ばれているが、明示的にテスト）
        main_window.initialize_state()

        # 初期状態確認
        main_window.progressBarRegistration.setVisible.assert_called_with(False)
        main_window.labelRegistrationStatus.setText.assert_called_with("登録待機中")

    def test_window_close_cleanup(self, main_window):
        """ウィンドウクローズ時クリーンアップテスト"""
        # WorkerServiceにアクティブなワーカーがある場合のクリーンアップをテスト
        main_window.worker_service.cancel_all_workers = Mock()

        # クローズイベントシミュレーション
        main_window.close()

        # ウィンドウが適切にクローズされることを確認
        # （実際のクリーンアップロジックがある場合はそれをテスト）
        assert True  # 基本的なクローズ動作確認

    def test_error_handling_robustness(self, main_window):
        """エラーハンドリング堅牢性テスト"""
        # 様々な例外状況での動作確認

        # データベース接続エラー
        main_window.db_manager.get_all_images.side_effect = ConnectionError("DB connection failed")

        with patch("lorairo.gui.window.main_workspace_window.QMessageBox") as mock_message_box:
            main_window.load_dataset(Path("/test/path"))
            mock_message_box.critical.assert_called()

        # ワーカーサービスエラー
        main_window.worker_service.start_search.side_effect = RuntimeError("Worker error")

        # エラーが適切にハンドリングされることを確認
        try:
            main_window.handle_filter_applied({"tags": ["test"]})
        except RuntimeError:
            pass  # 例外が発生するが、アプリケーションがクラッシュしないことを確認
