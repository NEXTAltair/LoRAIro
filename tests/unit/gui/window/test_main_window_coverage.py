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

    def test_on_staged_images_changed_does_not_push_to_export_widget(self):
        """#896: エクスポートタブは自治購読するため MainWindow からは push しない (ADR 0055)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [1, 2, 3])
        mock_window.export_tab.set_image_ids.assert_not_called()

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
        """Phase 5/#896: export_data は ExportTab.refresh() でステージング再読込し遷移する。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow.export_data(mock_window)
        mock_window.export_tab.refresh.assert_called_once_with()
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
        mock_window.staging_state_manager.get_image_ids.return_value = [7]

        MainWindow.send_selected_to_batch_tag(mock_window, False)

        mock_window.annotate_tab.add_image_ids_to_staging.assert_called_once_with([7])
        # #1059: ステージング追加でタブは移動しない
        mock_window.tabWidgetMainMode.setCurrentWidget.assert_not_called()

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
        mock_window.dataset_state_manager.selected_image_ids = [1, 2, 3]
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()
        # 全件がステージングに受理された
        mock_window.staging_state_manager.get_image_ids.return_value = [1, 2, 3]
        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])
        mock_window.annotate_tab.add_image_ids_to_staging.assert_called_once_with([1, 2, 3])
        # #1059: タブは移動せず、ステータスバー通知でフィードバックする
        mock_window.tabWidgetMainMode.setCurrentWidget.assert_not_called()
        mock_window.statusBar.return_value.showMessage.assert_called_once_with(
            "3件をステージングに追加しました", 5000
        )

    def test_send_selected_deselects_only_staged_ids(self):
        """#1096/#1112: 送った画像だけ選択解除し、他ページの選択は保持する (Codex P2)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        # 他ページ選択 (99) を含む全選択。payload は可視ページの [1, 2, 3] のみ。
        mock_window.dataset_state_manager.selected_image_ids = [1, 2, 3, 99]
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()
        # 1, 2, 3 は受理された (99 は payload 外なので staging には無い)
        mock_window.staging_state_manager.get_image_ids.return_value = [1, 2, 3]

        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])

        # 全 clear ではなく、送った 1/2/3 を除いた残り (他ページ 99) を set し直す
        mock_window.dataset_state_manager.clear_selection.assert_not_called()
        mock_window.dataset_state_manager.set_selected_images.assert_called_once_with([99])

    def test_send_selected_keeps_selection_for_rejected_ids(self):
        """#1112 (2巡目): 上限/解決失敗で受理されなかった ID は選択を残す (Codex P2)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = [1, 2, 3]
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()
        # 上限到達で 1, 2 のみ受理、3 は拒否された
        mock_window.staging_state_manager.get_image_ids.return_value = [1, 2]

        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])

        # 受理された 1/2 だけ解除し、拒否された 3 は選択を残す
        mock_window.dataset_state_manager.set_selected_images.assert_called_once_with([3])
        # 受理件数でフィードバックする (target 件数 3 ではなく 2)
        mock_window.statusBar.return_value.showMessage.assert_called_once_with(
            "2件をステージングに追加しました", 5000
        )

    def test_send_selected_none_accepted_keeps_all_selection(self):
        """#1112 (2巡目): 1件も受理されなければ選択を一切変更しない (Codex P2)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = [1, 2, 3]
        mock_window.annotate_tab = Mock()
        mock_window.tabWidgetMainMode = Mock()
        # 上限到達で 1 件も受理されなかった (staging は無関係な既存分のみ)
        mock_window.staging_state_manager.get_image_ids.return_value = [50, 51]

        MainWindow.send_selected_to_batch_tag(mock_window, [1, 2, 3])

        mock_window.dataset_state_manager.set_selected_images.assert_not_called()
        mock_window.dataset_state_manager.clear_selection.assert_not_called()
        mock_window.statusBar.return_value.showMessage.assert_called_once_with(
            "0件をステージングに追加しました", 5000
        )

    def test_send_selected_no_ids_does_not_change_selection(self):
        """#1096: 送信対象が無い場合は選択を変更しない (誤操作で選択を失わない)。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state_manager = Mock()
        mock_window.dataset_state_manager.selected_image_ids = []
        mock_window.annotate_tab = Mock()

        with patch("lorairo.gui.window.main_window.QMessageBox"):
            MainWindow.send_selected_to_batch_tag(mock_window, [])

        mock_window.dataset_state_manager.set_selected_images.assert_not_called()
        mock_window.dataset_state_manager.clear_selection.assert_not_called()


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


class TestSplitterStateDelegation:
    """#896: MainWindow は splitter サイズ状態の save/restore を SearchTab へ委譲する。

    #865/#869 の orientation 維持・両 splitter 保存の不変条件は SearchTabWidget 側の
    ``save_layout_state`` / ``restore_layout_state`` テスト (test_search_tab.py) が担保する。
    MainWindow 側は委譲が行われることのみ検証する。
    """

    def test_save_window_state_delegates_splitter_to_search_tab(self, qtbot):
        """MainWindow は splitter 保存を SearchTab へ委譲する (#896)。"""
        from unittest.mock import MagicMock, Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.search_tab = MagicMock()
        with patch("lorairo.gui.window.main_window.QSettings"):
            MainWindow._save_window_state(mock_window)
        mock_window.search_tab.save_layout_state.assert_called_once()

    def test_restore_window_state_delegates_splitter_to_search_tab(self, qtbot):
        """MainWindow は splitter 復元を SearchTab へ委譲する (#896)。"""
        from unittest.mock import MagicMock, Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.SETTINGS_VERSION = MainWindow.SETTINGS_VERSION
        mock_window.search_tab = MagicMock()
        with patch("lorairo.gui.window.main_window.QSettings") as mock_settings_cls:
            settings = mock_settings_cls.return_value
            settings.value.side_effect = lambda key, *args, **kwargs: (
                MainWindow.SETTINGS_VERSION if key == "main_window/settings_version" else None
            )
            MainWindow._restore_window_state(mock_window)
        mock_window.search_tab.restore_layout_state.assert_called_once()


class TestModelSelectionStateManagerInit:
    """ModelSelectionStateManager 初期化と AnnotateTab への DI 検証 (#884)。"""

    def test_model_selection_state_manager_initialized(self) -> None:
        """MainWindow が ModelSelectionStateManager を初期化する (#884)。"""
        from unittest.mock import Mock

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


class TestAnnotationExecuteWrapper:
    """_on_annotation_execute_requested の縮退ガード (#896 PR4c, Codex P2)。

    controller 初期化が縮退した起動でも実行ボタンが無反応にならず、未初期化を
    警告することを検証する (旧 MainWindow.start_annotation の UX を保全)。
    """

    def test_delegates_and_navigates_when_started(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotation_workflow_controller = Mock()
        # 実行が実際に開始できた場合
        mock_window.annotation_workflow_controller.start_annotation.return_value = True

        MainWindow._on_annotation_execute_requested(mock_window, "batch_api")

        # #1099: 実行ボタンが渡す dispatch_mode を controller へ伝搬する
        mock_window.annotation_workflow_controller.start_annotation.assert_called_once_with("batch_api")
        # #1102: 開始成功時は Jobs タブへ遷移する
        mock_window._navigate_to_jobs_tab.assert_called_once_with()

    def test_no_navigation_when_start_rejected(self) -> None:
        """#1102 Codex P2: 実行が開始前に拒否された場合は Jobs へ遷移しない。"""
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotation_workflow_controller = Mock()
        # ステージング空・モデル未選択・射影失敗等で開始前に拒否
        mock_window.annotation_workflow_controller.start_annotation.return_value = False

        MainWindow._on_annotation_execute_requested(mock_window, "sync")

        mock_window.annotation_workflow_controller.start_annotation.assert_called_once_with("sync")
        mock_window._navigate_to_jobs_tab.assert_not_called()

    def test_warns_when_controller_missing(self) -> None:
        from unittest.mock import Mock, patch

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.annotation_workflow_controller = None

        with patch("lorairo.gui.window.main_window.QMessageBox") as mock_qmb:
            MainWindow._on_annotation_execute_requested(mock_window, "sync")
            mock_qmb.warning.assert_called_once()
        # controller 未初期化なら Jobs 遷移もしない
        mock_window._navigate_to_jobs_tab.assert_not_called()


class TestNavigateToJobsTab:
    """#1102: アノテーション実行後の Jobs タブ遷移。"""

    def test_navigates_to_jobs_tab_when_present(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.tabWidgetMainMode.indexOf.return_value = 3

        MainWindow._navigate_to_jobs_tab(mock_window)

        mock_window.tabWidgetMainMode.setCurrentWidget.assert_called_once_with(mock_window.jobs_tab)

    def test_no_navigation_when_jobs_tab_missing(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.jobs_tab = None

        MainWindow._navigate_to_jobs_tab(mock_window)

        mock_window.tabWidgetMainMode.setCurrentWidget.assert_not_called()

    def test_no_navigation_when_jobs_tab_not_inserted(self) -> None:
        from unittest.mock import Mock

        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.tabWidgetMainMode.indexOf.return_value = -1

        MainWindow._navigate_to_jobs_tab(mock_window)

        mock_window.tabWidgetMainMode.setCurrentWidget.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
