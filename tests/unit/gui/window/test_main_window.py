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

    def test_on_annotation_finished_updates_cache(self, mock_window_with_annotation):
        """アノテーション完了時にサマリーダイアログ表示後、画像キャッシュが更新される"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result(
            {
                "abc123def456": {"model1": Mock()},
                "xyz789ghi012": {"model1": Mock()},
            }
        )

        # find_image_ids_by_phashes_multi のモック (#633: 別版で複数 image_id になり得る)
        mock_window_with_annotation.db_manager.image_repo.find_image_ids_by_phashes_multi.return_value = {
            "abc123def456": [101],
            "xyz789ghi012": [102],
        }

        with patch(
            "lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"
        ) as mock_dialog_class:
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

        # サマリーダイアログが実行結果とともに表示される
        mock_dialog_class.assert_called_once_with(result, parent=mock_window_with_annotation)
        mock_dialog_class.return_value.exec.assert_called_once()

        # pHashから画像IDを検索 (multi)
        mock_window_with_annotation.db_manager.image_repo.find_image_ids_by_phashes_multi.assert_called_once()

        # キャッシュが更新される
        mock_window_with_annotation.dataset_state_manager.refresh_images.assert_called_once_with([101, 102])

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

    def test_on_annotation_finished_handles_missing_dependencies(self):
        """依存関係なし時はダイアログ表示後に早期リターン"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
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

    def test_on_annotation_finished_handles_phash_lookup_failure(self, mock_window_with_annotation):
        """pHash検索失敗時にエラーログを出力する"""
        from lorairo.gui.window.main_window import MainWindow

        result = self._make_execution_result({"abc123": {"model1": Mock()}})
        mock_window_with_annotation.db_manager.image_repo.find_image_ids_by_phashes_multi.side_effect = (
            Exception("DB error")
        )

        with (
            patch("lorairo.gui.widgets.annotation_summary_dialog.AnnotationSummaryDialog"),
            patch("lorairo.gui.window.main_window.logger") as mock_logger,
        ):
            mock_logger.opt.return_value = mock_logger  # opt(exception=True).error 経路を捕捉 (#1153)
            MainWindow._on_annotation_finished(mock_window_with_annotation, result)

            # エラーログが出力される
            mock_logger.error.assert_called_once()
            assert "キャッシュ更新失敗" in mock_logger.error.call_args[0][0]

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
