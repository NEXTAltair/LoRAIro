"""MainWindow のタグ DB 背景準備 (#1438) のユニットテスト。"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QStatusBar

from lorairo.gui.services.progress_state_service import ProgressStateService
from lorairo.gui.window import main_window as main_window_module
from lorairo.gui.window.main_window import MainWindow
from lorairo.gui.workers.tag_db_warmup_worker import TagDbWarmupResult


def _fake_window() -> MagicMock:
    window = MagicMock()
    window._closing = False
    return window


@pytest.mark.unit
def test_warmup_done_notifies_all_tabs():
    window = _fake_window()

    MainWindow._on_tag_db_warmup_done(
        window, TagDbWarmupResult(reader_ready=True, tag_management_ready=True)
    )

    for tab in (window.search_tab, window.annotate_tab, window.results_tab, window.export_tab):
        tab.on_tag_db_ready.assert_called_once_with()


@pytest.mark.unit
def test_warmup_failure_still_refreshes_tabs_without_raising():
    window = _fake_window()

    MainWindow._on_tag_db_warmup_done(window, "boom")

    window.search_tab.on_tag_db_ready.assert_called_once_with()


@pytest.mark.unit
def test_warmup_done_skips_missing_tabs_and_closing_window():
    window = _fake_window()
    window.results_tab = None
    window.export_tab = None

    MainWindow._on_tag_db_warmup_done(window, TagDbWarmupResult(True, True))
    window.search_tab.on_tag_db_ready.assert_called_once_with()

    closing = _fake_window()
    closing._closing = True
    MainWindow._on_tag_db_warmup_done(closing, TagDbWarmupResult(True, True))
    closing.search_tab.on_tag_db_ready.assert_not_called()


@pytest.mark.unit
def test_start_warmup_is_skipped_when_initialization_failed():
    window = _fake_window()
    window._initialization_failed = True
    window._tag_db_manager = None

    MainWindow.start_tag_db_warmup(window)

    assert window._tag_db_manager is None


@pytest.mark.unit
def test_warmup_progress_uses_permanent_widget_not_message(qtbot, monkeypatch):
    """準備中は常設の進捗部品に不定進捗で出し、完了通知だけを showMessage に出す (ADR 0108)。"""
    bar = QStatusBar()
    qtbot.addWidget(bar)
    window = _fake_window()
    window._initialization_failed = False
    window._tag_db_manager = None
    window.progress_state_service = ProgressStateService(status_bar=bar)
    window.statusBar.return_value = bar
    window._finish_tag_db_warmup_progress = lambda: MainWindow._finish_tag_db_warmup_progress(window)
    monkeypatch.setattr(main_window_module, "WorkerManager", MagicMock())
    monkeypatch.setattr(main_window_module, "TagDbWarmupWorker", MagicMock())

    MainWindow.start_tag_db_warmup(window)

    widget = window.progress_state_service.progress_widget
    assert widget is not None
    assert not widget.isHidden()
    assert widget.is_indeterminate()
    assert "タグDBを準備中" in widget.text()
    assert bar.currentMessage() == ""

    MainWindow._on_tag_db_warmup_done(
        window, TagDbWarmupResult(reader_ready=True, tag_management_ready=True)
    )

    assert widget.isHidden()
    assert bar.currentMessage() == "タグDBの準備が完了しました"
