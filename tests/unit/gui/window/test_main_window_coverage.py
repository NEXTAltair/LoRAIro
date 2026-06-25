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

    def test_on_pipeline_search_canceled_delegates_without_error_notification(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_pipeline_search_canceled(mock_window, "search-123")
        mock_window._delegate_to_pipeline_control.assert_called_once_with(
            "on_search_canceled", "search-123"
        )

    def test_on_pipeline_thumbnail_error_updates_notification_widget(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.error_notification_widget = Mock()
        MainWindow._on_pipeline_thumbnail_error(mock_window, "thumb error")
        mock_window._delegate_to_pipeline_control.assert_called_once_with(
            "on_thumbnail_error", "thumb error"
        )
        mock_window.error_notification_widget.update_error_count.assert_called_once()

    def test_on_pipeline_thumbnail_canceled_delegates_without_error_notification(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_pipeline_thumbnail_canceled(mock_window, "thumbnail-123")
        mock_window._delegate_to_pipeline_control.assert_called_once_with(
            "on_thumbnail_canceled", "thumbnail-123"
        )


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

    def test_on_batch_registration_canceled_delegates_without_error_notification(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_registration_canceled(mock_window, "worker_1")
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_batch_registration_canceled", "worker_1"
        )


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

    def test_on_annotation_canceled_delegates_without_error_notification(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_annotation_canceled(mock_window, "annotation_123")
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_batch_annotation_canceled", "annotation_123"
        )

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

    def test_load_images_from_db_delegates_to_search_tab(self):
        """#869: 検索起動ロジックは SearchTabWidget が所有するため委譲する。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow.load_images_from_db(mock_window)
        mock_window.search_tab.load_images_from_db.assert_called_once_with()


# NOTE: #869 で Rating/Score 編集ハンドラ (_on_rating_update_requested /
# _on_score_update_requested / _on_save_requested / _handle_rating_changed /
# _handle_score_changed) と選択ハンドラ (_handle_selection_changed_for_rating)、
# および _get_current_image_payload は SearchTabWidget へ移送された。
# これらの振る舞い検証は tests/unit/gui/tab/test_search_tab.py が担う。


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


class TestStagingFanOut:
    """ステージング集合 fan-out のテスト (#868)。

    アノテ対象 UI 更新ロジックは AnnotateTabWidget へ移送済み (#868) のため、
    MainWindow 側はエクスポート対象件数ラベルの更新と、アノテ/エクスポートタブ
    への委譲だけを担う。
    """

    def test_handle_staging_cleared_updates_export_ui_and_delegates(self):
        """ステージングクリアでエクスポート件数を 0 にし、アノテタブへ空集合を委譲する。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._handle_staging_cleared(mock_window)
        mock_window._update_export_target_ui.assert_called_once_with(0)
        mock_window.annotate_tab.set_staging_target.assert_called_once_with([])

    def test_on_staged_images_changed_updates_with_count(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [1, 2, 3])
        mock_window._update_export_target_ui.assert_called_once_with(3)
        mock_window.annotate_tab.set_staging_target.assert_called_once_with([1, 2, 3])

    def test_on_staged_images_changed_syncs_export_widget(self):
        """Phase 5: ステージング変更はエクスポートタブの対象にもライブ反映される (ADR 0055)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [1, 2, 3])
        mock_window.export_tab.set_image_ids.assert_called_once_with([1, 2, 3])

    def test_on_staged_images_changed_skips_export_sync_when_widget_missing(self):
        """Phase 5: エクスポートタブ未初期化時は同期をスキップする。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.export_tab = None
        # export_tab が None でも例外なく処理が完了する
        MainWindow._on_staged_images_changed(mock_window, [1, 2])
        mock_window._update_export_target_ui.assert_called_once_with(2)
        mock_window.annotate_tab.set_staging_target.assert_called_once_with([1, 2])

    def test_on_staged_images_changed_empty_list(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [])
        mock_window._update_export_target_ui.assert_called_once_with(0)

    def test_on_staged_images_changed_none(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, None)
        mock_window._update_export_target_ui.assert_called_once_with(0)


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

    def test_export_data_switches_to_export_tab(self):
        """Phase 5: export_data はステージング集合を再読込してエクスポートタブへ遷移する。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window._get_staged_export_ids.return_value = [1, 2]
        MainWindow.export_data(mock_window)
        mock_window.export_tab.set_image_ids.assert_called_once_with([1, 2])
        mock_window.tabWidgetMainMode.setCurrentWidget.assert_called_once_with(mock_window.tabExport)

    def test_export_data_without_export_widget_shows_warning(self):
        """Phase 5: エクスポートタブ未初期化時は警告を表示して遷移しない。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.export_tab = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.export_data(mock_window)
            mock_qmb.warning.assert_called_once()
        mock_window.tabWidgetMainMode.setCurrentWidget.assert_not_called()


class TestTabChangedHandler:
    """メインタブ切り替えハンドラのテスト（widget 同一性ベース）"""

    def test_on_main_tab_changed_annotate_tab_refreshes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        annotate_tab = Mock()
        mock_window.tabBatchTag = annotate_tab
        mock_window.tabWidgetMainMode.widget.return_value = annotate_tab
        MainWindow._on_main_tab_changed(mock_window, 2)
        mock_window._refresh_batch_tag_staging.assert_called_once()

    def test_on_main_tab_changed_jobs_tab_refreshes_jobs(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        jobs_widget = Mock()
        mock_window.jobs_tab = jobs_widget
        mock_window.tabWidgetMainMode.widget.return_value = jobs_widget
        MainWindow._on_main_tab_changed(mock_window, 3)
        # dispatch 表は widget 同一性で一致した delegate へ委譲する
        mock_window._refresh_jobs_tab.assert_called_once()

    def test_on_main_tab_changed_errors_tab_refreshes(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        errors_container = Mock()
        mock_window.tabErrors = errors_container
        mock_window.tabWidgetMainMode.widget.return_value = errors_container
        MainWindow._on_main_tab_changed(mock_window, 5)
        # #871: タブ切替は _refresh_errors_tab (= ErrorsTabWidget.refresh) へ委譲する
        mock_window._refresh_errors_tab.assert_called_once()

    def test_on_main_tab_changed_export_tab_syncs_staging(self):
        """Phase 5: エクスポートタブ表示時はステージング集合を再読込する。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        export_tab = Mock()
        mock_window.tabExport = export_tab
        mock_window.tabWidgetMainMode.widget.return_value = export_tab
        MainWindow._on_main_tab_changed(mock_window, 6)
        mock_window._refresh_export_tab.assert_called_once()

    def test_on_main_tab_changed_search_tab_is_silent(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        # どの既知 widget にも一致しないタブ（検索 / マップ / 結果）は無処理
        mock_window.tabWidgetMainMode.widget.return_value = Mock()
        MainWindow._on_main_tab_changed(mock_window, 0)
        mock_window._refresh_batch_tag_staging.assert_not_called()


class TestRefreshBatchTagStaging:
    """アノテタブ再計算委譲のテスト (#868)。

    ステージングリスト・run bar・pipeline・preflight の再描画は
    AnnotateTabWidget.refresh() へ委譲される。
    """

    def test_refresh_batch_tag_staging_no_annotate_tab_logs_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotate_tab = None
        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            MainWindow._refresh_batch_tag_staging(mock_window)
            mock_logger.warning.assert_called_once()

    def test_refresh_batch_tag_staging_delegates_to_annotate_tab(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._refresh_batch_tag_staging(mock_window)
        mock_window.annotate_tab.refresh.assert_called_once_with()


class TestPanelToggle:
    """パネル表示切替のテスト。

    #869: パネル本体と splitter サイズの退避/復元は SearchTabWidget が所有する。
    MainWindow は menubar の checkable action を契約スロットへ薄く中継するだけ。
    """

    def test_toggle_filter_panel_delegates_to_search_tab(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._toggle_filter_panel(mock_window, False)
        mock_window.search_tab.toggle_filter_panel.assert_called_once_with()

    def test_toggle_filter_panel_no_search_tab_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = None
        # search_tab 未初期化でも例外なく完了する
        MainWindow._toggle_filter_panel(mock_window, True)

    def test_toggle_preview_panel_delegates_to_search_tab(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._toggle_preview_panel(mock_window, False)
        mock_window.search_tab.toggle_preview_panel.assert_called_once_with()

    def test_toggle_preview_panel_no_search_tab_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = None
        MainWindow._toggle_preview_panel(mock_window, True)


class TestSendSelectedToBatchTag:
    """バッチタグへの画像送信テスト"""

    def test_send_selected_no_state_manager_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_send_selected_no_annotate_tab_shows_warning(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.annotate_tab = None
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window)
            mock_qmb.warning.assert_called_once()

    def test_send_selected_no_target_ids_shows_information(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = []
        mock_window.annotate_tab = Mock()
        # #869: サムネイルセレクタは search_tab.thumbnail_selector 経由 (直接参照は無い)
        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window, None)
            mock_qmb.information.assert_called_once()

    def test_send_selected_treats_qt_clicked_bool_as_button_invocation(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = [7]
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()

        MainWindow.send_selected_to_batch_tag(mock_window, False)

        mock_window.annotate_tab.add_image_ids_to_staging.assert_called_once_with([7])

    def test_send_selected_explicit_empty_ids_does_not_fallback(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = [1]
        mock_window.annotate_tab = Mock()

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow.send_selected_to_batch_tag(mock_window, [])

        mock_window.annotate_tab.add_image_ids_to_staging.assert_not_called()
        mock_qmb.information.assert_called_once()

    def test_send_selected_with_ids_adds_to_staging(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()
        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])
        mock_window.annotate_tab.add_image_ids_to_staging.assert_called_once_with([1, 2, 3])


class TestErrorHandlers:
    """エラーハンドラのテスト"""

    # NOTE: _on_error_resolve / _on_errors_resolve_group は #871 で ErrorsTabWidget へ
    # 移設したため、resolve 振る舞いの検証は tests/unit/gui/tab/test_errors_tab.py に移動。

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

    def test_on_batch_import_canceled_delegates_without_error_notification(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_batch_import_canceled(mock_window, "batch_import_123")
        mock_window._delegate_to_progress_state.assert_called_once_with(
            "on_batch_import_canceled", "batch_import_123"
        )


class TestDatabaseStatusLabel:
    """データベースステータスラベルのテスト。

    #869: DB 状態バー (labelDbInfo) は SearchTabWidget へ移管したため、
    更新は search_tab.set_db_info 経由で行う。
    """

    def test_update_database_status_label_no_search_tab_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock(spec=[])
        # search_tab 属性が無い (タブ生成前) なら no-op
        MainWindow._update_database_status_label(mock_window)

    def test_update_database_status_label_none_search_tab_returns_early(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = None
        MainWindow._update_database_status_label(mock_window)

    def test_update_database_status_label_updates_via_search_tab(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = Mock()
        mock_root = Mock()
        mock_root.resolve.return_value = Path("/test/project")
        mock_img_db = Mock()
        mock_img_db.resolve.return_value = Path("/test/db.sqlite")
        with patch("lorairo.gui.window.main_window.get_current_project_root", return_value=mock_root):
            with patch("lorairo.gui.window.main_window.IMG_DB_PATH", mock_img_db):
                with patch("lorairo.gui.window.main_window.get_user_tag_db_path", return_value=None):
                    MainWindow._update_database_status_label(mock_window)
        mock_window.search_tab.set_db_info.assert_called_once()

    def test_update_database_status_label_handles_exception(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = Mock()
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


class TestRestoreSplitterStatesOrientation:
    """#865: QSplitter.restoreState が orientation を巻き戻さないことの検証。

    #869: 3 ペイン作業領域 splitter は SearchTabWidget が所有するため、
    MainWindow は search_tab.main_splitter プロパティ経由で復元する。
    """

    def test_restore_preserves_designed_orientation(self, qtbot):
        """旧 (縦) 保存状態を横スプリッターへ復元しても横のまま維持される。"""
        from unittest.mock import Mock

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QSplitter, QWidget

        from lorairo.gui.window.main_window import MainWindow

        # 旧 (縦) スプリッターの保存状態 (orientation を含む)
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(QWidget())
        vertical.addWidget(QWidget())
        saved_vertical_state = vertical.saveState()

        # 新 (横) スプリッター = .ui 由来の設計 orientation (work area=Horizontal)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(QWidget())
        horizontal.addWidget(QWidget())

        mock_window = Mock()
        mock_window.search_tab.main_splitter = horizontal

        settings = Mock()
        settings.value.side_effect = lambda key: (
            saved_vertical_state if key == "splitter/main_work_area" else None
        )

        MainWindow._restore_splitter_states(mock_window, settings)

        assert horizontal.orientation() == Qt.Orientation.Horizontal

    def test_save_persists_both_main_and_preview_splitters(self, qtbot):
        """#869 回帰防止: 作業領域とプレビュー詳細 splitter の両方を保存する。"""
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab.main_splitter.saveState.return_value = b"main-state"
        mock_window.search_tab.preview_splitter.saveState.return_value = b"preview-state"

        settings = Mock()
        MainWindow._save_splitter_states(mock_window, settings)

        saved_keys = {call.args[0] for call in settings.setValue.call_args_list}
        assert "splitter/main_work_area" in saved_keys
        assert "splitter/preview_details" in saved_keys

    def test_restore_preserves_preview_orientation(self, qtbot):
        """#865/#869: プレビュー詳細 splitter の縦 orientation を復元後も維持する。"""
        from unittest.mock import Mock

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QSplitter, QWidget

        from lorairo.gui.window.main_window import MainWindow

        # 旧 (横) 保存状態
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(QWidget())
        horizontal.addWidget(QWidget())
        saved_horizontal_state = horizontal.saveState()

        # 新 (縦) = .ui 由来の設計 orientation (preview-details=Vertical)
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(QWidget())
        vertical.addWidget(QWidget())

        mock_window = Mock()
        mock_window.search_tab.preview_splitter = vertical

        settings = Mock()
        settings.value.side_effect = lambda key: (
            saved_horizontal_state if key == "splitter/preview_details" else None
        )

        MainWindow._restore_splitter_states(mock_window, settings)

        assert vertical.orientation() == Qt.Orientation.Vertical


class TestModelSelectionStateManagerInit:
    """ModelSelectionStateManager 初期化と AnnotateTab への DI 検証 (#884)。"""

    def test_model_selection_state_manager_initialized(self) -> None:
        """MainWindow が ModelSelectionStateManager を初期化する (#884)。"""
        from unittest.mock import Mock, patch

        from lorairo.gui.state.model_selection_state import ModelSelectionStateManager
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        # RuntimeError が起きない正常系
        MainWindow._initialize_model_selection_state_manager(mock_window)
        assert isinstance(mock_window.model_selection_state_manager, ModelSelectionStateManager)

    def test_model_selection_state_manager_init_failure_sets_none(self) -> None:
        """ModelSelectionStateManager 初期化失敗時は None を設定する (#884)。"""
        from unittest.mock import Mock, patch

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        with patch(
            "lorairo.gui.window.main_window.ModelSelectionStateManager",
            side_effect=RuntimeError("init error"),
        ):
            MainWindow._initialize_model_selection_state_manager(mock_window)
        assert mock_window.model_selection_state_manager is None


class _StubModel:
    """provider_batch_capability helper が読む属性だけ持つ stub。"""

    def __init__(self, *, id: int, provider: str, litellm_model_id: str) -> None:
        self.id = id
        self.provider = provider
        self.litellm_model_id = litellm_model_id
        self.model_types: tuple[object, ...] = ()


class TestStartAnnotationDispatchMode:
    """start_annotation の dispatch mode 分岐テスト (#884 Phase 2c, ADR 0076 §1)。"""

    def test_batch_api_mode_delegates_to_async_dispatch(self) -> None:
        """dispatch_mode=batch_api は async dispatch へ委譲し同期 workflow を起動しない。"""
        from unittest.mock import Mock

        from lorairo.gui.widgets.run_settings_dialog import RunOptions
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotation_workflow_controller = Mock()
        mock_window.annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")

        MainWindow.start_annotation(mock_window)

        mock_window._dispatch_async_batch.assert_called_once()
        mock_window.annotation_workflow_controller.start_annotation_workflow.assert_not_called()

    def test_sync_mode_runs_workflow(self) -> None:
        """dispatch_mode=sync は従来どおり同期 workflow を起動する。"""
        from unittest.mock import Mock

        from lorairo.gui.widgets.run_settings_dialog import RunOptions
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotation_workflow_controller = Mock()
        mock_window.annotate_tab.run_options.return_value = RunOptions(dispatch_mode="sync")
        mock_window.annotate_tab.selected_litellm_model_ids.return_value = ["openai/gpt-4o"]
        # tabBatchTag 経路 (ステージング必須) を避けるため別 widget を currentWidget に返す
        mock_window.tabWidgetMainMode.currentWidget.return_value = Mock()

        MainWindow.start_annotation(mock_window)

        mock_window.annotation_workflow_controller.start_annotation_workflow.assert_called_once()


class TestDispatchAsyncBatch:
    """_dispatch_async_batch の射影 + fail-closed gate テスト (#884 Phase 2c, ADR 0076 §2)。"""

    @staticmethod
    def _build_window(
        *,
        ratings: dict[int, str | None],
        selected: list[str],
        discovery: list[str],
        model: object | None,
        in_progress: bool = False,
    ) -> object:
        from unittest.mock import Mock

        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        mock_window = Mock()
        mock_window._async_dispatch_in_progress = in_progress
        mock_window.annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")
        mock_window.annotate_tab.selected_litellm_model_ids.return_value = selected
        mock_window.annotate_tab.get_staged_items.return_value = {10: ("img10", "stored/10.webp")}
        # processed パス解決 (ADR 0064) は別メソッド。既定で解決成功を返す。
        mock_window._resolve_processed_paths_for_batch.return_value = {10: "/data/processed/10.webp"}

        workflow_service = Mock()
        workflow_service.list_batch_capable_models.return_value = discovery
        mock_window.service_container.provider_batch_workflow_service = workflow_service
        mock_window.service_container.annotator_library = Mock()
        mock_window.db_manager.image_repo.get_latest_normalized_ratings_by_image_ids.return_value = ratings
        mock_window.db_manager.model_repo.get_model_by_litellm_id.return_value = model
        return mock_window

    def test_all_sendable_batch_capable_starts_worker(self) -> None:
        from unittest.mock import patch

        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._dispatch_async_batch(mock_window)
            mock_qmb.warning.assert_not_called()
            mock_qmb.critical.assert_not_called()

        mock_window._start_async_dispatch_worker.assert_called_once()
        assert mock_window._async_dispatch_in_progress is True

    def test_run_settings_prompt_profile_and_description_forwarded(self) -> None:
        # #902: run settings の prompt_profile / description を射影へ配線する
        # (旧: "default" / None 固定)。ADR 0076 §1。
        from unittest.mock import patch

        from lorairo.gui.widgets.run_settings_dialog import RunOptions
        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        mock_window.annotate_tab.run_options.return_value = RunOptions(
            dispatch_mode="batch_api",
            prompt_profile="photoreal-v2",
            description="monthly audit run",
        )

        with (
            patch("lorairo.gui.window.main_window.QMessageBox"),
            patch("lorairo.gui.window.main_window.project_async_batch_dispatch") as mock_project,
        ):
            MainWindow._dispatch_async_batch(mock_window)

        mock_project.assert_called_once()
        kwargs = mock_project.call_args.kwargs
        assert kwargs["prompt_profile"] == "photoreal-v2"
        assert kwargs["description"] == "monthly audit run"

    def test_unrated_images_rejected(self) -> None:
        from unittest.mock import patch

        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={},  # 未判定 (unrated)
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._dispatch_async_batch(mock_window)
            mock_qmb.warning.assert_called_once()

        mock_window._start_async_dispatch_worker.assert_not_called()

    def test_non_batch_capable_model_rejected(self) -> None:
        from unittest.mock import patch

        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],  # local は discovery に無い
            model=model,
        )

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._dispatch_async_batch(mock_window)
            mock_qmb.warning.assert_called_once()

        mock_window._start_async_dispatch_worker.assert_not_called()

    def test_no_staged_images_shows_info(self) -> None:
        from unittest.mock import patch

        from lorairo.gui.window.main_window import MainWindow

        mock_window = self._build_window(
            ratings={},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=None,
        )
        mock_window.annotate_tab.get_staged_items.return_value = {}

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._dispatch_async_batch(mock_window)
            mock_qmb.information.assert_called_once()

        mock_window._start_async_dispatch_worker.assert_not_called()

    def test_reentry_guard_blocks_second_dispatch(self) -> None:
        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
            in_progress=True,
        )

        MainWindow._dispatch_async_batch(mock_window)

        mock_window._start_async_dispatch_worker.assert_not_called()

    def test_dry_run_skips_submission(self) -> None:
        from unittest.mock import patch

        from lorairo.gui.widgets.run_settings_dialog import RunOptions
        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        mock_window.annotate_tab.run_options.return_value = RunOptions(
            dispatch_mode="batch_api", dry_run=True
        )

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._dispatch_async_batch(mock_window)
            mock_qmb.information.assert_called_once()

        mock_window._start_async_dispatch_worker.assert_not_called()

    def test_missing_processed_paths_rejected(self) -> None:
        # ADR 0064: processed 版が無い画像があれば dispatch しない。
        from lorairo.gui.window.main_window import MainWindow

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        mock_window = self._build_window(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        mock_window._resolve_processed_paths_for_batch.return_value = None  # 解決失敗

        MainWindow._dispatch_async_batch(mock_window)

        mock_window._start_async_dispatch_worker.assert_not_called()


class TestFinalizeSubmittedJobs:
    """_finalize_submitted_jobs の二重送信防止テスト (#900 Codex P2)。"""

    def test_finalize_clears_staging_and_refreshes_jobs(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.staging_state_manager = Mock()
        mock_window._async_dispatch_image_ids = [10, 11]
        mock_window.jobs_tab = Mock()

        MainWindow._finalize_submitted_jobs(mock_window, [101])

        mock_window.staging_state_manager.remove_image_ids.assert_called_once_with([10, 11])
        mock_window.jobs_tab.refresh.assert_called_once()

    def test_finalize_noop_when_no_jobs(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.staging_state_manager = Mock()
        mock_window._async_dispatch_image_ids = [10]

        MainWindow._finalize_submitted_jobs(mock_window, [])

        mock_window.staging_state_manager.remove_image_ids.assert_not_called()

    def test_failed_with_partial_finalizes(self) -> None:
        from unittest.mock import Mock, patch

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._on_async_dispatch_failed(mock_window, ValueError("boom"), [101])
            mock_qmb.critical.assert_called_once()

        mock_window._finalize_submitted_jobs.assert_called_once_with([101])

    def test_failed_total_does_not_finalize(self) -> None:
        from unittest.mock import Mock, patch

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._on_async_dispatch_failed(mock_window, ValueError("boom"), [])
            mock_qmb.critical.assert_called_once()

        mock_window._finalize_submitted_jobs.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
