"""Tests for DatasetExportWidget GUI component.

Comprehensive test suite for dataset export functionality including:
- Widget initialization and UI state management
- Service integration with DatasetExportService
- Validation workflow and result display
- Async export processing with progress tracking
- Error handling and user interactions
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt

from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget, DatasetExportWorker
from lorairo.services.service_container import ServiceContainer


@pytest.fixture
def mock_service_container():
    """Create mock ServiceContainer with DatasetExportService."""
    container = Mock(spec=ServiceContainer)

    # Mock export service with required methods
    export_service = Mock()
    export_service.validate_export_requirements.return_value = {
        "total_images": 5,
        "valid_images": 5,
        "missing_processed": 0,
        "missing_metadata": 0,
        "issues": [],
    }
    export_service.export_dataset_txt_format.return_value = Path("/tmp/export")
    export_service.export_dataset_json_format.return_value = Path("/tmp/export")

    container.dataset_export_service.return_value = export_service
    return container


@pytest.fixture
def sample_image_ids():
    """Sample image IDs for testing."""
    return [1, 2, 3, 4, 5]


@pytest.fixture
def export_widget(qtbot, mock_service_container, sample_image_ids):
    """Create DatasetExportWidget with mocked dependencies."""
    widget = DatasetExportWidget(
        service_container=mock_service_container, initial_image_ids=sample_image_ids
    )
    qtbot.addWidget(widget)
    return widget


class TestDatasetExportWidgetInitialization:
    """Tests for widget initialization and setup."""

    def test_widget_initialization(self, qtbot, mock_service_container, sample_image_ids):
        """Test widget initializes correctly with proper UI setup."""
        widget = DatasetExportWidget(
            service_container=mock_service_container, initial_image_ids=sample_image_ids
        )
        qtbot.addWidget(widget)

        # Check basic properties
        assert widget.image_ids == sample_image_ids
        assert widget.validation_results is None
        assert widget.export_worker is None
        assert widget.export_thread is None

        # Check UI elements exist
        assert widget.ui.comboBoxResolution is not None
        assert widget.ui.radioTxtSeparate is not None
        assert widget.ui.radioTxtMerged is not None
        assert widget.ui.radioJson is not None
        assert widget.ui.validateButton is not None
        assert widget.ui.exportButton is not None
        assert widget.ui.cancelButton is not None
        assert widget.ui.closeButton is not None

        # Check initial UI state
        assert widget.ui.comboBoxResolution.currentText() == "512px"
        assert widget.ui.radioTxtSeparate.isChecked()
        assert not widget.ui.exportButton.isEnabled()
        assert not widget.ui.cancelButton.isEnabled()
        assert widget.ui.totalImagesLabel.text() == "対象画像数: 5"

    def test_widget_initialization_empty_images(self, qtbot, mock_service_container):
        """Test widget initialization with empty image list."""
        widget = DatasetExportWidget(service_container=mock_service_container, initial_image_ids=[])
        qtbot.addWidget(widget)

        # Check UI state for empty images
        assert widget.ui.totalImagesLabel.text() == "対象画像数: 0"
        assert not widget.ui.validateButton.isEnabled()
        assert widget.ui.statusLabel.text() == "対象画像が選択されていません"

    def test_button_group_setup(self, export_widget):
        """Test radio button group is properly configured."""
        # Check button group exists and has correct buttons
        assert hasattr(export_widget, "format_button_group")

        # Check exclusive selection behavior
        export_widget.ui.radioTxtMerged.setChecked(True)
        assert not export_widget.ui.radioTxtSeparate.isChecked()
        assert not export_widget.ui.radioJson.isChecked()


class TestUIInteractions:
    """Tests for user interface interactions."""

    def test_resolution_selection(self, export_widget):
        """Test resolution combo box selection."""
        # Test initial state
        assert export_widget._get_selected_resolution() == 512

        # Test selection change
        export_widget.ui.comboBoxResolution.setCurrentText("1024px")
        assert export_widget._get_selected_resolution() == 1024

    def test_format_selection(self, export_widget):
        """Test export format selection methods."""
        # Test initial format
        assert export_widget._get_selected_format() == "txt_separate"

        # Test format changes
        export_widget.ui.radioTxtMerged.setChecked(True)
        assert export_widget._get_selected_format() == "txt_merged"

        export_widget.ui.radioJson.setChecked(True)
        assert export_widget._get_selected_format() == "json"

    def test_settings_change_clears_validation(self, export_widget):
        """Test that changing settings clears validation results."""
        # Set initial validation results
        export_widget.validation_results = {"valid_images": 5}
        export_widget.ui.exportButton.setEnabled(True)

        # Change resolution
        export_widget.ui.comboBoxResolution.setCurrentText("1024px")

        # Check validation is cleared
        assert export_widget.validation_results is None
        assert not export_widget.ui.exportButton.isEnabled()
        assert "再検証が必要" in export_widget.ui.statusLabel.text()

    def test_close_button(self, qtbot, export_widget):
        """Test close button functionality."""
        with patch.object(export_widget, "close") as mock_close:
            qtbot.mouseClick(export_widget.ui.closeButton, Qt.MouseButton.LeftButton)
            mock_close.assert_called_once()


class TestValidationWorkflow:
    """Tests for validation functionality."""

    def test_validation_with_valid_images(self, qtbot, export_widget):
        """Test validation workflow with valid images."""
        # Click validate button
        qtbot.mouseClick(export_widget.ui.validateButton, Qt.MouseButton.LeftButton)

        # Check service was called
        export_service = export_widget.export_service
        export_service.validate_export_requirements.assert_called_once_with(
            image_ids=export_widget.image_ids, resolution=512
        )

        # Check UI updates
        assert export_widget.ui.exportButton.isEnabled()
        assert export_widget.ui.totalImagesLabel.text() == "対象画像数: 5"
        assert export_widget.ui.validImagesLabel.text() == "エクスポート可能: 5"
        assert export_widget.ui.errorCountLabel.text() == "エラー: 0"
        assert "エクスポート可能" in export_widget.ui.statusLabel.text()

    def test_validation_with_errors(self, qtbot, export_widget):
        """Test validation workflow with validation errors."""
        # Mock validation with errors
        export_widget.export_service.validate_export_requirements.return_value = {
            "total_images": 5,
            "valid_images": 3,
            "missing_processed": 1,
            "missing_metadata": 1,
            "issues": ["Image 4: Missing processed file", "Image 5: No annotations"],
        }

        qtbot.mouseClick(export_widget.ui.validateButton, Qt.MouseButton.LeftButton)

        # Check UI reflects errors
        assert export_widget.ui.validImagesLabel.text() == "エクスポート可能: 3"
        assert export_widget.ui.errorCountLabel.text() == "エラー: 2"
        assert "問題が見つかりました" in export_widget.ui.validationDetailsText.toPlainText()

    def test_validation_with_no_valid_images(self, qtbot, export_widget):
        """Test validation when no images are exportable."""
        # Mock validation with no valid images
        export_widget.export_service.validate_export_requirements.return_value = {
            "total_images": 5,
            "valid_images": 0,
            "missing_processed": 3,
            "missing_metadata": 2,
            "issues": ["All images have issues"],
        }

        qtbot.mouseClick(export_widget.ui.validateButton, Qt.MouseButton.LeftButton)

        # Check export button remains disabled
        assert not export_widget.ui.exportButton.isEnabled()
        assert "エクスポート不可" in export_widget.ui.statusLabel.text()

    def test_validation_with_empty_images(self, qtbot, mock_service_container):
        """Test validation with empty image list."""
        widget = DatasetExportWidget(service_container=mock_service_container, initial_image_ids=[])
        qtbot.addWidget(widget)

        with patch.object(widget, "_show_warning") as mock_warning:
            # Manually enable button for test
            widget.ui.validateButton.setEnabled(True)
            qtbot.mouseClick(widget.ui.validateButton, Qt.MouseButton.LeftButton)

            mock_warning.assert_called_once_with("エクスポートする画像が選択されていません。")

    def test_validation_service_error(self, qtbot, export_widget):
        """Test validation when service throws error."""
        # Mock service to raise exception
        export_widget.export_service.validate_export_requirements.side_effect = Exception("Service error")

        with patch.object(export_widget, "_handle_error") as mock_handle_error:
            qtbot.mouseClick(export_widget.ui.validateButton, Qt.MouseButton.LeftButton)

            mock_handle_error.assert_called_once()
            error_msg = mock_handle_error.call_args[0][0]
            assert "検証処理でエラーが発生しました" in error_msg


class TestExportWorkflow:
    """Tests for export functionality."""

    def test_export_without_validation(self, qtbot, export_widget):
        """Test export attempt without prior validation."""
        with patch.object(export_widget, "_show_warning") as mock_warning:
            qtbot.mouseClick(export_widget.ui.exportButton, Qt.MouseButton.LeftButton)
            mock_warning.assert_called_once_with("先に検証を実行してください。")

    @patch("lorairo.gui.widgets.dataset_export_widget.QFileDialog.getExistingDirectory")
    def test_export_txt_format(self, mock_file_dialog, qtbot, export_widget):
        """Test TXT format export workflow."""
        # Setup validation results
        export_widget.validation_results = {"valid_images": 5}
        export_widget.ui.exportButton.setEnabled(True)

        # Mock file dialog
        mock_file_dialog.return_value = "/tmp/export"

        # Mock worker creation and threading
        with patch.object(export_widget, "_start_export_worker") as mock_start_worker:
            qtbot.mouseClick(export_widget.ui.exportButton, Qt.MouseButton.LeftButton)

            mock_start_worker.assert_called_once()
            args = mock_start_worker.call_args[1]
            assert args["export_format"] == "txt_separate"
            assert args["resolution"] == 512
            assert not args["merge_caption"]

    @patch("lorairo.gui.widgets.dataset_export_widget.QFileDialog.getExistingDirectory")
    def test_export_json_format(self, mock_file_dialog, qtbot, export_widget):
        """Test JSON format export workflow."""
        # Setup for JSON export
        export_widget.validation_results = {"valid_images": 5}
        export_widget.ui.exportButton.setEnabled(True)
        export_widget.ui.radioJson.setChecked(True)

        mock_file_dialog.return_value = "/tmp/export"

        with patch.object(export_widget, "_start_export_worker") as mock_start_worker:
            qtbot.mouseClick(export_widget.ui.exportButton, Qt.MouseButton.LeftButton)

            args = mock_start_worker.call_args[1]
            assert args["export_format"] == "json"

    def test_export_no_output_directory(self, qtbot, export_widget):
        """Test export when no output directory is selected."""
        export_widget.validation_results = {"valid_images": 5}
        export_widget.ui.exportButton.setEnabled(True)

        with patch.object(export_widget, "_get_output_directory", return_value=None):
            with patch.object(export_widget, "_start_export_worker") as mock_start_worker:
                qtbot.mouseClick(export_widget.ui.exportButton, Qt.MouseButton.LeftButton)
                mock_start_worker.assert_not_called()


class TestAsyncExportProcessing:
    """Tests for async export processing with workers."""

    def test_export_worker_initialization(self):
        """Test DatasetExportWorker initialization."""
        mock_service = Mock()
        image_ids = [1, 2, 3]
        output_path = Path("/tmp/export")

        worker = DatasetExportWorker(
            export_service=mock_service,
            image_ids=image_ids,
            output_path=output_path,
            resolution=512,
            export_format="txt_separate",
            merge_caption=False,
            latest_only=True,
        )

        assert worker.export_service == mock_service
        assert worker.image_ids == image_ids
        assert worker.output_path == output_path
        assert worker.resolution == 512
        assert worker.export_format == "txt_separate"
        assert not worker.merge_caption
        assert worker.latest_only

    def test_worker_txt_export_success(self, qtbot):
        """Test worker TXT export success."""
        mock_service = Mock()
        mock_service.export_dataset_txt_format.return_value = Path("/tmp/export/output")

        worker = DatasetExportWorker(
            export_service=mock_service,
            image_ids=[1, 2, 3],
            output_path=Path("/tmp/export"),
            resolution=512,
            export_format="txt_separate",
        )

        # Connect signals for testing
        progress_signals = []
        finished_signals = []
        error_signals = []

        worker.progress.connect(lambda p, m: progress_signals.append((p, m)))
        worker.finished.connect(lambda p: finished_signals.append(p))
        worker.error.connect(lambda e: error_signals.append(e))

        # Run worker
        worker.run()

        # Check signals
        assert len(progress_signals) >= 2  # Start and completion
        assert len(finished_signals) == 1
        assert len(error_signals) == 0
        assert finished_signals[0] == "/tmp/export/output"

    def test_worker_json_export_success(self, qtbot):
        """Test worker JSON export success."""
        mock_service = Mock()
        mock_service.export_dataset_json_format.return_value = Path("/tmp/export/output")

        worker = DatasetExportWorker(
            export_service=mock_service,
            image_ids=[1, 2, 3],
            output_path=Path("/tmp/export"),
            resolution=1024,
            export_format="json",
        )

        finished_signals = []
        worker.finished.connect(lambda p: finished_signals.append(p))

        worker.run()

        # Check service was called correctly
        mock_service.export_dataset_json_format.assert_called_once_with(
            image_ids=[1, 2, 3],
            output_path=Path("/tmp/export"),
            resolution=1024,
            metadata_filename="metadata.json",
        )
        assert finished_signals[0] == "/tmp/export/output"

    def test_worker_export_error(self, qtbot):
        """Test worker handling of export errors."""
        mock_service = Mock()
        mock_service.export_dataset_txt_format.side_effect = Exception("Export failed")

        worker = DatasetExportWorker(
            export_service=mock_service,
            image_ids=[1, 2, 3],
            output_path=Path("/tmp/export"),
            resolution=512,
            export_format="txt_separate",
        )

        error_signals = []
        finished_signals = []

        worker.error.connect(lambda e: error_signals.append(e))
        worker.finished.connect(lambda p: finished_signals.append(p))

        worker.run()

        assert len(error_signals) == 1
        assert len(finished_signals) == 0
        assert "Export failed" in error_signals[0]


class TestProgressAndCancellation:
    """Tests for progress tracking and cancellation."""

    def test_export_progress_updates(self, qtbot, export_widget):
        """Test export progress signal handling."""
        progress_updates = []
        export_widget.export_progress.connect(lambda p, m: progress_updates.append((p, m)))

        # Simulate progress updates
        export_widget._on_export_progress(25, "処理中...")
        export_widget._on_export_progress(50, "半分完了")
        export_widget._on_export_progress(100, "完了")

        # Check progress updates
        assert len(progress_updates) == 3
        assert progress_updates[0] == (25, "処理中...")
        assert progress_updates[2] == (100, "完了")

        # Check UI updates
        assert export_widget.ui.exportProgressBar.value() == 100
        assert export_widget.ui.statusLabel.text() == "完了"

    def test_export_completion(self, qtbot, export_widget):
        """Test export completion handling."""
        completion_signals = []
        export_widget.export_completed.connect(lambda p: completion_signals.append(p))

        with patch.object(export_widget, "_cleanup_worker"):
            with patch("lorairo.gui.widgets.dataset_export_widget.QMessageBox.information"):
                export_widget._on_export_finished("/tmp/export/result")

        # Check completion handling
        assert len(completion_signals) == 1
        assert completion_signals[0] == "/tmp/export/result"
        assert export_widget.ui.exportButton.isEnabled()
        assert not export_widget.ui.cancelButton.isEnabled()

    def test_export_cancellation(self, qtbot, export_widget):
        """Test export cancellation."""
        # Mock running thread
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        export_widget.export_thread = mock_thread

        qtbot.mouseClick(export_widget.ui.cancelButton, Qt.MouseButton.LeftButton)

        # Check thread termination
        mock_thread.terminate.assert_called_once()
        mock_thread.wait.assert_called_once()
        assert "キャンセル" in export_widget.ui.statusLabel.text()

    def test_export_error_handling(self, qtbot, export_widget):
        """Test export error handling."""
        error_signals = []
        export_widget.export_error.connect(lambda e: error_signals.append(e))

        with patch.object(export_widget, "_cleanup_worker"):
            with patch.object(export_widget, "_handle_error") as mock_handle_error:
                export_widget._on_export_error("Export error occurred")

        # Check error handling
        assert len(error_signals) == 1
        assert error_signals[0] == "Export error occurred"
        mock_handle_error.assert_called_once_with("Export error occurred")


class TestUtilityMethods:
    """Tests for utility and helper methods."""

    def test_set_image_ids(self, export_widget):
        """Test updating image IDs."""
        new_ids = [10, 20, 30]
        export_widget.set_image_ids(new_ids)

        assert export_widget.image_ids == new_ids
        assert export_widget.validation_results is None
        assert not export_widget.ui.exportButton.isEnabled()
        assert export_widget.ui.totalImagesLabel.text() == "対象画像数: 3"

    def test_cleanup_worker(self, export_widget):
        """Test worker cleanup."""
        # Mock thread and worker
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        mock_worker = Mock()

        export_widget.export_thread = mock_thread
        export_widget.export_worker = mock_worker

        export_widget._cleanup_worker()

        # Check cleanup
        assert export_widget.export_thread is None
        assert export_widget.export_worker is None

    def test_close_event_cleanup(self, qtbot, export_widget):
        """Test cleanup on dialog close."""
        # Mock running thread
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        export_widget.export_thread = mock_thread

        with patch.object(export_widget, "_cleanup_worker") as mock_cleanup:
            # Simulate close event
            export_widget.close()

            # Check thread termination and cleanup
            mock_thread.terminate.assert_called_once()
            mock_cleanup.assert_called_once()


class TestErrorHandling:
    """Tests for error handling and user feedback."""

    def test_handle_error_updates_ui(self, export_widget):
        """Test error handling updates UI correctly."""
        with patch("lorairo.gui.widgets.dataset_export_widget.QMessageBox.critical") as mock_msg:
            export_widget._handle_error("Test error message")

            # Check UI state
            assert export_widget.ui.statusLabel.text() == "エラーが発生しました"
            assert not export_widget.ui.cancelButton.isEnabled()
            assert not export_widget.ui.exportProgressBar.isVisible()

            # Check error dialog
            mock_msg.assert_called_once()
            args = mock_msg.call_args[0]
            assert args[1] == "エラー"
            assert args[2] == "Test error message"

    def test_show_warning(self, export_widget):
        """Test warning message display."""
        with patch("lorairo.gui.widgets.dataset_export_widget.QMessageBox.warning") as mock_warn:
            export_widget._show_warning("Test warning")

            mock_warn.assert_called_once()
            args = mock_warn.call_args[0]
            assert args[1] == "警告"
            assert args[2] == "Test warning"


# Integration test markers
@pytest.mark.integration
class TestDatasetExportIntegration:
    """Integration tests requiring real file operations."""

    @pytest.mark.skipif(not Path("/tmp").exists(), reason="Requires /tmp directory")
    def test_full_export_workflow_integration(self, qtbot, mock_service_container, tmp_path):
        """Integration test for complete export workflow."""
        # Setup real export service behavior
        export_service = mock_service_container.dataset_export_service.return_value
        export_service.validate_export_requirements.return_value = {
            "total_images": 2,
            "valid_images": 2,
            "missing_processed": 0,
            "missing_metadata": 0,
            "issues": [],
        }
        export_service.export_dataset_txt_format.return_value = tmp_path / "exported"

        widget = DatasetExportWidget(service_container=mock_service_container, initial_image_ids=[1, 2])
        qtbot.addWidget(widget)

        # Run validation
        qtbot.mouseClick(widget.ui.validateButton, Qt.MouseButton.LeftButton)
        assert widget.ui.exportButton.isEnabled()

        # Mock file dialog for output directory
        with patch.object(widget, "_get_output_directory", return_value=tmp_path):
            with patch.object(widget, "_start_export_worker") as mock_start:
                qtbot.mouseClick(widget.ui.exportButton, Qt.MouseButton.LeftButton)
                mock_start.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
