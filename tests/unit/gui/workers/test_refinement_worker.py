"""RefinementWorker のテスト (#931)。

execute() の戻り値と finished Signal の payload (image_id 同梱) を検証する。
RefinementService は fake で差し替える。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation

from lorairo.gui.workers.refinement_worker import RefinementResult, RefinementWorker


def _rec(tag: str) -> RefinementRecommendation:
    return RefinementRecommendation(
        source_tag=tag,
        normalized_tag=tag,
        needs_refinement=True,
        score=0.7,
        reasons=[RefinementReason(code="broad_single_word", message="too generic")],  # type: ignore[arg-type]
        suggestions=[],
        proposals=[],
    )


class _FakeService:
    """recommend_for_tags の呼び出しを記録する fake。"""

    def __init__(self, result: dict[str, RefinementRecommendation]) -> None:
        self._result = result
        self.calls: list[tuple[list[str], object, object]] = []
        self.cancel_checks: list[object] = []

    def resolve_candidate_counts(self, recommendations, *, repo=None):  # type: ignore[no-untyped-def]
        return {}

    def recommend_for_tags(self, tags, format_map=None, repo=None, cancel_check=None, image_id=None):  # type: ignore[no-untyped-def]
        self.calls.append((list(tags), format_map, repo))
        self.cancel_checks.append(cancel_check)
        return self._result


class _CheckpointService:
    """評価ループ相当の場所で cancel_check を呼ぶ fake (#1024 協調キャンセル検証用)。"""

    def __init__(self) -> None:
        self.evaluated: list[str] = []

    def resolve_candidate_counts(self, recommendations, *, repo=None):  # type: ignore[no-untyped-def]
        return {}

    def recommend_for_tags(self, tags, format_map=None, repo=None, cancel_check=None, image_id=None):  # type: ignore[no-untyped-def]
        for tag in tags:
            if cancel_check is not None:
                cancel_check()
            self.evaluated.append(tag)
        return {}


@pytest.mark.unit
def test_execute_returns_result_with_image_id() -> None:
    service = _FakeService({"flower": _rec("flower")})
    worker = RefinementWorker(service, image_id=42, tags=["flower", "blue_eyes"])

    result = worker.execute()

    assert isinstance(result, RefinementResult)
    assert result.image_id == 42
    assert set(result.recommendations.keys()) == {"flower"}
    assert service.calls[0][0] == ["flower", "blue_eyes"]


@pytest.mark.unit
def test_execute_passes_format_map_and_repo() -> None:
    service = _FakeService({})
    sentinel_repo = object()
    worker = RefinementWorker(
        service, image_id=1, tags=["flower"], format_map={"flower": "danbooru"}, repo=sentinel_repo
    )

    worker.execute()

    _, format_map, repo = service.calls[0]
    assert format_map == {"flower": "danbooru"}
    assert repo is sentinel_repo


@pytest.mark.unit
def test_execute_passes_cancel_check_to_service() -> None:
    """execute() は service に協調キャンセル用の cancel_check を渡す (#1024)。"""
    service = _FakeService({})
    worker = RefinementWorker(service, image_id=1, tags=["flower"])

    worker.execute()

    assert service.cancel_checks == [worker._check_cancellation]


@pytest.mark.gui
def test_cancel_during_evaluation_emits_canceled_not_finished(qtbot) -> None:
    """評価途中のキャンセル要求はチェックポイントで中断し canceled で終端する (#1024)。"""
    service = _CheckpointService()
    worker = RefinementWorker(service, image_id=1, tags=["a", "b", "c"])
    worker.cancel()  # 実行前にキャンセル要求 (最初のチェックポイントで中断される)

    finished_results: list[object] = []
    worker.finished.connect(finished_results.append)
    with qtbot.waitSignal(worker.canceled, timeout=2000):
        worker.run()

    assert finished_results == []
    assert service.evaluated == []  # 1タグも評価せず中断


@pytest.mark.gui
def test_finished_signal_emits_result(qtbot) -> None:
    service = _FakeService({"flower": _rec("flower")})
    worker = RefinementWorker(service, image_id=7, tags=["flower"])

    with qtbot.waitSignal(worker.finished, timeout=2000) as blocker:
        worker.run()

    result = blocker.args[0]
    assert isinstance(result, RefinementResult)
    assert result.image_id == 7
    assert "flower" in result.recommendations
