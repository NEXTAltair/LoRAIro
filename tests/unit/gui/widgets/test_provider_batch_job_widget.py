"""ProviderBatchJobWidget tests (ADR 0041 統一フロー).

ModelSelectionWidget は service container を要求するため、本 widget の単体テストでは
軽量 fake クラスに差し替えて単一選択 / batch-capable フィルタ / submit 配線を検証する。
batch-capable 判定ロジック自体は ModelSelectionWidget / provider_batch_capability の
個別テストでカバーされる。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QWidget

import lorairo.gui.widgets.provider_batch_job_widget as widget_module
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


class _FakeModelSelectionWidget(QWidget):
    """ModelSelectionWidget の軽量スタブ (service container 非依存)。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.single_selection_mode: bool | None = None
        self.batch_filter_calls: list[tuple[bool, str, object]] = []
        self._selected_model: str | None = None

    def set_single_selection_mode(self, enabled: bool) -> None:
        self.single_selection_mode = enabled

    def set_batch_capable_filtering(self, enabled: bool, task_type: str, model_source: object) -> None:
        self.batch_filter_calls.append((enabled, task_type, model_source))

    def get_selected_model(self) -> str | None:
        return self._selected_model


@pytest.fixture(autouse=True)
def _stub_model_selection(monkeypatch):
    """ProviderBatchJobWidget が生成する ModelSelectionWidget を fake に差替える。"""
    monkeypatch.setattr(widget_module, "ModelSelectionWidget", _FakeModelSelectionWidget)


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
        "anthropic/claude-3-5-sonnet": _model(
            id=9,
            provider="anthropic",
            litellm_model_id="anthropic/claude-3-5-sonnet",
        ),
        "openai/omni-moderation-latest": _model(
            id=11,
            provider="openai",
            litellm_model_id="openai/omni-moderation-latest",
            model_types=(SimpleNamespace(name="ratings"),),
        ),
    }.get(litellm_id)
    repository.list_provider_batch_jobs.return_value = [_job()]
    repository.get_provider_batch_job.return_value = _job()
    repository.list_provider_batch_items.return_value = [_item()]
    workflow.submit_images.return_value = 42
    workflow.fetch_results.return_value = SimpleNamespace(items=(_item(),))
    workflow.import_results.return_value = SimpleNamespace(imported_count=1, total_count=1)
    return workflow, repository, model_source, model_repository


@pytest.mark.unit
@pytest.mark.gui
def test_initial_ui_created(widget):
    assert widget.tableJobs.columnCount() == 5
    assert widget.tableItems.columnCount() == 5
    assert widget.comboBoxItemStatus.count() == 4
    assert widget.comboBoxTaskType.currentText() == "annotation"
    assert "0 枚" in widget.labelTarget.text()


@pytest.mark.unit
@pytest.mark.gui
def test_model_selection_starts_in_single_mode(widget):
    assert widget._model_selection_widget.single_selection_mode is True


@pytest.mark.unit
@pytest.mark.gui
def test_set_dependencies_enables_batch_filtering_and_lists_jobs(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies

    widget.set_dependencies(workflow, repository, model_source, model_repository)

    assert widget._model_selection_widget.batch_filter_calls == [(True, "annotation", model_source)]
    assert widget.tableJobs.rowCount() == 1


@pytest.mark.unit
@pytest.mark.gui
def test_task_type_change_reevaluates_batch_filter(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)

    widget.comboBoxTaskType.setCurrentText("rating_preflight")

    assert widget._model_selection_widget.batch_filter_calls[-1] == (
        True,
        "rating_preflight",
        model_source,
    )


@pytest.mark.unit
@pytest.mark.gui
def test_target_label_updates_on_staged_images_changed(widget, monkeypatch):
    monkeypatch.setattr(widget._staging_widget, "count", lambda: 3)

    widget._staging_widget.staged_images_changed.emit([1, 2, 3])

    assert "3 枚" in widget.labelTarget.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_resolves_annotation_params(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    widget.lineEditDescription.setText("nightly")

    widget.submit_job()

    workflow.submit_images.assert_called_once_with(
        provider="anthropic",
        endpoint="/v1/messages",
        litellm_model_id="anthropic/claude-3-5-sonnet",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=9,
        description="nightly",
        task_type="annotation",
    )
    assert "Submitted Provider Batch job 42" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_rating_preflight_uses_moderations_endpoint(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.comboBoxTaskType.setCurrentText("rating_preflight")
    widget._model_selection_widget._selected_model = "openai/omni-moderation-latest"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])

    widget.submit_job()

    workflow.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/moderations",
        litellm_model_id="openai/omni-moderation-latest",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=11,
        description=None,
        task_type="rating_preflight",
    )


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_without_model_warns(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = None
    warning = MagicMock()
    monkeypatch.setattr(widget_module.QMessageBox, "warning", warning)

    widget.submit_job()

    warning.assert_called_once()
    workflow.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_without_staged_images_warns(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [])
    warning = MagicMock()
    monkeypatch.setattr(widget_module.QMessageBox, "warning", warning)

    widget.submit_job()

    warning.assert_called_once()
    workflow.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.gui
def test_set_dataset_state_manager_forwards_to_staging(widget, monkeypatch):
    state = DatasetStateManager()
    forwarded = MagicMock()
    monkeypatch.setattr(widget._staging_widget, "set_dataset_state_manager", forwarded)

    widget.set_dataset_state_manager(state)

    forwarded.assert_called_once_with(state)


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
    monkeypatch.setattr(widget_module.QMessageBox, "critical", critical)

    widget.cancel_selected_job()

    critical.assert_called_once()
    assert widget.labelStatus.text() == "Cancel failed"
