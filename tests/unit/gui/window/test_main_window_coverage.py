"""MainWindow 拡張ユニットテスト - Issue #155

main_window.py のカバレッジ 59% → 75%+ に向けた追加テスト。
Mock-selfパターンを使用してGUIコンポーネントを必要とせず実行可能。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestDelegateMethods:
    """委譲ヘルパーメソッドのテスト"""

    def test_delegate_to_pipeline_control_calls_method(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_control_service = Mock()
        MainWindow._delegate_to_pipeline_control(mock_window, "on_search_started", "w1")
        mock_window.pipeline_control_service.on_search_started.assert_called_once_with("w1")

    def test_delegate_to_pipeline_control_no_service_logs_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_control_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._delegate_to_pipeline_control(mock_window, "on_search_started", "w1")
            mock_logger.error.assert_called_once()
            assert "PipelineControlService" in mock_logger.error.call_args[0][0]

    def test_delegate_to_result_handler_calls_method(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.result_handler_service = Mock()
        MainWindow._delegate_to_result_handler(mock_window, "handle_annotation_error", "err")
        mock_window.result_handler_service.handle_annotation_error.assert_called_once()

    def test_delegate_to_result_handler_no_service_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.result_handler_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._delegate_to_result_handler(mock_window, "handle_annotation_error", "err")
            mock_logger.warning.assert_called_once()

    def test_delegate_to_progress_state_calls_method(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.progress_state_service = Mock()
        MainWindow._delegate_to_progress_state(mock_window, "on_batch_registration_started", "w1")
        mock_window.progress_state_service.on_batch_registration_started.assert_called_once_with("w1")

    def test_delegate_to_progress_state_no_service_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.progress_state_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._delegate_to_progress_state(mock_window, "on_batch_registration_started", "w1")
            mock_logger.warning.assert_called_once()


class TestPipelineEventHandlers:
    """パイプラインイベントハンドラのテスト"""

    def test_on_search_completed_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        result = {"images": []}
        MainWindow._on_search_completed_start_thumbnail(mock_window, result)
        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_search_completed", result)

    def test_on_thumbnail_completed_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        result = {"thumbnails": []}
        MainWindow._on_thumbnail_completed_update_display(mock_window, result)
        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_thumbnail_completed", result)

    def test_on_pipeline_search_started_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_pipeline_search_started(mock_window, "worker_1")
        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_search_started", "worker_1")

    def test_on_pipeline_thumbnail_started_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_pipeline_thumbnail_started(mock_window, "worker_2")
        mock_window._delegate_to_pipeline_control.assert_called_once_with(
            "on_thumbnail_started", "worker_2"
        )

    def test_on_pipeline_search_error_updates_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        MainWindow._on_pipeline_search_error(mock_window, "search error")
        mock_window._delegate_to_pipeline_control.assert_called_once_with("on_search_error", "search error")
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_on_pipeline_search_error_no_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = None
        MainWindow._on_pipeline_search_error(mock_window, "search error")

    def test_on_pipeline_thumbnail_error_updates_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        MainWindow._on_pipeline_thumbnail_error(mock_window, "thumb error")
        mock_window._delegate_to_pipeline_control.assert_called_once_with(
            "on_thumbnail_error", "thumb error"
        )
        mock_window.error_notification_widget.update_error_count.assert_called_once()


class TestBatchRegistrationHandlers:
    """バッチ登録ハンドラのテスト"""

    def test_on_batch_registration_started_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_registration_started(mock_window, "worker_1")
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_batch_registration_started", "worker_1"
        )

    def test_on_batch_registration_finished_with_result_handler(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.result_handler_service = Mock()
        mock_window.database_registration_completed = Mock()
        result = Mock()
        MainWindow._on_batch_registration_finished(mock_window, result)
        mock_window.result_handler_service.handle_batch_registration_finished.assert_called_once()

    def test_on_batch_registration_finished_fallback_without_result_handler(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.result_handler_service = None
        mock_window.statusBar.return_value = Mock()
        result = Mock()
        MainWindow._on_batch_registration_finished(mock_window, result)
        mock_window.statusBar().showMessage.assert_called()

    def test_on_batch_registration_error_calls_qmessagebox(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.progress_state_service = Mock()
        mock_window.error_notification_widget = Mock()
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._on_batch_registration_error(mock_window, "登録エラー")
            mock_qmb.critical.assert_called_once()

    def test_on_batch_registration_error_updates_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.progress_state_service = None
        mock_window.error_notification_widget = Mock()
        with patch("lorairo.gui.window.main_window.QMessageBox"):
            MainWindow._on_batch_registration_error(mock_window, "エラー")
        mock_window.error_notification_widget.update_error_count.assert_called_once()


class TestWorkerProgressHandlers:
    """ワーカー進捗ハンドラのテスト"""

    def test_on_worker_progress_updated_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_worker_progress_updated(mock_window, "w1", {"progress": 50})
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_worker_progress_updated", "w1", {"progress": 50}
        )

    def test_on_worker_batch_progress_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_worker_batch_progress(mock_window, "w1", 3, 10, "image.jpg")
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_worker_batch_progress", "w1", 3, 10, "image.jpg"
        )

    def test_on_batch_annotation_started_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_annotation_started(mock_window, 100)
        mock_window._delegate_to_progress_state.assert_called_once_with("on_batch_annotation_started", 100)

    def test_on_batch_annotation_progress_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_annotation_progress(mock_window, 5, 10)
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_batch_annotation_progress", 5, 10
        )


class TestResultHandlerDelegates:
    """ResultHandler委譲ハンドラのテスト"""

    def test_on_annotation_error_delegates_and_updates_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        MainWindow._on_annotation_error(mock_window, "アノテーションエラー")
        mock_window._delegate_to_result_handler.assert_called_once()
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_on_annotation_error_no_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = None
        MainWindow._on_annotation_error(mock_window, "エラー")

    def test_on_batch_annotation_finished_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_annotation_finished(mock_window, {"result": "data"})
        mock_window._delegate_to_result_handler.assert_called_once()

    def test_on_model_sync_completed_delegates(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_model_sync_completed(mock_window, {"sync": "result"})
        mock_window._delegate_to_result_handler.assert_called_once()


class TestCancelPipeline:
    """パイプラインキャンセルのテスト"""

    def test_cancel_current_pipeline_with_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_control_service = Mock()
        MainWindow.cancel_current_pipeline(mock_window)
        mock_window.pipeline_control_service.cancel_current_pipeline.assert_called_once()

    def test_cancel_current_pipeline_no_service_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_control_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow.cancel_current_pipeline(mock_window)
            mock_logger.warning.assert_called_once()


class TestDatasetRegistration:
    """データセット登録のテスト"""

    def test_select_and_process_dataset_calls_execute(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow.select_and_process_dataset(mock_window)
        mock_window._execute_dataset_registration.assert_called_once()

    def test_execute_dataset_registration_with_controller(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_controller = Mock()
        MainWindow._execute_dataset_registration(mock_window)
        mock_window.dataset_controller.select_and_register_images.assert_called_once()

    def test_execute_dataset_registration_without_controller_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_controller = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._execute_dataset_registration(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_load_images_from_db_calls_search_handler(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow.load_images_from_db(mock_window)
        mock_window._on_search_completed_start_thumbnail.assert_called_once_with(True)


class TestRatingScoreHandlers:
    """Rating/Score更新ハンドラのテスト"""

    def test_on_rating_update_requested_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_rating_update_requested(mock_window, 1, "PG")
            mock_logger.warning.assert_called_once()

    def test_on_rating_update_requested_success(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_rating.return_value = True
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_rating_update_requested(mock_window, 1, "R")
            mock_logger.info.assert_called_once()

    def test_on_rating_update_requested_failure(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_rating.return_value = False
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_rating_update_requested(mock_window, 1, "X")
            mock_logger.error.assert_called_once()

    def test_on_score_update_requested_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_score_update_requested(mock_window, 1, 750)
            mock_logger.warning.assert_called_once()

    def test_on_score_update_requested_success(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_score.return_value = True
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_score_update_requested(mock_window, 1, 750)
            mock_logger.info.assert_called_once()

    def test_on_score_update_requested_failure(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_score.return_value = False
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_score_update_requested(mock_window, 1, 750)
            mock_logger.error.assert_called_once()

    def test_handle_rating_changed_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._handle_rating_changed(mock_window, 1, "PG")
            mock_logger.warning.assert_called_once()

    def test_handle_rating_changed_success_refreshes_cache(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_rating.return_value = True
        mock_window.dataset_state_manager = Mock()
        MainWindow._handle_rating_changed(mock_window, 42, "R")
        mock_window.dataset_state_manager.refresh_image.assert_called_once_with(42)

    def test_handle_rating_changed_failure_logs_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_rating.return_value = False
        mock_window.dataset_state_manager = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._handle_rating_changed(mock_window, 42, "X")
            mock_logger.error.assert_called_once()

    def test_handle_score_changed_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._handle_score_changed(mock_window, 1, 500)
            mock_logger.warning.assert_called_once()

    def test_handle_score_changed_success_refreshes_cache(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_score.return_value = True
        mock_window.dataset_state_manager = Mock()
        MainWindow._handle_score_changed(mock_window, 42, 800)
        mock_window.dataset_state_manager.refresh_image.assert_called_once_with(42)

    def test_handle_score_changed_failure_logs_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.update_score.return_value = False
        mock_window.dataset_state_manager = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._handle_score_changed(mock_window, 42, 800)
            mock_logger.error.assert_called_once()


class TestSelectionHandlerExtended:
    """選択ハンドラ拡張テスト（単一・複数選択）"""

    def test_handle_selection_changed_single_image_populates_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.selectedImageDetailsWidget = Mock()
        mock_window.selectedImageDetailsWidget._rating_score_widget = Mock()
        mock_window.dataset_state_manager = Mock()
        image_data = {"id": 1, "rating_value": "PG"}
        mock_window.dataset_state_manager.get_image_by_id.return_value = image_data

        MainWindow._handle_selection_changed_for_rating(mock_window, [1])

        mock_window.selectedImageDetailsWidget._rating_score_widget.populate_from_image_data.assert_called_once_with(
            image_data
        )

    def test_handle_selection_changed_single_image_no_data_no_populate(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.selectedImageDetailsWidget = Mock()
        mock_window.selectedImageDetailsWidget._rating_score_widget = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.get_image_by_id.return_value = None

        MainWindow._handle_selection_changed_for_rating(mock_window, [1])

        mock_window.selectedImageDetailsWidget._rating_score_widget.populate_from_image_data.assert_not_called()

    def test_handle_selection_changed_multiple_images_batch_mode(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.selectedImageDetailsWidget = Mock()
        mock_window.selectedImageDetailsWidget._rating_score_widget = Mock()
        mock_window.db_manager = Mock()

        MainWindow._handle_selection_changed_for_rating(mock_window, [1, 2, 3])

        mock_window.selectedImageDetailsWidget._rating_score_widget.populate_from_selection.assert_called_once_with(
            [1, 2, 3], mock_window.db_manager
        )

    def test_handle_selection_changed_no_widget_attr_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock(spec=[])
        MainWindow._handle_selection_changed_for_rating(mock_window, [1])


class TestSaveRequestHandler:
    """保存リクエストハンドラのテスト"""

    def test_on_save_requested_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_save_requested(mock_window, {"image_id": 1, "rating": "PG", "score": 500})
            mock_logger.warning.assert_called_once()

    def test_on_save_requested_no_image_id(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_save_requested(mock_window, {"image_id": None, "rating": "PG"})
            mock_logger.warning.assert_called_once()

    def test_on_save_requested_updates_rating_and_score(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        MainWindow._on_save_requested(mock_window, {"image_id": 10, "rating": "R", "score": 700})
        mock_window.image_db_write_service.update_rating.assert_called_once_with(10, "R")
        mock_window.image_db_write_service.update_score.assert_called_once_with(10, 700)

    def test_on_save_requested_no_rating_skips_rating_update(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        MainWindow._on_save_requested(mock_window, {"image_id": 10, "rating": None, "score": 700})
        mock_window.image_db_write_service.update_rating.assert_not_called()
        mock_window.image_db_write_service.update_score.assert_called_once_with(10, 700)

    def test_on_save_requested_no_score_skips_score_update(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        MainWindow._on_save_requested(mock_window, {"image_id": 10, "rating": "X", "score": None})
        mock_window.image_db_write_service.update_rating.assert_called_once_with(10, "X")
        mock_window.image_db_write_service.update_score.assert_not_called()


class TestCurrentImagePayload:
    """現在選択中画像データ取得のテスト"""

    def test_get_current_image_payload_no_state_manager(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = None
        result = MainWindow._get_current_image_payload(mock_window)
        assert result is None

    def test_get_current_image_payload_no_current_image(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.get_current_image_data.return_value = None
        result = MainWindow._get_current_image_payload(mock_window)
        assert result is None

    def test_get_current_image_payload_returns_correct_structure(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.get_current_image_data.return_value = {
            "id": 42,
            "rating_value": "R",
            "score_value": 7.5,
            "tags_text": "landscape, sky",
            "caption_text": "A beautiful landscape",
        }
        result = MainWindow._get_current_image_payload(mock_window)
        assert result is not None
        assert result["id"] == 42
        assert result["rating"] == "R"
        assert result["score"] == 750
        assert result["tags"] == "landscape, sky"
        assert result["caption"] == "A beautiful landscape"

    def test_get_current_image_payload_handles_none_values(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.get_current_image_data.return_value = {
            "id": 1,
            "rating_value": None,
            "score_value": None,
            "tags_text": None,
            "caption_text": None,
        }
        result = MainWindow._get_current_image_payload(mock_window)
        assert result is not None
        assert result["rating"] == "PG"
        assert result["score"] == 0
        assert result["tags"] == ""
        assert result["caption"] == ""


class TestBatchTagWrite:
    """バッチタグ書き込みのテスト"""

    def test_execute_batch_tag_write_no_service(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = None
        result = MainWindow._execute_batch_tag_write(mock_window, [1, 2], "landscape")
        assert result is False

    def test_execute_batch_tag_write_success_refreshes_cache(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.add_tag_batch.return_value = True
        mock_window.dataset_state_manager = Mock()
        result = MainWindow._execute_batch_tag_write(mock_window, [1, 2], "landscape")
        assert result is True
        mock_window.dataset_state_manager.refresh_images.assert_called_once_with([1, 2])

    def test_execute_batch_tag_write_failure_no_cache_update(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.image_db_write_service = Mock()
        mock_window.image_db_write_service.add_tag_batch.return_value = False
        mock_window.dataset_state_manager = Mock()
        result = MainWindow._execute_batch_tag_write(mock_window, [1, 2], "tag")
        assert result is False
        mock_window.dataset_state_manager.refresh_images.assert_not_called()


class TestQuickTagDialog:
    """クイックタグダイアログのテスト"""

    def test_show_quick_tag_dialog_empty_ids(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._show_quick_tag_dialog(mock_window, [])
            mock_logger.warning.assert_called_once()

    def test_show_quick_tag_dialog_with_ids_shows_dialog(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch("lorairo.gui.window.main_window.QuickTagDialog") as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            MainWindow._show_quick_tag_dialog(mock_window, [1, 2])
            mock_dialog_class.assert_called_once_with([1, 2], parent=mock_window)
            mock_dialog.exec.assert_called_once()


class TestAnnotationTargetUI:
    """アノテーション対象UI更新のテスト"""

    def test_update_annotation_target_ui_zero_count(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.labelAnnotationTarget = Mock()
        mock_window.btnAnnotationExecute = Mock()
        MainWindow._update_annotation_target_ui(mock_window, 0)
        label_text = mock_window.labelAnnotationTarget.setText.call_args[0][0]
        assert "0 枚" in label_text
        mock_window.btnAnnotationExecute.setEnabled.assert_called_once_with(False)

    def test_update_annotation_target_ui_nonzero_count(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.labelAnnotationTarget = Mock()
        mock_window.btnAnnotationExecute = Mock()
        MainWindow._update_annotation_target_ui(mock_window, 5)
        label_text = mock_window.labelAnnotationTarget.setText.call_args[0][0]
        assert "5 枚" in label_text
        mock_window.btnAnnotationExecute.setEnabled.assert_called_once_with(True)

    def test_update_annotation_target_ui_no_attrs_no_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock(spec=[])
        MainWindow._update_annotation_target_ui(mock_window, 3)

    def test_handle_staging_cleared_calls_update_ui(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._handle_staging_cleared(mock_window)
        mock_window._update_annotation_target_ui.assert_called_once_with(0)

    def test_on_staged_images_changed_updates_with_count(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [1, 2, 3])
        mock_window._update_annotation_target_ui.assert_called_once_with(3)

    def test_on_staged_images_changed_empty_list(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [])
        mock_window._update_annotation_target_ui.assert_called_once_with(0)

    def test_on_staged_images_changed_none(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, None)
        mock_window._update_annotation_target_ui.assert_called_once_with(0)


class TestOpenDialogs:
    """設定・エクスポートダイアログのテスト"""

    def test_open_settings_with_controller(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.settings_controller = Mock()
        MainWindow.open_settings(mock_window)
        mock_window.settings_controller.open_settings_dialog.assert_called_once()

    def test_open_settings_without_controller_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.settings_controller = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.open_settings(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_export_data_with_controller(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.export_controller = Mock()
        MainWindow.export_data(mock_window)
        mock_window.export_controller.open_export_dialog.assert_called_once()

    def test_export_data_without_controller_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.export_controller = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.export_data(mock_window)
            mock_qmb.warning.assert_called_once()


class TestTabChangedHandler:
    """メインタブ切り替えハンドラのテスト"""

    def test_on_main_tab_changed_workspace_tab_logs_info(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_main_tab_changed(mock_window, 0)
            mock_logger.info.assert_called_once_with("Switched to Workspace tab")

    def test_on_main_tab_changed_batch_tag_tab_refreshes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_main_tab_changed(mock_window, 1)
        mock_window._refresh_batch_tag_staging.assert_called_once()

    def test_on_main_tab_changed_unknown_tab_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._on_main_tab_changed(mock_window, 99)
            mock_logger.warning.assert_called_once()
            assert "99" in mock_logger.warning.call_args[0][0]


class TestRefreshBatchTagStaging:
    """バッチタグステージングリフレッシュのテスト"""

    def test_refresh_batch_tag_staging_no_widget_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.batchTagAddWidget = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._refresh_batch_tag_staging(mock_window)
            mock_logger.warning.assert_called_once()

    def test_refresh_batch_tag_staging_calls_refresh_method(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_widget = Mock()
        mock_window.batchTagAddWidget = mock_widget
        MainWindow._refresh_batch_tag_staging(mock_window)
        mock_widget._refresh_staging_list_ui.assert_called_once()

    def test_refresh_batch_tag_staging_no_refresh_method_logs_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_widget = Mock(spec=["__class__", "__str__"])
        mock_window.batchTagAddWidget = mock_widget
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._refresh_batch_tag_staging(mock_window)
            mock_logger.error.assert_called_once()


class TestPanelToggle:
    """パネル表示切替のテスト"""

    def test_toggle_filter_panel_hide_saves_splitter_sizes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_panel = Mock()
        mock_splitter = Mock()
        mock_splitter.sizes.return_value = [300, 500]
        mock_window.frameFilterSearchPanel = mock_panel
        mock_window.splitterMainWorkArea = mock_splitter
        MainWindow._toggle_filter_panel(mock_window, False)
        mock_panel.setVisible.assert_called_once_with(False)
        assert mock_window._main_splitter_sizes_before_filter_hide == [300, 500]

    def test_toggle_filter_panel_show_restores_sizes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_panel = Mock()
        mock_splitter = Mock()
        mock_window.frameFilterSearchPanel = mock_panel
        mock_window.splitterMainWorkArea = mock_splitter
        mock_window._main_splitter_sizes_before_filter_hide = [300, 500]
        MainWindow._toggle_filter_panel(mock_window, True)
        mock_panel.setVisible.assert_called_once_with(True)
        mock_splitter.setSizes.assert_called_once_with([300, 500])

    def test_toggle_filter_panel_no_panel_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.frameFilterSearchPanel = None
        MainWindow._toggle_filter_panel(mock_window, True)

    def test_toggle_preview_panel_hide_saves_splitter_sizes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_panel = Mock()
        mock_splitter = Mock()
        mock_splitter.sizes.return_value = [400, 400]
        mock_window.framePreviewDetailPanel = mock_panel
        mock_window.splitterMainWorkArea = mock_splitter
        MainWindow._toggle_preview_panel(mock_window, False)
        mock_panel.setVisible.assert_called_once_with(False)
        assert mock_window._main_splitter_sizes_before_preview_hide == [400, 400]

    def test_toggle_preview_panel_show_restores_sizes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_panel = Mock()
        mock_splitter = Mock()
        mock_window.framePreviewDetailPanel = mock_panel
        mock_window.splitterMainWorkArea = mock_splitter
        mock_window._main_splitter_sizes_before_preview_hide = [400, 400]
        MainWindow._toggle_preview_panel(mock_window, True)
        mock_panel.setVisible.assert_called_once_with(True)
        mock_splitter.setSizes.assert_called_once_with([400, 400])


class TestSendSelectedToBatchTag:
    """バッチタグへの画像送信テスト"""

    def test_send_selected_no_state_manager_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_send_selected_no_batch_widget_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.batchTagAddWidget = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_send_selected_no_target_ids_shows_information(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = []
        mock_window.batchTagAddWidget = Mock()
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window, None)
            mock_qmb.information.assert_called_once()

    def test_send_selected_with_ids_adds_to_staging(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.batchTagAddWidget = Mock()
        mock_window.tabWidgetMainMode = Mock()
        mock_window.tabWidgetBatchTagWorkflow = Mock()
        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])
        mock_window.batchTagAddWidget.add_image_ids_to_staging.assert_called_once_with([1, 2, 3])


class TestErrorHandlers:
    """エラーハンドラのテスト"""

    def test_on_error_resolved_updates_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        MainWindow._on_error_resolved(mock_window, 42)
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_on_error_resolved_no_notification_widget_no_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = None
        MainWindow._on_error_resolved(mock_window, 42)

    def test_on_batch_import_error_shows_critical_and_updates_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._on_batch_import_error(mock_window, "インポートエラー")
            mock_qmb.critical.assert_called_once()
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_on_batch_import_error_no_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = None
        with patch("lorairo.gui.window.main_window.QMessageBox"):
            MainWindow._on_batch_import_error(mock_window, "エラー")


class TestDatabaseStatusLabel:
    """データベースステータスラベルのテスト"""

    def test_update_database_status_label_no_attr_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock(spec=[])
        MainWindow._update_database_status_label(mock_window)

    def test_update_database_status_label_none_label_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.labelDbInfo = None
        MainWindow._update_database_status_label(mock_window)

    def test_update_database_status_label_updates_text(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.labelDbInfo = Mock()
        mock_root = Mock()
        mock_root.resolve.return_value = Path("/test/project")
        mock_img_db = Mock()
        mock_img_db.resolve.return_value = Path("/test/db.sqlite")
        with patch("lorairo.gui.window.main_window.get_current_project_root", return_value=mock_root):
            with patch("lorairo.gui.window.main_window.IMG_DB_PATH", mock_img_db):
                with patch("lorairo.gui.window.main_window.USER_TAG_DB_PATH", None):
                    MainWindow._update_database_status_label(mock_window)
        mock_window.labelDbInfo.setText.assert_called_once()

    def test_update_database_status_label_handles_exception(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.labelDbInfo = Mock()
        with patch(
            "lorairo.gui.window.main_window.get_current_project_root", side_effect=RuntimeError("DB error")
        ):
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                MainWindow._update_database_status_label(mock_window)
                mock_logger.warning.assert_called_once()


class TestHandleBatchTagAddEdgeCases:
    """バッチタグ追加エッジケースのテスト"""

    def test_handle_batch_tag_add_empty_image_ids_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._handle_batch_tag_add(mock_window, [], "landscape")
            mock_logger.warning.assert_called_once()
            assert "empty" in mock_logger.warning.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
