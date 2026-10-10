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


if __name__ == "__main__":
    pytest.main([__file__])
