from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


class TestFilterSearchPanelAutocomplete:
    def test_extract_last_token(self):
        assert FilterSearchPanel._extract_last_token("cat, dog") == "dog"
        assert FilterSearchPanel._extract_last_token("single") == "single"

    def test_on_tag_completer_activated_replaces_last_token(self, qtbot):
        panel = FilterSearchPanel()
        qtbot.addWidget(panel)

        panel.ui.lineEditSearch.setText("cat, do")
        panel._on_tag_completer_activated("dog")

        assert panel.ui.lineEditSearch.text() == "cat, dog, "
