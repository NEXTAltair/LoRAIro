"""SelectedImageDetailsWidget の refinement 配線テスト (#931, Phase 4)。

worker 完了の image_id 照合 (レース)・ignore の永続化と再評価・評価起動を、
実スレッドを使わず fake サービス / fake worker manager で検証する。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation

from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.workers.refinement_worker import RefinementResult

pytestmark = pytest.mark.gui


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
    def __init__(self) -> None:
        self.ignored: list[tuple[str, str]] = []

    def recommend_for_tags(self, tags, format_map=None, repo=None):  # type: ignore[no-untyped-def]
        return {t: _rec(t) for t in tags}

    def ignore(self, tag: str, reason_code: str) -> None:
        self.ignored.append((tag, reason_code))


class _FakeWorkerManager:
    def __init__(self) -> None:
        self.started: list[tuple[str, object]] = []

    def start_worker(self, worker_id, worker, auto_cleanup=True):  # type: ignore[no-untyped-def]
        self.started.append((worker_id, worker))
        return True


def _make_widget(qtbot) -> SelectedImageDetailsWidget:
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    return widget


def test_finished_applies_when_image_matches(qtbot, monkeypatch) -> None:
    widget = _make_widget(qtbot)
    widget.current_image_id = 5
    applied: list[dict] = []
    monkeypatch.setattr(widget.annotation_display, "apply_refinements", applied.append)

    widget._on_refinement_finished(RefinementResult(image_id=5, recommendations={"flower": _rec("flower")}))

    assert len(applied) == 1
    assert set(applied[0].keys()) == {"flower"}


def test_finished_discards_on_image_mismatch(qtbot, monkeypatch) -> None:
    widget = _make_widget(qtbot)
    widget.current_image_id = 5
    applied: list[dict] = []
    monkeypatch.setattr(widget.annotation_display, "apply_refinements", applied.append)

    widget._on_refinement_finished(RefinementResult(image_id=9, recommendations={"flower": _rec("flower")}))

    assert applied == []


def test_trigger_starts_worker(qtbot) -> None:
    widget = _make_widget(qtbot)
    service = _FakeService()
    manager = _FakeWorkerManager()
    widget.set_refinement_service(service, worker_manager=manager)
    widget.current_image_id = 5
    widget._current_tag_canonicals = ["flower", "blue_eyes"]

    widget._trigger_refinement_evaluation()

    assert len(manager.started) == 1
    worker_id, _worker = manager.started[0]
    assert worker_id.startswith("refinement_")


def test_trigger_noop_without_tags(qtbot) -> None:
    widget = _make_widget(qtbot)
    service = _FakeService()
    manager = _FakeWorkerManager()
    widget.set_refinement_service(service, worker_manager=manager)
    widget.current_image_id = 5
    widget._current_tag_canonicals = []

    widget._trigger_refinement_evaluation()

    assert manager.started == []


def test_ignored_persists_and_reevaluates(qtbot) -> None:
    widget = _make_widget(qtbot)
    service = _FakeService()
    manager = _FakeWorkerManager()
    widget.set_refinement_service(service, worker_manager=manager)
    widget.current_image_id = 5
    widget._current_tag_canonicals = ["flower"]

    widget._on_refinement_ignored("flower", "broad_single_word")

    assert service.ignored == [("flower", "broad_single_word")]
    assert len(manager.started) == 1  # 再評価が起動した
