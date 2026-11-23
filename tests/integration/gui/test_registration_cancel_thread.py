"""実 QThread 上の登録 worker を Jobs 行と同じ経路でキャンセルする統合テスト (#1621)。

タグ DB の長い検索を、SQL 中断レジストリ (``sql_abort``) を見て ``interrupted`` で抜ける
偽の登録処理で再現する。``WorkerService.cancel_job`` は GUI スレッドを待たせずに協調
キャンセルを要求し、worker は処理済み件数と中断状態を返して終わる。QThread と worker は
GUI スレッドで破棄される (worker スレッドで deleteLater しない)。
"""

import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from lorairo.database.db_manager import RegistrationOutcome, RegistrationSideEffectResult
from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.workers import sql_abort
from lorairo.gui.workers.registration_worker import DatabaseRegistrationResult
from lorairo.gui.workers.terminal import WorkerOutcome, WorkerTerminalEvent
from lorairo.services.job_ledger_service import JobStatus


@pytest.mark.gui
def test_cancel_job_stops_registration_in_tag_search(qtbot, tmp_path: Path):
    images = [tmp_path / f"image{i}.png" for i in range(3)]
    fsm = Mock()
    fsm.get_image_files.return_value = images
    db_manager = Mock()
    db_manager.annotation_repo.batch_resolve_tag_ids.return_value = {}
    in_tag_search = threading.Event()
    worker_threads: list[int] = []

    def register(path: Path, *_args, **_kwargs) -> RegistrationSideEffectResult:
        if path == images[0]:
            return RegistrationSideEffectResult(RegistrationOutcome.REGISTERED, 1, {})
        # 2 枚目: タグ DB の長い検索。progress handler と同じ判定で中断されるまで抜けない
        worker_threads.append(threading.get_ident())
        in_tag_search.set()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if sql_abort.current_thread_cancel_requested():
                raise OperationalError("SELECT ...", {}, Exception("interrupted"))
            time.sleep(0.005)
        raise AssertionError("キャンセル要求が worker スレッドの SQL 中断判定に届かない")

    db_manager.register_image_with_side_effects.side_effect = register
    service = WorkerService(db_manager, fsm)
    terminals: list[WorkerTerminalEvent] = []
    service.worker_terminal.connect(terminals.append)

    worker_id = service.start_batch_registration(tmp_path)
    qtbot.waitUntil(in_tag_search.is_set, timeout=10000)
    assert worker_threads and worker_threads[0] != threading.get_ident()

    started = time.monotonic()
    assert service.cancel_job(worker_id) is True
    # GUI スレッドでスレッド終了を待たない (cancel_worker の grace 待機・terminate を使わない)
    assert time.monotonic() - started < 0.5
    assert service.job_ledger.get(worker_id).status is JobStatus.CANCELING

    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=10000)
    event = terminals[0]
    assert event.outcome is WorkerOutcome.SUCCEEDED
    result = event.result
    assert isinstance(result, DatabaseRegistrationResult)
    assert result.cancelled is True
    assert (result.registered_count, result.error_count, result.total_count) == (1, 0, 3)
    assert result.interrupted_file == "image1.png"
    # 3 枚目には進まず、キャンセルを画像エラーとして記録しない
    assert db_manager.register_image_with_side_effects.call_count == 2
    db_manager.save_error_record.assert_not_called()
    entry = service.job_ledger.get(worker_id)
    assert entry.status is JobStatus.CANCELED
    assert entry.summary == "中断: 1/3 件処理済み (中断対象: image1.png)"

    # スレッド終了後、GUI スレッド側で参照を解放して破棄する
    manager = service.worker_manager
    qtbot.waitUntil(lambda: not manager._retiring_workers and not manager.active_workers, timeout=10000)
