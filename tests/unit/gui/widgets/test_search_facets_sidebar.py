from __future__ import annotations

import datetime

import pytest

from lorairo.gui.widgets.search_facets_sidebar import SearchFacetsSidebar


@pytest.mark.unit
@pytest.mark.gui
class TestSearchFacetsSidebar:
    def test_initial_facet_values_all_none(self, qtbot: pytest.FixtureRequest) -> None:
        """初期状態で全ファセット値が None であることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        vals = sidebar.get_facet_values()
        assert vals["manual_edit_filter"] is None
        assert vals["reviewed_at_filter"] is None
        assert vals["error_state_filter"] is None
        assert vals["model_filter"] is None
        assert vals["created_at_range"] is None

    def test_facets_changed_signal_emitted_on_radio_change(self, qtbot: pytest.FixtureRequest) -> None:
        """ラジオボタン変更時に facets_changed シグナルが発火することを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        with qtbot.waitSignal(sidebar.facets_changed, timeout=3000):
            sidebar._manual_edit_buttons[1].click()

    def test_get_facet_values_manual_edit_true(self, qtbot: pytest.FixtureRequest) -> None:
        """「あり」選択時に manual_edit_filter が True になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._manual_edit_buttons[1].click()
        vals = sidebar.get_facet_values()
        assert vals["manual_edit_filter"] is True

    def test_get_facet_values_manual_edit_false(self, qtbot: pytest.FixtureRequest) -> None:
        """「なし」選択時に manual_edit_filter が False になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._manual_edit_buttons[2].click()
        vals = sidebar.get_facet_values()
        assert vals["manual_edit_filter"] is False

    def test_get_facet_values_reviewed_unreviewed(self, qtbot: pytest.FixtureRequest) -> None:
        """「未レビュー」選択時に reviewed_at_filter が "unreviewed" になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._reviewed_buttons[1].click()
        vals = sidebar.get_facet_values()
        assert vals["reviewed_at_filter"] == "unreviewed"

    def test_get_facet_values_reviewed_reviewed(self, qtbot: pytest.FixtureRequest) -> None:
        """「済み」選択時に reviewed_at_filter が "reviewed" になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._reviewed_buttons[2].click()
        vals = sidebar.get_facet_values()
        assert vals["reviewed_at_filter"] == "reviewed"

    def test_get_facet_values_error_has_error(self, qtbot: pytest.FixtureRequest) -> None:
        """「あり」選択時に error_state_filter が "has_error" になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._error_buttons[1].click()
        vals = sidebar.get_facet_values()
        assert vals["error_state_filter"] == "has_error"

    def test_get_facet_values_error_no_error(self, qtbot: pytest.FixtureRequest) -> None:
        """「なし」選択時に error_state_filter が "no_error" になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._error_buttons[2].click()
        vals = sidebar.get_facet_values()
        assert vals["error_state_filter"] == "no_error"

    def test_update_models_populates_list(self, qtbot: pytest.FixtureRequest) -> None:
        """update_models がモデルリストに items を設定することを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o", "anthropic/claude-3-5-haiku"])
        assert sidebar._model_list.count() == 2

    def test_model_filter_none_when_no_selection(self, qtbot: pytest.FixtureRequest) -> None:
        """モデル未選択時に model_filter が None になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o", "anthropic/claude-3-5-haiku"])
        vals = sidebar.get_facet_values()
        assert vals["model_filter"] is None

    def test_model_filter_returns_selected_models(self, qtbot: pytest.FixtureRequest) -> None:
        """モデル選択時に model_filter が選択済みモデルのリストを返すことを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o", "anthropic/claude-3-5-haiku"])
        sidebar._model_list.item(0).setSelected(True)
        vals = sidebar.get_facet_values()
        assert vals["model_filter"] == ["openai/gpt-4o"]

    def test_facets_changed_emitted_on_model_selection(self, qtbot: pytest.FixtureRequest) -> None:
        """モデル選択変更時に facets_changed シグナルが発火することを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o"])
        with qtbot.waitSignal(sidebar.facets_changed, timeout=3000):
            sidebar._model_list.item(0).setSelected(True)

    def test_clear_all_resets_to_initial(self, qtbot: pytest.FixtureRequest) -> None:
        """clear_all() が全ファセットを初期値にリセットすることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar._manual_edit_buttons[1].click()
        sidebar._reviewed_buttons[2].click()
        sidebar._error_buttons[1].click()
        sidebar.clear_all()
        vals = sidebar.get_facet_values()
        assert vals["manual_edit_filter"] is None
        assert vals["reviewed_at_filter"] is None
        assert vals["error_state_filter"] is None
        assert vals["created_at_range"] is None

    def test_histogram_range_updates_created_at_range(self, qtbot: pytest.FixtureRequest) -> None:
        """ヒストグラムのクリックで created_at_range が更新されることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        now = datetime.datetime.now(datetime.UTC)
        end = now + datetime.timedelta(days=1)

        with qtbot.waitSignal(sidebar.facets_changed, timeout=3000) as blocker:
            sidebar._histogram.range_selected.emit(now, end)

        vals = blocker.args[0]
        assert vals["created_at_range"] == (now, end)

    def test_update_histogram_delegates_to_histogram_widget(self, qtbot: pytest.FixtureRequest) -> None:
        """update_histogram が内部の DateHistogramWidget に委譲されることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        now = datetime.datetime.now(datetime.UTC)
        bins = [(now, now + datetime.timedelta(days=1), 3)]
        sidebar.update_histogram(bins)
        assert sidebar._histogram._bins == bins

    def test_model_search_filters_visible_items(self, qtbot: pytest.FixtureRequest) -> None:
        """モデル名検索入力で一致しない項目が非表示になることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o", "anthropic/claude-3-5-haiku", "wd-v1-4-tagger"])

        sidebar._model_search.setText("claude")

        visible = [
            sidebar._model_list.item(i).text()
            for i in range(sidebar._model_list.count())
            if not sidebar._model_list.item(i).isHidden()
        ]
        assert visible == ["anthropic/claude-3-5-haiku"]

    def test_model_search_empty_shows_all_items(self, qtbot: pytest.FixtureRequest) -> None:
        """検索語をクリアすると全項目が再表示されることを確認する。"""
        sidebar = SearchFacetsSidebar()
        qtbot.addWidget(sidebar)
        sidebar.update_models(["openai/gpt-4o", "wd-v1-4-tagger"])
        sidebar._model_search.setText("gpt")
        sidebar._model_search.clear()

        hidden = [sidebar._model_list.item(i).isHidden() for i in range(sidebar._model_list.count())]
        assert hidden == [False, False]
