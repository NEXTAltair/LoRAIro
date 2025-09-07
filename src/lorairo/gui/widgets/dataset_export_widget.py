"""Dataset Export Widget for LoRA training compatible dataset export.

Provides GUI interface for exporting filtered datasets using DatasetExportService
with validation, progress tracking, and async processing capabilities.
"""

from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QButtonGroup, QDialog, QFileDialog, QMessageBox, QWidget

from ...services.service_container import ServiceContainer
from ..designer.DatasetExportWidget_ui import Ui_DatasetExportWidget


class DatasetExportWorker(QObject):
    """Worker for async dataset export processing."""

    # Signals
    progress = Signal(int, str)  # (progress_percent, message)
    finished = Signal(str)  # export_path
    error = Signal(str)  # error_message

    def __init__(
        self,
        export_service,
        image_ids: list[int],
        output_path: Path,
        resolution: int,
        export_format: str,
        merge_caption: bool = False,
        latest_only: bool = False,
    ) -> None:
        """Initialize export worker.

        Args:
            export_service: DatasetExportService instance
            image_ids: List of image IDs to export
            output_path: Output directory path
            resolution: Image resolution (512, 768, 1024, 1536)
            export_format: Export format ("txt_separate", "txt_merged", "json")
            merge_caption: Whether to merge captions with tags
            latest_only: Whether to use only latest annotations
        """
        super().__init__()
        self.export_service = export_service
        self.image_ids = image_ids
        self.output_path = output_path
        self.resolution = resolution
        self.export_format = export_format
        self.merge_caption = merge_caption
        self.latest_only = latest_only

    def run(self) -> None:
        """Execute export processing with progress reporting."""
        try:
            logger.info(
                f"Starting dataset export: {len(self.image_ids)} images, "
                f"{self.resolution}px, format={self.export_format}"
            )

            self.progress.emit(10, "エクスポート処理を開始しています...")

            # Execute export based on format
            if self.export_format == "json":
                result_path = self.export_service.export_dataset_json_format(
                    image_ids=self.image_ids,
                    output_path=self.output_path,
                    resolution=self.resolution,
                    metadata_filename="metadata.json",
                )
                self.progress.emit(90, "JSON形式でエクスポート中...")
            else:
                # TXT formats (separate or merged)
                merge_option = self.export_format == "txt_merged" or self.merge_caption
                result_path = self.export_service.export_dataset_txt_format(
                    image_ids=self.image_ids,
                    output_path=self.output_path,
                    resolution=self.resolution,
                    merge_caption=merge_option,
                )
                self.progress.emit(90, "TXT形式でエクスポート中...")

            self.progress.emit(100, "エクスポート完了")
            self.finished.emit(str(result_path))
            logger.info(f"Dataset export completed: {result_path}")

        except Exception as e:
            error_msg = f"エクスポート処理でエラーが発生しました: {e!s}"
            logger.error(error_msg)
            self.error.emit(error_msg)


class DatasetExportWidget(QDialog):
    """Widget for dataset export functionality.

    Provides UI for selecting export options, validating requirements,
    and executing dataset export operations with progress tracking.
    """

    # Signals
    export_started = Signal()
    export_progress = Signal(int, str)  # (progress, message)
    export_completed = Signal(str)  # export_path
    export_error = Signal(str)  # error_message

    def __init__(
        self,
        service_container: ServiceContainer,
        initial_image_ids: list[int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize DatasetExportWidget.

        Args:
            service_container: Service container for dependency injection
            initial_image_ids: Initial list of image IDs to export
            parent: Parent widget
        """
        super().__init__(parent)
        self.ui = Ui_DatasetExportWidget()
        self.ui.setupUi(self)

        # Services
        self.service_container = service_container
        self.export_service = service_container.dataset_export_service()

        # Data
        self.image_ids = initial_image_ids or []
        self.validation_results: dict[str, Any] | None = None
        self.export_worker: DatasetExportWorker | None = None
        self.export_thread: QThread | None = None

        # UI setup
        self._setup_ui()
        self._connect_signals()
        self._update_initial_state()

        logger.debug(f"DatasetExportWidget initialized with {len(self.image_ids)} images")

    def _setup_ui(self) -> None:
        """Set up UI components and initial state."""
        # Set up button group for radio buttons (exclusive selection)
        self.format_button_group = QButtonGroup(self)
        self.format_button_group.addButton(self.ui.radioTxtSeparate, 0)
        self.format_button_group.addButton(self.ui.radioTxtMerged, 1)
        self.format_button_group.addButton(self.ui.radioJson, 2)

        # Set default resolution
        self.ui.comboBoxResolution.setCurrentText("512px")

        # Configure dialog properties
        self.setModal(True)
        self.setWindowTitle("データセットエクスポート")
        self.resize(1200, 800)

    def _connect_signals(self) -> None:
        """Connect UI signals to appropriate slots."""
        # Button connections
        self.ui.validateButton.clicked.connect(self._on_validate_clicked)
        self.ui.exportButton.clicked.connect(self._on_export_clicked)
        self.ui.cancelButton.clicked.connect(self._on_cancel_clicked)
        self.ui.closeButton.clicked.connect(self.close)

        # UI state change connections
        self.ui.comboBoxResolution.currentTextChanged.connect(self._on_settings_changed)
        self.format_button_group.idChanged.connect(self._on_settings_changed)
        self.ui.latestOnlyCheckBox.toggled.connect(self._on_settings_changed)

    def _update_initial_state(self) -> None:
        """Update UI to reflect initial state."""
        # Update image count
        image_count = len(self.image_ids)
        self.ui.totalImagesLabel.setText(f"対象画像数: {image_count}")

        if image_count == 0:
            self.ui.validateButton.setEnabled(False)
            self.ui.statusLabel.setText("対象画像が選択されていません")
            self.ui.validationDetailsText.setPlainText(
                "エクスポートする画像が選択されていません。\n"
                "フィルタリング条件を設定して画像を表示してください。"
            )
        else:
            self.ui.statusLabel.setText("検証実行の準備完了")

    def _on_validate_clicked(self) -> None:
        """Handle validation button click."""
        if not self.image_ids:
            self._show_warning("エクスポートする画像が選択されていません。")
            return

        try:
            self.ui.validateButton.setEnabled(False)
            self.ui.statusLabel.setText("検証実行中...")

            # Get current settings
            resolution = self._get_selected_resolution()

            # Perform validation
            self.validation_results = self.export_service.validate_export_requirements(
                image_ids=self.image_ids, resolution=resolution
            )

            # Update validation display
            self._display_validation_results(self.validation_results)

            # Enable export if validation passed
            valid_count = self.validation_results.get("valid_images", 0)
            if valid_count > 0:
                self.ui.exportButton.setEnabled(True)
                self.ui.statusLabel.setText("検証完了 - エクスポート可能")
            else:
                self.ui.exportButton.setEnabled(False)
                self.ui.statusLabel.setText("検証完了 - エクスポート不可")

        except Exception as e:
            self._handle_error(f"検証処理でエラーが発生しました: {e!s}")
        finally:
            self.ui.validateButton.setEnabled(True)

    def _display_validation_results(self, results: dict[str, Any]) -> None:
        """Display validation results in UI."""
        # Update summary labels
        total = results.get("total_images", 0)
        valid = results.get("valid_images", 0)
        errors = results.get("missing_processed", 0) + results.get("missing_metadata", 0)

        self.ui.totalImagesLabel.setText(f"対象画像数: {total}")
        self.ui.validImagesLabel.setText(f"エクスポート可能: {valid}")
        self.ui.errorCountLabel.setText(f"エラー: {errors}")

        # Update detailed results
        details = []
        if valid > 0:
            details.append(f"✅ {valid}件の画像がエクスポート可能です。")

        issues = results.get("issues", [])
        if issues:
            details.append("\n⚠️ 問題が見つかりました:")
            for issue in issues[:10]:  # Limit to first 10 issues
                details.append(f"  • {issue}")
            if len(issues) > 10:
                details.append(f"  • ... 他{len(issues) - 10}件")

        self.ui.validationDetailsText.setPlainText("\n".join(details))

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        if not self.validation_results or self.validation_results.get("valid_images", 0) == 0:
            self._show_warning("先に検証を実行してください。")
            return

        # Get output directory
        output_path = self._get_output_directory()
        if not output_path:
            return

        try:
            # Prepare export settings
            resolution = self._get_selected_resolution()
            export_format = self._get_selected_format()
            merge_caption = export_format == "txt_merged"
            latest_only = self.ui.latestOnlyCheckBox.isChecked()

            # Start async export
            self._start_export_worker(
                output_path=output_path,
                resolution=resolution,
                export_format=export_format,
                merge_caption=merge_caption,
                latest_only=latest_only,
            )

        except Exception as e:
            self._handle_error(f"エクスポート開始でエラーが発生しました: {e!s}")

    def _start_export_worker(
        self,
        output_path: Path,
        resolution: int,
        export_format: str,
        merge_caption: bool,
        latest_only: bool,
    ) -> None:
        """Start async export worker."""
        # Update UI state
        self.ui.exportButton.setEnabled(False)
        self.ui.cancelButton.setEnabled(True)
        self.ui.exportProgressBar.setVisible(True)
        self.ui.exportProgressBar.setValue(0)
        self.ui.statusLabel.setText("エクスポート処理中...")

        # Create worker and thread
        self.export_worker = DatasetExportWorker(
            export_service=self.export_service,
            image_ids=self.image_ids,
            output_path=output_path,
            resolution=resolution,
            export_format=export_format,
            merge_caption=merge_caption,
            latest_only=latest_only,
        )

        self.export_thread = QThread()
        self.export_worker.moveToThread(self.export_thread)

        # Connect worker signals
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.error.connect(self._on_export_error)
        self.export_thread.started.connect(self.export_worker.run)

        # Start processing
        self.export_thread.start()
        self.export_started.emit()

    def _on_export_progress(self, progress: int, message: str) -> None:
        """Handle export progress updates."""
        self.ui.exportProgressBar.setValue(progress)
        self.ui.statusLabel.setText(message)
        self.export_progress.emit(progress, message)

    def _on_export_finished(self, export_path: str) -> None:
        """Handle export completion."""
        self._cleanup_worker()

        # Update UI
        self.ui.exportProgressBar.setValue(100)
        self.ui.statusLabel.setText("エクスポート完了")
        self.ui.exportButton.setEnabled(True)
        self.ui.cancelButton.setEnabled(False)

        # Notify completion
        self.export_completed.emit(export_path)

        # Show completion message
        QMessageBox.information(
            self,
            "エクスポート完了",
            f"データセットのエクスポートが完了しました。\n\n出力先: {export_path}",
        )

    def _on_export_error(self, error_message: str) -> None:
        """Handle export error."""
        self._cleanup_worker()
        self._handle_error(error_message)
        self.export_error.emit(error_message)

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        if self.export_thread and self.export_thread.isRunning():
            self.export_thread.terminate()
            self.export_thread.wait()
            self._cleanup_worker()

        self.ui.statusLabel.setText("エクスポートがキャンセルされました")
        self.ui.exportProgressBar.setVisible(False)
        self.ui.exportButton.setEnabled(True)
        self.ui.cancelButton.setEnabled(False)

    def _on_settings_changed(self) -> None:
        """Handle settings change - clear validation results."""
        if self.validation_results:
            self.validation_results = None
            self.ui.exportButton.setEnabled(False)
            self.ui.validImagesLabel.setText("エクスポート可能: --")
            self.ui.errorCountLabel.setText("エラー: --")
            self.ui.validationDetailsText.clear()
            self.ui.statusLabel.setText("設定が変更されました - 再検証が必要")

    def _get_selected_resolution(self) -> int:
        """Get selected resolution value."""
        resolution_text = self.ui.comboBoxResolution.currentText()
        return int(resolution_text.replace("px", ""))

    def _get_selected_format(self) -> str:
        """Get selected export format."""
        if self.ui.radioTxtSeparate.isChecked():
            return "txt_separate"
        elif self.ui.radioTxtMerged.isChecked():
            return "txt_merged"
        else:  # radioJson
            return "json"

    def _get_output_directory(self) -> Path | None:
        """Get output directory from user selection."""
        # Check if DirectoryPickerWidget has a path set
        if hasattr(self.ui.exportDirectoryPicker, "get_directory"):
            directory = self.ui.exportDirectoryPicker.get_directory()
            if directory:
                return Path(directory)

        # Fallback to file dialog
        directory = QFileDialog.getExistingDirectory(
            self, "エクスポート先ディレクトリを選択", str(Path.home())
        )

        return Path(directory) if directory else None

    def _cleanup_worker(self) -> None:
        """Clean up worker thread and objects."""
        if self.export_thread:
            if self.export_thread.isRunning():
                self.export_thread.quit()
                self.export_thread.wait()
            self.export_thread = None

        self.export_worker = None

    def _handle_error(self, message: str) -> None:
        """Handle error with user notification."""
        logger.error(message)
        self.ui.statusLabel.setText("エラーが発生しました")
        self.ui.exportButton.setEnabled(bool(self.validation_results))
        self.ui.cancelButton.setEnabled(False)
        self.ui.exportProgressBar.setVisible(False)

        QMessageBox.critical(self, "エラー", message)

    def _show_warning(self, message: str) -> None:
        """Show warning message to user."""
        QMessageBox.warning(self, "警告", message)

    def closeEvent(self, event) -> None:
        """Handle dialog close event."""
        # Clean up any running workers
        if self.export_thread and self.export_thread.isRunning():
            self.export_thread.terminate()
            self.export_thread.wait()

        self._cleanup_worker()
        super().closeEvent(event)

    def set_image_ids(self, image_ids: list[int]) -> None:
        """Update image IDs and refresh UI state."""
        self.image_ids = image_ids
        self.validation_results = None
        self._update_initial_state()
        self.ui.exportButton.setEnabled(False)
        self.ui.validImagesLabel.setText("エクスポート可能: --")
        self.ui.errorCountLabel.setText("エラー: --")
        self.ui.validationDetailsText.clear()
