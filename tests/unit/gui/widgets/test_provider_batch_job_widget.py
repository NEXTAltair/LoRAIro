from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.provider_batch_job_widget import ProviderBatchJobWidget


def _job(job_id: int = 1, status: str = "running") -> SimpleNamespace:
    return SimpleNamespace(
        id=job_id,
        provider="openai",
        model_id=10,
        status=status,
        request_count=2,
        succeeded_count=1,
        failed_count=1,
        canceled_count=0,
        submitted_at=datetime(2026, 5, 26, 1, 2, tzinfo=UTC),
        completed_at=None,
        imported_at=None,
    )


def _item(custom_id: str = "image-1") -> SimpleNamespace:
    return SimpleNamespace(
        custom_id=custom_id,
        image_id=1,
        model_id=10,
        status="failed",
        error_type="rate_limit",
        error_message="try later",
    )


def _container() -> SimpleNamespace:
    repository = Mock()
    repository.list_provider_batch_jobs.return_value = [_job()]
    repository.list_provider_batch_items.return_value = [_item()]
    repository.get_models_by_litellm_ids.return_value = {
        "gpt-4.1-mini": SimpleNamespace(
            id=10,
            name="GPT 4.1 mini",
            provider="openai",
            litellm_model_id="gpt-4.1-mini",
            discontinued_at=None,
        )
    }
    repository.get_model_objects.return_value = [
        SimpleNamespace(id=10, name="GPT 4.1 mini", litellm_model_id="gpt-4.1-mini")
    ]

    workflow_service = Mock()
    workflow_service.submit_images.return_value = 42

    annotator_library = Mock()
    annotator_library.list_batch_capable_models.return_value = [
        {"provider": "openai", "name": "GPT 4.1 mini", "litellm_model_id": "gpt-4.1-mini"},
        {"provider": "google", "name": "Gemini", "litellm_model_id": "gemini-2.0-flash"},
        {"provider": "local", "name": "Local", "litellm_model_id": "local/test"},
    ]

    return SimpleNamespace(
        provider_batch_workflow_service=workflow_service,
        db_manager=SimpleNamespace(repository=repository),
        annotator_library=annotator_library,
    )


def test_populates_job_and_item_tables(qtbot):
    container = _container()
    widget = ProviderBatchJobWidget(container)  # type: ignore[arg-type]
    qtbot.addWidget(widget)

    assert widget.jobTableWidget.rowCount() == 1
    assert widget.jobTableWidget.item(0, 0).text() == "1"
    assert widget.jobTableWidget.item(0, 2).text() == "gpt-4.1-mini"
    assert widget.jobTableWidget.item(0, 4).text() == "2"

    widget.jobTableWidget.selectRow(0)

    assert widget.itemTableWidget.rowCount() == 1
    assert widget.itemTableWidget.item(0, 0).text() == "image-1"
    assert widget.itemTableWidget.item(0, 3).text() == "failed"
    assert widget.itemTableWidget.item(0, 5).text() == "try later"


def test_action_buttons_call_workflow_service(qtbot):
    container = _container()
    widget = ProviderBatchJobWidget(container)  # type: ignore[arg-type]
    qtbot.addWidget(widget)
    widget.jobTableWidget.selectRow(0)

    widget.cancelButton.click()
    container.provider_batch_workflow_service.cancel.assert_called_once_with(1)

    widget.fetchButton.click()
    container.provider_batch_workflow_service.fetch_results.assert_called_once_with(1)

    widget.importButton.click()
    container.provider_batch_workflow_service.import_results.assert_called_once_with(1)


def test_submit_uses_selected_and_manual_image_ids(qtbot):
    container = _container()
    dataset_state = DatasetStateManager()
    dataset_state.set_selected_images([7, 8])
    widget = ProviderBatchJobWidget(container, dataset_state)  # type: ignore[arg-type]
    qtbot.addWidget(widget)
    widget.imageIdsLineEdit.setText("8, 9")
    widget.descriptionLineEdit.setText("nightly batch")

    with qtbot.waitSignal(widget.submit_completed, timeout=1000) as blocker:
        widget.submitButton.click()

    assert blocker.args == [42]
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="responses",
        litellm_model_id="gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[7, 8, 9],
        model_id=10,
        description="nightly batch",
    )


def test_submit_validation_requires_image_ids(qtbot, monkeypatch):
    container = _container()
    widget = ProviderBatchJobWidget(container)  # type: ignore[arg-type]
    qtbot.addWidget(widget)
    widget.useSelectedImagesCheckBox.setChecked(False)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message) or QMessageBox.StandardButton.Ok,
    )

    widget.submitButton.click()

    container.provider_batch_workflow_service.submit_images.assert_not_called()
    assert warnings == ["Provider Batch submit requires at least one image ID."]
