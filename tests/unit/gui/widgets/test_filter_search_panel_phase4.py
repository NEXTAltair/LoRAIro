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
    return widget, service


@pytest.mark.unit
@pytest.mark.gui
class TestSearchFacetsSidebarComposition:
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

        service.get_recently_used_model_ids.assert_called_once()
        service.get_created_at_histogram.assert_called_once()

    def test_models_populated_in_sidebar(self, panel_with_service):
        """サービス設定後にサイドバーのモデルリストが更新される。"""
        panel, _service = panel_with_service
        # get_recently_used_model_ids で返した 2 件がサイドバーに反映される
        model_list = panel._search_facets_sidebar._model_list
        assert model_list.count() == 2
