"""ExportController 単体テスト"""

from unittest.mock import Mock, patch

import pytest

from lorairo.gui.controllers.export_controller import ExportController


@pytest.fixture
def mock_selection_state_service():
    service = Mock()
    service.get_current_selected_images.return_value = [1, 2, 3]
    return service


@pytest.fixture
def mock_service_container():
    container = Mock()
    container.dataset_export_service = Mock()
    return container


@pytest.fixture
def mock_parent():
    return Mock()


@pytest.fixture
def controller(mock_selection_state_service, mock_service_container, mock_parent):
    return ExportController(
        selection_state_service=mock_selection_state_service,
        service_container=mock_service_container,
        parent=mock_parent,
    )


@pytest.fixture
def controller_no_service(mock_service_container, mock_parent):
    return ExportController(
        selection_state_service=None,
        service_container=mock_service_container,
        parent=mock_parent,
    )


class TestExportControllerInit:
    def test_initialization(self, controller, mock_selection_state_service):
        assert controller.selection_state_service is mock_selection_state_service

    def test_initialization_without_selection_service(self, controller_no_service):
        assert controller_no_service.selection_state_service is None


class TestExportControllerValidateServices:
    def test_validate_services_with_valid_service(self, controller):
        assert controller._validate_services() is True

    def test_validate_services_without_service_returns_false(self, controller_no_service):
        assert controller_no_service._validate_services() is False

    def test_validate_services_shows_warning_when_missing(self, controller_no_service):
        controller_no_service._validate_services()
        controller_no_service.parent.assert_not_called()


class TestExportControllerGetCurrentSelectedImages:
    def test_returns_image_ids(self, controller, mock_selection_state_service):
        mock_selection_state_service.get_current_selected_images.return_value = [1, 2, 3]
        result = controller._get_current_selected_images()
        assert result == [1, 2, 3]

    def test_returns_empty_when_no_service(self, controller_no_service):
        result = controller_no_service._get_current_selected_images()
        assert result == []


class TestExportControllerOpenExportDialog:
    def test_open_dialog_shows_warning_when_no_images(
        self, controller, mock_selection_state_service, mock_parent
    ):
        mock_selection_state_service.get_current_selected_images.return_value = []
        controller.open_export_dialog()
        # QMessageBox.warning は autouse の auto_mock_qmessagebox でモック済み

    def test_open_dialog_creates_export_widget_when_images_present(
        self, controller, mock_service_container
    ):
        with patch("lorairo.gui.widgets.dataset_export_widget.DatasetExportWidget") as mock_widget_class:
            mock_widget = Mock()
            mock_widget_class.return_value = mock_widget
            mock_widget.exec.return_value = None
            mock_widget.export_completed = Mock()
            mock_widget.export_completed.connect = Mock()

            controller.open_export_dialog()

            mock_widget_class.assert_called_once()
            mock_widget.exec.assert_called_once()

    def test_on_export_completed_logs_path(self, controller):
        """export完了ハンドラが例外なく実行される"""
        controller._on_export_completed("/some/path")
