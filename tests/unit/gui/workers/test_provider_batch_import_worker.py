"""ProviderBatchImportWorker の単体テスト (#1158)。

run() を直接呼び (同期実行)、refresh→fetch→import の分岐とシグナル発火を検証する。
worker 化の目的は GUI スレッドをブロックしないことなので、ここでは分岐ロジックと
例外 marshal (ADR 0044) を確認する。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lorairo.gui.workers.provider_batch_import_worker import (
    ProviderBatchCollectOutcome,
    ProviderBatchImportWorker,
)
from lorairo.services.provider_batch_service import ProviderBatchError


class _FakeWorkflowService:
    """refresh / fetch_results / import_results の呼び出しを記録する fake。"""

    def __init__(
        self,
        refresh_job: Any,
        *,
        fetch_result: Any = None,
        import_result: Any = None,
        refresh_exc: Exception | None = None,
        fetch_exc: Exception | None = None,
    ) -> None:
        self._refresh_job = refresh_job
        self._fetch_result = fetch_result
        self._import_result = import_result
        self._refresh_exc = refresh_exc
        self._fetch_exc = fetch_exc
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def refresh(self, job_id: int) -> Any:
        self.calls.append(("refresh", (job_id,)))
        if self._refresh_exc is not None:
            raise self._refresh_exc
        return self._refresh_job

    def fetch_results(self, job_id: int) -> Any:
        self.calls.append(("fetch_results", (job_id,)))
        if self._fetch_exc is not None:
            raise self._fetch_exc
        return self._fetch_result

    def import_results(self, job_id: int, fetch_result: Any) -> Any:
        self.calls.append(("import_results", (job_id, fetch_result)))
        return self._import_result


def _job(**overrides: Any) -> SimpleNamespace:
    values = {"status": "submitted", "imported_at": None}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.gui
class TestProviderBatchImportWorker:
    def test_completed_job_fetches_and_imports_then_emits_collected(self, qtbot: Any) -> None:
        fetch_result = SimpleNamespace(items=())
        import_result = SimpleNamespace(imported_count=3, total_count=3)
        fake = _FakeWorkflowService(
            _job(status="completed"),
            fetch_result=fetch_result,
            import_result=import_result,
        )
        worker = ProviderBatchImportWorker(fake, 42)

        outcomes: list[tuple[int, ProviderBatchCollectOutcome]] = []
        finished: list[bool] = []
        worker.succeeded.connect(lambda jid, outcome: outcomes.append((jid, outcome)))
        worker.finished.connect(lambda: finished.append(True))

        worker.run()

        assert finished == [True]
        assert len(outcomes) == 1
        job_id, outcome = outcomes[0]
        assert job_id == 42
        assert outcome.kind == "collected"
        assert outcome.import_result is import_result
        assert fake.calls == [
            ("refresh", (42,)),
            ("fetch_results", (42,)),
            ("import_results", (42, fetch_result)),
        ]

    def test_imported_job_skips_fetch_import_and_emits_imported(self, qtbot: Any) -> None:
        fake = _FakeWorkflowService(_job(status="imported"))
        worker = ProviderBatchImportWorker(fake, 42)

        outcomes: list[ProviderBatchCollectOutcome] = []
        worker.succeeded.connect(lambda _jid, outcome: outcomes.append(outcome))

        worker.run()

        assert outcomes[0].kind == "imported"
        # 保存済みは fetch / import を呼ばない (二重保存防止)
        assert fake.calls == [("refresh", (42,))]

    def test_incomplete_job_emits_status_only(self, qtbot: Any) -> None:
        fake = _FakeWorkflowService(_job(status="validating"))
        worker = ProviderBatchImportWorker(fake, 42)

        outcomes: list[ProviderBatchCollectOutcome] = []
        worker.succeeded.connect(lambda _jid, outcome: outcomes.append(outcome))

        worker.run()

        assert outcomes[0].kind == "status"
        assert fake.calls == [("refresh", (42,))]

    def test_provider_error_is_marshalled_to_failed(self, qtbot: Any) -> None:
        fake = _FakeWorkflowService(
            _job(status="completed"),
            fetch_exc=ProviderBatchError("結果ファイルは削除済みです"),
        )
        worker = ProviderBatchImportWorker(fake, 42)

        failures: list[tuple[int, object]] = []
        finished: list[bool] = []
        succeeded: list[Any] = []
        worker.failed.connect(lambda jid, err: failures.append((jid, err)))
        worker.finished.connect(lambda: finished.append(True))
        worker.succeeded.connect(lambda *_: succeeded.append(True))

        worker.run()

        # worker thread 境界では全例外を捕捉し failed で marshal する (ADR 0044)
        assert len(failures) == 1
        assert failures[0][0] == 42
        assert isinstance(failures[0][1], ProviderBatchError)
        assert succeeded == []
        assert finished == [True]

    def test_unexpected_exception_is_marshalled_to_failed(self, qtbot: Any) -> None:
        fake = _FakeWorkflowService(_job(status="submitted"), refresh_exc=RuntimeError("boom"))
        worker = ProviderBatchImportWorker(fake, 42)

        failures: list[tuple[int, object]] = []
        worker.failed.connect(lambda jid, err: failures.append((jid, err)))

        worker.run()

        assert len(failures) == 1
        assert isinstance(failures[0][1], RuntimeError)
