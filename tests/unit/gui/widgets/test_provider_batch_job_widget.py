"""ProviderBatchJobWidget tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.provider_batch_job_widget import ProviderBatchJobWidget


def _model(**overrides):
    values = {
        "id": 7,
        "provider": "openai",
        "litellm_model_id": "openai/gpt-4.1-mini",
        "model_types": (),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _job(**overrides):
    values = {
        "id": 42,
        "provider": "openai",
        "provider_job_id": "batch_42",
        "status": "submitted",
        "provider_status": "validating",
        "endpoint": "/v1/chat/completions",
        "model_id": 7,
        "request_count": 2,
        "succeeded_count": 0,
        "failed_count": 1,
        "canceled_count": 0,
        "expired_count": 0,
        "submitted_at": datetime(2026, 1, 1, tzinfo=UTC),
        "completed_at": None,
        "canceled_at": None,
        "expires_at": None,
        "imported_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _item(**overrides):
    values = {
        "custom_id": "img-1",
        "image_id": 1,
        "status": "failed",
        "error_type": "provider_error",
        "error_message": "bad request",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def widget(qtbot):
    provider_widget = ProviderBatchJobWidget()
    qtbot.addWidget(provider_widget)
    return provider_widget


@pytest.fixture
def dependencies():
    workflow = MagicMock()
    repository = MagicMock()
    model_repository = MagicMock()
    model_source = MagicMock()

    model_repository.get_model_by_litellm_id.side_effect = lambda litellm_id: {
        "openai/gpt-4.1-mini": _model(),
        "openrouter/openai/gpt-4.1-mini": _model(
            id=8,
            provider="openrouter",
            litellm_model_id="openrouter/openai/gpt-4.1-mini",
        ),
        "anthropic/claude-3-5-sonnet": _model(
            id=9,
            provider="anthropic",
            litellm_model_id="anthropic/claude-3-5-sonnet",
        ),
    }.get(litellm_id)
    repository.list_provider_batch_jobs.return_value = [_job()]
    repository.get_provider_batch_job.return_value = _job()
    repository.list_provider_batch_items.return_value = [_item()]
    model_source.list_batch_capable_models.return_value = (
        "openai/gpt-4.1-mini",
        "openrouter/openai/gpt-4.1-mini",
        "anthropic/claude-3-5-sonnet",
    )
    workflow.submit_images.return_value = 42
    workflow.fetch_results.return_value = SimpleNamespace(items=(_item(),))
    workflow.import_results.return_value = SimpleNamespace(imported_count=1, total_count=1)
    return workflow, repository, model_source, model_repository


@pytest.mark.unit
@pytest.mark.gui
def test_initial_ui_created(widget):
    assert widget.comboBoxModel is not None
    assert widget.lineEditImageIds is not None
    assert widget.tableJobs.columnCount() == 5
    assert widget.comboBoxItemStatus.count() == 4


@pytest.mark.unit
@pytest.mark.gui
def test_set_dependencies_filters_direct_batch_models(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies

    widget.set_dependencies(workflow, repository, model_source, model_repository)

    assert widget.comboBoxModel.count() == 2
    labels = [widget.comboBoxModel.itemText(i) for i in range(widget.comboBoxModel.count())]
    assert "openai: openai/gpt-4.1-mini" in labels
    assert "anthropic: anthropic/claude-3-5-sonnet" in labels
    assert all("openrouter" not in label for label in labels)
    assert widget.tableJobs.rowCount() == 1


@pytest.mark.unit
@pytest.mark.gui
def test_unresolved_batch_capable_models_do_not_fallback_to_all_models(widget):
    workflow = MagicMock()
    repository = MagicMock()
    model_repository = MagicMock()
    model_source = MagicMock()
    model_source.list_batch_capable_models.return_value = ("openai/missing-from-db",)
    model_repository.get_model_by_litellm_id.return_value = None
    model_repository.get_model_objects.return_value = [_model()]
    repository.list_provider_batch_jobs.return_value = []

    widget.set_dependencies(workflow, repository, model_source, model_repository)

    assert widget.comboBoxModel.count() == 0
    model_repository.get_model_objects.assert_not_called()


@pytest.mark.unit
@pytest.mark.gui
def test_use_selected_images_populates_manual_ids(widget):
    state = DatasetStateManager()
    state._selected_image_ids = [3, 5]
    widget.set_dataset_state_manager(state)

    widget.use_selected_images()

    assert widget.lineEditImageIds.text() == "3, 5"
    assert "2 selected" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_calls_workflow(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.lineEditImageIds.setText("1, 2")
    widget.lineEditDescription.setText("nightly")

    widget.submit_job()

    workflow.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/chat/completions",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=7,
        description="nightly",
        task_type="annotation",
    )
    assert "Submitted Provider Batch job 42" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_set_dependencies_filters_for_rating_preflight_task(widget):
    workflow = MagicMock()
    repository = MagicMock()
    model_repository = MagicMock()
    model_source = MagicMock()
    model_source.list_batch_capable_models.return_value = (
        "openai/gpt-4.1-mini",
        "openai/omni-moderation-latest",
        "anthropic/claude-3-5-sonnet",
    )
    model_repository.get_model_by_litellm_id.side_effect = lambda litellm_id: {
        "openai/gpt-4.1-mini": _model(),
        "openai/omni-moderation-latest": _model(
            id=11,
            provider="openai",
            litellm_model_id="openai/omni-moderation-latest",
            model_types=(SimpleNamespace(name="ratings"),),
        ),
        "anthropic/claude-3-5-sonnet": _model(
            id=9,
            provider="anthropic",
            litellm_model_id="anthropic/claude-3-5-sonnet",
        ),
    }.get(litellm_id)
    repository.list_provider_batch_jobs.return_value = []

    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.comboBoxTaskType.setCurrentText("rating_preflight")

    assert widget.comboBoxModel.count() == 1
    assert widget.comboBoxModel.itemText(0) == "openai: openai/omni-moderation-latest"


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_rating_preflight_uses_moderations_endpoint(widget):
    workflow = MagicMock()
    repository = MagicMock()
    model_repository = MagicMock()
    model_source = MagicMock()
    workflow.submit_images.return_value = 42
    model_source.list_batch_capable_models.return_value = ("openai/omni-moderation-latest",)
    model_repository.get_model_by_litellm_id.return_value = _model(
        id=11,
        provider="openai",
        litellm_model_id="openai/omni-moderation-latest",
        model_types=(SimpleNamespace(name="ratings"),),
    )
    repository.list_provider_batch_jobs.return_value = []

    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.comboBoxTaskType.setCurrentText("rating_preflight")
    widget.lineEditImageIds.setText("1, 2")
    widget.lineEditDescription.setText("nightly")

    widget.submit_job()

    workflow.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/moderations",
        litellm_model_id="openai/omni-moderation-latest",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=11,
        description="nightly",
        task_type="rating_preflight",
    )


@pytest.mark.unit
@pytest.mark.gui
def test_job_selection_loads_detail_and_failed_items(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.comboBoxItemStatus.setCurrentText("failed")

    widget.tableJobs.selectRow(0)

    repository.get_provider_batch_job.assert_called_with(42)
    repository.list_provider_batch_items.assert_called_with(42, status="failed")
    assert "provider_status: validating" in widget.textEditJobDetail.toPlainText()
    assert widget.tableItems.rowCount() == 1
    assert widget.tableItems.item(0, 3).text() == "provider_error"


@pytest.mark.unit
@pytest.mark.gui
def test_refresh_cancel_fetch_import_actions_call_workflow(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()
    widget.cancel_selected_job()
    widget.fetch_selected_job()
    widget.import_selected_job()

    workflow.refresh.assert_called_once_with(42)
    workflow.cancel.assert_called_once_with(42)
    workflow.fetch_results.assert_called_once_with(42)
    workflow.import_results.assert_called_once_with(42)
    assert "Imported 1/1" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_clearing_job_selection_resets_current_job(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.tableJobs.clearSelection()

    assert widget._current_job_id is None
    assert widget.textEditJobDetail.toPlainText() == ""
    assert widget.tableItems.rowCount() == 0


@pytest.mark.unit
@pytest.mark.gui
def test_action_handlers_catch_unexpected_errors(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)
    workflow.cancel.side_effect = RuntimeError("adapter exploded")
    critical = MagicMock()
    monkeypatch.setattr("lorairo.gui.widgets.provider_batch_job_widget.QMessageBox.critical", critical)

    widget.cancel_selected_job()

    critical.assert_called_once()
    assert widget.labelStatus.text() == "Cancel failed"
