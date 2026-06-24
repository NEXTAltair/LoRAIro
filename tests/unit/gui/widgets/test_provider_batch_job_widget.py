"""ProviderBatchJobWidget tests (ADR 0076 §3 — 監視専用台帳).

作成入口 (ステージング + モデルピッカー + Submit) は Annotate の dispatch 射影へ移したため
(ADR 0076)、本 widget は Provider Batch ジョブの監視・lifecycle / 復旧操作のみを持つ。
本テストは監視台帳としての振る舞い (一覧 / 詳細 / 項目 / 状態確認 / キャンセル / fetch / import /
同期ジョブ台帳) と、作成入口が存在しないことを検証する。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import lorairo.gui.widgets.provider_batch_job_widget as widget_module
from lorairo.gui.widgets.provider_batch_job_widget import ProviderBatchJobWidget


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
    """監視台帳が使う workflow_service / repository の最小モック。"""
    workflow = MagicMock()
    repository = MagicMock()

    repository.list_provider_batch_jobs.return_value = [_job()]
    repository.get_provider_batch_job.return_value = _job()
    repository.list_provider_batch_items.return_value = [_item()]
    workflow.refresh.return_value = _job()
    workflow.fetch_results.return_value = SimpleNamespace(items=(_item(),))
    workflow.import_results.return_value = SimpleNamespace(
        imported_count=1,
        skipped_count=0,
        error_count=0,
        total_count=1,
    )
    return workflow, repository


# === 監視台帳の基本 UI ===


@pytest.mark.unit
@pytest.mark.gui
def test_initial_ui_created(widget):
    assert widget.tableJobs.columnCount() == 5
    assert widget.tableItems.columnCount() == 5
    assert widget.comboBoxItemStatus.count() == 4
    assert widget.buttonRefreshStatus.text() == "状態を確認"
    assert not hasattr(widget, "buttonFetch")
    assert not hasattr(widget, "buttonImport")


# === ADR 0076 §3: 作成入口 (ステージング / モデルピッカー / Submit) が無いこと ===


@pytest.mark.unit
@pytest.mark.gui
def test_submit_authoring_controls_removed(widget):
    """作成入口の UI コントロールが撤去されていること (ADR 0076 §3)。"""
    assert not hasattr(widget, "buttonSubmit")
    assert not hasattr(widget, "stagingWidget")
    assert not hasattr(widget, "buttonAddSelected")
    assert not hasattr(widget, "comboBoxTaskType")
    assert not hasattr(widget, "labelTarget")
    assert not hasattr(widget, "lineEditPromptProfile")
    assert not hasattr(widget, "lineEditDescription")
    assert not hasattr(widget, "modelSelectionPlaceholder")


@pytest.mark.unit
@pytest.mark.gui
def test_submit_authoring_methods_removed(widget):
    """作成入口のメソッド / 状態管理ハンドラが撤去されていること (ADR 0076 §3)。"""
    assert not hasattr(widget, "submit_job")
    assert not hasattr(widget, "get_staging_widget")
    assert not hasattr(widget, "get_model_selection_widget")
    assert not hasattr(widget, "set_staging_state_manager")
    assert not hasattr(widget, "set_dataset_state_manager")


@pytest.mark.unit
@pytest.mark.gui
def test_set_dependencies_lists_jobs(widget, dependencies):
    """set_dependencies は workflow_service / repository のみで一覧を表示する。"""
    workflow, repository = dependencies

    widget.set_dependencies(workflow, repository)

    assert widget.tableJobs.rowCount() == 1


# === ジョブ詳細 / 項目 ===


@pytest.mark.unit
@pytest.mark.gui
def test_job_selection_loads_detail_and_failed_items(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    widget.comboBoxItemStatus.setCurrentText("failed")

    widget.tableJobs.selectRow(0)

    repository.get_provider_batch_job.assert_called_with(42)
    repository.list_provider_batch_items.assert_called_with(42, status="failed")
    assert "provider_status: validating" in widget.textEditJobDetail.toPlainText()
    assert widget.tableItems.rowCount() == 1
    assert widget.tableItems.item(0, 3).text() == "provider_error"


# === 状態確認 (refresh → fetch → import) ===


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_incomplete_job_only_refreshes_status(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.refresh.assert_called_once_with(42)
    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert "検証中" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_completed_job_fetches_and_imports(widget, dependencies):
    workflow, repository = dependencies
    workflow.refresh.return_value = _job(status="completed", provider_status="completed")
    fetch_result = SimpleNamespace(items=(_item(),))
    import_result = SimpleNamespace(imported_count=1, skipped_count=0, error_count=0, total_count=1)
    workflow.fetch_results.return_value = fetch_result
    workflow.import_results.return_value = import_result
    widget.set_dependencies(workflow, repository)
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
    workflow, repository = dependencies
    repository.get_provider_batch_job.return_value = _job(
        status="imported", imported_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.refresh.assert_not_called()
    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert "保存済み" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_partial_import_shows_summary(widget, dependencies):
    workflow, repository = dependencies
    workflow.refresh.return_value = _job(status="completed", provider_status="completed")
    workflow.import_results.return_value = SimpleNamespace(
        imported_count=1,
        skipped_count=1,
        error_count=1,
        total_count=3,
    )
    widget.set_dependencies(workflow, repository)
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
    workflow, repository = dependencies
    workflow.refresh.return_value = _job(status=status, provider_status=status)
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    widget.refresh_selected_job_status()

    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert expected in widget.labelStatus.text()


# === lifecycle / 復旧操作 ===


@pytest.mark.unit
@pytest.mark.gui
def test_cancel_fetch_import_recovery_actions_call_workflow(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
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
    workflow, repository = dependencies
    repository.get_provider_batch_job.return_value = _job(status=status)
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    assert widget.buttonCancel.isEnabled() is cancel_enabled


@pytest.mark.unit
@pytest.mark.gui
def test_recovery_actions_live_in_job_context_menu(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    assert widget._action_fetch_results.text() == "結果を取得"
    assert widget._action_import_results.text() == "結果を取り込み"
    assert widget._action_fetch_results.isEnabled()
    assert widget._action_import_results.isEnabled()


@pytest.mark.unit
@pytest.mark.gui
def test_context_menu_selects_row_under_cursor(widget, dependencies, monkeypatch):
    workflow, repository = dependencies
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
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    second_row_position = widget.tableJobs.visualItemRect(widget.tableJobs.item(1, 0)).center()
    widget._show_job_context_menu(second_row_position)

    assert widget._current_job_id == 43
    assert widget.tableJobs.currentRow() == 1


@pytest.mark.unit
@pytest.mark.gui
def test_clearing_job_selection_resets_current_job(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    widget.tableJobs.selectRow(0)

    widget.tableJobs.clearSelection()

    assert widget._current_job_id is None
    assert widget.textEditJobDetail.toPlainText() == ""
    assert widget.tableItems.rowCount() == 0


@pytest.mark.unit
@pytest.mark.gui
def test_action_handlers_catch_unexpected_errors(widget, dependencies, monkeypatch):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
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
    # 作成入口 (groupBoxExecution) 撤去後、監視セクションは sync 台帳の直後 (ADR 0076 §3)
    assert widget.splitterRight.indexOf(widget.groupBoxStatus) == 1


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
