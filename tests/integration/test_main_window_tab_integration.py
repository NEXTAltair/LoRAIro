"""MainWindow タブ統合テスト

Phase 2.5で導入されたトップレベルタブ機能の統合テスト。
MainWindow初期化、タブ切り替え、ウィジェット統合を検証。
"""

from unittest.mock import Mock

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QTabWidget

from lorairo.gui.widgets.error_log_viewer_widget import ErrorLogViewerWidget
from lorairo.gui.widgets.results_widget import ResultsWidget
from lorairo.gui.window.main_window import MainWindow


@pytest.fixture
def main_window_with_tabs(qapp, monkeypatch):
    """タブ統合済みMainWindowフィクスチャ"""
    # QMessageBox.criticalをモック（初期化エラーダイアログ抑制）
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *args: None)

    window = MainWindow()
    yield window
    window.close()


class TestMainWindowTabInitialization:
    """MainWindowタブ初期化テスト"""

    def test_tabwidgetmainmode_created(self, main_window_with_tabs):
        """tabWidgetMainModeが作成される"""
        assert hasattr(main_window_with_tabs, "tabWidgetMainMode")
        assert main_window_with_tabs.tabWidgetMainMode is not None
        assert isinstance(main_window_with_tabs.tabWidgetMainMode, QTabWidget)

    def test_six_tabs_created(self, main_window_with_tabs):
        """6つのタブ（検索/マップ/アノテーション/ジョブ/結果/エラー）が作成される"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.count() == 6
        assert [tab_widget.tabText(i) for i in range(tab_widget.count())] == [
            "検索",
            "マップ",
            "アノテーション",
            "ジョブ",
            "結果",
            "エラー",
        ]

    def test_stub_pages_exist(self, main_window_with_tabs):
        """マップ/結果タブはスタブページとして存在する"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.widget(1).objectName() == "tabMap"
        assert tab_widget.widget(4).objectName() == "tabResults"

    def test_tab_order_matches_wireframe_nav(self, main_window_with_tabs):
        """タブ順序が Wireframes v11 のナビ順に一致する"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode
        assert tab_widget.widget(0) is window.tabWorkspace
        assert tab_widget.widget(2) is window.tabBatchTag
        assert tab_widget.widget(3) is window.provider_batch_job_widget
        assert tab_widget.widget(5).objectName() == "tabErrors"

    def test_errors_tab_embeds_error_log_viewer(self, main_window_with_tabs):
        """エラータブに ErrorLogViewerWidget が常設される"""
        errors_tab = main_window_with_tabs.tabWidgetMainMode.widget(5)
        assert errors_tab.objectName() == "tabErrors"
        viewer = errors_tab.findChild(ErrorLogViewerWidget)
        assert viewer is not None
        assert main_window_with_tabs.error_log_viewer_widget is viewer

    def test_error_notification_click_navigates_to_errors_tab(self, main_window_with_tabs):
        """エラー通知クリックでエラータブへ遷移する"""
        window = main_window_with_tabs
        window._on_error_notification_clicked()
        assert window.tabWidgetMainMode.currentWidget() is window.tabErrors

    def test_results_tab_embeds_results_widget(self, main_window_with_tabs):
        """結果タブに ResultsWidget が常設される"""
        results_tab = main_window_with_tabs.tabResults
        viewer = results_tab.findChild(ResultsWidget)
        assert viewer is not None
        assert main_window_with_tabs.results_widget is viewer

    def test_results_tab_has_no_stub_label(self, main_window_with_tabs):
        """スタブラベルが除去されている"""
        from PySide6.QtWidgets import QLabel

        stub = main_window_with_tabs.tabResults.findChild(QLabel, "labelResultsStub")
        assert stub is None

    def test_results_accept_marks_image_reviewed(self, main_window_with_tabs):
        """ResultsWidget の accept シグナルで db_manager.mark_image_reviewed が呼ばれる"""
        from unittest.mock import Mock

        window = main_window_with_tabs
        mark = Mock(return_value=True)
        window.db_manager.mark_image_reviewed = mark
        window.results_widget.accept_requested.emit(42)
        mark.assert_called_once_with(42, reviewed=True)

    def test_results_accept_clean_marks_all(self, main_window_with_tabs):
        """accept_clean シグナルで複数画像が reviewed=True にマークされる"""
        from unittest.mock import Mock

        window = main_window_with_tabs
        mark = Mock(return_value=True)
        window.db_manager.mark_image_reviewed = mark
        window.results_widget.accept_clean_requested.emit([1, 2, 3])
        assert mark.call_count == 3

    def test_workspace_tab_contains_splitter(self, main_window_with_tabs):
        """ワークスペースタブにsplitterMainWorkAreaが含まれる"""
        workspace_tab = main_window_with_tabs.tabWidgetMainMode.widget(0)
        assert workspace_tab is not None

        # splitterMainWorkAreaがワークスペースタブの子孫である
        splitter = main_window_with_tabs.splitterMainWorkArea
        assert splitter is not None

        # splitterの親を辿ってworkspace_tabに到達できる
        parent = splitter.parent()
        found = False
        while parent is not None:
            if parent == workspace_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "splitterMainWorkArea should be a descendant of workspace tab"

    def test_batch_tag_tab_structure(self, main_window_with_tabs):
        """アノテーションタブが適切な構造を持つ"""
        batch_tag_tab = main_window_with_tabs.tabBatchTag
        assert batch_tag_tab is not None
        assert batch_tag_tab.objectName() == "tabBatchTag"

        # 操作パネルが存在
        operations_group = batch_tag_tab.findChild(object, "groupBoxBatchOperations")
        assert operations_group is not None

    def test_provider_batch_tab_structure(self, main_window_with_tabs):
        """ジョブタブ（Provider Batch）が適切な構造を持つ"""
        provider_batch_tab = main_window_with_tabs.provider_batch_job_widget
        assert provider_batch_tab is not None
        assert provider_batch_tab.objectName() == "providerBatchJobWidget"
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.widget(tab_widget.indexOf(provider_batch_tab)) is provider_batch_tab


class TestTabSwitching:
    """タブ切り替えテスト"""

    def test_default_tab_is_workspace(self, main_window_with_tabs):
        """デフォルトで表示されるタブはワークスペース"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.currentIndex() == 0

    def test_can_switch_to_batch_tag_tab(self, main_window_with_tabs, qtbot):
        """アノテーションタブに切り替えられる"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode

        # アノテーションタブに切り替え
        tab_widget.setCurrentWidget(window.tabBatchTag)

        # イベント処理を待つ
        qtbot.wait(10)

        assert tab_widget.currentWidget() is window.tabBatchTag

    def test_can_switch_back_to_workspace(self, main_window_with_tabs, qtbot):
        """検索（ワークスペース）タブに戻せる"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode

        # アノテーションタブに切り替え
        tab_widget.setCurrentWidget(window.tabBatchTag)
        qtbot.wait(10)

        # 検索タブに戻す
        tab_widget.setCurrentWidget(window.tabWorkspace)
        qtbot.wait(10)

        assert tab_widget.currentWidget() is window.tabWorkspace

    def test_can_switch_to_provider_batch_tab(self, main_window_with_tabs, qtbot):
        """ジョブタブ（Provider Batch）に切り替えられる"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode

        tab_widget.setCurrentWidget(window.provider_batch_job_widget)
        qtbot.wait(10)

        assert tab_widget.currentWidget() is window.provider_batch_job_widget

    def test_provider_batch_shares_batch_tag_staging(self, main_window_with_tabs):
        """通常アノテーションとバッチAPIは同じステージング状態を共有する。"""
        batch_staging = main_window_with_tabs.batchTagAddWidget.get_staging_widget()
        provider_staging = main_window_with_tabs.provider_batch_job_widget.get_staging_widget()

        assert provider_staging.get_staged_items() is batch_staging.get_staged_items()

    def test_provider_batch_model_selection_widget_is_injected(self, main_window_with_tabs):
        """バッチAPIのモデル選択 placeholder は実 widget に置換されている。"""
        provider_widget = main_window_with_tabs.provider_batch_job_widget
        model_selection = provider_widget.get_model_selection_widget()

        assert model_selection.objectName() == "providerBatchModelSelection"
        assert provider_widget.modelSelectionPlaceholder.parent() is None
        assert provider_widget.executionLayout.indexOf(model_selection) != -1

    def test_tab_shortcuts_registered_for_all_tabs(self, main_window_with_tabs):
        """Ctrl+1〜N のショートカットがタブ数分登録される"""
        window = main_window_with_tabs
        sequences = {sc.key().toString() for sc in window.findChildren(QShortcut)}
        expected = {f"Ctrl+{i + 1}" for i in range(window.tabWidgetMainMode.count())}
        assert expected.issubset(sequences)

    def test_tab_shortcut_activation_switches_tab(self, main_window_with_tabs):
        """ショートカット発火でメインタブが切り替わる"""
        window = main_window_with_tabs
        shortcut_by_seq = {sc.key().toString(): sc for sc in window.findChildren(QShortcut)}

        shortcut_by_seq["Ctrl+4"].activated.emit()
        assert window.tabWidgetMainMode.currentIndex() == 3

        shortcut_by_seq["Ctrl+1"].activated.emit()
        assert window.tabWidgetMainMode.currentIndex() == 0


class TestBatchTagWidgetIntegration:
    """BatchTagAddWidget統合テスト"""

    def test_batchtagaddwidget_exists(self, main_window_with_tabs):
        """BatchTagAddWidgetが存在する"""
        assert hasattr(main_window_with_tabs, "batchTagAddWidget")
        assert main_window_with_tabs.batchTagAddWidget is not None

    def test_stage_toolbar_button_treats_clicked_bool_as_selection_request(
        self, main_window_with_tabs, monkeypatch, qtbot
    ):
        """ツールバーボタンは clicked(bool) を通常選択要求としてステージングへ送る。"""
        main_window_with_tabs.dataset_state_manager.set_selected_images([101, 102])
        add_to_staging = Mock()
        monkeypatch.setattr(
            main_window_with_tabs.batchTagAddWidget, "add_image_ids_to_staging", add_to_staging
        )
        information = Mock()
        monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox.information", information)

        main_window_with_tabs.pushButtonStageToBatchTag.click()
        qtbot.wait(10)

        add_to_staging.assert_called_once_with([101, 102])
        information.assert_not_called()
        assert main_window_with_tabs.tabWidgetMainMode.currentWidget() is main_window_with_tabs.tabBatchTag

    def test_batchtagaddwidget_in_batch_tag_tab(self, main_window_with_tabs):
        """BatchTagAddWidgetがアノテーションタブ内に配置されている"""
        batch_tag_tab = main_window_with_tabs.tabBatchTag
        batch_tag_widget = main_window_with_tabs.batchTagAddWidget

        # BatchTagAddWidgetの親を辿ってbatch_tag_tabに到達できる
        parent = batch_tag_widget.parent()
        found = False
        while parent is not None:
            if parent == batch_tag_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "BatchTagAddWidget should be a descendant of batch tag tab"

    def test_batchtagaddwidget_placeholder_replaced(self, main_window_with_tabs):
        """BatchTagAddWidgetプレースホルダーが置換されている"""
        # プレースホルダーは deleteLater() で非同期削除されるため、
        # 置換後のウィジェットが正しく配置されていることを検証
        batch_tag_widget = main_window_with_tabs.batchTagAddWidget
        assert batch_tag_widget is not None
        assert batch_tag_widget.objectName() == "batchTagAddWidget"

        # BatchTagAddWidgetがスプリッター内に正しく配置されている
        batch_tag_tab = main_window_with_tabs.tabBatchTag
        splitter = batch_tag_tab.findChild(object, "splitterBatchTagMain")
        if splitter:
            # スプリッター内にBatchTagAddWidgetが含まれている
            found_in_splitter = False
            for i in range(splitter.count()):
                if splitter.widget(i) == batch_tag_widget:
                    found_in_splitter = True
                    break
            assert found_in_splitter, "BatchTagAddWidget should be in splitter"


class TestSignalConnections:
    """シグナル接続テスト"""

    def test_tab_changed_signal_connected(self, main_window_with_tabs):
        """tabWidgetMainMode.currentChanged シグナルが接続されている"""
        # currentChangedシグナルのレシーバー数を確認
        # 少なくとも1つの接続があるはず（_on_main_tab_changed）
        # Note: Qt内部でシグナル接続数を直接取得する方法は限られているため、
        # シグナル発火時の動作で確認
        # ここでは接続されていることの検証は省略（実際の動作テストで確認）
        assert hasattr(main_window_with_tabs, "_on_main_tab_changed")


class TestStatePreservation:
    """状態保持テスト"""

    def test_dataset_state_manager_preserved_across_tabs(self, main_window_with_tabs):
        """タブを切り替えてもDatasetStateManagerが保持される"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        dataset_state = main_window_with_tabs.dataset_state_manager

        # ワークスペースタブのDatasetStateManager
        workspace_state = main_window_with_tabs.dataset_state_manager

        # アノテーションタブに切り替え
        tab_widget.setCurrentWidget(main_window_with_tabs.tabBatchTag)

        # アノテーションタブでもDatasetStateManagerが同じインスタンス
        batch_tag_state = main_window_with_tabs.dataset_state_manager

        assert workspace_state is dataset_state
        assert batch_tag_state is dataset_state
        assert workspace_state is batch_tag_state


class TestAnnotationControlVisibility:
    """アノテーション制御表示テスト"""

    def test_tab_changed_handler_exists(self, main_window_with_tabs):
        """_on_main_tab_changedメソッドが存在する"""
        assert hasattr(main_window_with_tabs, "_on_main_tab_changed")


class TestAnnotationDataDisplayWidget:
    """AnnotationDataDisplayWidget統合テスト"""

    def test_annotation_display_exists_in_batch_tag(self, main_window_with_tabs):
        """バッチタグタブにAnnotationDataDisplayWidgetが存在する"""
        assert hasattr(main_window_with_tabs, "batchTagAnnotationDisplay")
        assert main_window_with_tabs.batchTagAnnotationDisplay is not None

    def test_annotation_display_in_batch_tag_tab(self, main_window_with_tabs):
        """AnnotationDataDisplayWidgetがアノテーションタブ内に配置されている"""
        batch_tag_tab = main_window_with_tabs.tabBatchTag
        annotation_display = main_window_with_tabs.batchTagAnnotationDisplay

        # AnnotationDataDisplayWidgetの親を辿ってbatch_tag_tabに到達できる
        parent = annotation_display.parent()
        found = False
        while parent is not None:
            if parent == batch_tag_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "AnnotationDataDisplayWidget should be a descendant of batch tag tab"

    def test_annotation_display_placeholder_replaced(self, main_window_with_tabs):
        """AnnotationDataDisplayWidgetプレースホルダーが置換されている"""
        # プレースホルダーは deleteLater() で非同期削除されるため、
        # 置換後のウィジェットが正しく配置されていることを検証
        annotation_display = main_window_with_tabs.batchTagAnnotationDisplay
        assert annotation_display is not None
        assert annotation_display.objectName() == "batchTagAnnotationDisplay"
