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
        assert not widget._spin_page.isEnabled()
        assert widget._spin_page.objectName() == "paginationPageSpinBox"
        assert widget._spin_page.keyboardTracking() is False

    def test_tooltips_set(self, widget):
        assert widget._btn_first.toolTip() == "最初のページへ"
        assert widget._btn_prev.toolTip() == "前のページへ"
        assert widget._btn_next.toolTip() == "次のページへ"
        assert widget._btn_last.toolTip() == "最後のページへ"
        assert widget._spin_page.toolTip() == "移動先ページ番号（Enterで移動）"


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


class TestPaginationNavWidgetRange:
    """件数・範囲表示 (ADR 0006 / DS Pagination)。"""

    def test_range_hidden_without_total_items(self, widget):
        """total_items 未指定なら件数・範囲は空文字。"""
        widget.update_state(current=1, total=5, is_loading=False)
        assert widget._label_range.text() == ""

    def test_range_first_page(self, widget):
        """先頭ページの範囲は 1-pagesize / 総件数。"""
        widget.update_state(current=1, total=5, is_loading=False, total_items=247, page_size=50)
        assert widget._label_range.text() == "1-50 / 247 件"

    def test_range_last_page_clamps_to_total(self, widget):
        """末尾ページの終端は総件数で頭打ちになる。"""
        widget.update_state(current=5, total=5, is_loading=False, total_items=247, page_size=50)
        assert widget._label_range.text() == "201-247 / 247 件"

    def test_range_zero_items(self, widget):
        """総件数 0 のときは 0 件。"""
        widget.update_state(current=1, total=1, is_loading=False, total_items=0, page_size=50)
        assert widget._label_range.text() == "0 件"


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

    def test_spin_page_emits_page_requested(self, widget, qtbot):
        widget.update_state(current=1, total=5, is_loading=False)
        assert widget._spin_page.isEnabled()
        assert widget._spin_page.minimum() == 1
        assert widget._spin_page.maximum() == 5
        with qtbot.waitSignal(widget.page_requested, timeout=1000) as blocker:
            widget._spin_page.setValue(4)
        assert blocker.args == [4]

    def test_spin_page_same_page_or_loading_does_not_emit(self, widget):
        emitted = []
        widget.page_requested.connect(emitted.append)
        widget.update_state(current=2, total=5, is_loading=False)
        widget._on_spin_page_changed(2)
        assert emitted == []

        widget.update_state(current=2, total=5, is_loading=True)
        assert not widget._spin_page.isEnabled()
        widget._on_spin_page_changed(3)
        assert emitted == []
