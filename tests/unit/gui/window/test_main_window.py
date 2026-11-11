"""MainWindow ユニットテスト

責任分離後のMainWindowのビジネスロジックをテスト
- データベースアクセスロジック
- エラーハンドリング
- サービス統合

Note: これらのテストはGUIコンポーネントを実際に作成せず、
ビジネスロジックのみをテストします。
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

# NOTE: #869 で以下のロジックは SearchTabWidget へ移送された。これらの振る舞い
# 検証は tests/unit/gui/tab/test_search_tab.py が担う:
#   - ImageDBWriteService 配線 (_setup_image_db_write_service) と
#     SelectedImageDetailsWidget / ImagePreviewWidget の DatasetStateManager 接続
#   - バッチ Rating/Score 書込 (_handle_batch_rating_changed / _handle_batch_score_changed)
#   - 選択変更 → 詳細表示クリア (_handle_selection_changed_for_rating)


class TestMainWindowAnnotationCompletion:
    """アノテーション完了ハンドラーテスト"""

    @pytest.fixture
    def mock_window_with_annotation(self):
        """アノテーション完了テスト用のモックMainWindow"""
        window = Mock()
        window._closing = False
        window.dataset_state_manager = Mock()
        window.db_manager = Mock()
        window.db_manager.repository = Mock()
        window.statusBar = Mock(return_value=Mock())
        return window

    @staticmethod
    def _make_execution_result(results):
        """AnnotationWorker.execute() が返す現行形式の結果を構築する (#1187)"""
        from lorairo.gui.workers.annotation_worker import AnnotationExecutionResult

        return AnnotationExecutionResult(
            results=results,
            total_images=len(results),
            models_used=["model1"],
        )

    def test_on_annotation_finished_schedules_annotation_refresh(self, mock_window_with_annotation):
        """完了ハンドラはpHashを渡し、GUI上でDB再取得しない。"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result(
            {
                "abc123def456": {"model1": Mock()},
                "xyz789ghi012": {"model1": Mock()},
            }
        )

        with patch(
            "lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"
        ) as mock_dialog_class:
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

        # サマリーダイアログが実行結果とともに表示される
        mock_dialog_class.assert_called_once_with(result, parent=mock_window_with_annotation)
        mock_dialog_class.return_value.exec.assert_called_once()

        mock_window_with_annotation.dataset_state_manager.refresh_annotations_after_execution.assert_called_once_with(
            {"abc123def456", "xyz789ghi012"}
        )
        mock_window_with_annotation.db_manager.image_repo.find_image_ids_by_phashes_multi.assert_not_called()
        mock_window_with_annotation.dataset_state_manager.refresh_images.assert_not_called()

    def test_on_annotation_finished_handles_empty_result(self, mock_window_with_annotation):
        """空の結果でもダイアログ表示のみでエラーが発生しない"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result({})

        with patch(
            "lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"
        ) as mock_dialog_class:
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

        mock_dialog_class.return_value.exec.assert_called_once()
        # 結果が空なら pHash 検索は行わない
        assert not mock_window_with_annotation.db_manager.image_repo.find_image_ids_by_phashes_multi.called
        mock_window_with_annotation.dataset_state_manager.refresh_annotations_after_execution.assert_not_called()

    def test_on_annotation_finished_handles_missing_dependencies(self):
        """依存関係なし時はダイアログ表示後に早期リターン"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window._closing = False
        mock_window.dataset_state_manager = None
        mock_window.db_manager = Mock()

        result = self._make_execution_result({"abc": {"model1": Mock()}})

        with patch(
            "lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"
        ) as mock_dialog_class:
            MainWindow._on_annotation_finished(mock_window, result)

        mock_dialog_class.return_value.exec.assert_called_once()
        # find_image_ids_by_phashes_multi は呼ばれない
        assert not mock_window.db_manager.image_repo.find_image_ids_by_phashes_multi.called

    def test_on_annotation_finished_handles_refresh_start_failure(self, mock_window_with_annotation):
        """更新開始失敗を保存結果と区別し、成功ログを出さない。"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result({"abc123": {"model1": Mock()}})
        mock_window_with_annotation.dataset_state_manager.refresh_annotations_after_execution.side_effect = Exception(
            "DB error"
        )

        with (
            patch("lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"),
            patch("lorairo.gui.window.main_window.logger") as mock_logger,
        ):
            mock_logger.opt.return_value = mock_logger  # opt(exception=True).error 経路を捕捉 (#1153)
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

            # エラーログが出力される
            mock_logger.error.assert_called_once()
            assert "画面更新開始失敗" in mock_logger.error.call_args[0][0]
            assert "保存結果とは別" in mock_logger.error.call_args[0][0]
            mock_logger.info.assert_not_called()

    def test_on_annotation_finished_ignores_completion_after_close(self, mock_window_with_annotation):
        from lorairo.gui.window.main_window import MainWindow

        mock_window_with_annotation._closing = True
        result = self._make_execution_result({"abc": {"model1": Mock()}})

        with patch("lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog") as dialog:
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

        dialog.assert_not_called()
        mock_window_with_annotation.dataset_state_manager.refresh_annotations_after_execution.assert_not_called()

    def test_on_annotation_finished_ignores_close_during_summary(self, mock_window_with_annotation):
        """サマリーのネストしたイベントループで閉じても新しい取得を開始しない。"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result({"abc": {"model1": Mock()}})

        def close_during_dialog():
            mock_window_with_annotation._closing = True

        with patch("lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog") as dialog:
            dialog.return_value.exec.side_effect = close_during_dialog
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

        mock_window_with_annotation.dataset_state_manager.refresh_annotations_after_execution.assert_not_called()

    def test_summary_dialog_navigation_and_restage_handlers(self, mock_window_with_annotation):
        """サマリーダイアログの各ハンドラがタブ遷移および再ステージングを行う (#1557)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window_with_annotation.tabWidgetMainMode = Mock()
        mock_window_with_annotation.tabResults = Mock()
        mock_window_with_annotation.tabErrors = Mock()
        mock_window_with_annotation.tabBatchTag = Mock()
        mock_window_with_annotation.statusBar = Mock(return_value=Mock())

        MainWindow._on_summary_open_results(mock_window_with_annotation)
        mock_window_with_annotation.tabWidgetMainMode.setCurrentWidget.assert_called_with(
            mock_window_with_annotation.tabResults
        )

        MainWindow._on_summary_open_errors(mock_window_with_annotation)
        mock_window_with_annotation.tabWidgetMainMode.setCurrentWidget.assert_called_with(
            mock_window_with_annotation.tabErrors
        )

        mock_window_with_annotation.staging_state_manager = Mock()
        mock_window_with_annotation.db_manager.get_image_id_by_filepath.return_value = 42
        mock_window_with_annotation.dataset_state_manager.get_image_by_id.return_value = None
        mock_window_with_annotation.db_manager.get_image_metadata.return_value = {"id": 42}

        MainWindow._restage_failed_annotation_paths(mock_window_with_annotation, ["/path/failed.jpg"])
        mock_window_with_annotation.staging_state_manager.add_image_ids.assert_called_once_with([42])
        mock_window_with_annotation.tabWidgetMainMode.setCurrentWidget.assert_called_with(
            mock_window_with_annotation.tabBatchTag
        )

    def test_close_stops_annotation_refresh_before_other_shutdown(self, qtbot):
        """実際のQt closeイベントで、終了フラグを立ててから取得を停止する。"""
        from PySide6.QtWidgets import QMainWindow

        from lorairo.gui.window.main_window import MainWindow

        with patch.object(MainWindow, "__init__", QMainWindow.__init__):
            window = MainWindow()
        qtbot.addWidget(window)
        window._closing = False
        window._save_window_state = Mock()
        window.dataset_state_manager = Mock()
        window.export_tab = None
        window.search_tab = None
        window.results_tab = None
        window.annotate_tab = None
        window.jobs_tab = None

        def check_closing():
            assert window._closing is True
            window._save_window_state.assert_not_called()

        window.dataset_state_manager.shutdown_annotation_refresh.side_effect = check_closing
        window.close()

        window.dataset_state_manager.shutdown_annotation_refresh.assert_called_once_with()
        window._save_window_state.assert_called_once_with()
        window.dataset_state_manager.shutdown_annotation_refresh.side_effect = None

    def test_setup_worker_pipeline_signals_includes_annotation(self):
        """WorkerService pipeline シグナル接続にアノテーション完了が含まれる"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.worker_service = Mock()
        # required_signalsを全て持つようにモック (batch_import_* は JobsTabWidget が
        # self-wire するため、ここでの接続対象には含めない、#874)
        for signal_name in [
            "batch_registration_started",
            "batch_registration_finished",
            "batch_registration_error",
            "batch_registration_canceled",
            "enhanced_annotation_finished",
            "enhanced_annotation_error",
            "enhanced_annotation_canceled",
            "enhanced_annotation_started",
            "batch_import_started",
            "worker_progress_updated",
            "worker_batch_progress",
            "operation_event",
        ]:
            setattr(mock_window.worker_service, signal_name, Mock())

        with patch("lorairo.gui.window.main_window.logger"):
            MainWindow._setup_worker_pipeline_signals(mock_window)

            for signal_name in [
                "batch_registration_started",
                "batch_registration_finished",
                "batch_registration_error",
                "batch_registration_canceled",
                "enhanced_annotation_finished",
                "enhanced_annotation_error",
                "enhanced_annotation_canceled",
                "worker_progress_updated",
                "worker_batch_progress",
                "operation_event",
            ]:
                getattr(mock_window.worker_service, signal_name).connect.assert_called_once()

    def test_worker_operation_event_updates_error_notification_for_current_failure(self):
        """current な operation failure は pipeline 委譲後にエラー通知を更新する"""
        from lorairo.gui.services.operation_events import OperationOutcome, OperationType
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        mock_window._delegate_to_pipeline_control = Mock()
        event = SimpleNamespace(
            operation_type=OperationType.SEARCH,
            outcome=OperationOutcome.FAILED,
            is_current=True,
        )

        MainWindow._on_worker_operation_event(mock_window, event)

        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_operation_event", event)
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_worker_operation_event_ignores_superseded_failure_notification(self):
        """superseded operation failure は stale なのでエラー通知数を更新しない"""
        from lorairo.gui.services.operation_events import OperationOutcome, OperationType
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        mock_window._delegate_to_pipeline_control = Mock()
        event = SimpleNamespace(
            operation_type=OperationType.SEARCH,
            outcome=OperationOutcome.FAILED,
            is_current=False,
        )

        MainWindow._on_worker_operation_event(mock_window, event)

        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_operation_event", event)
        mock_window.error_notification_widget.update_error_count.assert_not_called()

    def test_worker_operation_event_ignores_non_pipeline_failure_notification(self):
        """batch/annotation/import failure は dedicated handler 側でエラー通知を更新する"""
        from lorairo.gui.services.operation_events import OperationOutcome, OperationType
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        mock_window._delegate_to_pipeline_control = Mock()
        event = SimpleNamespace(
            operation_type=OperationType.BATCH_REGISTRATION,
            outcome=OperationOutcome.FAILED,
            is_current=True,
        )

        MainWindow._on_worker_operation_event(mock_window, event)

        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_operation_event", event)
        mock_window.error_notification_widget.update_error_count.assert_not_called()


class TestProjectFileSystemManagerInitialization:
    """GUI の FileSystemManager はプロジェクト確定時 (起動時) に初期化される (#1360)。"""

    def test_create_project_fsm_initializes_with_current_project_root(self, tmp_path, monkeypatch):
        """登録操作を経なくても FSM はプロジェクトルート配下で初期化済みになる。"""
        from lorairo.filesystem import FileSystemManager
        from lorairo.gui.window.main_window import MainWindow

        monkeypatch.setattr("lorairo.gui.window.main_window.get_current_project_root", lambda: tmp_path)

        fsm = MainWindow._create_project_file_system_manager()

        assert isinstance(fsm, FileSystemManager)
        assert fsm.initialized is True
        assert fsm.image_dataset_dir == tmp_path / "image_dataset"
        assert fsm.original_images_dir is not None
        assert fsm.original_images_dir.is_relative_to(tmp_path / "image_dataset" / "original_images")
        assert fsm.original_images_dir.is_dir()

    def test_create_project_fsm_returns_uninitialized_on_os_error(self, tmp_path, monkeypatch):
        """ディレクトリ作成失敗では起動を止めず、未初期化の FSM を返す。"""
        from lorairo.filesystem import FileSystemManager
        from lorairo.gui.window.main_window import MainWindow

        monkeypatch.setattr("lorairo.gui.window.main_window.get_current_project_root", lambda: tmp_path)

        def _raise_os_error(self: FileSystemManager, output_dir: object) -> None:
            raise PermissionError("read-only filesystem")

        monkeypatch.setattr(FileSystemManager, "initialize", _raise_os_error)

        fsm = MainWindow._create_project_file_system_manager()

        assert isinstance(fsm, FileSystemManager)
        assert fsm.initialized is False

    def test_initialize_services_shares_initialized_fsm_with_worker_service(
        self, qapp, tmp_path, monkeypatch
    ):
        """_initialize_services は初期化済み FSM を WorkerService と共有する。

        DatasetController には同じ ``self.file_system_manager`` が渡され、
        CropDialogLauncher は ``worker_service.fsm`` を使う (search_tab) ため、
        この同一性が GUI 全体の FSM 共有の起点になる。
        """
        from lorairo.gui.services.worker_service import WorkerService
        from lorairo.gui.window.main_window import MainWindow

        monkeypatch.setattr("lorairo.gui.window.main_window.get_current_project_root", lambda: tmp_path)
        container = Mock()
        container.db_manager = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.get_service_container", Mock(return_value=container)
        )
        monkeypatch.setattr("lorairo.gui.window.main_window.ConfigurationService", Mock())
        monkeypatch.setattr("lorairo.gui.window.main_window.DatasetStateManager", Mock())

        window = Mock()
        window._create_project_file_system_manager = MainWindow._create_project_file_system_manager

        MainWindow._initialize_services(window)

        window._handle_critical_initialization_failure.assert_not_called()
        assert window.file_system_manager.initialized is True
        assert window.file_system_manager.image_dataset_dir == tmp_path / "image_dataset"
        assert isinstance(window.worker_service, WorkerService)
        assert window.worker_service.fsm is window.file_system_manager

    def test_on_annotation_canceled_invalidates_persisted_phashes(self):
        from lorairo.gui.window.main_window import MainWindow
        from lorairo.gui.workers.annotation_worker import AnnotationWorker

        AnnotationWorker._unconsumed_persisted_phashes.clear()
        AnnotationWorker._unconsumed_persisted_phashes.add("phash_saved")

        window = Mock()
        window._closing = False
        window.dataset_state_manager = Mock()
        window.db_manager = Mock()

        MainWindow._on_annotation_canceled(window, "annotation_1")

        window.dataset_state_manager.refresh_annotations_after_execution.assert_called_once_with(
            {"phash_saved"}
        )
        assert AnnotationWorker._unconsumed_persisted_phashes == set()


class TestMainWindowSelectDeselectScoping:
    """全選択 (Ctrl+A) / 選択解除 (Ctrl+D) のアクティブタブ限定ディスパッチ (#1551)。"""

    @staticmethod
    def _make_window_stub():
        search_tab = SimpleNamespace(thumbnail_selector=Mock())
        export_tab = SimpleNamespace(thumbnail_selector=Mock())
        tab_workspace = Mock(name="tabWorkspace")
        tab_export = Mock(name="tabExport")
        tab_annotate = Mock(name="tabBatchTag")
        tab_results = Mock(name="tabResults")
        tab_errors = Mock(name="tabErrors")
        tab_widget = Mock()
        window = SimpleNamespace(
            tabWidgetMainMode=tab_widget,
            tabWorkspace=tab_workspace,
            tabExport=tab_export,
            tabBatchTag=tab_annotate,
            tabResults=tab_results,
            tabErrors=tab_errors,
            search_tab=search_tab,
            export_tab=export_tab,
            jobs_tab=Mock(name="jobs_tab"),
            actionSelectAll=Mock(),
            actionDeselectAll=Mock(),
            _refresh_search_tab=Mock(),
            _refresh_batch_tag_staging=Mock(),
            _refresh_jobs_tab=Mock(),
            _refresh_results_tab=Mock(),
            _refresh_errors_tab=Mock(),
            _refresh_export_tab=Mock(),
        )
        return window

    def test_select_and_deselect_all_dispatch_to_search_tab_when_active(self):
        """検索タブがアクティブなときは search_tab.thumbnail_selector のみ操作する。"""
        from lorairo.gui.window.main_window import MainWindow

        window = self._make_window_stub()
        window.tabWidgetMainMode.currentWidget.return_value = window.tabWorkspace

        MainWindow._on_select_all_triggered(window)
        MainWindow._on_deselect_all_triggered(window)

        window.search_tab.thumbnail_selector._select_all_items.assert_called_once_with()
        window.search_tab.thumbnail_selector._deselect_all_items.assert_called_once_with()
        window.export_tab.thumbnail_selector._select_all_items.assert_not_called()
        window.export_tab.thumbnail_selector._deselect_all_items.assert_not_called()

    def test_select_and_deselect_all_dispatch_to_export_tab_when_active(self):
        """エクスポートタブがアクティブなときは export_tab.thumbnail_selector のみ操作する。"""
        from lorairo.gui.window.main_window import MainWindow

        window = self._make_window_stub()
        window.tabWidgetMainMode.currentWidget.return_value = window.tabExport

        MainWindow._on_select_all_triggered(window)
        MainWindow._on_deselect_all_triggered(window)

        window.export_tab.thumbnail_selector._select_all_items.assert_called_once_with()
        window.export_tab.thumbnail_selector._deselect_all_items.assert_called_once_with()
        window.search_tab.thumbnail_selector._select_all_items.assert_not_called()
        window.search_tab.thumbnail_selector._deselect_all_items.assert_not_called()

    def test_select_and_deselect_all_noop_on_non_selector_tabs(self):
        """Annotate / Results / Errors / Jobs 等の別タブ表示中はどのセレクタも操作しない。"""
        from lorairo.gui.window.main_window import MainWindow

        window = self._make_window_stub()
        for other_tab in (window.tabBatchTag, window.tabResults, window.tabErrors, window.jobs_tab):
            window.tabWidgetMainMode.currentWidget.return_value = other_tab
            MainWindow._on_select_all_triggered(window)
            MainWindow._on_deselect_all_triggered(window)

        window.search_tab.thumbnail_selector._select_all_items.assert_not_called()
        window.search_tab.thumbnail_selector._deselect_all_items.assert_not_called()
        window.export_tab.thumbnail_selector._select_all_items.assert_not_called()
        window.export_tab.thumbnail_selector._deselect_all_items.assert_not_called()

    def test_tab_change_updates_selection_actions_enabled_state(self):
        """タブ切替時にサムネイルセレクタを持つタブでのみ全選択/選択解除を有効化する。"""
        from lorairo.gui.window.main_window import MainWindow

        window = self._make_window_stub()

        window.tabWidgetMainMode.widget.return_value = window.tabBatchTag
        MainWindow._on_main_tab_changed(window, 1)
        window.actionSelectAll.setEnabled.assert_called_with(False)
        window.actionDeselectAll.setEnabled.assert_called_with(False)

        window.tabWidgetMainMode.widget.return_value = window.tabExport
        MainWindow._on_main_tab_changed(window, 4)
        window.actionSelectAll.setEnabled.assert_called_with(True)
        window.actionDeselectAll.setEnabled.assert_called_with(True)

        window.tabWidgetMainMode.widget.return_value = window.tabWorkspace
        MainWindow._on_main_tab_changed(window, 0)
        window.actionSelectAll.setEnabled.assert_called_with(True)
        window.actionDeselectAll.setEnabled.assert_called_with(True)

    def test_connect_menu_actions_wires_select_and_deselect_dispatch_handlers(self):
        """_connect_menu_actions は直接 search_tab ではなく MainWindow のディスパッチへ接続する。"""
        from lorairo.gui.window.main_window import MainWindow

        window = self._make_window_stub()
        window.tabWidgetMainMode.currentWidget.return_value = window.tabWorkspace
        window._on_select_all_triggered = Mock()
        window._on_deselect_all_triggered = Mock()

        MainWindow._connect_menu_actions(window)

        window.actionSelectAll.triggered.connect.assert_called_once_with(window._on_select_all_triggered)
        window.actionDeselectAll.triggered.connect.assert_called_once_with(
            window._on_deselect_all_triggered
        )


class TestMainWindowCloseConfirmationAndCancel:
    """実行中ジョブがある場合の終了確認と全ワーカーキャンセル (#1556)。"""

    @staticmethod
    def _make_closable_window(qtbot):
        from PySide6.QtWidgets import QMainWindow

        from lorairo.gui.window.main_window import MainWindow

        with patch.object(MainWindow, "__init__", QMainWindow.__init__):
            window = MainWindow()
        qtbot.addWidget(window)
        window._closing = False
        window._save_window_state = Mock()
        window.dataset_state_manager = Mock()
        window.worker_service = Mock()
        window.worker_service.get_active_worker_count.return_value = 0
        window.export_tab = None
        window.search_tab = None
        window.results_tab = None
        window.annotate_tab = None
        window.jobs_tab = None
        window.annotation_workflow_controller = None
        return window

    def test_close_with_running_jobs_rejected_ignores_event_and_does_not_shutdown(self, qtbot, monkeypatch):
        """実行中ジョブがあり確認ダイアログで No を選んだ場合は終了を中断する。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        window.worker_service.get_active_worker_count.return_value = 2
        question_mock = Mock(return_value=QMessageBox.StandardButton.No)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_called_once_with(
            window,
            "終了確認",
            "実行中のジョブが 2 件あります。中断して終了しますか？",  # noqa: RUF001
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert not event.isAccepted()
        assert window._closing is False
        window.worker_service.cancel_all_workers.assert_not_called()
        window.dataset_state_manager.shutdown_annotation_refresh.assert_not_called()
        window._save_window_state.assert_not_called()

    def test_close_with_running_jobs_confirmed_cancels_all_workers_and_closes(self, qtbot, monkeypatch):
        """実行中ジョブがあり確認ダイアログで Yes を選んだ場合は全ワーカーをキャンセルして終了する。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        window.worker_service.get_active_worker_count.return_value = 1
        question_mock = Mock(return_value=QMessageBox.StandardButton.Yes)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_called_once()
        assert event.isAccepted()
        assert window._closing is True
        window.worker_service.cancel_all_workers.assert_called_once_with()
        window.dataset_state_manager.shutdown_annotation_refresh.assert_called_once_with()
        window._save_window_state.assert_called_once_with()

    def test_close_with_running_export_thread_prompts_and_counts_job(self, qtbot, monkeypatch):
        """エクスポートスレッド実行中も実行中ジョブ件数に含めて終了確認する。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        export_thread = Mock()
        export_thread.isRunning.return_value = True
        window.export_tab = SimpleNamespace(_export_thread=export_thread, shutdown=Mock())
        question_mock = Mock(return_value=QMessageBox.StandardButton.No)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_called_once_with(
            window,
            "終了確認",
            "実行中のジョブが 1 件あります。中断して終了しますか？",  # noqa: RUF001
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert not event.isAccepted()
        window.export_tab.shutdown.assert_not_called()

    def test_close_with_running_async_batch_dispatch_prompts_and_counts_job(self, qtbot, monkeypatch):
        """Batch API 非同期送信スレッド実行中も実行中ジョブ件数に含めて終了確認する (#1556 Codex P2)。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        dispatch_thread = Mock()
        dispatch_thread.isRunning.return_value = True
        window.annotation_workflow_controller = SimpleNamespace(
            _async_dispatch_in_progress=True,
            _async_dispatch_thread=dispatch_thread,
        )
        question_mock = Mock(return_value=QMessageBox.StandardButton.No)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_called_once_with(
            window,
            "終了確認",
            "実行中のジョブが 1 件あります。中断して終了しますか？",  # noqa: RUF001
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert not event.isAccepted()
        window.worker_service.cancel_all_workers.assert_not_called()

    def test_close_with_running_provider_batch_collect_runners_prompts_and_counts_jobs(
        self, qtbot, monkeypatch
    ):
        """Provider Batch 結果回収スレッド実行中も実行中ジョブ件数に含めて終了確認する (#1556 Codex P2)。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        running_thread_1 = Mock()
        running_thread_1.isRunning.return_value = True
        running_thread_2 = Mock()
        running_thread_2.isRunning.return_value = True
        stopped_thread = Mock()
        stopped_thread.isRunning.return_value = False
        batch_widget = SimpleNamespace(
            _collect_runners={
                101: (running_thread_1, Mock()),
                102: (running_thread_2, Mock()),
                103: (stopped_thread, Mock()),
            },
            shutdown=Mock(),
        )
        window.jobs_tab = SimpleNamespace(provider_batch_job_widget=batch_widget)
        question_mock = Mock(return_value=QMessageBox.StandardButton.No)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_called_once_with(
            window,
            "終了確認",
            "実行中のジョブが 2 件あります。中断して終了しますか？",  # noqa: RUF001
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert not event.isAccepted()
        batch_widget.shutdown.assert_not_called()

    def test_close_with_no_running_jobs_cancels_all_workers_without_prompt(self, qtbot, monkeypatch):
        """実行中ジョブがない場合は確認ダイアログを出さずに cancel_all_workers を呼んで終了する。"""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox

        window = self._make_closable_window(qtbot)
        question_mock = Mock(return_value=QMessageBox.StandardButton.No)
        monkeypatch.setattr(QMessageBox, "question", question_mock)

        event = QCloseEvent()
        window.closeEvent(event)

        question_mock.assert_not_called()
        assert event.isAccepted()
        assert window._closing is True
        window.worker_service.cancel_all_workers.assert_called_once_with()


class TestMainWindowWave5Features:
    """Issue #1547, #1550, #1565 のユニットテスト。"""

    def test_clamp_initial_window_size_clamps_1080p_overflow(self):
        """初期ウィンドウサイズが 1600x900 を超える場合 1440x860 以下へクランプする (#1565)。"""
        from lorairo.gui.window.main_window import MainWindow

        window = Mock()
        window.width.return_value = 1287
        window.height.return_value = 1178
        screen = Mock()
        avail = Mock()
        avail.width.return_value = 1920
        avail.height.return_value = 1040
        screen.availableGeometry.return_value = avail
        window.screen.return_value = screen

        MainWindow._clamp_initial_window_size(window)

        window.resize.assert_called_once_with(1287, 860)

    def test_populate_file_menu_adds_project_and_registration_actions(self, qapp):
        """File メニューにプロジェクト操作・画像登録・ログフォルダ等のアクションを追加する (#1547, #1550)。"""
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMainWindow, QMenu

        from lorairo.gui.window.main_window import MainWindow

        with patch.object(MainWindow, "__init__", QMainWindow.__init__):
            window = MainWindow()
        window.menuFile = QMenu("ファイル", window)
        window.actionExit = QAction("終了", window)
        window.menuFile.addAction(window.actionExit)

        MainWindow._populate_file_menu(window)

        action_names = [a.objectName() for a in window.menuFile.actions() if not a.isSeparator()]
        assert "actionOpenProject" in action_names
        assert "actionNewProject" in action_names
        assert "actionRegisterImages" in action_names
        assert "actionBatchImport" in action_names
        assert "actionGoToExport" in action_names
        assert "actionRefreshView" in action_names
        assert "actionOpenLogFolder" in action_names
        assert action_names[-1] == window.actionExit.objectName()

    def test_open_project_updates_title_and_settings(self, tmp_path):
        """_open_project がプロジェクト選択・QSettings 保存・タイトル更新を行う (#1547)。"""
        from lorairo.gui.window.main_window import MainWindow

        proj_dir = tmp_path / "my_project_20260707_001"
        proj_dir.mkdir()
        window = Mock()
        window.config_service = Mock()
        window.search_tab = Mock()
        window.statusBar.return_value = Mock()

        with patch("lorairo.gui.window.main_window.QSettings") as mock_qsettings:
            selected = MainWindow._open_project(window, proj_dir)

        assert selected == proj_dir.resolve()
        mock_qsettings.return_value.setValue.assert_called_once_with(
            "project/active_project_dir", str(proj_dir.resolve())
        )
        window.setWindowTitle.assert_called_once_with(f"LoRAIro — {proj_dir.name}")
        window.search_tab.set_dataset_path.assert_called_once_with(str(proj_dir.resolve()))

    def test_open_project_rebinds_live_services_and_clears_state(self, tmp_path):
        """_open_project が ServiceContainer と依存サービス/状態マネージャを再バインドする (#1547, Codex P1 #4531611132)。"""
        from lorairo.gui.window.main_window import MainWindow

        proj_dir = tmp_path / "dataset_switch_test"
        proj_dir.mkdir()
        window = Mock()
        window.config_service = Mock()
        window.service_container = Mock()
        new_db_mgr = Mock()
        window.service_container.db_manager = new_db_mgr
        window.service_container.file_system_manager = Mock()
        window.worker_service = Mock()
        window.dataset_state_manager = Mock()
        window.staging_state_manager = Mock()
        window.dataset_controller = Mock()
        window.search_tab = Mock()
        window.annotate_tab = Mock()
        window.errors_tab = Mock()
        window.export_tab = Mock()
        window.jobs_tab = Mock()
        window.results_tab = Mock()
        window.map_tab = Mock()
        window.statusBar.return_value = Mock()

        with patch("lorairo.gui.window.main_window.QSettings"):
            MainWindow._open_project(window, proj_dir)

        window.service_container.set_active_project_directory.assert_called_once_with(proj_dir.resolve())
        assert window.db_manager is new_db_mgr
        assert window.worker_service.db_manager is new_db_mgr
        assert window.dataset_controller.db_manager is new_db_mgr
        window._configure_async_dispatch_controller.assert_called_once_with()
        window.dataset_state_manager.clear.assert_called_once()
        window.dataset_state_manager.set_db_manager.assert_called_once_with(new_db_mgr)
        window.staging_state_manager.clear.assert_called_once()
        assert window.search_tab.db_manager is new_db_mgr
        assert window.annotate_tab.db_manager is new_db_mgr
        assert window.errors_tab.db_manager is new_db_mgr
        assert window.export_tab.db_manager is new_db_mgr
        assert window.jobs_tab.db_manager is new_db_mgr
        assert window.results_tab.db_manager is new_db_mgr
        assert window.map_tab.db_manager is new_db_mgr
        window.load_images_from_db.assert_called_once()

    def test_restore_window_state_preserves_geometry_on_version_mismatch(self):
        """SETTINGS_VERSION 不一致でも geometry / state / active_tab は復元し splitter のみスキップ (#1565)。"""
        from lorairo.gui.window.main_window import MainWindow

        window = Mock()
        window.SETTINGS_VERSION = MainWindow.SETTINGS_VERSION
        window.search_tab = Mock()
        window.tabWidgetMainMode = Mock()
        window.tabWidgetMainMode.count.return_value = 3
        tab0 = Mock()
        tab0.objectName.return_value = "tabWorkspace"
        tab1 = Mock()
        tab1.objectName.return_value = "tabBatchTag"
        window.tabWidgetMainMode.widget.side_effect = lambda idx: [tab0, tab1, Mock()][idx]
        window.tabWidgetMainMode.tabText.return_value = ""

        values = {
            "main_window/settings_version": MainWindow.SETTINGS_VERSION - 1,
            "main_window/geometry": b"geom",
            "main_window/state": b"state",
            "current_tab_name": "tabBatchTag",
        }
        with patch("lorairo.gui.window.main_window.QSettings") as mock_qsettings:
            mock_qsettings.return_value.value.side_effect = lambda k, *a, **kw: values.get(k)
            MainWindow._restore_window_state(window)

        window.restoreGeometry.assert_called_once_with(b"geom")
        window.restoreState.assert_called_once_with(b"state")
        window.tabWidgetMainMode.setCurrentIndex.assert_called_once_with(1)
        window.search_tab.restore_layout_state.assert_not_called()

    def test_show_about_dialog_includes_version_project_and_log_path(self, tmp_path):
        """About ダイアログにバージョン・プロジェクトパス・ログパスを含める (#1550)。"""
        from lorairo.gui.window.main_window import MainWindow

        window = Mock()
        with (
            patch("lorairo.gui.window.main_window.get_current_project_root", return_value=tmp_path),
            patch("lorairo.gui.window.main_window.QMessageBox.about") as mock_about,
        ):
            MainWindow._show_about_dialog(window)

        mock_about.assert_called_once()
        about_text = mock_about.call_args.args[2]
        assert "バージョン:" in about_text
        assert str(tmp_path.resolve()) in about_text
        assert "ログファイル:" in about_text

    def test_map_tab_rebind_project_dependencies_updates_tag_cloud(self, qtbot):
        from lorairo.gui.tab.map_tab import MapTabWidget

        db1 = Mock()
        db2 = Mock()
        tab = MapTabWidget(db_manager=db1)
        qtbot.addWidget(tab)

        tab.rebind_project_dependencies(db2)

        assert tab.db_manager is db2
        assert tab.tag_cloud._db is db2

    def test_search_tab_rebind_crop_and_comparison_launchers_resets_state(self):
        from lorairo.gui.tab.search_tab import SearchTabWidget

        crop_launcher = Mock()
        crop_launcher._closing = True
        comparison_launcher = Mock()
        comparison_launcher._dialog = Mock()
        tab = SimpleNamespace(
            _crop_dialog_launcher=crop_launcher,
            _image_comparison_launcher=comparison_launcher,
            _worker_service=None,
            _service_container=SimpleNamespace(file_system_manager=Mock()),
            _dataset_state_manager=Mock(),
        )
        db2 = Mock()

        with patch("lorairo.gui.tab.search_tab.ImageComparisonLauncher") as mock_cmp_cls:
            SearchTabWidget._rebind_crop_and_comparison_launchers(tab, db2)

        crop_launcher.shutdown.assert_called_once()
        assert crop_launcher._closing is False
        assert crop_launcher._db_manager is db2
        comparison_launcher.shutdown.assert_called_once()
        assert comparison_launcher._dialog is None
        mock_cmp_cls.assert_called_once_with(db2, tab, tab._dataset_state_manager)

    def test_results_tab_rebind_project_dependencies_clears_retained_cohort(self):
        from lorairo.gui.tab.results_tab import ResultsTabWidget

        tab = SimpleNamespace(
            _db_manager=Mock(),
            _last_cohort_ids=[10, 20],
            _last_cohort_names={10: "a.png", 20: "b.png"},
            _annotation_review_widget=Mock(),
            refresh=Mock(),
        )
        db2 = Mock()

        ResultsTabWidget.rebind_project_dependencies(tab, db2)

        assert tab._db_manager is db2
        assert tab._last_cohort_ids == []
        assert tab._last_cohort_names == {}
        tab._annotation_review_widget.set_image_names.assert_called_once_with({})
        tab._annotation_review_widget.set_image_ids.assert_called_once_with([])
        tab.refresh.assert_called_once_with()


if __name__ == "__main__":
    pytest.main([__file__])
