"""ProviderBatchJobWidget tests (ADR 0076 §3 — 監視専用台帳 / Issue #1103 — 追跡カード).

作成入口 (ステージング + モデルピッカー + Submit) は Annotate の dispatch 射影へ移したため
(ADR 0076)、本 widget は Provider Batch ジョブの監視・lifecycle / 復旧操作のみを持つ。
Issue #1103 でフラットテーブルを追跡カード (ProviderBatchJobCard) に置き換えた。
本テストは監視台帳としての振る舞い (カード台帳 / 状態確認 / キャンセル / fetch+import 連鎖 /
展開詳細 / empty state / 同期ジョブ台帳) と、作成入口が存在しないことを検証する。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel

import lorairo.gui.widgets.provider_batch_job_widget as widget_module
from lorairo.gui.widgets.provider_batch_job_card import (
    ProviderBatchJobCard,
    derive_view_state,
)
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


def _card(widget, job_id: int = 42) -> ProviderBatchJobCard:
    card = widget.cards().get(job_id)
    assert card is not None, f"card for job {job_id} not found"
    return card


# === 監視台帳の基本 UI (Issue #1103 — カード台帳) ===


@pytest.mark.unit
@pytest.mark.gui
def test_initial_ui_is_card_ledger_without_flat_table(widget):
    """フラットテーブル UI が撤去され、カード台帳 + empty state で初期化される。"""
    assert not hasattr(widget, "tableJobs")
    assert not hasattr(widget, "tableItems")
    assert not hasattr(widget, "textEditJobDetail")
    assert not hasattr(widget, "comboBoxItemStatus")
    assert not hasattr(widget, "buttonRefreshStatus")
    assert not hasattr(widget, "buttonCancel")
    assert widget.cards() == {}
    assert widget.emptyStateWidget is not None
    assert widget.labelStatus.text() == "Ready"


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
def test_monitor_only_intent_is_explicit_in_ui(widget):
    """監視専用であることが UI 上で明示されること (ADR 0076 §3 / Phase 4c)。"""
    hint_text = widget.labelMonitorOnlyHint.text()
    assert "監視専用" in hint_text
    assert "Annotate" in hint_text


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
def test_recovery_context_menu_removed(widget):
    """右クリック復旧メニューが撤去されていること (Issue #1103 — 右クリック隠蔽なし)。"""
    assert not hasattr(widget, "_action_fetch_results")
    assert not hasattr(widget, "_action_import_results")


@pytest.mark.unit
@pytest.mark.gui
def test_set_dependencies_builds_cards(widget, dependencies):
    """set_dependencies は workflow_service / repository のみでカード台帳を構築する。"""
    workflow, repository = dependencies

    widget.set_dependencies(workflow, repository)

    assert len(widget.cards()) == 1
    assert not widget.emptyStateWidget.isVisible()
    assert widget.labelJobCount.text() == "· 1"


@pytest.mark.unit
@pytest.mark.gui
def test_empty_state_shown_when_no_jobs(widget, dependencies, qtbot):
    """0 件のとき empty state を表示する (テーブルの空白では表現しない)。"""
    workflow, repository = dependencies
    repository.list_provider_batch_jobs.return_value = []

    widget.set_dependencies(workflow, repository)
    widget.show()
    qtbot.waitExposed(widget)

    assert widget.cards() == {}
    assert widget.emptyStateWidget.isVisible()
    assert widget.labelJobCount.text() == "· 0"


@pytest.mark.unit
@pytest.mark.gui
def test_list_failure_shows_error_banner_and_keeps_cards(widget, dependencies):
    """一覧取得失敗時はエラーバナーを出し、最終既知状態のカードを保持する。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    assert len(widget.cards()) == 1

    repository.list_provider_batch_jobs.side_effect = RuntimeError("network timeout")
    widget.refresh_jobs()

    assert len(widget.cards()) == 1  # 台帳保持
    assert not widget._error_banner.isHidden() or widget._error_banner.isVisibleTo(widget)
    assert "取得できません" in widget.labelStatus.text()


# === 追跡カードの表示状態 (Issue #1103 デザイン Frame B) ===


@pytest.mark.unit
@pytest.mark.gui
@pytest.mark.parametrize(
    ("job_kwargs", "expected"),
    [
        ({"status": "submitted"}, "active"),
        ({"status": "validating"}, "active"),
        ({"status": "running"}, "active"),
        ({"status": "canceling"}, "active"),
        ({"status": "completed"}, "collectable"),
        ({"status": "imported"}, "imported"),
        ({"status": "completed", "imported_at": datetime(2026, 1, 2, tzinfo=UTC)}, "imported"),
        ({"status": "failed"}, "failed"),
        ({"status": "canceled"}, "canceled"),
        ({"status": "expired"}, "expired"),
    ],
)
def test_derive_view_state(job_kwargs, expected):
    assert derive_view_state(_job(**job_kwargs)) == expected


@pytest.mark.unit
@pytest.mark.gui
def test_active_card_has_check_and_cancel_buttons(widget, dependencies):
    """進行中カードは「↻ 状態を確認」(primary) と「キャンセル」を footer に持つ。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert card.view_state == "active"
    assert card.check_button is not None
    assert card.check_button.text() == "↻ 状態を確認"
    assert card.cancel_button is not None
    assert card.cancel_button.isEnabled()


@pytest.mark.unit
@pytest.mark.gui
def test_collectable_card_has_collect_button_only(widget, dependencies):
    """完了・未回収カードは「↓ 結果を取得」のみ (キャンセル不可)。"""
    workflow, repository = dependencies
    repository.list_provider_batch_jobs.return_value = [
        _job(status="completed", provider_status="completed")
    ]
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert card.view_state == "collectable"
    assert card.check_button is not None
    assert card.check_button.text() == "↓ 結果を取得"
    assert card.cancel_button is None


@pytest.mark.unit
@pytest.mark.gui
@pytest.mark.parametrize("status", ["imported", "failed", "canceled", "expired"])
def test_terminal_cards_have_no_action_buttons(widget, dependencies, status):
    """terminal カード (取込済み/失敗/キャンセル/期限切れ) はアクションを持たない。"""
    workflow, repository = dependencies
    repository.list_provider_batch_jobs.return_value = [_job(status=status)]
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert card.check_button is None
    assert card.cancel_button is None


@pytest.mark.unit
@pytest.mark.gui
def test_card_shows_shortened_batch_id_and_request_count(widget, dependencies):
    """カードヘッダにジョブ ID 短縮表記と requests 数を表示する。"""
    workflow, repository = dependencies
    repository.list_provider_batch_jobs.return_value = [
        _job(provider_job_id="batch_68a41f0e2c9f2c", request_count=512)
    ]
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    labels = [w.text() for w in card.findChildren(QLabel)]
    assert any("batch_68a…9f2c" in text for text in labels)
    assert any("512 requests" in text for text in labels)


# === 状態確認 (refresh → fetch → import) ===


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_incomplete_job_only_refreshes_status(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    widget.check_job_status(42)

    workflow.refresh.assert_called_once_with(42)
    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert "検証中" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_via_card_button_click(widget, dependencies, qtbot):
    """カード footer の「↻ 状態を確認」クリックで状態確認が走る。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert card.check_button is not None
    card.check_button.click()

    workflow.refresh.assert_called_once_with(42)


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

    widget.check_job_status(42)

    workflow.refresh.assert_called_once_with(42)
    workflow.fetch_results.assert_called_once_with(42)
    workflow.import_results.assert_called_once_with(42, fetch_result)
    assert "処理完了" in widget.labelStatus.text()
    assert "DB保存が完了" in widget.labelStatus.text()


def test_check_status_result_file_gone_is_handled_not_crash(widget, dependencies):
    """#1152: 結果ファイル削除済み(404)→ProviderBatchError を widget が処理し未処理例外にしない。"""
    from lorairo.services.provider_batch_service import ProviderBatchError

    workflow, repository = dependencies
    workflow.refresh.return_value = _job(status="completed", provider_status="completed")
    workflow.fetch_results.side_effect = ProviderBatchError(
        "結果ファイルは provider 側で削除済みです（保存期限切れの可能性）。"
        "このジョブの結果は回収できません。再送は Annotate から行ってください。"
    )
    widget.set_dependencies(workflow, repository)

    # 未処理例外を出さず (catch されている)、専用メッセージ表示 + WARNING ログ (#1150)
    messages = _capture_warnings(lambda: widget.check_job_status(42))

    assert "削除済み" in widget.labelStatus.text()
    assert "回収できません" in widget.labelStatus.text()
    assert any("status check failed (job 42)" in m and "削除済み" in m for m in messages)


@pytest.mark.unit
@pytest.mark.gui
def test_check_status_for_imported_job_does_not_save_again(widget, dependencies):
    workflow, repository = dependencies
    repository.get_provider_batch_job.return_value = _job(
        status="imported", imported_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    widget.set_dependencies(workflow, repository)

    widget.check_job_status(42)

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

    widget.check_job_status(42)

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

    widget.check_job_status(42)

    workflow.fetch_results.assert_not_called()
    workflow.import_results.assert_not_called()
    assert expected in widget.labelStatus.text()


# === lifecycle / 復旧操作 ===


@pytest.mark.unit
@pytest.mark.gui
def test_cancel_job_calls_workflow(widget, dependencies):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    widget.cancel_job(42)

    workflow.cancel.assert_called_once_with(42)
    assert "キャンセルを要求しました" in widget.labelStatus.text()


def _capture_warnings(func) -> list[str]:
    """loguru の WARNING 以上を捕捉して func 実行中のメッセージを返す (#1150)。"""
    from lorairo.utils.log import logger

    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")
    try:
        func()
    finally:
        logger.remove(sink_id)
    return messages


def test_check_job_status_provider_error_logs_warning(widget, dependencies):
    """#1150: check_job_status の ProviderBatchError が WARNING ログに残る (事後診断可能)。"""
    from lorairo.services.provider_batch_service import ProviderBatchError

    workflow, repository = dependencies
    workflow.refresh.side_effect = ProviderBatchError("adapter 未登録")
    widget.set_dependencies(workflow, repository)

    messages = _capture_warnings(lambda: widget.check_job_status(42))

    assert any("status check failed (job 42)" in m and "adapter 未登録" in m for m in messages)
    # ダイアログ / labelStatus のフィードバックは維持
    assert "adapter 未登録" in widget.labelStatus.text()


def test_cancel_job_provider_error_logs_warning(widget, dependencies):
    """#1150: cancel_job の ProviderBatchError が WARNING ログに残る。"""
    from lorairo.services.provider_batch_service import ProviderBatchError

    workflow, repository = dependencies
    workflow.cancel.side_effect = ProviderBatchError("ジョブは既に完了しています")
    widget.set_dependencies(workflow, repository)

    messages = _capture_warnings(lambda: widget.cancel_job(42))

    assert any("cancel failed (job 42)" in m and "既に完了" in m for m in messages)
    assert "既に完了" in widget.labelStatus.text()


@pytest.mark.unit
@pytest.mark.gui
def test_cancel_via_card_button_click(widget, dependencies):
    """カード footer のキャンセルボタンクリックでキャンセルが走る。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert card.cancel_button is not None
    card.cancel_button.click()

    workflow.cancel.assert_called_once_with(42)


@pytest.mark.unit
@pytest.mark.gui
def test_action_handlers_catch_unexpected_errors(widget, dependencies, monkeypatch):
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)
    workflow.cancel.side_effect = RuntimeError("adapter exploded")
    critical = MagicMock()
    monkeypatch.setattr(widget_module.QMessageBox, "critical", critical)

    widget.cancel_job(42)

    critical.assert_called_once()
    assert widget.labelStatus.text() == "cancel に失敗しました"


# === 展開詳細 (progressive disclosure) ===


@pytest.mark.unit
@pytest.mark.gui
def test_card_expansion_loads_detail_and_items(widget, dependencies, qtbot):
    """「詳細 ▸」で展開すると kv 詳細と項目テーブルが読み込まれる。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    card = _card(widget)
    assert not card.expanded
    card._disc_button.click()

    assert card.expanded
    repository.list_provider_batch_items.assert_called_with(42, status=None)
    assert card.items_table.rowCount() == 1
    assert card.items_table.item(0, 3).text() == "provider_error"
    # kv 詳細に主要フィールドが含まれる
    labels = [w.text() for w in card._expansion.findChildren(QLabel)]
    assert any("batch_42" in text for text in labels)
    assert any("validating" in text for text in labels)


@pytest.mark.unit
@pytest.mark.gui
def test_expanded_state_survives_refresh(widget, dependencies):
    """refresh_jobs でカードを再構築しても展開状態を維持する。"""
    workflow, repository = dependencies
    widget.set_dependencies(workflow, repository)

    _card(widget)._disc_button.click()
    widget.refresh_jobs()

    assert _card(widget).expanded


# === ADR 0066: 統一 Jobs lifecycle ビュー (同期ジョブ台帳セクション) ===


@pytest.mark.unit
@pytest.mark.gui
def test_sync_jobs_section_inserted_at_top_of_right_splitter(widget):
    """同期ジョブ台帳セクションが右ペイン先頭に拡張方式で追加される"""
    sync_widget = widget.get_sync_jobs_widget()
    assert widget.splitterRight.indexOf(sync_widget) == 0
    # Provider Batch バンド (Issue #1103 カード台帳) は sync 台帳の直後
    assert widget.splitterRight.indexOf(widget.batchBandWidget) == 1


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
