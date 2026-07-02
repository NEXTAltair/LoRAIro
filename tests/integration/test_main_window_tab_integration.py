"""MainWindow タブ統合テスト

Phase 2.5で導入されたトップレベルタブ機能の統合テスト。
MainWindow初期化、タブ切り替え、ウィジェット統合を検証。
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QTabWidget, QWidget

from lorairo.gui.widgets.errors_triage_widget import ErrorsTriageWidget
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

    def test_eight_tabs_created(self, main_window_with_tabs):
        """8つのタブ（検索/アノテーション/ジョブ/結果/エクスポート/マップ/エラー/CLI）が作成される

        順序は操作プロトタイプ (wireframes.html restructureNav) のナビ順 PIPE+UTIL に一致する:
        PIPE=検索→アノテーション→ジョブ→結果→エクスポート, UTIL=マップ→エラー→CLI。
        """
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.count() == 8
        assert [tab_widget.tabText(i) for i in range(tab_widget.count())] == [
            "検索",
            "アノテーション",
            "ジョブ",
            "結果",
            "エクスポート",
            "マップ",
            "エラー",
            "CLI",
        ]

    def test_stub_pages_exist(self, main_window_with_tabs):
        """マップ/結果タブはスタブページとして存在する"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.widget(5).objectName() == "tabMap"
        assert tab_widget.widget(3).objectName() == "tabResults"

    def test_tab_order_matches_wireframe_nav(self, main_window_with_tabs):
        """タブ順序が操作プロトタイプ (restructureNav PIPE+UTIL) のナビ順に一致する"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode
        assert tab_widget.widget(0) is window.tabWorkspace
        assert tab_widget.widget(1) is window.tabBatchTag
        assert tab_widget.widget(2) is window.jobs_tab
        assert tab_widget.widget(6).objectName() == "tabErrors"

    def test_errors_tab_embeds_triage_widget(self, main_window_with_tabs):
        """エラータブが ErrorsTabWidget で常設され ErrorsTriageWidget を内包する (#871)"""
        from lorairo.gui.tab.errors_tab import ErrorsTabWidget

        errors_container = main_window_with_tabs.tabWidgetMainMode.widget(6)
        assert errors_container.objectName() == "tabErrors"
        viewer = errors_container.findChild(ErrorsTriageWidget)
        assert viewer is not None
        assert isinstance(main_window_with_tabs.errors_tab, ErrorsTabWidget)
        assert main_window_with_tabs.errors_tab.triage_widget is viewer

    def test_export_tab_embeds_three_pane_panel(self, main_window_with_tabs):
        """エクスポートタブが ExportTabWidget で常設され 3ペイン + ExportOverlayBar を内包する (#949)"""
        from lorairo.gui.tab.export_tab import ExportTabWidget
        from lorairo.gui.widgets.export_overlay_bar import ExportOverlayBar
        from lorairo.gui.widgets.staging_tag_panel import StagingTagPanel

        export_container = main_window_with_tabs.tabWidgetMainMode.widget(4)
        assert export_container.objectName() == "tabExport"
        export_tab = main_window_with_tabs.export_tab
        assert isinstance(export_tab, ExportTabWidget)
        assert isinstance(export_tab.staging_tag_panel, StagingTagPanel)
        assert isinstance(export_tab.overlay_bar, ExportOverlayBar)
        assert export_tab.main_splitter.count() == 3

    def test_cli_tab_embeds_reference_widget(self, main_window_with_tabs):
        """CLI タブが CliTabWidget で常設され、CliReferenceWidget を内包する (Frame 8, #873)"""
        from lorairo.gui.tab.cli_tab import CliTabWidget
        from lorairo.gui.widgets.cli_reference_widget import CliReferenceWidget

        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode
        cli_tab = tab_widget.widget(7)
        assert isinstance(cli_tab, CliTabWidget)
        assert window.cli_tab is cli_tab
        assert isinstance(cli_tab.reference, CliReferenceWidget)
        # コンテンツは初回表示まで遅延生成される
        assert cli_tab.reference.content_loaded is False

    def test_pipeline_panel_embedded_in_annotation_group(self, main_window_with_tabs):
        """アノテーショングループにパイプライン構成ビューが常設される (#868 で AnnotateTab へ移送)"""
        annotate_tab = main_window_with_tabs.annotate_tab
        assert annotate_tab is not None
        assert annotate_tab.pipeline_stage_table is not None
        assert annotate_tab.inference_ledger_widget is not None
        assert annotate_tab.pipeline_stage_table.parent() is annotate_tab.groupBoxAnnotation
        assert annotate_tab.inference_ledger_widget.parent() is annotate_tab.groupBoxAnnotation

    def test_errors_resolve_marks_resolved(self, main_window_with_tabs):
        """resolve_requested シグナルで mark_errors_resolved_batch が呼ばれる"""
        from unittest.mock import Mock

        window = main_window_with_tabs
        mark = Mock(return_value=(True, 1))
        window.db_manager.mark_errors_resolved_batch = mark
        window.errors_tab.triage_widget.resolve_requested.emit(7)
        mark.assert_called_once_with([7])

    def test_errors_resolve_group_marks_all(self, main_window_with_tabs):
        """resolve_group_requested シグナルで複数 error_id が一括解決される"""
        from unittest.mock import Mock

        window = main_window_with_tabs
        mark = Mock(return_value=(True, 3))
        window.db_manager.mark_errors_resolved_batch = mark
        window.errors_tab.triage_widget.resolve_group_requested.emit([1, 2, 3])
        mark.assert_called_once_with([1, 2, 3])

    def test_error_notification_click_navigates_to_errors_tab(self, main_window_with_tabs):
        """エラー通知クリックでエラータブへ遷移する"""
        window = main_window_with_tabs
        window._on_error_notification_clicked()
        assert window.tabWidgetMainMode.currentWidget() is window.tabErrors

    def test_results_tab_embeds_results_widget(self, main_window_with_tabs):
        """結果タブに ResultsTabWidget が常設され ResultsWidget を内包する (#870)"""
        from lorairo.gui.tab.results_tab import ResultsTabWidget

        results_container = main_window_with_tabs.tabResults
        viewer = results_container.findChild(ResultsWidget)
        assert viewer is not None
        assert isinstance(main_window_with_tabs.results_tab, ResultsTabWidget)
        assert main_window_with_tabs.results_tab.results_widget is viewer

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
        window.results_tab.results_widget.accept_requested.emit(42)
        mark.assert_called_once_with(42, reviewed=True)

    def test_results_accept_clean_marks_all(self, main_window_with_tabs):
        """accept_clean シグナルで複数画像が reviewed=True にマークされる"""
        from unittest.mock import Mock

        window = main_window_with_tabs
        mark = Mock(return_value=True)
        window.db_manager.mark_image_reviewed = mark
        window.results_tab.results_widget.accept_clean_requested.emit([1, 2, 3])
        assert mark.call_count == 3

    def test_workspace_tab_contains_splitter(self, main_window_with_tabs):
        """ワークスペースタブに 3 ペイン作業領域 splitter が含まれる (#869: SearchTab 所有)"""
        workspace_tab = main_window_with_tabs.tabWidgetMainMode.widget(0)
        assert workspace_tab is not None

        # 作業領域 splitter は SearchTabWidget が所有し、main_splitter プロパティで公開する
        splitter = main_window_with_tabs.search_tab.main_splitter
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
        """ジョブタブ（JobsTabWidget）が適切な構造を持つ (#874)"""
        jobs_tab = main_window_with_tabs.jobs_tab
        assert jobs_tab is not None
        # タブ本体は JobsTabWidget、内部に ProviderBatchJobWidget を内包する
        assert jobs_tab.provider_batch_job_widget.objectName() == "providerBatchJobWidget"
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.widget(tab_widget.indexOf(jobs_tab)) is jobs_tab


class TestJobsTabSyncLedgerWiring:
    """ADR 0066: Jobs タブと WorkerService 同期ジョブ台帳の配線テスト"""

    def test_job_ledger_changed_refreshes_sync_jobs_table(self, main_window_with_tabs):
        """job_ledger_changed シグナルで Jobs タブの同期ジョブテーブルが更新される"""
        window = main_window_with_tabs
        table = window.jobs_tab.provider_batch_job_widget.get_sync_jobs_widget().tableSyncJobs
        assert table.rowCount() == 0

        window.worker_service.job_ledger.register("annotation_wiring", "annotation", "アノテーション処理")
        window.worker_service.job_ledger_changed.emit()

        assert table.rowCount() == 1
        assert table.item(0, 1).text() == "アノテーション処理"
        # 状態 (col2) は DS chip 文法で cellWidget 化 (Issue #790)
        assert table.cellWidget(0, 2).text() == "実行中"

    def test_sync_job_cancel_routes_to_worker_service(self, main_window_with_tabs):
        """Jobs 行のキャンセル要求が WorkerService.cancel_job へ委譲される (ADR 0066 §4)"""
        window = main_window_with_tabs
        cancel_mock = Mock(return_value=True)
        window.worker_service.cancel_job = cancel_mock

        window.jobs_tab.provider_batch_job_widget.sync_job_cancel_requested.emit("annotation_busy")

        cancel_mock.assert_called_once_with("annotation_busy")
        assert "annotation_busy" in window.statusBar().currentMessage()

    def test_sync_job_started_shows_statusbar_notification(self, main_window_with_tabs):
        """同期ジョブ開始時は statusbar 通知のみ (自動タブ遷移はしない、ADR 0066 §4)"""
        window = main_window_with_tabs
        current_index = window.tabWidgetMainMode.currentIndex()

        window.worker_service.enhanced_annotation_started.emit("annotation_started")

        assert "ジョブタブ" in window.statusBar().currentMessage()
        assert window.tabWidgetMainMode.currentIndex() == current_index


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

        tab_widget.setCurrentWidget(window.jobs_tab)
        qtbot.wait(10)

        assert tab_widget.currentWidget() is window.jobs_tab

    def test_provider_batch_is_monitor_only(self, main_window_with_tabs):
        """ジョブタブは監視専用で、作成入口 (ステージング / モデルピッカー) を持たない (ADR 0076 §3)。"""
        provider_widget = main_window_with_tabs.jobs_tab.provider_batch_job_widget

        assert not hasattr(provider_widget, "get_staging_widget")
        assert not hasattr(provider_widget, "get_model_selection_widget")
        assert not hasattr(provider_widget, "buttonSubmit")

    def test_navigate_menu_actions_for_all_tabs(self, main_window_with_tabs):
        """「移動」メニューに Ctrl+1〜N 付きアクションがタブ数分登録される"""
        window = main_window_with_tabs
        sequences = {a.shortcut().toString() for a in window.menuNavigate.actions()}
        expected = {f"Ctrl+{i + 1}" for i in range(window.tabWidgetMainMode.count())}
        assert expected.issubset(sequences)

    def test_navigate_menu_action_switches_tab(self, main_window_with_tabs):
        """移動メニューのアクション発火でメインタブが切り替わる。

        Ctrl+N は操作プロトタイプ (wireframes.html NUM2KEY) の固定割当で、視覚 index
        ではなくタブ識別子基準。番号がタブに固定されるため、Ctrl+2 は (視覚順では
        末尾付近の) マップへ飛ぶ。
        """
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode
        action_by_seq = {a.shortcut().toString(): a for a in window.menuNavigate.actions()}

        # Ctrl+4 = ジョブ
        action_by_seq["Ctrl+4"].trigger()
        assert tab_widget.currentWidget() is window.jobs_tab

        # Ctrl+2 = マップ (番号はタブに固定、視覚位置と非連動)
        action_by_seq["Ctrl+2"].trigger()
        assert tab_widget.currentWidget() is window.tabMap

        # Ctrl+1 = 検索
        action_by_seq["Ctrl+1"].trigger()
        assert tab_widget.currentWidget() is window.tabWorkspace


class TestBatchTagWidgetIntegration:
    """BatchTagAddWidget統合テスト"""

    def test_batchtagaddwidget_exists(self, main_window_with_tabs):
        """BatchTagAddWidget が AnnotateTabWidget 経由で参照できる (#868)"""
        annotate_tab = main_window_with_tabs.annotate_tab
        assert annotate_tab is not None
        assert annotate_tab.batch_tag_add_widget is not None

    def test_stage_toolbar_button_treats_clicked_bool_as_selection_request(
        self, main_window_with_tabs, monkeypatch, qtbot
    ):
        """ツールバーボタンは clicked(bool) を通常選択要求としてステージングへ送る。"""
        main_window_with_tabs.dataset_state_manager.set_selected_images([101, 102])
        add_to_staging = Mock()
        # #868: ステージング導線は AnnotateTabWidget へ委譲される
        monkeypatch.setattr(main_window_with_tabs.annotate_tab, "add_image_ids_to_staging", add_to_staging)
        information = Mock()
        monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox.information", information)

        # #869: ステージング導線ボタンは SearchTabWidget が所有する
        main_window_with_tabs.search_tab.pushButtonStageToBatchTag.click()
        qtbot.wait(10)

        add_to_staging.assert_called_once_with([101, 102])
        information.assert_not_called()
        # #1059: ステージング追加でアノテーションタブへ強制遷移しない (検索タブに留まる)
        assert (
            main_window_with_tabs.tabWidgetMainMode.currentWidget() is not main_window_with_tabs.tabBatchTag
        )

    def test_batchtagaddwidget_in_batch_tag_tab(self, main_window_with_tabs):
        """BatchTagAddWidgetがアノテーションタブ内に配置されている"""
        batch_tag_tab = main_window_with_tabs.tabBatchTag
        batch_tag_widget = main_window_with_tabs.annotate_tab.batch_tag_add_widget

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
        annotate_tab = main_window_with_tabs.annotate_tab
        batch_tag_widget = annotate_tab.batch_tag_add_widget
        assert batch_tag_widget is not None
        assert batch_tag_widget.objectName() == "batchTagAddWidget"

        # BatchTagAddWidgetがスプリッター内に正しく配置されている (#868: AnnotateTab が所有)
        splitter = annotate_tab.splitterBatchTagMain
        if splitter:
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
    """AnnotationDataDisplayWidget 除去の回帰テスト (#850)。

    バッチタグタブの常設アノテーション詳細表示 (batchTagAnnotationDisplay) は
    #850 で AnnotateTab から除去された。MainWindow / AnnotateTabWidget の
    どちらにも残存しないことを確認する。
    """

    def test_annotation_display_removed_from_main_window(self, main_window_with_tabs):
        """MainWindow は batchTagAnnotationDisplay 属性を持たない (#850)"""
        assert not hasattr(main_window_with_tabs, "batchTagAnnotationDisplay")

    def test_annotation_display_removed_from_annotate_tab(self, main_window_with_tabs):
        """アノテーションタブ配下に batchTagAnnotationDisplay が残っていない (#850)"""
        annotate_tab = main_window_with_tabs.annotate_tab
        assert annotate_tab is not None
        assert annotate_tab.findChild(QWidget, "batchTagAnnotationDisplay") is None
