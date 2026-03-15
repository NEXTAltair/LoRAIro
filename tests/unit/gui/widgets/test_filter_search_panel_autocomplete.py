from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


def test_extract_current_tag_token():
    assert FilterSearchPanel._extract_current_tag_token("1girl, long") == "long"
    assert FilterSearchPanel._extract_current_tag_token("solo") == "solo"


def test_apply_completion_for_current_token(qtbot):
    panel = FilterSearchPanel()
    qtbot.addWidget(panel)

    panel.ui.lineEditSearch.setText("1girl, lon")
    panel._apply_completion_for_current_token("long_hair")

    assert panel.ui.lineEditSearch.text() == "1girl, long_hair, "
