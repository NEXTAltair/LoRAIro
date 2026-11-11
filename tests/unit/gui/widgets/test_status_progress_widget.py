"""StatusProgressWidget と通知 (showMessage) の分担を実 QStatusBar で検証する (ADR 0108)。"""

import threading
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

from lorairo.gui.services.progress_state_service import ProgressStateService
from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.widgets.status_progress_widget import StatusProgressWidget
from lorairo.gui.workers.base import WorkerProgress


@pytest.fixture
def window(qtbot):
    """タブとステータスバーを持つ実ウィンドウ (MainWindow と同じ構成の最小版)。"""
    win = QMainWindow()
    tabs = QTabWidget(win)
    tabs.addTab(QLabel("search"), "検索")
    tabs.addTab(QLabel("annotate"), "アノテーション")
    win.setCentralWidget(tabs)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


@pytest.fixture
def service(window):
    return ProgressStateService(status_bar=window.statusBar())


def _widget(service: ProgressStateService) -> StatusProgressWidget:
    widget = service.progress_widget
    assert widget is not None
    return widget


@pytest.mark.unit
class TestStatusProgressWidget:
    def test_initially_hidden(self, qtbot):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        assert widget.isHidden()
        assert widget.text() == ""

    def test_determinate_progress(self, qtbot):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        widget.set_progress("登録中", 3, 12)
        assert not widget.isHidden()
        assert widget.text() == "登録中"
        assert widget.label.toolTip() == "登録中"
        assert not widget.is_indeterminate()
        assert widget.progress_bar.maximum() == 12
        assert widget.progress_bar.value() == 3

    @pytest.mark.parametrize("total", [None, 0, -1])
    def test_indeterminate_progress(self, qtbot, total):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        widget.set_progress("準備中", None, total)
        assert widget.is_indeterminate()
        assert widget.progress_bar.minimum() == 0
        assert widget.progress_bar.maximum() == 0

    def test_value_is_clamped(self, qtbot):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        widget.set_progress("x", 50, 10)
        assert widget.progress_bar.value() == 10
        widget.set_progress("x", -5, 10)
        assert widget.progress_bar.value() == 0

    def test_long_text_is_elided_but_full_text_kept(self, qtbot):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        long_text = "バッチ処理中... 1/2 (50%) - " + "very_long_file_name_" * 30 + ".png"
        widget.set_progress(long_text, 1, 2)
        assert widget.text() == long_text
        assert widget.label.toolTip() == long_text
        assert len(widget.label.text()) < len(long_text)

    def test_clear_hides_and_stops_indeterminate(self, qtbot):
        widget = StatusProgressWidget()
        qtbot.addWidget(widget)
        widget.set_progress("準備中")
        widget.clear()
        assert widget.isHidden()
        assert widget.text() == ""
        assert not widget.is_indeterminate()


@pytest.mark.unit
class TestProgressAndNotificationSeparation:
    def test_notification_during_progress_keeps_progress_widget(self, window, service, qtbot):
        """(1) 進捗表示中に通知を出しても進捗部品が残る。"""
        service.on_worker_batch_progress("w1", 2, 10, "a.jpg")
        widget = _widget(service)
        assert widget.isVisible()
        window.statusBar().showMessage("タグを追加しました", 5000)
        assert window.statusBar().currentMessage() == "タグを追加しました"
        assert widget.isVisible()
        assert widget.text() == "バッチ処理中... 2/10 (20%) - a.jpg"
        assert widget.progress_bar.value() == 2

    def test_progress_update_does_not_erase_notification(self, window, service):
        """(2) 通知が先でも、進捗の更新で通知が消えない。"""
        bar = window.statusBar()
        bar.showMessage("設定を保存しました", 5000)
        service.on_batch_registration_started("w1")
        service.on_worker_progress_updated(
            "w1", WorkerProgress(30, "登録中", processed_count=3, total_count=10)
        )
        service.on_worker_batch_progress("w1", 4, 10, "b.jpg")
        assert bar.currentMessage() == "設定を保存しました"
        widget = _widget(service)
        assert widget.isVisible()
        assert widget.progress_bar.value() == 4

    def test_widget_hidden_without_progress(self, window, service):
        """(3) 進捗が無いときは部品が非表示。終端で再び隠れる。"""
        widget = _widget(service)
        assert not widget.isVisible()
        service.on_worker_batch_progress("w1", 1, 2, "a.jpg")
        assert widget.isVisible()
        service.on_worker_terminal("w1")
        assert not widget.isVisible()

    def test_indeterminate_display_in_statusbar(self, window, service):
        """(4) 件数不明の工程は不定進捗で表示する。"""
        service.show_progress("tag_db", "タグDBを準備中です")
        widget = _widget(service)
        assert widget.isVisible()
        assert widget.is_indeterminate()
        assert window.statusBar().currentMessage() == ""

    def test_progress_survives_tab_switch(self, window, service, qtbot):
        """(5) タブを切り替えても進捗表示が続く。"""
        tabs = window.centralWidget()
        assert isinstance(tabs, QTabWidget)
        service.on_worker_batch_progress("w1", 5, 10, "a.jpg")
        widget = _widget(service)
        tabs.setCurrentIndex(1)
        qtbot.waitUntil(lambda: tabs.currentIndex() == 1)
        assert widget.isVisible()
        tabs.setCurrentIndex(0)
        qtbot.waitUntil(lambda: tabs.currentIndex() == 0)
        assert widget.isVisible()
        assert widget.progress_bar.value() == 5


class _ProgressReceiver(QObject):
    """MainWindow と同じく GUI スレッドの QObject で worker signal を受ける受け口。"""

    def __init__(self, service: ProgressStateService) -> None:
        super().__init__()
        self._service = service
        self.threads: list[threading.Thread] = []

    @Slot(str, int, int, str)
    def on_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        self.threads.append(threading.current_thread())
        self._service.on_worker_batch_progress(worker_id, current, total, filename)


@pytest.mark.unit
def test_cross_thread_progress_is_applied_on_gui_thread(window, service, qtbot):
    """worker スレッドから emit した進捗は queued で GUI スレッドの部品へ反映される。"""
    worker_service = WorkerService(Mock(), Mock())
    receiver = _ProgressReceiver(service)
    worker_service.worker_batch_progress.connect(receiver.on_batch_progress)

    class Emitter(QThread):
        def run(self) -> None:
            worker_service.worker_batch_progress.emit("w1", 7, 9, "c.jpg")

    emitter = Emitter()
    emitter.start()
    try:
        qtbot.waitUntil(lambda: _widget(service).isVisible())
    finally:
        assert emitter.wait(5000)
    assert receiver.threads == [threading.main_thread()]
    assert _widget(service).progress_bar.value() == 7
