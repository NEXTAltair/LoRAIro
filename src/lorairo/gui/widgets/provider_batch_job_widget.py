"""Provider Batch job management widget."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.utils.log import logger

_DIRECT_PROVIDERS = {"openai", "anthropic"}
_DEFAULT_ENDPOINTS = {
    "openai": "/v1/chat/completions",
    "anthropic": "/v1/messages",
}
_ITEM_STATUSES = ("all", "failed", "expired", "canceled")


class ProviderBatchJobWidget(QWidget):
    """Provider Batch job submit/list/detail widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("providerBatchJobWidget")

        self._workflow_service: Any = None
        self._repository: Any = None
        self._model_source: Any = None
        self._dataset_state_manager: Any = None
        self._current_job_id: int | None = None

        self._setup_ui()
        self._connect_signals()

    def set_dependencies(self, workflow_service: Any, repository: Any, model_source: Any = None) -> None:
        """Inject services used by the widget."""
        self._workflow_service = workflow_service
        self._repository = repository
        self._model_source = model_source
        self.refresh_models()
        self.refresh_jobs()

    def set_dataset_state_manager(self, dataset_state_manager: Any) -> None:
        """Set shared dataset state for selected image ID import."""
        self._dataset_state_manager = dataset_state_manager

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 1)
        root.addLayout(right, 2)

        self.groupBoxSubmit = QGroupBox("Submit")
        submit_layout = QFormLayout(self.groupBoxSubmit)

        self.comboBoxModel = QComboBox()
        self.comboBoxModel.setObjectName("comboBoxProviderBatchModel")
        self.comboBoxModel.setMinimumWidth(320)
        submit_layout.addRow("Model", self.comboBoxModel)

        self.lineEditImageIds = QLineEdit()
        self.lineEditImageIds.setObjectName("lineEditProviderBatchImageIds")
        self.lineEditImageIds.setPlaceholderText("1, 2, 3")
        submit_layout.addRow("Image IDs", self.lineEditImageIds)

        self.lineEditPromptProfile = QLineEdit("default")
        self.lineEditPromptProfile.setObjectName("lineEditProviderBatchPromptProfile")
        submit_layout.addRow("Prompt", self.lineEditPromptProfile)

        self.lineEditDescription = QLineEdit()
        self.lineEditDescription.setObjectName("lineEditProviderBatchDescription")
        submit_layout.addRow("Description", self.lineEditDescription)

        submit_buttons = QHBoxLayout()
        self.buttonUseSelected = QPushButton("Use Selected")
        self.buttonUseSelected.setObjectName("buttonProviderBatchUseSelected")
        self.buttonRefreshModels = QPushButton("Refresh Models")
        self.buttonRefreshModels.setObjectName("buttonProviderBatchRefreshModels")
        self.buttonSubmit = QPushButton("Submit")
        self.buttonSubmit.setObjectName("buttonProviderBatchSubmit")
        submit_buttons.addWidget(self.buttonUseSelected)
        submit_buttons.addWidget(self.buttonRefreshModels)
        submit_buttons.addWidget(self.buttonSubmit)
        submit_layout.addRow(submit_buttons)
        left.addWidget(self.groupBoxSubmit)

        self.groupBoxJobs = QGroupBox("Jobs")
        jobs_layout = QVBoxLayout(self.groupBoxJobs)
        job_buttons = QHBoxLayout()
        self.buttonRefreshJobs = QPushButton("Refresh")
        self.buttonRefreshJobs.setObjectName("buttonProviderBatchRefreshJobs")
        self.buttonRefreshStatus = QPushButton("Refresh Status")
        self.buttonRefreshStatus.setObjectName("buttonProviderBatchRefreshStatus")
        self.buttonCancel = QPushButton("Cancel")
        self.buttonCancel.setObjectName("buttonProviderBatchCancel")
        self.buttonFetch = QPushButton("Fetch")
        self.buttonFetch.setObjectName("buttonProviderBatchFetch")
        self.buttonImport = QPushButton("Import")
        self.buttonImport.setObjectName("buttonProviderBatchImport")
        for button in (
            self.buttonRefreshJobs,
            self.buttonRefreshStatus,
            self.buttonCancel,
            self.buttonFetch,
            self.buttonImport,
        ):
            job_buttons.addWidget(button)
        jobs_layout.addLayout(job_buttons)

        self.tableJobs = QTableWidget(0, 5)
        self.tableJobs.setObjectName("tableProviderBatchJobs")
        self.tableJobs.setHorizontalHeaderLabels(
            ["ID", "Provider", "Status", "Provider Status", "Requests"]
        )
        self.tableJobs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tableJobs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        jobs_layout.addWidget(self.tableJobs)
        right.addWidget(self.groupBoxJobs, 1)

        detail_row = QHBoxLayout()
        self.groupBoxDetail = QGroupBox("Detail")
        detail_layout = QVBoxLayout(self.groupBoxDetail)
        self.textEditJobDetail = QTextEdit()
        self.textEditJobDetail.setObjectName("textEditProviderBatchJobDetail")
        self.textEditJobDetail.setReadOnly(True)
        detail_layout.addWidget(self.textEditJobDetail)
        detail_row.addWidget(self.groupBoxDetail, 1)

        self.groupBoxItems = QGroupBox("Items")
        items_layout = QVBoxLayout(self.groupBoxItems)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Status"))
        self.comboBoxItemStatus = QComboBox()
        self.comboBoxItemStatus.setObjectName("comboBoxProviderBatchItemStatus")
        self.comboBoxItemStatus.addItems(_ITEM_STATUSES)
        filter_layout.addWidget(self.comboBoxItemStatus)
        filter_layout.addStretch()
        items_layout.addLayout(filter_layout)
        self.tableItems = QTableWidget(0, 5)
        self.tableItems.setObjectName("tableProviderBatchItems")
        self.tableItems.setHorizontalHeaderLabels(
            ["Custom ID", "Image ID", "Status", "Error Type", "Error Message"]
        )
        self.tableItems.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        items_layout.addWidget(self.tableItems)
        detail_row.addWidget(self.groupBoxItems, 1)
        right.addLayout(detail_row, 1)

        self.labelStatus = QLabel("Ready")
        self.labelStatus.setObjectName("labelProviderBatchStatus")
        left.addWidget(self.labelStatus)
        left.addStretch()

    def _connect_signals(self) -> None:
        self.buttonUseSelected.clicked.connect(self.use_selected_images)
        self.buttonRefreshModels.clicked.connect(self.refresh_models)
        self.buttonSubmit.clicked.connect(self.submit_job)
        self.buttonRefreshJobs.clicked.connect(self.refresh_jobs)
        self.buttonRefreshStatus.clicked.connect(self.refresh_selected_job_status)
        self.buttonCancel.clicked.connect(self.cancel_selected_job)
        self.buttonFetch.clicked.connect(self.fetch_selected_job)
        self.buttonImport.clicked.connect(self.import_selected_job)
        self.tableJobs.itemSelectionChanged.connect(self._on_job_selection_changed)
        self.comboBoxItemStatus.currentTextChanged.connect(self.refresh_items)

    @Slot()
    def refresh_models(self) -> None:
        """Refresh direct provider batch capable models."""
        self.comboBoxModel.clear()
        if self._repository is None:
            return

        try:
            models = self._load_batch_capable_models()
        except Exception as e:
            logger.warning(f"Provider Batch model discovery failed: {e}")
            models = []

        for model in models:
            provider = self._direct_provider_for_model(model)
            if provider is None:
                continue
            label = f"{provider}: {model.litellm_model_id}"
            self.comboBoxModel.addItem(
                label,
                {
                    "model_id": model.id,
                    "provider": provider,
                    "litellm_model_id": model.litellm_model_id,
                    "endpoint": _DEFAULT_ENDPOINTS[provider],
                },
            )
        self.labelStatus.setText(f"{self.comboBoxModel.count()} batch-capable model(s)")

    def _load_batch_capable_models(self) -> list[Any]:
        source = self._model_source
        raw_models: tuple[Any, ...] = ()
        if source is not None and hasattr(source, "list_batch_capable_models"):
            raw_models = tuple(source.list_batch_capable_models())

        resolved: list[Any] = []
        seen: set[str] = set()
        for raw in raw_models:
            litellm_id = self._litellm_id_from_batch_model(raw)
            if not litellm_id:
                continue
            model = self._repository.get_model_by_litellm_id(litellm_id)
            if model is not None and model.litellm_model_id not in seen:
                resolved.append(model)
                seen.add(model.litellm_model_id)

        if resolved:
            return resolved

        get_model_objects = getattr(self._repository, "get_model_objects", None)
        if callable(get_model_objects):
            return list(get_model_objects())
        return []

    @staticmethod
    def _litellm_id_from_batch_model(raw: Any) -> str | None:
        if isinstance(raw, str):
            return raw
        value = (
            getattr(raw, "litellm_model_id", None)
            or getattr(raw, "model_id", None)
            or getattr(raw, "name", None)
        )
        return str(value) if value else None

    @staticmethod
    def _direct_provider_for_model(model: Any) -> str | None:
        provider = str(getattr(model, "provider", "") or "").lower()
        litellm_id = str(getattr(model, "litellm_model_id", "") or "")
        route_prefix = litellm_id.split("/", 1)[0].lower() if "/" in litellm_id else ""
        direct = provider if provider in _DIRECT_PROVIDERS else route_prefix
        if direct in _DIRECT_PROVIDERS:
            return direct
        return None

    @Slot()
    def use_selected_images(self) -> None:
        if self._dataset_state_manager is None:
            self.labelStatus.setText("Dataset state is not available")
            return
        image_ids = self._dataset_state_manager.selected_image_ids
        self.lineEditImageIds.setText(", ".join(str(image_id) for image_id in image_ids))
        self.labelStatus.setText(f"Loaded {len(image_ids)} selected image ID(s)")

    def _parse_image_ids(self) -> list[int]:
        raw = self.lineEditImageIds.text().strip()
        if not raw:
            return []
        image_ids: list[int] = []
        for token in re.split(r"[\s,]+", raw):
            if not token:
                continue
            image_id = int(token)
            if image_id <= 0:
                raise ValueError("image ID must be positive")
            image_ids.append(image_id)
        return image_ids

    @Slot()
    def submit_job(self) -> None:
        if self._workflow_service is None:
            self.labelStatus.setText("Provider Batch service is not available")
            return
        model_data = self.comboBoxModel.currentData()
        if not model_data:
            QMessageBox.warning(self, "Provider Batch", "No batch-capable model is selected.")
            return
        try:
            image_ids = self._parse_image_ids()
            if not image_ids:
                raise ValueError("image IDs are required")
            job_id = self._workflow_service.submit_images(
                provider=model_data["provider"],
                endpoint=model_data["endpoint"],
                litellm_model_id=model_data["litellm_model_id"],
                prompt_profile=self.lineEditPromptProfile.text().strip() or "default",
                image_ids=image_ids,
                model_id=model_data["model_id"],
                description=self.lineEditDescription.text().strip() or None,
            )
            self.refresh_jobs()
            self.select_job(job_id)
            self.labelStatus.setText(f"Submitted Provider Batch job {job_id}")
        except (ProviderBatchError, ValueError) as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            logger.error(f"Provider Batch submit failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Provider Batch", str(e))
            self.labelStatus.setText("Submit failed")

    @Slot()
    def refresh_jobs(self) -> None:
        if self._repository is None:
            return
        try:
            jobs = self._repository.list_provider_batch_jobs(limit=100, offset=0)
        except Exception as e:
            logger.warning(f"Provider Batch job list failed: {e}")
            self.tableJobs.setRowCount(0)
            self.labelStatus.setText("Provider Batch jobs unavailable")
            return
        self.tableJobs.setRowCount(0)
        for job in jobs:
            row = self.tableJobs.rowCount()
            self.tableJobs.insertRow(row)
            job_id = int(job.id)
            values = [
                str(job_id),
                str(getattr(job, "provider", "")),
                str(getattr(job, "status", "")),
                str(getattr(job, "provider_status", "") or ""),
                str(getattr(job, "request_count", 0)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job_id)
                self.tableJobs.setItem(row, column, item)
        self.labelStatus.setText(f"Loaded {len(jobs)} Provider Batch job(s)")

    def select_job(self, job_id: int) -> None:
        for row in range(self.tableJobs.rowCount()):
            item = self.tableJobs.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == job_id:
                self.tableJobs.selectRow(row)
                return

    @Slot()
    def _on_job_selection_changed(self) -> None:
        selected = self.tableJobs.selectedItems()
        if not selected:
            self._current_job_id = None
            self.textEditJobDetail.clear()
            self.tableItems.setRowCount(0)
            return
        job_id = selected[0].data(Qt.ItemDataRole.UserRole)
        self._current_job_id = int(job_id)
        self.refresh_detail()
        self.refresh_items()

    @Slot()
    def refresh_detail(self) -> None:
        if self._repository is None or self._current_job_id is None:
            return
        job = self._repository.get_provider_batch_job(self._current_job_id)
        if job is None:
            self.textEditJobDetail.clear()
            return
        fields = [
            "id",
            "provider",
            "provider_job_id",
            "status",
            "provider_status",
            "endpoint",
            "model_id",
            "request_count",
            "succeeded_count",
            "failed_count",
            "canceled_count",
            "expired_count",
            "submitted_at",
            "completed_at",
            "canceled_at",
            "expires_at",
            "imported_at",
        ]
        self.textEditJobDetail.setPlainText(
            "\n".join(f"{field}: {getattr(job, field, '')}" for field in fields)
        )

    @Slot()
    def refresh_items(self) -> None:
        if self._repository is None or self._current_job_id is None:
            return
        status = self.comboBoxItemStatus.currentText()
        status_filter = None if status == "all" else status
        items = self._repository.list_provider_batch_items(self._current_job_id, status=status_filter)
        self.tableItems.setRowCount(0)
        for item_obj in items:
            row = self.tableItems.rowCount()
            self.tableItems.insertRow(row)
            values = [
                str(getattr(item_obj, "custom_id", "")),
                str(getattr(item_obj, "image_id", "") or ""),
                str(getattr(item_obj, "status", "")),
                str(getattr(item_obj, "error_type", "") or ""),
                str(getattr(item_obj, "error_message", "") or ""),
            ]
            for column, value in enumerate(values):
                self.tableItems.setItem(row, column, QTableWidgetItem(value))

    def _require_current_job_id(self) -> int | None:
        if self._current_job_id is None:
            QMessageBox.information(self, "Provider Batch", "Select a Provider Batch job first.")
            return None
        return self._current_job_id

    def _handle_action_error(self, action: str, error: Exception) -> None:
        logger.error(f"Provider Batch {action} failed: {error}", exc_info=True)
        QMessageBox.critical(self, "Provider Batch", str(error))
        self.labelStatus.setText(f"{action.capitalize()} failed")

    @Slot()
    def refresh_selected_job_status(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            self._workflow_service.refresh(job_id)
            self.labelStatus.setText(f"Refreshed Provider Batch job {job_id}")
            self.refresh_jobs()
            self.select_job(job_id)
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("refresh", e)

    @Slot()
    def cancel_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            self._workflow_service.cancel(job_id)
            self.labelStatus.setText(f"Cancel requested for Provider Batch job {job_id}")
            self.refresh_jobs()
            self.select_job(job_id)
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("cancel", e)

    @Slot()
    def fetch_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            result = self._workflow_service.fetch_results(job_id)
            self.labelStatus.setText(
                f"Fetched Provider Batch job {job_id}: {len(getattr(result, 'items', ()) or ())} item(s)"
            )
            self.refresh_detail()
            self.refresh_items()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("fetch", e)

    @Slot()
    def import_selected_job(self) -> None:
        job_id = self._require_current_job_id()
        if job_id is None or self._workflow_service is None:
            return
        try:
            result = self._workflow_service.import_results(job_id)
            self.labelStatus.setText(
                f"Imported {result.imported_count}/{result.total_count} Provider Batch result(s)"
            )
            self.refresh_detail()
            self.refresh_items()
        except ProviderBatchError as e:
            QMessageBox.warning(self, "Provider Batch", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("import", e)
