"""ProviderBatchJobWidget tests (ADR 0041 統一フロー).

ModelSelectionWidget は service container を要求するため、本 widget の単体テストでは
軽量 fake クラスに差し替えて単一選択 / batch-capable フィルタ / submit 配線を検証する。
batch-capable 判定ロジック自体は ModelSelectionWidget / provider_batch_capability の
個別テストでカバーされる。
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Event
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
    workflow.refresh.return_value = _job()
    workflow.fetch_results.return_value = SimpleNamespace(items=(_item(),))
    workflow.import_results.return_value = SimpleNamespace(
        imported_count=1,
        skipped_count=0,
        error_count=0,
        total_count=1,
    )
    return workflow, repository, model_source, model_repository


def _submit_and_wait(widget, qtbot) -> None:
    with qtbot.waitSignal(widget.submit_completed, timeout=3000):
        widget.submit_job()


@pytest.mark.unit
@pytest.mark.gui
def test_initial_ui_created(widget):
    assert widget.tableJobs.columnCount() == 5
    assert widget.tableItems.columnCount() == 5
    assert widget.comboBoxItemStatus.count() == 4
    assert widget.comboBoxTaskType.currentText() == "annotation"
    assert widget.buttonRefreshStatus.text() == "状態を確認"
    assert not hasattr(widget, "buttonFetch")
    assert not hasattr(widget, "buttonImport")
    assert "0 枚" in widget.labelTarget.text()


@pytest.mark.unit
@pytest.mark.gui
def test_model_selection_starts_in_single_mode(widget):
    assert widget._model_selection_widget.single_selection_mode is True


@pytest.mark.unit
@pytest.mark.gui
def test_model_selection_placeholder_is_replaced(widget):
    assert widget.get_model_selection_widget().objectName() == "providerBatchModelSelection"
    assert widget.modelSelectionPlaceholder.parent() is None
    assert widget.executionLayout.indexOf(widget.get_model_selection_widget()) != -1


@pytest.mark.unit
@pytest.mark.gui
def test_shared_staging_state_manager_uses_same_staged_items(widget, qtbot):
    """共有 StagingStateManager 注入で Annotate↔Jobs のステージング集合が同一になる (ADR 0074)。"""
    from lorairo.gui.state.staging_state import StagingStateManager

    manager = StagingStateManager()
    widget.set_staging_state_manager(manager)

    inner = widget.get_staging_widget()
    assert inner.get_staging_state_manager() is manager
    # SSoT の OrderedDict 実体を共有する (旧 connect_shared_staging と同等)
    assert inner.get_staged_items() is manager.get_staged_items()


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
def test_submit_job_resolves_annotation_params(widget, dependencies, monkeypatch, qtbot):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    widget.lineEditDescription.setText("nightly")

    _submit_and_wait(widget, qtbot)

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
    assert "バッチAPIジョブ 42 を送信しました" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_button_shows_busy_state_only_while_submitting(widget, dependencies, monkeypatch, qtbot):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    default_style = widget.buttonSubmit.styleSheet()
    entered = Event()
    release = Event()

    def submit_side_effect(**_kwargs):
        entered.set()
        release.wait(timeout=2)
        return 42

    workflow.submit_images.side_effect = submit_side_effect

    widget.submit_job()
    qtbot.waitUntil(entered.is_set, timeout=1000)

    submit_thread = widget._submit_thread
    assert submit_thread is not None
    assert submit_thread.parent() is None
    assert submit_thread in widget_module._ACTIVE_SUBMIT_THREADS
    assert widget._submit_in_progress is True
    assert widget.buttonSubmit.text() == "送信中..."
    assert widget.buttonSubmit.isEnabled() is False
    assert "background-color" in widget.buttonSubmit.styleSheet()
    with qtbot.waitSignal(widget.submit_completed, timeout=3000):
        release.set()
    assert submit_thread not in widget_module._ACTIVE_SUBMIT_THREADS
    assert widget.buttonSubmit.text() == "送信"
    assert widget.buttonSubmit.isEnabled() is True
    assert widget.buttonSubmit.styleSheet() == default_style
    assert "バッチAPIジョブ 42 を送信しました" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_button_recovers_after_provider_error(widget, dependencies, monkeypatch, qtbot):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    warning = MagicMock()
    monkeypatch.setattr(widget_module.QMessageBox, "warning", warning)
    workflow.submit_images.side_effect = widget_module.ProviderBatchError("provider rejected")

    _submit_and_wait(widget, qtbot)

    warning.assert_called_once()
    assert widget.buttonSubmit.text() == "送信"
    assert widget.buttonSubmit.isEnabled() is True
    assert widget.buttonSubmit.styleSheet() == ""
    assert widget.labelStatus.text() == "provider rejected"


@pytest.mark.unit
@pytest.mark.gui
def test_submit_button_recovers_after_unexpected_submit_error(widget, dependencies, monkeypatch, qtbot):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    critical = MagicMock()
    monkeypatch.setattr(widget_module.QMessageBox, "critical", critical)
    workflow.submit_images.side_effect = RuntimeError("adapter exploded")

    _submit_and_wait(widget, qtbot)

    critical.assert_called_once()
    assert widget.buttonSubmit.text() == "送信"
    assert widget.buttonSubmit.isEnabled() is True
    assert widget.buttonSubmit.styleSheet() == ""
    assert widget.labelStatus.text() == "送信に失敗しました"


@pytest.mark.unit
@pytest.mark.gui
def test_submit_success_removes_submitted_images_from_staging(widget, dependencies, monkeypatch, qtbot):
    # Issue #571: 送信成功で送信済み対象のみをステージングから除外し、再送信を構造的に防ぐ。
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    remove = MagicMock()
    monkeypatch.setattr(widget._staging_widget, "remove_image_ids", remove)

    _submit_and_wait(widget, qtbot)

    remove.assert_called_once_with([1, 2])
    assert "バッチAPIジョブ 42 を送信しました" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_success_keeps_status_when_post_refresh_fails(widget, dependencies, monkeypatch, qtbot):
    # Issue #571 review: submit 成功後の一覧更新が失敗しても送信成功を覆さず除外を確定する。
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    remove = MagicMock()
    monkeypatch.setattr(widget._staging_widget, "remove_image_ids", remove)
    monkeypatch.setattr(widget, "select_job", MagicMock(side_effect=RuntimeError("detail boom")))

    _submit_and_wait(widget, qtbot)

    remove.assert_called_once_with([1, 2])
    assert "バッチAPIジョブ 42 を送信しました" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_success_status_survives_refresh_jobs_failure(widget, dependencies, monkeypatch, qtbot):
    # Issue #571 review: refresh_jobs が list 失敗を内部で握って labelStatus を上書きしても
    # 送信成功表示が残ること。
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    monkeypatch.setattr(widget._staging_widget, "remove_image_ids", MagicMock())
    repository.list_provider_batch_jobs.side_effect = RuntimeError("job list boom")

    _submit_and_wait(widget, qtbot)

    assert widget.labelStatus.text() == "バッチAPIジョブ 42 を送信しました"


@pytest.mark.unit
@pytest.mark.gui
def test_submit_error_keeps_staging(widget, dependencies, monkeypatch, qtbot):
    # Issue #571: 失敗時はステージングを残し、ユーザーが再試行できるようにする。
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    monkeypatch.setattr(widget_module.QMessageBox, "warning", MagicMock())
    remove = MagicMock()
    monkeypatch.setattr(widget._staging_widget, "remove_image_ids", remove)
    workflow.submit_images.side_effect = widget_module.ProviderBatchError("provider rejected")

    _submit_and_wait(widget, qtbot)

    remove.assert_not_called()


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_reentrancy_guard_submits_once(widget, dependencies, monkeypatch, qtbot):
    # Issue #571: submit 中の再入で二重送信されないこと。
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget._model_selection_widget._selected_model = "anthropic/claude-3-5-sonnet"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])
    entered = Event()
    release = Event()

    def submit_side_effect(**_kwargs):
        entered.set()
        release.wait(timeout=2)
        return 42

    workflow.submit_images.side_effect = submit_side_effect

    widget.submit_job()
    qtbot.waitUntil(entered.is_set, timeout=1000)
    widget.submit_job()
    with qtbot.waitSignal(widget.submit_completed, timeout=3000):
        release.set()

    assert workflow.submit_images.call_count == 1


@pytest.mark.unit
@pytest.mark.gui
def test_submit_job_rating_preflight_uses_moderations_endpoint(widget, dependencies, monkeypatch, qtbot):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.comboBoxTaskType.setCurrentText("rating_preflight")
    widget._model_selection_widget._selected_model = "openai/omni-moderation-latest"
    monkeypatch.setattr(widget._staging_widget, "get_image_ids", lambda: [1, 2])

    _submit_and_wait(widget, qtbot)

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
def test_check_status_for_incomplete_job_only_refreshes_status(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.refresh.assert_called_once_with(42)
    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert "検証中" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_completed_job_fetches_and_imports(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    workflow.refresh.return_value = _job(status="completed", provider_status="completed")
    fetch_result = SimpleNamespace(items=(_item(),))
    import_result = SimpleNamespace(imported_count=1, skipped_count=0, error_count=0, total_count=1)
    workflow.fetch_results.return_value = fetch_result
    workflow.import_results.return_value = import_result
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.refresh.assert_called_once_with(42)
    workflow.fetch_results.assert_called_once_with(42)
    workflow.import_results.assert_called_once_with(42, fetch_result)
    assert "処理完了" in widget.labelStatus.text()
    assert "DB保存が完了" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_imported_job_does_not_save_again(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    repository.get_provider_batch_job.return_value = _job(
        status="imported", imported_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.refresh.assert_not_called()
    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert "保存済み" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_partial_import_shows_summary(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    workflow.refresh.return_value = _job(status="completed", provider_status="completed")
    workflow.import_results.return_value = SimpleNamespace(
        imported_count=1,
        skipped_count=1,
        error_count=1,
        total_count=3,
    )
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    assert "保存 1/3 件" in widget.labelStatus.text()
    assert "スキップ 1 件" in widget.labelStatus.text()
    assert "エラー 1 件" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("failed", "失敗"),
        ("expired", "期限切れ"),
        ("canceled", "キャンセル済み"),
    ],
)
def test_check_status_for_terminal_non_importable_jobs_shows_distinct_status(
    widget, dependencies, status, expected
):
    workflow, repository, model_source, model_repository = dependencies
    workflow.refresh.return_value = _job(status=status, provider_status=status)
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert expected in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_cancel_fetch_import_recovery_actions_call_workflow(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    widget.cancel_selected_job()
    widget.fetch_selected_job()
    widget.import_selected_job()

    workflow.cancel.assert_called_once_with(42)
    workflow.fetch_results.assert_called_once_with(42)
    workflow.import_results.assert_called_once_with(42)
    assert "バッチAPI結果 1/1 件をDB保存しました" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
@pytest.mark.parametrize(
    ("status", "cancel_enabled"),
    [
        ("submitted", True),
        ("validating", True),
        ("running", True),
        ("canceling", True),
        ("completed", False),
        ("imported", False),
        ("failed", False),
        ("expired", False),
        ("canceled", False),
    ],
)
def test_cancel_button_is_enabled_only_for_cancelable_jobs(widget, dependencies, status, cancel_enabled):
    workflow, repository, model_source, model_repository = dependencies
    repository.get_provider_batch_job.return_value = _job(status=status)
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    assert widget.buttonCancel.isEnabled() is cancel_enabled


@pytest.mark.unit
@pytest.mark.gui
def test_recovery_actions_live_in_job_context_menu(widget, dependencies):
    workflow, repository, model_source, model_repository = dependencies
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    assert widget._action_fetch_results.text() == "結果を取得"
    assert widget._action_import_results.text() == "結果を取り込み"
    assert widget._action_fetch_results.isEnabled()
    assert widget._action_import_results.isEnabled()


@pytest.mark.unit
@pytest.mark.gui
def test_context_menu_selects_row_under_cursor(widget, dependencies, monkeypatch):
    workflow, repository, model_source, model_repository = dependencies
    jobs = [_job(id=42), _job(id=43, provider_job_id="batch_43", status="completed")]
    repository.list_provider_batch_jobs.return_value = jobs
    repository.get_provider_batch_job.side_effect = lambda job_id: next(
        job for job in jobs if job.id == job_id
    )

    class _FakeMenu:
        def __init__(self, parent=None) -> None:
            self.parent = parent
            self.actions = []

        def addAction(self, action) -> None:
            self.actions.append(action)

        def exec(self, _position) -> None:
            return None

    monkeypatch.setattr(widget_module, "QMenu", _FakeMenu)
    widget.set_dependencies(workflow, repository, model_source, model_repository)
    widget.tableJobs.selectRow(0)

    second_row_position = widget.tableJobs.visualItemRect(widget.tableJobs.item(1, 0)).center()
    widget._show_job_context_menu(second_row_position)

    assert widget._current_job_id == 43
    assert widget.tableJobs.currentRow() == 1


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
    assert widget.labelStatus.text() == "cancel に失敗しました"


# === ADR 0066: 統一 Jobs lifecycle ビュー (同期ジョブ台帳セクション) ===


@pytest.mark.unit
@pytest.mark.gui
def test_sync_jobs_section_inserted_at_top_of_right_splitter(widget):
    """同期ジョブ台帳セクションが右ペイン先頭に拡張方式で追加される"""
    sync_widget = widget.get_sync_jobs_widget()
    assert widget.splitterRight.indexOf(sync_widget) == 0
    # 既存の Provider Batch セクションは置換されず残る (拡張方式)
    assert widget.splitterRight.indexOf(widget.groupBoxExecution) == 1
    assert widget.splitterRight.indexOf(widget.groupBoxStatus) == 2


@pytest.mark.unit
@pytest.mark.gui
def test_sync_jobs_empty_state_keeps_table_frame(widget):
    """台帳未注入でも空テーブル枠を表示する (ADR 0066 §1)"""
    table = widget.get_sync_jobs_widget().tableSyncJobs
    assert table.columnCount() == 7
    assert table.rowCount() == 0


@pytest.mark.unit
@pytest.mark.gui
def test_set_job_ledger_renders_entries(widget):
    from lorairo.services.job_ledger_service import JobLedgerService

    ledger = JobLedgerService()
    ledger.register("annotation_1", "annotation", "アノテーション処理")

    widget.set_job_ledger(ledger)

    table = widget.get_sync_jobs_widget().tableSyncJobs
    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "アノテーション処理"


@pytest.mark.unit
@pytest.mark.gui
def test_refresh_sync_jobs_reflects_ledger_changes(widget):
    from lorairo.services.job_ledger_service import JobLedgerService, JobStatus

    ledger = JobLedgerService()
    widget.set_job_ledger(ledger)
    assert widget.get_sync_jobs_widget().tableSyncJobs.rowCount() == 0

    ledger.register("annotation_1", "annotation", "アノテーション処理")
    ledger.finish("annotation_1", JobStatus.FINISHED, "完了")
    widget.refresh_sync_jobs()

    table = widget.get_sync_jobs_widget().tableSyncJobs
    assert table.rowCount() == 1
    # 状態 (col2) は DS chip 文法で cellWidget 化 (Issue #790)
    assert table.cellWidget(0, 2).text() == "完了"


@pytest.mark.unit
@pytest.mark.gui
def test_sync_job_cancel_button_emits_widget_signal(widget, qtbot):
    """行のキャンセルボタンが sync_job_cancel_requested として再発行される"""
    from lorairo.services.job_ledger_service import JobLedgerService

    ledger = JobLedgerService()
    ledger.register("annotation_busy", "annotation", "アノテーション処理")
    widget.set_job_ledger(ledger)

    button = widget.get_sync_jobs_widget().tableSyncJobs.cellWidget(0, 6)
    with qtbot.waitSignal(widget.sync_job_cancel_requested, timeout=1000) as blocker:
        button.click()

    assert blocker.args == ["annotation_busy"]
