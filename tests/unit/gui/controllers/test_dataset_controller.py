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
    manager.initialize_from_dataset_selection.return_value = Path("/test/lorairo_data/project_001")
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
        """正常系:ディレクトリ選択→バッチ登録開始"""
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
            selected_dir, mock_file_system_manager, folder_tags={}
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

    @patch("lorairo.gui.controllers.dataset_controller.show_warning")
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
        mock_msgbox.assert_called_once()
        call_args = mock_msgbox.call_args
        assert call_args[0][0] == mock_parent
        # 内部クラス名は本文に出さず、技術情報は detail へ回す (#1569)
        assert "WorkerService" not in call_args[0][2]
        assert "再起動" in call_args[0][2]
        assert "WorkerService" in call_args.kwargs["detail"]

    @patch("lorairo.gui.controllers.dataset_controller.show_warning")
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

        # Assert: 警告メッセージが表示される
        mock_msgbox.assert_called_once()
        call_args = mock_msgbox.call_args
        assert call_args[0][0] == mock_parent
        assert "FileSystemManager" not in call_args[0][2]
        assert "再起動" in call_args[0][2]
        assert "FileSystemManager" in call_args.kwargs["detail"]

    def test_get_parent_versions_failure_notifies_status_bar(self, mock_parent):
        """親の版一覧の取得に失敗したら、空の候補を返しつつステータスバーへ通知する (#1569)。"""
        db_manager = Mock()
        db_manager.image_repo.session_factory = Mock(side_effect=RuntimeError("boom"))
        controller = DatasetController(
            db_manager=db_manager,
            file_system_manager=Mock(),
            worker_service=Mock(),
            parent=mock_parent,
        )
        with patch(
            "lorairo.gui.controllers.dataset_controller.DatasetRepository",
            side_effect=RuntimeError("boom"),
        ):
            result = controller.get_parent_versions_by_dataset()

        assert result == {}
        mock_parent.statusBar.return_value.showMessage.assert_called_once()
        assert "親の版一覧" in mock_parent.statusBar.return_value.showMessage.call_args[0][0]

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
            selected_dir, mock_file_system_manager, folder_tags={}
        )

    @patch("lorairo.gui.controllers.dataset_controller.show_warning")
    def test_select_and_register_images_worker_submission_failed(
        self,
        mock_warning,
        controller,
        mock_worker_service,
    ):
        """Worker投入失敗時のハンドリング (#1569: 警告ダイアログも表示する)"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_worker_service.start_batch_registration_with_fsm.return_value = None  # 失敗

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: エラーログとユーザー向け警告ダイアログが出力される
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once()
        mock_warning.assert_called_once_with(
            controller.parent, "バッチ登録エラー", "バッチ登録の開始に失敗しました。"
        )

    @patch("lorairo.gui.controllers.dataset_controller.show_critical")
    def test_select_and_register_images_exception_handling(
        self,
        mock_msgbox,
        controller,
        mock_file_system_manager,
    ):
        """例外発生時のエラーハンドリング (#1569: detail に例外文字列を渡す)"""
        # Arrange
        selected_dir = Path("/test/dataset")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_file_system_manager.initialize_from_dataset_selection.side_effect = Exception("Test error")

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: エラーメッセージが表示される
        mock_msgbox.assert_called_once_with(
            controller.parent,
            "バッチ登録エラー",
            "データセット登録の開始に失敗しました。",
            detail="Test error",
        )

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
        expected_output_dir = Path("/test/lorairo_data/project_001")
        mock_dialog_callback = Mock(return_value=selected_dir)
        mock_file_system_manager.initialize_from_dataset_selection.return_value = expected_output_dir

        # Act
        controller.select_and_register_images(mock_dialog_callback)

        # Assert: 新しいメソッドが正しいパラメータで呼ばれる
        mock_file_system_manager.initialize_from_dataset_selection.assert_called_once_with(selected_dir)

        # Assert: 初期化されたFileSystemManagerがWorkerに渡される
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once_with(
            selected_dir, mock_file_system_manager, folder_tags={}
        )


class TestDatasetControllerKohyaImport:
    """設定JSONの有無による分岐と完了/失敗ポップアップ"""

    def _selection(self, configs):
        from lorairo.gui.widgets.dataset_select_dialog import DatasetSelection

        return DatasetSelection(
            directory=Path("/data/set"),
            config_files=tuple(configs),
            dataset_name="ds",
            version_name="v1",
            kohya_import=True,
        )

    def test_selection_without_json_uses_plain_registration(self, controller, mock_worker_service):
        from lorairo.gui.widgets.dataset_select_dialog import DatasetSelection

        sel = DatasetSelection(directory=Path("/data/set"))
        controller.select_and_register_images(Mock(return_value=sel))
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once()
        mock_worker_service.start_dataset_import.assert_not_called()

    def test_selection_without_json_passes_folder_tags(
        self, controller, mock_worker_service, mock_file_system_manager
    ):
        from lorairo.gui.widgets.dataset_select_dialog import DatasetSelection

        sel = DatasetSelection(directory=Path("/data/set"), folder_tags={Path("chara_a"): ("chara a",)})
        controller.select_and_register_images(Mock(return_value=sel))
        mock_worker_service.start_batch_registration_with_fsm.assert_called_once_with(
            Path("/data/set"), mock_file_system_manager, folder_tags={Path("chara_a"): ("chara a",)}
        )

    def test_selection_with_json_starts_dataset_import(
        self, controller, mock_worker_service, mock_file_system_manager
    ):
        cfg = Path("/cfg/a.json")
        controller.select_and_register_images(Mock(return_value=self._selection([cfg])))
        mock_worker_service.start_batch_registration_with_fsm.assert_not_called()
        mock_worker_service.start_dataset_import.assert_called_once_with(
            Path("/data/set"), "ds", "v1", [cfg], mock_file_system_manager, None
        )

    def test_kohya_selection_without_json_starts_dataset_import_with_overrides(
        self, controller, mock_worker_service, mock_file_system_manager
    ):
        """設定 JSON なしでも Kohya 取り込みを選べば取り込みに進み、確定値を渡す (#1453 / #1452)。"""
        from dataclasses import replace

        from lorairo.services.dataset_import_service import FolderOverride

        override = FolderOverride("10_a", include=True, num_repeats=3, trigger_word="trig")
        sel = replace(self._selection([]), folder_overrides=(override,))
        controller.select_and_register_images(Mock(return_value=sel))
        mock_worker_service.start_batch_registration_with_fsm.assert_not_called()
        mock_worker_service.start_dataset_import.assert_called_once_with(
            Path("/data/set"), "ds", "v1", [], mock_file_system_manager, [override]
        )

    def test_dataset_import_start_failure_shows_critical(self, controller, mock_worker_service):
        mock_worker_service.start_dataset_import.side_effect = RuntimeError("boom")
        with patch("lorairo.gui.controllers.dataset_controller.show_critical") as crit:
            controller.select_and_register_images(Mock(return_value=self._selection([Path("/cfg/a.json")])))
        crit.assert_called_once_with(
            controller.parent,
            "データセット取り込みエラー",
            "データセット取り込みの開始に失敗しました。",
            detail="boom",
        )

    def test_finished_shows_result_popup(self, controller):
        from lorairo.services.dataset_import_service import DatasetImportResult

        result = DatasetImportResult(1, 7, 2, 10, 1, [3, 4], images_without_text=5)
        with patch("lorairo.gui.controllers.dataset_controller.show_information") as info:
            controller._on_dataset_import_finished(result)
        text = info.call_args.args[2]
        assert "7" in text and "10" in text and "1" in text and "2" in text
        assert "学習テキストの無い画像数: 5" in text

    def test_error_shows_warning_popup(self, controller):
        with patch("lorairo.gui.controllers.dataset_controller.show_warning") as warn:
            controller._on_dataset_import_error("failed")
        assert warn.call_args.args[2] == "failed"

    def test_selection_with_parent_version_passes_parent_version_id(
        self, controller, mock_worker_service, mock_file_system_manager
    ):
        """選択結果に親の版 ID があれば start_dataset_import へ渡す (#1478)。"""
        from dataclasses import replace

        sel = replace(self._selection([]), parent_version_id=42)
        controller.select_and_register_images(Mock(return_value=sel))
        mock_worker_service.start_dataset_import.assert_called_once_with(
            Path("/data/set"),
            "ds",
            "v1",
            [],
            mock_file_system_manager,
            None,
            parent_version_id=42,
        )

    def test_get_parent_versions_by_dataset_groups_repository_versions(self, controller, mock_db_manager):
        """DatasetRepository.list_versions の結果をデータセット名ごとにまとめる (#1478)。"""
        from lorairo.database.repository.dataset import VersionSummary

        mock_db_manager.image_repo.session_factory = lambda: None
        summaries = [
            VersionSummary(1, "v01", 10, "ds_a", None, None, 1, 5),
            VersionSummary(2, "v02", 10, "ds_a", 1, None, 1, 5),
            VersionSummary(3, "v01", 20, "ds_b", None, None, 2, 8),
        ]
        with patch("lorairo.gui.controllers.dataset_controller.DatasetRepository") as repo_cls:
            repo_cls.return_value.list_versions.return_value = summaries
            grouped = controller.get_parent_versions_by_dataset()

        assert grouped == {
            "ds_a": [(1, "v01"), (2, "v02")],
            "ds_b": [(3, "v01")],
        }

    def test_batch_registration_finished_updates_status_bar(self, controller, mock_parent):
        """登録完了時にステータスバーへ次ステップ案内を表示する (#1550)。"""
        controller._on_batch_registration_finished()
        mock_parent.statusBar.return_value.showMessage.assert_called_once()
        msg = mock_parent.statusBar.return_value.showMessage.call_args.args[0]
        assert "画像の登録が完了しました" in msg
