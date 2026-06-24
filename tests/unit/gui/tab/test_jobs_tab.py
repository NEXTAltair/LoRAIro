"""JobsTabWidget の GUI テスト (Epic #867 / #874)。

MainWindow から JobsTabWidget へ移送した責務 (ProviderBatchJobWidget の配置・DI 転送・
WorkerService シグナルの self-wire・同期ジョブキャンセル・Batch API 結果インポートの
ファイル選択/Dry-Run/結果ダイアログ・共有サービスへの Signal 委譲) を、実
``JobsTabWidget`` インスタンス相手に検証する。

内部の ``ProviderBatchJobWidget`` は service container を要求し構築が重いため、本
単体テストでは軽量 fake へ差し替え、JobsTabWidget 自身の配線・委譲ロジックに集中する。
ProviderBatchJobWidget 自体の振る舞いは ``tests/unit/gui/widgets/test_provider_batch_job_widget.py``
でカバーされる。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox, QWidget

import lorairo.gui.tab.jobs_tab as jobs_tab_module
from lorairo.gui.tab.jobs_tab import JobsTabWidget
from lorairo.services.batch_import_service import BatchImportResult


class _FakeProviderBatchJobWidget(QWidget):
    """ProviderBatchJobWidget の軽量スタブ (service container 非依存)。

    ADR 0076 §3: 作成入口撤去に伴い staging / dataset 注入は持たない (監視専用)。
    """

    sync_job_cancel_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job_ledger: object | None = None
        self.dependencies: dict[str, object] = {}
        self.refresh_jobs_calls = 0
        self.refresh_sync_jobs_calls = 0

    def set_dependencies(self, **kwargs: object) -> None:
        self.dependencies = kwargs

    def set_job_ledger(self, job_ledger: object) -> None:
        self.job_ledger = job_ledger

    def refresh_jobs(self, update_label: bool = True) -> None:
        self.refresh_jobs_calls += 1

    def refresh_sync_jobs(self) -> None:
        self.refresh_sync_jobs_calls += 1


@pytest.fixture(autouse=True)
def _stub_provider_batch_widget(monkeypatch):
    """JobsTabWidget が生成する ProviderBatchJobWidget を fake に差替える。"""
    monkeypatch.setattr(jobs_tab_module, "ProviderBatchJobWidget", _FakeProviderBatchJobWidget)


@pytest.fixture
def service_container() -> Mock:
    """provider_batch_workflow_service / repo / annotator_library / model_repo を満たす最小 container。"""
    return Mock()


@pytest.fixture
def worker_service() -> MagicMock:
    """job_ledger / batch import / cancel_job を満たす最小 WorkerService。"""
    ws = MagicMock()
    ws.cancel_job.return_value = True
    return ws


@pytest.fixture
def tab(qtbot, service_container: Mock, worker_service: MagicMock) -> JobsTabWidget:
    """実 JobsTabWidget を生成して返す (内部 widget は fake)。"""
    widget = JobsTabWidget(
        service_container=service_container,
        db_manager=Mock(),
        worker_service=worker_service,
    )
    qtbot.addWidget(widget)
    return widget


# == 1. 構築・DI 転送 =========================================================


@pytest.mark.gui
def test_tab_embeds_provider_batch_widget(tab: JobsTabWidget) -> None:
    """内部の ProviderBatchJobWidget を fake で内包する。"""
    assert isinstance(tab.provider_batch_job_widget, _FakeProviderBatchJobWidget)


@pytest.mark.gui
def test_di_forwarded_to_inner_widget(
    tab: JobsTabWidget,
    service_container: Mock,
) -> None:
    """job_ledger と監視用 service 依存を内部 widget へ転送する (ADR 0076 §3)。

    作成入口撤去に伴い staging / dataset / model_source / model_repository は転送しない。
    """
    inner = tab.provider_batch_job_widget
    assert inner.job_ledger is tab._worker_service.job_ledger
    assert inner.dependencies["workflow_service"] is (service_container.provider_batch_workflow_service)
    assert inner.dependencies["repository"] is service_container.db_manager.provider_batch_repo
    assert "model_source" not in inner.dependencies
    assert "model_repository" not in inner.dependencies


@pytest.mark.gui
def test_worker_signals_self_wired(tab: JobsTabWidget, worker_service: MagicMock) -> None:
    """job_ledger_changed / batch_import_* を自身で接続する。"""
    worker_service.job_ledger_changed.connect.assert_called_once_with(
        tab.provider_batch_job_widget.refresh_sync_jobs
    )
    worker_service.batch_import_finished.connect.assert_called_once_with(tab._on_batch_import_finished)
    worker_service.batch_import_error.connect.assert_called_once_with(tab._on_batch_import_error)
    worker_service.batch_import_canceled.connect.assert_called_once_with(tab._on_batch_import_canceled)


@pytest.mark.gui
def test_construction_safe_without_worker_service(qtbot, service_container: Mock) -> None:
    """worker_service が None でも例外なく構築でき、refresh() も安全。"""
    widget = JobsTabWidget(
        service_container=service_container,
        db_manager=Mock(),
        worker_service=None,
    )
    qtbot.addWidget(widget)
    assert widget._worker_service is None
    widget.refresh()  # 例外が出ないこと


# == 2. スロット・委譲 =========================================================


@pytest.mark.gui
def test_refresh_delegates_to_inner_widget(tab: JobsTabWidget) -> None:
    """refresh() は内部 widget の refresh_jobs を呼ぶ。"""
    before = tab.provider_batch_job_widget.refresh_jobs_calls
    tab.refresh()
    assert tab.provider_batch_job_widget.refresh_jobs_calls == before + 1


@pytest.mark.gui
def test_sync_job_cancel_calls_worker_and_emits_status(
    tab: JobsTabWidget, worker_service: MagicMock, qtbot
) -> None:
    """同期ジョブキャンセルは worker.cancel_job を呼び status_message_requested を emit する。"""
    with qtbot.waitSignal(tab.status_message_requested, timeout=1000) as blocker:
        tab.provider_batch_job_widget.sync_job_cancel_requested.emit("job-1")
    worker_service.cancel_job.assert_called_once_with("job-1")
    assert "job-1" in blocker.args[0]


@pytest.mark.gui
def test_sync_job_cancel_failure_does_not_emit_status(
    tab: JobsTabWidget, worker_service: MagicMock
) -> None:
    """cancel_job が False を返したら status_message は emit しない。"""
    worker_service.cancel_job.return_value = False
    received: list[tuple[str, int]] = []
    tab.status_message_requested.connect(lambda msg, t: received.append((msg, t)))
    tab.provider_batch_job_widget.sync_job_cancel_requested.emit("job-x")
    assert received == []


@pytest.mark.gui
def test_batch_import_error_relays_signal(tab: JobsTabWidget, qtbot) -> None:
    """batch import エラーは batch_import_error_occurred として MainWindow へ委譲する。"""
    with qtbot.waitSignal(tab.batch_import_error_occurred, timeout=1000) as blocker:
        tab._on_batch_import_error("インポート失敗")
    assert blocker.args[0] == "インポート失敗"


@pytest.mark.gui
def test_batch_import_canceled_relays_signal(tab: JobsTabWidget, qtbot) -> None:
    """batch import キャンセルは batch_import_canceled として MainWindow へ委譲する。"""
    with qtbot.waitSignal(tab.batch_import_canceled, timeout=1000) as blocker:
        tab._on_batch_import_canceled("worker-9")
    assert blocker.args[0] == "worker-9"


@pytest.mark.gui
def test_batch_import_finished_shows_dialog_and_emits_status(
    tab: JobsTabWidget, qtbot, monkeypatch
) -> None:
    """完了ハンドラは結果ダイアログを表示し status_message_requested を emit する。"""
    # モーダルダイアログをブロックせずに閉じる
    monkeypatch.setattr("lorairo.gui.tab.jobs_tab.QDialog.exec", lambda self: 0)
    result = BatchImportResult(total_records=3, parsed_ok=3, matched=2, unmatched=1, saved=2)
    with qtbot.waitSignal(tab.status_message_requested, timeout=1000) as blocker:
        tab._on_batch_import_finished(result)
    assert "2件保存" in blocker.args[0]


@pytest.mark.gui
def test_batch_import_finished_ignores_wrong_type(tab: JobsTabWidget) -> None:
    """BatchImportResult 以外は無視する (status は emit しない)。"""
    received: list[str] = []
    tab.status_message_requested.connect(lambda msg, t: received.append(msg))
    tab._on_batch_import_finished({"not": "a result"})
    assert received == []


# == 3. Batch インポート起動 ==================================================


@pytest.mark.gui
def test_start_batch_import_no_worker_service_warns(qtbot, service_container: Mock, monkeypatch) -> None:
    """worker_service 未初期化なら警告を出して何もしない。"""
    widget = JobsTabWidget(
        service_container=service_container,
        db_manager=Mock(),
        worker_service=None,
    )
    qtbot.addWidget(widget)
    warn_mock = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warn_mock)
    widget.start_batch_import()
    warn_mock.assert_called_once()


@pytest.mark.gui
def test_start_batch_import_dry_run_starts_worker(
    tab: JobsTabWidget, worker_service: MagicMock, monkeypatch
) -> None:
    """ファイル選択 → Dry-Run 選択で worker.start_batch_import(dry_run=True) を呼ぶ。"""
    monkeypatch.setattr(
        "lorairo.gui.tab.jobs_tab.QFileDialog.getOpenFileNames",
        lambda *a, **k: (["/tmp/a.jsonl"], ""),
    )
    dry_run_btn = object()
    fake_box = MagicMock()
    fake_box.addButton.side_effect = [dry_run_btn, object(), object()]
    fake_box.clickedButton.return_value = dry_run_btn
    monkeypatch.setattr("lorairo.gui.tab.jobs_tab.QMessageBox", MagicMock(return_value=fake_box))

    tab.start_batch_import()

    worker_service.start_batch_import.assert_called_once_with([Path("/tmp/a.jsonl")], dry_run=True)


@pytest.mark.gui
def test_start_batch_import_canceled_file_dialog_noop(
    tab: JobsTabWidget, worker_service: MagicMock, monkeypatch
) -> None:
    """ファイル未選択なら worker を起動しない。"""
    monkeypatch.setattr(
        "lorairo.gui.tab.jobs_tab.QFileDialog.getOpenFileNames",
        lambda *a, **k: ([], ""),
    )
    tab.start_batch_import()
    worker_service.start_batch_import.assert_not_called()
