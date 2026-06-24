"""AsyncBatchDispatchWorker の単体テスト (#884 Phase 2c, ADR 0076 §1)。

run() を直接呼び (同期実行)、submit_images の呼び出しとシグナル発火を検証する。
"""

from __future__ import annotations

from typing import Any

import pytest

from lorairo.gui.workers.async_batch_dispatch_worker import AsyncBatchDispatchWorker
from lorairo.services.dispatch_projection_service import DispatchEntry
from lorairo.services.provider_batch_service import ProviderBatchError


class _FakeWorkflowService:
    """submit_images の呼び出しを記録する fake。"""

    def __init__(
        self,
        job_ids: list[int] | None = None,
        raise_exc: Exception | None = None,
        raise_at_call: int | None = None,
    ) -> None:
        self._job_ids = list(job_ids or [])
        self._raise_exc = raise_exc
        self._raise_at_call = raise_at_call
        self.calls: list[dict[str, Any]] = []

    def submit_images(self, **kwargs: Any) -> int:
        self.calls.append(kwargs)
        call_index = len(self.calls) - 1
        if self._raise_exc is not None and (
            self._raise_at_call is None or self._raise_at_call == call_index
        ):
            raise self._raise_exc
        return self._job_ids[call_index]


def _entry(litellm_model_id: str, model_id: int) -> DispatchEntry:
    return DispatchEntry(
        provider="openai",
        endpoint="/v1/chat/completions",
        litellm_model_id=litellm_model_id,
        model_id=model_id,
        prompt_profile="default",
        description=None,
        task_type="annotation",
        image_ids=(10, 11),
        image_paths={10: "/data/p10.webp", 11: "/data/p11.webp"},
    )


@pytest.mark.gui
class TestAsyncBatchDispatchWorker:
    def test_submits_each_entry_and_emits_job_ids(self, qtbot: Any) -> None:
        entries = [_entry("openai/gpt-4o", 1), _entry("anthropic/claude-3-5-sonnet", 2)]
        fake = _FakeWorkflowService(job_ids=[101, 102])
        worker = AsyncBatchDispatchWorker(fake, entries)

        results: list[list[int]] = []
        finished: list[bool] = []
        worker.succeeded.connect(results.append)
        worker.finished.connect(lambda: finished.append(True))

        worker.run()

        assert results == [[101, 102]]
        assert finished == [True]
        assert len(fake.calls) == 2
        assert fake.calls[0]["litellm_model_id"] == "openai/gpt-4o"
        assert fake.calls[0]["model_id"] == 1
        assert fake.calls[0]["image_ids"] == [10, 11]
        assert fake.calls[0]["image_paths"] == {10: "/data/p10.webp", 11: "/data/p11.webp"}
        assert fake.calls[0]["task_type"] == "annotation"
        assert fake.calls[1]["model_id"] == 2

    def test_emits_failed_with_empty_job_ids_on_first_failure(self, qtbot: Any) -> None:
        fake = _FakeWorkflowService(raise_exc=ProviderBatchError("boom"))
        worker = AsyncBatchDispatchWorker(fake, [_entry("openai/gpt-4o", 1)])

        failures: list[tuple[object, list[int]]] = []
        finished: list[bool] = []
        succeeded: list[list[int]] = []
        worker.failed.connect(lambda err, ids: failures.append((err, ids)))
        worker.finished.connect(lambda: finished.append(True))
        worker.succeeded.connect(succeeded.append)

        worker.run()

        assert len(failures) == 1
        assert isinstance(failures[0][0], ProviderBatchError)
        assert failures[0][1] == []  # 送信済みなし
        assert succeeded == []
        assert finished == [True]

    def test_emits_failed_with_partial_job_ids_on_later_failure(self, qtbot: Any) -> None:
        # 1 件目成功 → 2 件目失敗。送信済み job_id を添えて重複送信を防ぐ。
        entries = [_entry("openai/gpt-4o", 1), _entry("anthropic/claude-3-5-sonnet", 2)]
        fake = _FakeWorkflowService(job_ids=[101, 0], raise_exc=ProviderBatchError("boom"), raise_at_call=1)
        worker = AsyncBatchDispatchWorker(fake, entries)

        failures: list[tuple[object, list[int]]] = []
        worker.failed.connect(lambda err, ids: failures.append((err, ids)))

        worker.run()

        assert len(failures) == 1
        assert failures[0][1] == [101]  # 1 件目は送信済み
