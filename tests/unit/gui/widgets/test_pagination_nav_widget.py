"""PaginationNavWidget 単体テスト"""

import pytest

from lorairo.gui.widgets.pagination_nav_widget import PaginationNavWidget


@pytest.fixture
def widget(qtbot):
    w = PaginationNavWidget()
    qtbot.addWidget(w)
    return w


class TestPaginationNavWidgetInit:
    def test_initialization(self, widget):
        assert widget is not None
        assert widget._current_page == 1
        assert widget._total_pages == 1
        assert widget._is_loading is False

    def test_initial_label_text(self, widget):
        assert widget._label_page.text() == "Page 1 / 1"

    def test_initial_buttons_disabled_on_single_page(self, widget):
        assert not widget._btn_first.isEnabled()
        assert not widget._btn_prev.isEnabled()
        assert not widget._btn_next.isEnabled()
        assert not widget._btn_last.isEnabled()


class TestPaginationNavWidgetUpdateState:
    def test_update_state_first_page(self, widget):
        widget.update_state(current=1, total=5, is_loading=False)
        assert widget._label_page.text() == "Page 1 / 5"
        assert not widget._btn_first.isEnabled()
        assert not widget._btn_prev.isEnabled()
        assert widget._btn_next.isEnabled()
        assert widget._btn_last.isEnabled()

    def test_update_state_middle_page(self, widget):
        widget.update_state(current=3, total=5, is_loading=False)
        assert widget._label_page.text() == "Page 3 / 5"
        assert widget._btn_first.isEnabled()
        assert widget._btn_prev.isEnabled()
        assert widget._btn_next.isEnabled()
        assert widget._btn_last.isEnabled()

    def test_update_state_last_page(self, widget):
        widget.update_state(current=5, total=5, is_loading=False)
        assert widget._label_page.text() == "Page 5 / 5"
        assert widget._btn_first.isEnabled()
        assert widget._btn_prev.isEnabled()
        assert not widget._btn_next.isEnabled()
        assert not widget._btn_last.isEnabled()

    def test_loading_state_disables_all_buttons(self, widget):
        widget.update_state(current=2, total=5, is_loading=True)
        assert not widget._btn_first.isEnabled()
        assert not widget._btn_prev.isEnabled()
        assert not widget._btn_next.isEnabled()
        assert not widget._btn_last.isEnabled()
        assert "Loading..." in widget._label_loading.text()

    def test_total_less_than_current_clamps_to_one(self, widget):
        widget.update_state(current=0, total=0, is_loading=False)
        assert widget._current_page == 1
        assert widget._total_pages == 1


class TestPaginationNavWidgetSignals:
    def test_next_button_emits_correct_page(self, widget, qtbot):
        widget.update_state(current=2, total=5, is_loading=False)
        with qtbot.waitSignal(widget.page_requested, timeout=1000) as blocker:
            widget._btn_next.click()
        assert blocker.args == [3]

    def test_prev_button_emits_correct_page(self, widget, qtbot):
        widget.update_state(current=3, total=5, is_loading=False)
        with qtbot.waitSignal(widget.page_requested, timeout=1000) as blocker:
            widget._btn_prev.click()
        assert blocker.args == [2]

    def test_first_button_emits_page_one(self, widget, qtbot):
        widget.update_state(current=3, total=5, is_loading=False)
        with qtbot.waitSignal(widget.page_requested, timeout=1000) as blocker:
            widget._btn_first.click()
        assert blocker.args == [1]

    def test_last_button_emits_total_pages(self, widget, qtbot):
        widget.update_state(current=2, total=5, is_loading=False)
        with qtbot.waitSignal(widget.page_requested, timeout=1000) as blocker:
            widget._btn_last.click()
        assert blocker.args == [5]
