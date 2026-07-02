"""SelectedImageDetailsWidget の refinement 配線テスト (#931, Phase 4)。

worker 完了の image_id 照合 (レース)・ignore の永続化と再評価・評価起動を、
実スレッドを使わず fake サービス / fake worker manager で検証する。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation
from PySide6.QtCore import QObject, Signal

from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.workers.refinement_worker import RefinementResult
from lorairo.gui.workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent

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

    def recommend_for_tags(self, tags, format_map=None, repo=None, cancel_check=None):  # type: ignore[no-untyped-def]
        return {t: _rec(t) for t in tags}

    def ignore(self, tag: str, reason_code: str) -> None:
        self.ignored.append((tag, reason_code))


class _FakeWorkerManager(QObject):
    """worker_terminal Signal を持つ fake (#1024 single-flight 配線用に QObject 化)。"""

    worker_terminal = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.started: list[tuple[str, object]] = []
        self.cancel_all_calls = 0
        self.cancel_requests: list[tuple[str, object]] = []

    def start_worker(self, worker_id, worker, auto_cleanup=True):  # type: ignore[no-untyped-def]
        self.started.append((worker_id, worker))
        return True

    def cancel_all_workers(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.cancel_all_calls += 1

    def request_cancel_worker(self, worker_id, reason=None):  # type: ignore[no-untyped-def]
        self.cancel_requests.append((worker_id, reason))
        return True

    def emit_terminal(self, worker_id: str, outcome: WorkerOutcome = WorkerOutcome.SUCCEEDED) -> None:
        """テストから worker 終端イベントを流すヘルパー。"""
        self.worker_terminal.emit(
            WorkerTerminalEvent(worker_id=worker_id, worker_type="refinement", outcome=outcome)
        )


def _make_widget(qtbot) -> SelectedImageDetailsWidget:
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    return widget


def test_finished_applies_when_image_matches(qtbot, monkeypatch) -> None:
    widget = _make_widget(qtbot)
    widget.current_image_id = 5
    widget._refinement_generation = 3
    applied: list[dict] = []
    monkeypatch.setattr(widget.annotation_display, "apply_refinements", applied.append)

    widget._on_refinement_finished(
        RefinementResult(image_id=5, generation=3, recommendations={"flower": _rec("flower")})
    )

    assert len(applied) == 1
    assert set(applied[0].keys()) == {"flower"}


def test_finished_discards_on_image_mismatch(qtbot, monkeypatch) -> None:
    widget = _make_widget(qtbot)
    widget.current_image_id = 5
    widget._refinement_generation = 3
    applied: list[dict] = []
    monkeypatch.setattr(widget.annotation_display, "apply_refinements", applied.append)

    widget._on_refinement_finished(
        RefinementResult(image_id=9, generation=3, recommendations={"flower": _rec("flower")})
    )

    assert applied == []


def test_finished_discards_stale_generation(qtbot, monkeypatch) -> None:
    """同一 image_id でも古い世代の結果は破棄する (A→B→A レース、Codex P2)。"""
    widget = _make_widget(qtbot)
    widget.current_image_id = 5
    widget._refinement_generation = 4  # 現行世代
    applied: list[dict] = []
    monkeypatch.setattr(widget.annotation_display, "apply_refinements", applied.append)

    # 古い世代 (2) の結果 — image_id は一致するが世代が古い
    widget._on_refinement_finished(
        RefinementResult(image_id=5, generation=2, recommendations={"flower": _rec("flower")})
    )

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


def _make_wired_widget(qtbot) -> tuple[SelectedImageDetailsWidget, _FakeWorkerManager]:
    widget = _make_widget(qtbot)
    manager = _FakeWorkerManager()
    widget.set_refinement_service(_FakeService(), worker_manager=manager)
    widget.current_image_id = 5
    widget._current_tag_canonicals = ["flower"]
    return widget, manager


def test_second_trigger_while_inflight_defers_and_cancels_old(qtbot) -> None:
    """実行中に再トリガーすると旧 worker へ協調キャンセル + 最新要求を pending 保持 (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()  # 1本目 (in-flight)
    widget._current_tag_canonicals = ["flower", "roses"]
    widget._trigger_refinement_evaluation()  # 2本目は起動されず pending へ

    assert len(manager.started) == 1
    inflight_id = manager.started[0][0]
    assert manager.cancel_requests == [(inflight_id, CancelReason.REFINEMENT_REPLACED)]
    assert widget._refinement_pending is not None
    assert widget._refinement_pending[1] == ["flower", "roses"]


def test_pending_keeps_only_latest_request(qtbot) -> None:
    """連打しても pending は最新1件だけ保持され、worker は積み上がらない (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    for tags in (["a"], ["b"], ["c"]):
        widget._current_tag_canonicals = tags
        widget._trigger_refinement_evaluation()

    assert len(manager.started) == 1  # in-flight は常に1本
    assert widget._refinement_pending is not None
    assert widget._refinement_pending[1] == ["c"]  # 最新のみ


def test_terminal_event_starts_pending_request(qtbot) -> None:
    """worker 終端イベントで pending の最新要求が起動される (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    widget._current_tag_canonicals = ["roses"]
    widget._trigger_refinement_evaluation()

    inflight_id = manager.started[0][0]
    manager.emit_terminal(inflight_id, WorkerOutcome.CANCELED)

    assert len(manager.started) == 2
    assert widget._refinement_pending is None
    assert widget._refinement_inflight_id == manager.started[1][0]


def test_terminal_event_for_other_worker_is_ignored(qtbot) -> None:
    """共有 manager 経由の他 worker の終端イベントでは枠を解放しない (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    inflight_id = widget._refinement_inflight_id

    manager.emit_terminal("search_1", WorkerOutcome.SUCCEEDED)

    assert widget._refinement_inflight_id == inflight_id  # 解放されない


def test_terminal_without_pending_frees_slot_for_next_trigger(qtbot) -> None:
    """pending 無しで終端したら次のトリガーは即起動される (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    manager.emit_terminal(manager.started[0][0])

    widget._trigger_refinement_evaluation()

    assert len(manager.started) == 2
    assert manager.cancel_requests == []  # キャンセルは発生しない


def test_terminal_drops_stale_pending_when_selection_cleared(qtbot) -> None:
    """選択解除後の終端イベントでは stale pending を起動しない (Codex P2)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    widget._trigger_refinement_evaluation()  # pending を作る (image 5)

    widget.current_image_id = None  # 選択解除 (無タグ画像への移動も同型)
    manager.emit_terminal(manager.started[0][0], WorkerOutcome.CANCELED)

    assert len(manager.started) == 1  # stale pending は起動されない
    assert widget._refinement_pending is None


def test_terminal_drops_stale_pending_when_tags_emptied(qtbot) -> None:
    """タグ無し状態になった後の終端イベントでも pending を起動しない (Codex P2)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    widget._trigger_refinement_evaluation()  # pending を作る

    widget._current_tag_canonicals = []
    manager.emit_terminal(manager.started[0][0], WorkerOutcome.CANCELED)

    assert len(manager.started) == 1


def test_shutdown_clears_pending_before_cancel(qtbot) -> None:
    """shutdown() は pending をクリアし、terminal イベントでの再起動を防ぐ (#1024)。"""
    widget, manager = _make_wired_widget(qtbot)

    widget._trigger_refinement_evaluation()
    widget._current_tag_canonicals = ["roses"]
    widget._trigger_refinement_evaluation()  # pending を作る

    widget.shutdown()
    manager.emit_terminal(manager.started[0][0], WorkerOutcome.CANCELED)

    assert widget._refinement_pending is None
    assert len(manager.started) == 1  # pending は起動されない


def test_shutdown_cancels_workers(qtbot) -> None:
    """shutdown() で refinement worker manager をキャンセルする (Codex P2 teardown)。"""
    widget = _make_widget(qtbot)
    service = _FakeService()
    manager = _FakeWorkerManager()
    widget.set_refinement_service(service, worker_manager=manager)

    widget.shutdown()

    assert manager.cancel_all_calls == 1


def test_shutdown_without_service_is_noop(qtbot) -> None:
    """サービス未配線でも shutdown() は例外にならない。"""
    widget = _make_widget(qtbot)
    widget.shutdown()  # 例外が出なければ OK
