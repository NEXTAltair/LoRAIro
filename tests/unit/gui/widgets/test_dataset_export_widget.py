"""DatasetExportWidget 単体テスト

ServiceContainer をモックして依存を分離。
QFileDialog は conftest.py の auto_mock_qfiledialog で自動モック済み。
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget


@pytest.fixture
def mock_service_container():
    container = Mock()
    container.dataset_export_service = Mock()
    container.dataset_export_service.validate_export_requirements.return_value = {
        "total_images": 0,
        "valid_images": 0,
        "missing_processed": 0,
        "missing_metadata": 0,
        "issues": [],
    }
    return container


@pytest.fixture
def widget_no_images(qtbot, mock_service_container):
    w = DatasetExportWidget(
        service_container=mock_service_container,
        initial_image_ids=[],
    )
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_with_images(qtbot, mock_service_container):
    w = DatasetExportWidget(
        service_container=mock_service_container,
        initial_image_ids=[1, 2, 3],
    )
    qtbot.addWidget(w)
    return w


class TestDatasetExportWidgetInit:
    def test_initialization_no_images(self, widget_no_images):
        assert widget_no_images is not None
        assert widget_no_images.image_ids == []

    def test_initialization_with_images(self, widget_with_images):
        assert widget_with_images.image_ids == [1, 2, 3]

    def test_is_modal_dialog(self, widget_with_images):
        assert widget_with_images.isModal()

    def test_window_title(self, widget_with_images):
        assert widget_with_images.windowTitle() == "データセットエクスポート"

    def test_has_export_signals(self, widget_with_images):
        assert hasattr(widget_with_images, "export_started")
        assert hasattr(widget_with_images, "export_completed")
        assert hasattr(widget_with_images, "export_error")


class TestDatasetExportWidgetNoImages:
    def test_validate_button_disabled_when_no_images(self, widget_no_images):
        assert not widget_no_images.ui.validateButton.isEnabled()

    def test_export_button_disabled_initially(self, widget_no_images):
        assert not widget_no_images.ui.exportButton.isEnabled()


class TestDatasetExportWidgetWithImages:
    def test_validate_button_enabled_with_images(self, widget_with_images):
        assert widget_with_images.ui.validateButton.isEnabled()

    def test_set_image_ids_updates_state(self, widget_no_images):
        widget_no_images.set_image_ids([10, 20])
        assert widget_no_images.image_ids == [10, 20]

    def test_validate_clears_previous_results_on_settings_change(self, widget_with_images):
        widget_with_images.validation_results = {"valid_images": 5}
        widget_with_images._on_settings_changed()
        assert widget_with_images.validation_results is None

    def test_get_selected_resolution_returns_int(self, widget_with_images):
        resolution = widget_with_images._get_selected_resolution()
        assert isinstance(resolution, int)
        assert resolution in (512, 768, 1024, 1536)

    def test_get_selected_format_returns_string(self, widget_with_images):
        fmt = widget_with_images._get_selected_format()
        assert fmt in ("txt_separate", "txt_merged", "json")


class TestDatasetExportWidgetValidation:
    def test_validate_shows_results(self, widget_with_images, mock_service_container):
        mock_service_container.dataset_export_service.validate_export_requirements.return_value = {
            "total_images": 3,
            "valid_images": 3,
            "missing_processed": 0,
            "missing_metadata": 0,
            "issues": [],
        }
        widget_with_images._on_validate_clicked()
        mock_service_container.dataset_export_service.validate_export_requirements.assert_called_once()
        assert widget_with_images.ui.exportButton.isEnabled()
