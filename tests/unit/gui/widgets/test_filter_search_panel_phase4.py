# tests/unit/gui/widgets/test_filter_search_panel_phase4.py
"""FilterSearchPanel x SearchFacetsSidebar の統合テスト (Phase 4)。

FilterSearchPanel が SearchFacetsSidebar を組み込み、
facets_changed シグナルを受け取って検索条件に反映することを検証する。
"""

from unittest.mock import MagicMock

import pytest

from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.gui.widgets.search_facets_sidebar import SearchFacetsSidebar


@pytest.fixture()
def panel(qtbot):
    """FilterSearchPanel インスタンスを作成して qtbot に登録する。"""
    widget = FilterSearchPanel()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture()
def panel_with_service(qtbot):
    """SearchFilterService が設定された FilterSearchPanel を返す。"""
    service = MagicMock()
    service.create_search_conditions = MagicMock(return_value=MagicMock())
    service.parse_search_input = MagicMock(return_value=([], []))
    service.get_current_conditions = MagicMock(return_value=None)
    service.get_recently_used_model_ids = MagicMock(return_value=["openai/gpt-4o", "anthropic/claude-3-5"])
    service.get_created_at_histogram = MagicMock(return_value=[])
    service.db_manager = MagicMock()
    service.db_manager.repository = MagicMock()
    service.db_manager.repository.merged_reader = None

    widget = FilterSearchPanel()
    qtbot.addWidget(widget)
    widget.set_search_filter_service(service)
    # ファセットは背景 worker で取得されるため、反映完了を待ってから返す (#1438)
    qtbot.waitUntil(lambda: widget._search_facets_sidebar._model_list.count() == 2, timeout=5000)
    return widget, service


@pytest.mark.unit
@pytest.mark.gui
class TestSearchFacetsSidebarComposition:
    def test_warning_filter_favorite_roundtrip_and_legacy_reset(self, panel):
        panel._search_facets_sidebar.set_review_warnings_only(True)
        saved = panel.get_current_conditions()
        assert saved["annotation_review_warnings_only"] is True
        panel._clear_all_inputs()
        assert panel.get_current_conditions()["annotation_review_warnings_only"] is False
        panel.apply_conditions(saved)
        assert panel.get_current_conditions()["annotation_review_warnings_only"] is True
        assert panel._facet_values["annotation_review_warnings_only"] is True
        panel.apply_conditions({"search_type": "tags", "keywords": ["dog"]})
        assert panel.get_current_conditions()["annotation_review_warnings_only"] is False

    """SearchFacetsSidebar が FilterSearchPanel に正しく組み込まれることを検証する。"""

    def test_search_facets_sidebar_is_created(self, panel):
        """_search_facets_sidebar が SearchFacetsSidebar インスタンスである。"""
        assert isinstance(panel._search_facets_sidebar, SearchFacetsSidebar)

    def test_facet_values_initialized_empty(self, panel):
        """_facet_values が空辞書で初期化されている。"""
        assert panel._facet_values == {}

    def test_search_facets_sidebar_has_parent(self, panel):
        """_search_facets_sidebar が panel の子孫に含まれる。"""
        # Qt は addWidget 後に親を layout の所有者に変更するため ancestor チェーンを確認する
        widget = panel._search_facets_sidebar
        current = widget
        found = False
        for _ in range(10):
            parent = current.parent()
            if parent is None:
                break
            if parent is panel:
                found = True
                break
            current = parent
        assert found, "_search_facets_sidebar の ancestor に FilterSearchPanel が含まれない"

    def test_expanding_spacer_remains_last(self, panel):
        """末尾の Expanding spacer がレイアウト最後尾に留まる (Issue #1095)。

        favorite_filter / search_facets_sidebar は spacer の手前に挿入され、
        spacer が両ウィジェットの間に挟まって余分な空白を生じさせないことを検証する。
        """
        contents_layout = panel.ui.scrollAreaWidgetContents.layout()
        last_index = contents_layout.count() - 1
        assert contents_layout.itemAt(last_index).spacerItem() is not None, (
            "レイアウト最後尾が spacer ではない"
        )
        favorite_index = contents_layout.indexOf(panel._favorite_filter)
        sidebar_index = contents_layout.indexOf(panel._search_facets_sidebar)
        assert favorite_index < last_index
        assert sidebar_index < last_index
        # favorite_filter の直後に sidebar が並び、両者の間に spacer が挟まらない
        assert sidebar_index == favorite_index + 1


@pytest.mark.unit
@pytest.mark.gui
class TestFacetsChangedSignal:
    """facets_changed シグナルのハンドリングを検証する。"""

    def test_facets_changed_stores_values(self, panel):
        """facets_changed シグナルで _facet_values が更新される。"""
        test_facets: dict[str, object] = {
            "manual_edit_filter": None,
            "reviewed_at_filter": "unreviewed",
            "error_state_filter": None,
            "model_filter": None,
            "created_at_range": None,
        }
        panel._search_facets_sidebar.facets_changed.emit(test_facets)
        assert panel._facet_values == test_facets

    def test_facets_changed_triggers_search(self, panel, monkeypatch):
        """facets_changed シグナルで _on_search_requested が呼ばれる。"""
        called: list[int] = []
        monkeypatch.setattr(panel, "_on_search_requested", lambda: called.append(1))

        test_facets: dict[str, object] = {"error_state_filter": "has_error"}
        panel._search_facets_sidebar.facets_changed.emit(test_facets)
        assert len(called) == 1

    def test_facet_error_filter_stored(self, panel):
        """error_state_filter='has_error' が _facet_values に正しく保存される。"""
        panel._search_facets_sidebar.facets_changed.emit({"error_state_filter": "has_error"})
        assert panel._facet_values.get("error_state_filter") == "has_error"

    def test_facet_model_filter_stored(self, panel):
        """model_filter がリストとして _facet_values に保存される。"""
        model_ids = ["openai/gpt-4o", "anthropic/claude-3-5"]
        panel._search_facets_sidebar.facets_changed.emit({"model_filter": model_ids})
        assert panel._facet_values.get("model_filter") == model_ids


@pytest.mark.unit
@pytest.mark.gui
class TestSetSearchFilterServicePhase4:
    """set_search_filter_service での Phase 4 初期化を検証する。"""

    def test_update_models_called_on_service_set(self, qtbot):
        """set_search_filter_service 後に update_models が呼ばれる。"""
        service = MagicMock()
        service.create_search_conditions = MagicMock(return_value=MagicMock())
        service.parse_search_input = MagicMock(return_value=([], []))
        service.get_current_conditions = MagicMock(return_value=None)
        service.get_recently_used_model_ids = MagicMock(return_value=["model-a", "model-b"])
        service.get_created_at_histogram = MagicMock(return_value=[])
        service.db_manager = MagicMock()
        service.db_manager.repository = MagicMock()
        service.db_manager.repository.merged_reader = None

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_search_filter_service(service)

        # ファセットは背景 worker で取得される (#1438)
        qtbot.waitUntil(lambda: service.get_recently_used_model_ids.call_count == 1, timeout=5000)
        qtbot.waitUntil(lambda: service.get_created_at_histogram.call_count == 1, timeout=5000)
        qtbot.waitUntil(lambda: panel._search_facets_sidebar._model_list.count() == 2, timeout=5000)

    def test_models_populated_in_sidebar(self, panel_with_service):
        """サービス設定後にサイドバーのモデルリストが更新される。"""
        panel, _service = panel_with_service
        # get_recently_used_model_ids で返した 2 件がサイドバーに反映される
        model_list = panel._search_facets_sidebar._model_list
        assert model_list.count() == 2


@pytest.mark.unit
@pytest.mark.gui
class TestFacetsAreAsync:
    """ファセット取得が GUI スレッドをブロックしない (#1438)。"""

    def test_set_search_filter_service_does_not_query_facets_on_gui_thread(self, qtbot):
        import threading

        caller_threads: list[int] = []

        def record_models(*_args, **_kwargs):
            caller_threads.append(threading.get_ident())
            return ["m1"]

        service = MagicMock()
        service.create_search_conditions = MagicMock(return_value=MagicMock())
        service.parse_search_input = MagicMock(return_value=([], []))
        service.get_recently_used_model_ids = MagicMock(side_effect=record_models)
        service.get_created_at_histogram = MagicMock(return_value=[])
        service.db_manager = MagicMock()
        service.db_manager.repository = MagicMock()
        service.db_manager.repository.merged_reader = None

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_search_filter_service(service)

        qtbot.waitUntil(lambda: bool(caller_threads), timeout=5000)
        assert caller_threads[0] != threading.get_ident()
        qtbot.waitUntil(lambda: panel._search_facets_sidebar._model_list.count() == 1, timeout=5000)
        panel.shutdown()

    def test_refresh_tag_suggestion_reader_enables_completion_after_ready(self, qtbot):
        service = MagicMock()
        service.create_search_conditions = MagicMock(return_value=MagicMock())
        service.parse_search_input = MagicMock(return_value=([], []))
        service.get_recently_used_model_ids = MagicMock(return_value=[])
        service.get_created_at_histogram = MagicMock(return_value=[])
        service.db_manager = MagicMock()
        service.db_manager.annotation_repo = MagicMock()
        service.db_manager.annotation_repo.peek_merged_reader.return_value = None
        service.db_manager.repository.merged_reader = None

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_search_filter_service(service)
        assert panel._tag_suggestion.tag_suggestion_service is None

        reader = object()
        service.db_manager.annotation_repo.peek_merged_reader.return_value = reader
        panel.refresh_tag_suggestion_reader()

        assert panel._tag_suggestion.tag_suggestion_service._merged_reader is reader
        panel.shutdown()


class TestFilterSearchPanelWave5_2:
    """Issue #1548 / #1549: FilterSearchPanel 拡張機能テスト。"""

    def test_search_input_placeholder_and_tooltip_mentions_tag_exclusion(self, qtbot) -> None:
        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        assert "-tag で除外" in panel.ui.lineEditSearch.placeholderText()
        assert "-tag で除外" in panel.ui.lineEditSearch.toolTip()
        panel.shutdown()

    def test_set_search_in_progress_toggles_button_text(self, qtbot) -> None:
        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        assert panel.ui.buttonApply.text() == "検索実行"

        panel.set_search_in_progress(True)
        assert panel.ui.buttonApply.text() == "中止"

        panel.set_search_in_progress(False)
        assert panel.ui.buttonApply.text() == "検索実行"
        panel.shutdown()

    def test_apply_clicked_when_in_progress_emits_cancel(self, qtbot) -> None:
        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_search_in_progress(True)

        cancel_emitted = False

        def on_cancel():
            nonlocal cancel_emitted
            cancel_emitted = True

        panel.search_cancel_requested.connect(on_cancel)
        panel.ui.buttonApply.click()
        assert cancel_emitted is True
        panel.shutdown()

    def test_clear_all_filters_triggers_search_refresh(self, qtbot) -> None:
        service = MagicMock()
        service.create_search_conditions.return_value = MagicMock()
        service.parse_search_input.return_value = ([], [])
        service.get_recently_used_model_ids.return_value = []
        service.get_created_at_histogram.return_value = []
        service.db_manager = MagicMock()
        service.db_manager.annotation_repo.peek_merged_reader.return_value = None
        service.db_manager.repository.merged_reader = None

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_search_filter_service(service)

        cleared_emitted = False
        panel.filter_cleared.connect(lambda: nonlocal_set())

        def nonlocal_set():
            nonlocal cleared_emitted
            cleared_emitted = True

        panel.clear_all_filters()
        assert cleared_emitted is True
        assert service.create_search_conditions.called
        panel.shutdown()

    def test_set_error_state_shows_message_in_pipeline(self, qtbot) -> None:
        from lorairo.gui.widgets.pipeline_state import PipelineState

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel.set_error_state("timeout error")
        assert panel.get_current_pipeline_state() == PipelineState.ERROR
        assert "timeout error" in panel._pipeline.current_message
        panel.shutdown()

    def test_hide_progress_resets_search_in_progress_and_transitions_displaying(self, qtbot) -> None:
        from lorairo.gui.widgets.pipeline_state import PipelineState

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel._pipeline.transition_to(PipelineState.LOADING_THUMBNAILS)
        assert panel._search_in_progress is True
        assert panel.ui.buttonApply.text() == "中止"

        panel.hide_progress_after_completion()
        assert panel._search_in_progress is False
        assert panel.ui.buttonApply.text() == "検索実行"
        assert panel.get_current_pipeline_state() == PipelineState.DISPLAYING
        panel.shutdown()

    def test_cancel_during_thumbnail_loading_cancels_all_search_and_thumbnail_workers(self, qtbot) -> None:
        from lorairo.gui.widgets.pipeline_state import PipelineState

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        worker_svc = MagicMock()
        panel.set_worker_service(worker_svc)
        panel._pipeline.transition_to(PipelineState.LOADING_THUMBNAILS)
        panel.ui.buttonApply.click()

        worker_svc.cancel_all_search_and_thumbnail_workers.assert_called_once()
        assert panel._search_in_progress is False
        assert panel.get_current_pipeline_state() == PipelineState.CANCELED
        panel.shutdown()

    def test_stale_thumbnail_completion_does_not_reset_active_search(self, qtbot) -> None:
        from lorairo.gui.widgets.pipeline_state import PipelineState

        panel = FilterSearchPanel()
        qtbot.addWidget(panel)
        panel._pipeline.transition_to(PipelineState.SEARCHING)
        panel._current_search_worker_id = "search_new_123"

        panel.notify_thumbnail_loading_completed(10)
        panel.hide_progress_after_completion()

        assert panel.get_current_pipeline_state() == PipelineState.SEARCHING
        assert panel._search_in_progress is True
        assert panel.ui.buttonApply.text() == "中止"
        panel.shutdown()
