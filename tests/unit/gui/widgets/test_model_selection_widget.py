"""ModelSelectionWidget 単体テスト

ModelSelectionService をモックして get_service_container() の呼び出しを回避。
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QProgressBar, QPushButton

from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget


@pytest.fixture
def mock_model_service():
    service = Mock()
    service.load_models.return_value = []
    service.get_recommended_models.return_value = []
    service.filter_models.return_value = []
    return service


@pytest.fixture
def widget(qtbot, mock_model_service):
    w = ModelSelectionWidget(model_selection_service=mock_model_service)
    qtbot.addWidget(w)
    return w


class TestModelSelectionWidgetInit:
    def test_initialization(self, widget, mock_model_service):
        assert widget is not None
        mock_model_service.load_models.assert_called_once()

    def test_has_model_selection_changed_signal(self, widget):
        assert hasattr(widget, "model_selection_changed")

    def test_has_selection_count_changed_signal(self, widget):
        assert hasattr(widget, "selection_count_changed")

    def test_initial_selected_models_empty(self, widget):
        assert widget.get_selected_models() == []

    def test_has_refresh_controls(self, widget):
        assert isinstance(widget.btnRefreshModels, QPushButton)
        assert isinstance(widget.refreshProgressBar, QProgressBar)
        assert widget.btnRefreshModels.text() == "更新"
        assert widget.refreshProgressBar.isVisible() is False

    def test_get_selection_info_returns_dict(self, widget):
        info = widget.get_selection_info()
        assert isinstance(info, dict)
        assert "selected_count" in info
        assert "total_available" in info
        assert "filtered_count" in info


class TestModelSelectionWidgetFilters:
    def test_apply_filters_does_not_crash(self, widget):
        widget.apply_filters(provider="openai", capabilities=["caption"])

    def test_select_all_does_not_crash_with_no_models(self, widget):
        widget.select_all_models()

    def test_deselect_all_does_not_crash_with_no_models(self, widget):
        widget.deselect_all_models()

    def test_select_recommended_does_not_crash_with_no_models(self, widget, mock_model_service):
        mock_model_service.get_recommended_models.return_value = []
        widget.select_recommended_models()

    def test_set_selected_models_does_not_crash_with_empty_list(self, widget):
        widget.set_selected_models([])


class TestModelSelectionWidgetRefreshThread:
    def test_stop_refresh_thread_quits_and_waits(self, widget):
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        widget._refresh_thread = thread
        widget._refresh_worker = Mock()

        widget._stop_refresh_thread()

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(30000)
        assert widget._refresh_thread is None
        assert widget._refresh_worker is None

    def test_stop_refresh_thread_ignores_missing_thread(self, widget):
        widget._refresh_thread = None

        widget._stop_refresh_thread()

        assert widget._refresh_thread is None
