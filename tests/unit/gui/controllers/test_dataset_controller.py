# tests/unit/gui/controllers/test_dataset_controller.py
"""DatasetControllerのユニットテスト"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.controllers.dataset_controller import DatasetController


@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManagerのモック"""
    return Mock()


@pytest.fixture
def mock_file_system_manager():
    """FileSystemManagerのモック"""
    manager = Mock()
    manager.initialize_from_dataset_selection.return_value = Path("/test/lorairo_output")
    return manager


@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.start_batch_registration_with_fsm.return_value = "worker-id-123"
    return service


@pytest.fixture
def mock_parent():
    """親ウィンドウのモック"""
    return Mock()


@pytest.fixture
def controller(mock_db_manager, mock_file_system_manager, mock_worker_service, mock_parent):
    """DatasetController fixture"""
    return DatasetController(
        mock_db_manager,
        mock_file_system_manager,
        mock_worker_service,
        mock_parent,
    )


class TestDatasetController:
    """DatasetControllerのテストクラス"""

    def test_init(self, mock_db_manager, mock_file_system_manager, mock_worker_service, mock_parent):
        """初期化が正常に行われる"""
        controller = DatasetController(
            mock_db_manager,
            mock_file_system_manager,
            mock_worker_service,
            mock_parent,
        )
        assert controller.db_manager == mock_db_manager
        assert controller.file_system_manager == mock_file_system_manager
        assert controller.worker_service == mock_worker_service
        assert controller.parent == mock_parent

    def test_init_without_parent(self, mock_db_manager, mock_file_system_manager, mock_worker_service):
        """親なしでも初期化できる"""
        controller = DatasetController(
            mock_db_manager,
            mock_file_system_manager,
            mock_worker_service,
            None,
        )
        assert controller.db_manager == mock_db_manager
        assert controller.file_system_manager == mock_file_system_manager
        assert controller.worker_service == mock_worker_service
        assert controller.parent is None

    def test_select_and_register_images_success(
        self,
        controller,
        mock_file_system_manager,
        mock_worker_service,
    ):
        """正常系：ディレクトリ選択→バッチ登録開始"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: callbackが呼ばれる
        mock_dialog_callback.assert_called_once()

        # Assert: FileSystemManagerが初期化される
        mock_file_system_manager.initialize_from_dataset_selection.assert_called_once_with(selected_dir)

        # Assert: WorkerServiceが呼ばれる
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once_with(
            selected_dir, mock_file_system_manager
        )

    def test_select_and_register_images_user_cancel(self, controller):
        """ユーザーがキャンセル時は処理を中断"""
        # Arrange
        mock_dialog_callback = Mock(return_value=None)

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: callbackが呼ばれる
        mock_dialog_callback.assert_called_once()

        # Assert: その後の処理は実行されない
        controller.file_system_manager.initialize_from_dataset_selection.assert_not_called()
        controller.worker_service.start_batch_registration_with_fsm.assert_not_called()

    @patch("lorairo.gui.controllers.dataset_controller.QMessageBox")
    def test_select_and_register_images_no_worker_service(self, mock_msgbox, mock_parent):
        """WorkerServiceがない場合は警告表示"""
        # Arrange
        controller = DatasetController(
            db_manager=Mock(),
            file_system_manager=Mock(),
            worker_service=None,  # WorkerServiceなし
            parent=mock_parent,
        )
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: 警告メッセージが表示される
        mock_msgbox.warning.assert_called_once()
        call_args = mock_msgbox.warning.call_args
        assert call_args[0][0] == mock_parent
        assert "WorkerService" in call_args[0][2]

    @patch("lorairo.gui.controllers.dataset_controller.QMessageBox")
    def test_select_and_register_images_no_filesystem_manager(self, mock_msgbox, mock_parent):
        """FileSystemManagerがない場合はエラー表示"""
        # Arrange
        controller = DatasetController(
            db_manager=Mock(),
            file_system_manager=None,  # FileSystemManagerなし
            worker_service=Mock(),
            parent=mock_parent,
        )
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: クリティカルエラーメッセージが表示される
        mock_msgbox.critical.assert_called_once()
        call_args = mock_msgbox.critical.call_args
        assert call_args[0][0] == mock_parent
        assert "FileSystemManager" in call_args[0][2]

    def test_select_and_register_images_worker_submission(
        self,
        controller,
        mock_file_system_manager,
        mock_worker_service,
    ):
        """Worker投入が正しく行われることを確認"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)
        worker_id = "test-worker-id"
        mock_worker_service.start_batch_registration_with_fsm.return_value = worker_id

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: Worker IDが返される
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once_with(
            selected_dir, mock_file_system_manager
        )

    def test_select_and_register_images_worker_submission_failed(
        self,
        controller,
        mock_worker_service,
    ):
        """Worker投入失敗時のハンドリング"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_worker_service.start_batch_registration_with_fsm.return_value = None  # 失敗

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: エラーログが出力される（例外は発生しない）
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once()

    @patch("lorairo.gui.controllers.dataset_controller.QMessageBox")
    def test_select_and_register_images_exception_handling(
        self,
        mock_msgbox,
        controller,
        mock_file_system_manager,
    ):
        """例外発生時のエラーハンドリング"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_file_system_manager.initialize_from_dataset_selection.side_effect = Exception(
            "Test error"
        )

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: エラーメッセージが表示される
        mock_msgbox.critical.assert_called_once()
        call_args = mock_msgbox.critical.call_args
        assert call_args[0][0] == controller.parent
        assert "Test error" in call_args[0][2]

    def test_select_and_register_images_no_parent(
        self,
        mock_db_manager,
        mock_file_system_manager,
        mock_worker_service,
    ):
        """親なしでも正常に動作する"""
        # Arrange
        controller = DatasetController(
            mock_db_manager,
            mock_file_system_manager,
            mock_worker_service,
            None,  # 親なし
        )
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: 正常に処理が完了する
        mock_file_system_manager.initialize_from_dataset_selection.assert_called_once()
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once()

    def test_filesystem_manager_integration(
        self,
        controller,
        mock_file_system_manager,
        mock_worker_service,
    ):
        """FileSystemManagerの新しいメソッドが正しく呼ばれる"""
        # Arrange
        selected_dir = Path("/test/dataset")
        expected_output_dir = Path("/test/lorairo_output")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_file_system_manager.initialize_from_dataset_selection.return_value = expected_output_dir

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: 新しいメソッドが正しいパラメータで呼ばれる
        mock_file_system_manager.initialize_from_dataset_selection.assert_called_once_with(selected_dir)

        # Assert: 初期化されたFileSystemManagerがWorkerに渡される
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once_with(
            selected_dir, mock_file_system_manager
        )
