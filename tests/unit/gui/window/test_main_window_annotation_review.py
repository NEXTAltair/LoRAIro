"""Cross-tab navigation from persisted Clef warnings to the manual editor."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QTabWidget, QWidget

from lorairo.gui.window.main_window import MainWindow


@pytest.mark.gui
def test_warning_navigation_selects_image_and_reloads_editor(qtbot) -> None:
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    search = QWidget()
    results = QWidget()
    tabs.addTab(search, "検索")
    tabs.addTab(results, "結果")
    tabs.setCurrentWidget(results)
    state = Mock()
    preview_action = QAction("プレビューと詳細", tabs)
    preview_action.setCheckable(True)
    toggle = Mock()
    preview_action.toggled.connect(toggle)
    window = SimpleNamespace(
        dataset_state_manager=state,
        search_tab=Mock(),
        tabWidgetMainMode=tabs,
        tabWorkspace=search,
        actionTogglePreviewPanel=preview_action,
    )

    MainWindow._open_annotation_review_image(window, 42)

    assert tabs.currentWidget() is search
    state.set_selected_images.assert_called_once_with([42])
    state.set_current_image.assert_called_once_with(42)
    state.refresh_images.assert_called_once_with([42])
    window.search_tab.show_preview_panel.assert_called_once()
    assert preview_action.isChecked()
    toggle.assert_not_called()


@pytest.mark.gui
def test_warning_navigation_without_search_leaves_selection_unchanged() -> None:
    state = Mock()
    window = SimpleNamespace(dataset_state_manager=state, search_tab=None)

    MainWindow._open_annotation_review_image(window, 42)

    state.set_current_image.assert_not_called()
    state.set_selected_images.assert_not_called()
