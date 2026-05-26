"""Provider Batch job management widget."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.provider_batch_service import ProviderBatchError
from ...services.service_container import ServiceContainer
from ...utils.log import logger
from ..state.dataset_state import DatasetStateManager


@dataclass(frozen=True)
class _ModelCandidate:
    provider: str
    litellm_model_id: str
    display_name: str
    model_id: int | None = None


class ProviderBatchJobWidget(QWidget):
    """Minimal Provider Batch queue management UI."""

    job_selected = Signal(int)
    jobs_refreshed = Signal()
    job_action_completed = Signal(str, int)
    submit_completed = Signal(int)

    _JOB_HEADERS: ClassVar[list[str]] = [
        "ID",
        "Provider",
        "Model",
        "Status",
        "Requested",
        "Succeeded",
        "Failed",
        "Canceled",
        "Submitted",
        "Completed",
        "Imported",
    ]
    _ITEM_HEADERS: ClassVar[list[str]] = [
        "Custom ID",
        "Image ID",
        "Model ID",
        "Status",
        "Error Type",
        "Error Message",
    ]
    _DIRECT_BATCH_PROVIDERS: ClassVar[set[str]] = {"openai", "anthropic"}

    def __init__(
        self,
        service_container: ServiceContainer,
        dataset_state_manager: DatasetStateManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_container = service_container
        self._dataset_state_manager = dataset_state_manager
        self._workflow_service = service_container.provider_batch_workflow_service
        self._repository = service_container.db_manager.repository
        self._model_candidates: list[_ModelCandidate] = []
        self._selected_job_id: int | None = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_models()
        self.refresh_jobs()

    def set_dataset_state_manager(self, dataset_state_manager: DatasetStateManager | None) -> None:
        """Set the shared dataset state used by the selected-images submit option."""
        self._dataset_state_manager = dataset_state_manager

    def _setup_ui(self) -> None:
        self.setObjectName("providerBatchJobWidget")
        layout = QVBoxLayout(self)

        submit_group = QGroupBox("Provider Batch Submit")
        submit_layout = QFormLayout(submit_group)

        self.providerComboBox = QComboBox()
        self.providerComboBox.setObjectName("providerBatchProviderComboBox")
        submit_layout.addRow("Provider", self.providerComboBox)

        self.modelComboBox = QComboBox()
        self.modelComboBox.setObjectName("providerBatchModelComboBox")
        submit_layout.addRow("Model", self.modelComboBox)

        self.endpointLineEdit = QLineEdit("responses")
        self.endpointLineEdit.setObjectName("providerBatchEndpointLineEdit")
        submit_layout.addRow("Endpoint", self.endpointLineEdit)

        self.promptProfileLineEdit = QLineEdit("default")
        self.promptProfileLineEdit.setObjectName("providerBatchPromptProfileLineEdit")
        submit_layout.addRow("Prompt profile", self.promptProfileLineEdit)

        self.useSelectedImagesCheckBox = QCheckBox("Use current selection")
        self.useSelectedImagesCheckBox.setObjectName("providerBatchUseSelectedImagesCheckBox")
        self.useSelectedImagesCheckBox.setChecked(True)
        submit_layout.addRow("Images", self.useSelectedImagesCheckBox)

        self.imageIdsLineEdit = QLineEdit()
        self.imageIdsLineEdit.setObjectName("providerBatchImageIdsLineEdit")
        self.imageIdsLineEdit.setPlaceholderText("Manual IDs, e.g. 12, 13, 21")
        submit_layout.addRow("Manual image IDs", self.imageIdsLineEdit)

        self.descriptionLineEdit = QLineEdit()
        self.descriptionLineEdit.setObjectName("providerBatchDescriptionLineEdit")
        submit_layout.addRow("Description", self.descriptionLineEdit)

        submit_buttons = QHBoxLayout()
        self.refreshModelsButton = QPushButton("Refresh models")
        self.refreshModelsButton.setObjectName("providerBatchRefreshModelsButton")
        self.submitButton = QPushButton("Submit")
        self.submitButton.setObjectName("providerBatchSubmitButton")
        submit_buttons.addWidget(self.refreshModelsButton)
        submit_buttons.addStretch(1)
        submit_buttons.addWidget(self.submitButton)
        submit_layout.addRow(submit_buttons)
        layout.addWidget(submit_group)

        toolbar = QHBoxLayout()
        self.refreshButton = QPushButton("Refresh")
        self.refreshButton.setObjectName("providerBatchRefreshButton")
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.setObjectName("providerBatchCancelButton")
        self.fetchButton = QPushButton("Fetch")
        self.fetchButton.setObjectName("providerBatchFetchButton")
        self.importButton = QPushButton("Import")
        self.importButton.setObjectName("providerBatchImportButton")
        toolbar.addWidget(self.refreshButton)
        toolbar.addStretch(1)
        toolbar.addWidget(self.cancelButton)
        toolbar.addWidget(self.fetchButton)
        toolbar.addWidget(self.importButton)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.jobTableWidget = QTableWidget(0, len(self._JOB_HEADERS))
        self.jobTableWidget.setObjectName("providerBatchJobTableWidget")
        self.jobTableWidget.setHorizontalHeaderLabels(self._JOB_HEADERS)
        self.jobTableWidget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobTableWidget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.jobTableWidget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobTableWidget.horizontalHeader().setStretchLastSection(True)

        self.itemTableWidget = QTableWidget(0, len(self._ITEM_HEADERS))
        self.itemTableWidget.setObjectName("providerBatchItemTableWidget")
        self.itemTableWidget.setHorizontalHeaderLabels(self._ITEM_HEADERS)
        self.itemTableWidget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.itemTableWidget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.itemTableWidget.horizontalHeader().setStretchLastSection(True)

        splitter.addWidget(self.jobTableWidget)
        splitter.addWidget(self.itemTableWidget)
        splitter.setSizes([360, 220])
        layout.addWidget(splitter, 1)

        self.statusLabel = QLabel()
        self.statusLabel.setObjectName("providerBatchStatusLabel")
        layout.addWidget(self.statusLabel)
        self._set_action_buttons_enabled(False)

    def _connect_signals(self) -> None:
        self.refreshModelsButton.clicked.connect(self.refresh_models)
        self.providerComboBox.currentTextChanged.connect(self._populate_model_combo)
        self.submitButton.clicked.connect(self._on_submit_clicked)
        self.refreshButton.clicked.connect(self.refresh_jobs)
        self.cancelButton.clicked.connect(self._on_cancel_clicked)
        self.fetchButton.clicked.connect(self._on_fetch_clicked)
        self.importButton.clicked.connect(self._on_import_clicked)
        self.jobTableWidget.itemSelectionChanged.connect(self._on_job_selection_changed)

    @Slot()
    def refresh_models(self) -> None:
        """Refresh batch-capable model choices from image-annotator-lib and local model rows."""
        try:
            raw_models = self._service_container.annotator_library.list_batch_capable_models()
            self._model_candidates = self._build_model_candidates(raw_models)
            providers = sorted({candidate.provider for candidate in self._model_candidates})

            self.providerComboBox.blockSignals(True)
            self.providerComboBox.clear()
            self.providerComboBox.addItems(providers)
            self.providerComboBox.blockSignals(False)
            self._populate_model_combo()
            self.statusLabel.setText(f"Batch-capable models: {len(self._model_candidates)}")
        except Exception as e:
            logger.error(f"Provider Batch model list refresh failed: {e}", exc_info=True)
            self._model_candidates = []
            self.providerComboBox.clear()
            self.modelComboBox.clear()
            self.statusLabel.setText(f"Model refresh failed: {e}")

    def _build_model_candidates(self, raw_models: Any) -> list[_ModelCandidate]:
        library_candidates = [
            candidate
            for raw_model in raw_models or []
            if (candidate := self._candidate_from_raw_model(raw_model)) is not None
        ]
        if not library_candidates:
            return []

        litellm_ids = {candidate.litellm_model_id for candidate in library_candidates}
        local_models: dict[str, Any] = {}
        get_models = getattr(self._repository, "get_models_by_litellm_ids", None)
        if get_models is not None:
            local_models = get_models(litellm_ids) or {}

        if not local_models:
            return library_candidates

        candidates: list[_ModelCandidate] = []
        by_id = {candidate.litellm_model_id: candidate for candidate in library_candidates}
        for litellm_model_id, model in local_models.items():
            provider = str(getattr(model, "provider", "") or "").lower()
            if provider not in self._DIRECT_BATCH_PROVIDERS:
                continue
            if getattr(model, "discontinued_at", None) is not None:
                continue
            library_candidate = by_id.get(str(litellm_model_id))
            if library_candidate is None:
                continue
            candidates.append(
                _ModelCandidate(
                    provider=provider,
                    litellm_model_id=library_candidate.litellm_model_id,
                    display_name=str(getattr(model, "name", "") or library_candidate.display_name),
                    model_id=getattr(model, "id", None),
                )
            )
        return candidates

    def _candidate_from_raw_model(self, raw_model: Any) -> _ModelCandidate | None:
        provider = self._raw_value(raw_model, "provider")
        litellm_model_id = self._raw_value(raw_model, "litellm_model_id") or self._raw_value(
            raw_model, "model_id"
        )
        if provider is None or litellm_model_id is None:
            return None
        name = self._raw_value(raw_model, "name") or litellm_model_id
        provider_key = provider.lower()
        if provider_key not in self._DIRECT_BATCH_PROVIDERS:
            return None
        if self._raw_value(raw_model, "discontinued_at") is not None:
            return None
        return _ModelCandidate(
            provider=provider_key,
            litellm_model_id=litellm_model_id,
            display_name=name,
        )

    @staticmethod
    def _raw_value(raw_model: Any, key: str) -> str | None:
        if isinstance(raw_model, dict):
            value = raw_model.get(key)
        else:
            value = getattr(raw_model, key, None)
        if value is None:
            return None
        return str(value)

    @Slot()
    def _populate_model_combo(self) -> None:
        provider = self.providerComboBox.currentText()
        self.modelComboBox.clear()
        for candidate in self._model_candidates:
            if candidate.provider != provider:
                continue
            self.modelComboBox.addItem(
                f"{candidate.display_name} ({candidate.litellm_model_id})",
                candidate,
            )
        self.submitButton.setEnabled(self.modelComboBox.count() > 0)

    @Slot()
    def refresh_jobs(self) -> None:
        """Reload provider batch jobs from the repository."""
        try:
            jobs = self._repository.list_provider_batch_jobs(limit=100)
            model_labels = self._model_labels_by_id()
            self.jobTableWidget.setRowCount(0)
            for row, job in enumerate(jobs):
                self.jobTableWidget.insertRow(row)
                values = [
                    getattr(job, "id", ""),
                    getattr(job, "provider", ""),
                    self._format_model_label(job, model_labels),
                    getattr(job, "status", ""),
                    getattr(job, "request_count", 0),
                    getattr(job, "succeeded_count", 0),
                    getattr(job, "failed_count", 0),
                    getattr(job, "canceled_count", 0),
                    self._format_datetime(getattr(job, "submitted_at", None)),
                    self._format_datetime(getattr(job, "completed_at", None)),
                    self._format_datetime(getattr(job, "imported_at", None)),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, getattr(job, "id", None))
                    self.jobTableWidget.setItem(row, column, item)
            self._selected_job_id = None
            self.itemTableWidget.setRowCount(0)
            self._set_action_buttons_enabled(False)
            self.statusLabel.setText(f"Provider Batch jobs: {len(jobs)}")
            self.jobs_refreshed.emit()
        except Exception as e:
            logger.error(f"Provider Batch job refresh failed: {e}", exc_info=True)
            self.statusLabel.setText(f"Job refresh failed: {e}")

    def _model_labels_by_id(self) -> dict[int, str]:
        get_model_objects = getattr(self._repository, "get_model_objects", None)
        if get_model_objects is None:
            return {}
        try:
            return {
                int(model.id): str(getattr(model, "litellm_model_id", None) or model.name)
                for model in get_model_objects()
                if getattr(model, "id", None) is not None
            }
        except Exception as e:
            logger.debug(f"Provider Batch model label lookup skipped: {e}")
            return {}

    def _format_model_label(self, job: Any, model_labels: dict[int, str]) -> str:
        model_id = getattr(job, "model_id", None)
        if isinstance(model_id, int):
            return model_labels.get(model_id, self._format_model_id(job))
        return self._format_model_id(job)

    @staticmethod
    def _format_model_id(job: Any) -> str:
        model_id = getattr(job, "model_id", None)
        return "" if model_id is None else f"model:{model_id}"

    @staticmethod
    def _format_datetime(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        return str(value)

    @Slot()
    def _on_job_selection_changed(self) -> None:
        selected_items = self.jobTableWidget.selectedItems()
        if not selected_items:
            self._selected_job_id = None
            self.itemTableWidget.setRowCount(0)
            self._set_action_buttons_enabled(False)
            return
        row = selected_items[0].row()
        id_item = self.jobTableWidget.item(row, 0)
        job_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item is not None else None
        self._selected_job_id = int(job_id) if job_id is not None else None
        self._set_action_buttons_enabled(self._selected_job_id is not None)
        if self._selected_job_id is not None:
            self.job_selected.emit(self._selected_job_id)
            self._refresh_items(self._selected_job_id)

    def _refresh_items(self, job_id: int) -> None:
        try:
            items = self._repository.list_provider_batch_items(job_id, limit=1000)
            self.itemTableWidget.setRowCount(0)
            for row, item_row in enumerate(items):
                self.itemTableWidget.insertRow(row)
                values = [
                    getattr(item_row, "custom_id", ""),
                    getattr(item_row, "image_id", ""),
                    getattr(item_row, "model_id", ""),
                    getattr(item_row, "status", ""),
                    getattr(item_row, "error_type", ""),
                    getattr(item_row, "error_message", ""),
                ]
                for column, value in enumerate(values):
                    self.itemTableWidget.setItem(
                        row,
                        column,
                        QTableWidgetItem(str(value) if value is not None else ""),
                    )
        except Exception as e:
            logger.error(f"Provider Batch item refresh failed: job_id={job_id}: {e}", exc_info=True)
            self.statusLabel.setText(f"Item refresh failed: {e}")

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        self.cancelButton.setEnabled(enabled)
        self.fetchButton.setEnabled(enabled)
        self.importButton.setEnabled(enabled)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        self._run_job_action("cancel", self._workflow_service.cancel)

    @Slot()
    def _on_fetch_clicked(self) -> None:
        self._run_job_action("fetch", self._workflow_service.fetch_results)

    @Slot()
    def _on_import_clicked(self) -> None:
        self._run_job_action("import", self._workflow_service.import_results)

    def _run_job_action(self, action_name: str, action: Any) -> None:
        if self._selected_job_id is None:
            QMessageBox.information(self, "Provider Batch", "Select a job first.")
            return
        job_id = self._selected_job_id
        try:
            action(job_id)
            self.statusLabel.setText(f"{action_name} completed: job {job_id}")
            self.refresh_jobs()
            self._select_job(job_id)
            self.job_action_completed.emit(action_name, job_id)
        except Exception as e:
            logger.error(f"Provider Batch {action_name} failed: job_id={job_id}: {e}", exc_info=True)
            QMessageBox.warning(self, "Provider Batch", f"{action_name} failed:\n{e}")
            self.statusLabel.setText(f"{action_name} failed: {e}")

    def _select_job(self, job_id: int) -> None:
        for row in range(self.jobTableWidget.rowCount()):
            item = self.jobTableWidget.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == job_id:
                self.jobTableWidget.selectRow(row)
                return

    @Slot()
    def _on_submit_clicked(self) -> None:
        try:
            image_ids = self._collect_submit_image_ids()
            candidate = self.modelComboBox.currentData()
            if not isinstance(candidate, _ModelCandidate):
                raise ValueError("Provider Batch model is not selected.")
            endpoint = self.endpointLineEdit.text().strip() or "responses"
            prompt_profile = self.promptProfileLineEdit.text().strip() or "default"
            description = self.descriptionLineEdit.text().strip() or None
            job_id = self._workflow_service.submit_images(
                provider=candidate.provider,
                endpoint=endpoint,
                litellm_model_id=candidate.litellm_model_id,
                prompt_profile=prompt_profile,
                image_ids=image_ids,
                model_id=candidate.model_id,
                description=description,
            )
            self.statusLabel.setText(f"Submitted Provider Batch job: {job_id}")
            self.refresh_jobs()
            self._select_job(job_id)
            self.submit_completed.emit(job_id)
        except (ProviderBatchError, ValueError) as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.statusLabel.setText(str(e))
        except Exception as e:
            logger.error(f"Provider Batch submit failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Provider Batch", f"Submit failed:\n{e}")
            self.statusLabel.setText(f"Submit failed: {e}")

    def _collect_submit_image_ids(self) -> list[int]:
        image_ids: list[int] = []
        if self.useSelectedImagesCheckBox.isChecked() and self._dataset_state_manager is not None:
            image_ids.extend(self._dataset_state_manager.selected_image_ids)
        manual_ids = self._parse_manual_image_ids(self.imageIdsLineEdit.text())
        image_ids.extend(manual_ids)
        deduped = list(dict.fromkeys(image_ids))
        if not deduped:
            raise ValueError("Provider Batch submit requires at least one image ID.")
        return deduped

    @staticmethod
    def _parse_manual_image_ids(raw_ids: str) -> list[int]:
        if not raw_ids.strip():
            return []
        tokens = raw_ids.replace("\n", ",").replace(" ", ",").split(",")
        image_ids: list[int] = []
        invalid_tokens: list[str] = []
        for token in tokens:
            stripped = token.strip()
            if not stripped:
                continue
            try:
                image_id = int(stripped)
            except ValueError:
                invalid_tokens.append(stripped)
                continue
            if image_id <= 0:
                invalid_tokens.append(stripped)
                continue
            image_ids.append(image_id)
        if invalid_tokens:
            raise ValueError(f"Invalid image IDs: {', '.join(invalid_tokens)}")
        return image_ids
