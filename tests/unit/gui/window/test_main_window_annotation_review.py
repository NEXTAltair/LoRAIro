"""Cross-tab navigation from persisted Clef warnings to the manual editor."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QStatusBar, QTabWidget, QVBoxLayout, QWidget

from lorairo.gui.state.staging_state import StagingStateManager
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


@pytest.mark.gui
def test_review_target_controls_open_search_and_staging_without_starting(qtbot) -> None:
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    search, annotation, results = QWidget(), QWidget(), QWidget()
    QVBoxLayout(results)
    tabs.addTab(search, "検索")
    tabs.addTab(annotation, "アノテーション")
    tabs.addTab(results, "結果")
    tabs.setCurrentWidget(results)
    status_bar = QStatusBar(tabs)
    window = SimpleNamespace(
        tabResults=results,
        tabWorkspace=search,
        tabBatchTag=annotation,
        tabWidgetMainMode=tabs,
        db_manager=Mock(),
        staging_state_manager=StagingStateManager(),
        _open_annotation_review_image=Mock(),
        _reload_results_annotation_review_service=Mock(),
        _refresh_search_annotation_review=Mock(),
        statusBar=lambda: status_bar,
    )
    MainWindow._setup_results_tab(window)
    review = window.results_tab.annotation_review_widget

    review.select_targets_button.click()
    assert tabs.currentWidget() is search
    state = Mock()
    state.get_image_by_id.return_value = {"stored_image_path": "/images/portrait.jpg"}
    window.staging_state_manager.set_dataset_state_manager(state)
    window.staging_state_manager.add_image_ids([42])
    tabs.setCurrentWidget(results)
    review.target_list_button.click()
    assert tabs.currentWidget() is annotation
    assert review._inflight_id is None
    assert window.staging_state_manager.get_image_ids() == [42]
    review.running_status_changed.emit("チェック中 1 / 2 枚")
    assert window._batch_review_status.text() == "チェック中 1 / 2 枚"
    assert not window._batch_review_status.isHidden()
    review.review_result_saved.emit(42)
    window._refresh_search_annotation_review.assert_called_once_with(42)
    review.running_status_changed.emit("")
    assert window._batch_review_status.isHidden()
