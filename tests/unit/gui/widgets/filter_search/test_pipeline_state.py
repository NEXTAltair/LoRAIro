# tests/unit/gui/widgets/filter_search/test_pipeline_state.py
"""PipelineStateMachine の Qt 非依存 unit test (ADR 0036 §6)。"""

import pytest

from lorairo.gui.widgets.filter_search.pipeline_state import (
    DEFAULT_STATE_MESSAGES,
    PipelineState,
    PipelineStateMachine,
)


@pytest.fixture()
def machine() -> PipelineStateMachine:
    """新しい PipelineStateMachine インスタンスを作成する。"""
    return PipelineStateMachine()


class TestInitialState:
    """初期状態のテスト。"""

    def test_default_state_is_idle(self, machine: PipelineStateMachine) -> None:
        assert machine.current_state == PipelineState.IDLE

    def test_is_not_active_initially(self, machine: PipelineStateMachine) -> None:
        assert machine.is_active() is False

    def test_default_state_messages_present(self, machine: PipelineStateMachine) -> None:
        for state in PipelineState:
            assert state in machine.state_messages
            assert machine.state_messages[state] == DEFAULT_STATE_MESSAGES[state]


class TestTransitionTo:
    """transition_to の状態遷移テスト。"""

    def test_transition_changes_state(self, machine: PipelineStateMachine) -> None:
        result = machine.transition_to(PipelineState.SEARCHING)

        assert result is True
        assert machine.current_state == PipelineState.SEARCHING

    def test_transition_to_same_state_is_ignored(self, machine: PipelineStateMachine) -> None:
        result = machine.transition_to(PipelineState.IDLE)

        assert result is False
        assert machine.current_state == PipelineState.IDLE

    def test_transition_invokes_listeners(self, machine: PipelineStateMachine) -> None:
        events: list[tuple[PipelineState, PipelineState]] = []
        machine.register_listener(lambda old, new: events.append((old, new)))

        machine.transition_to(PipelineState.SEARCHING)
        machine.transition_to(PipelineState.LOADING_THUMBNAILS)

        assert events == [
            (PipelineState.IDLE, PipelineState.SEARCHING),
            (PipelineState.SEARCHING, PipelineState.LOADING_THUMBNAILS),
        ]

    def test_same_state_does_not_invoke_listeners(self, machine: PipelineStateMachine) -> None:
        events: list[tuple[PipelineState, PipelineState]] = []
        machine.register_listener(lambda old, new: events.append((old, new)))

        machine.transition_to(PipelineState.IDLE)

        assert events == []

    def test_multiple_listeners_all_invoked(self, machine: PipelineStateMachine) -> None:
        calls_a: list[PipelineState] = []
        calls_b: list[PipelineState] = []
        machine.register_listener(lambda _old, new: calls_a.append(new))
        machine.register_listener(lambda _old, new: calls_b.append(new))

        machine.transition_to(PipelineState.SEARCHING)

        assert calls_a == [PipelineState.SEARCHING]
        assert calls_b == [PipelineState.SEARCHING]


class TestIsActive:
    """is_active の判定テスト。"""

    @pytest.mark.parametrize(
        "state,expected",
        [
            (PipelineState.IDLE, False),
            (PipelineState.SEARCHING, True),
            (PipelineState.LOADING_THUMBNAILS, True),
            (PipelineState.DISPLAYING, False),
            (PipelineState.ERROR, False),
            (PipelineState.CANCELED, False),
        ],
    )
    def test_is_active_per_state(
        self,
        machine: PipelineStateMachine,
        state: PipelineState,
        expected: bool,
    ) -> None:
        machine.transition_to(state)
        assert machine.is_active() is expected


class TestForceReset:
    """force_reset の動作テスト。"""

    def test_reset_from_searching_to_idle(self, machine: PipelineStateMachine) -> None:
        machine.transition_to(PipelineState.SEARCHING)
        machine.force_reset()

        assert machine.current_state == PipelineState.IDLE

    def test_reset_from_idle_is_noop(self, machine: PipelineStateMachine) -> None:
        events: list[PipelineState] = []
        machine.register_listener(lambda _old, new: events.append(new))

        machine.force_reset()

        assert machine.current_state == PipelineState.IDLE
        assert events == []


class TestNotifyThumbnailLoading:
    """thumbnail loading 通知時の状態遷移テスト。"""

    def test_started_from_searching(self, machine: PipelineStateMachine) -> None:
        machine.transition_to(PipelineState.SEARCHING)
        result = machine.notify_thumbnail_loading_started()

        assert result is True
        assert machine.current_state == PipelineState.LOADING_THUMBNAILS

    def test_started_from_idle_is_ignored(self, machine: PipelineStateMachine) -> None:
        result = machine.notify_thumbnail_loading_started()

        assert result is False
        assert machine.current_state == PipelineState.IDLE

    def test_completed_from_loading(self, machine: PipelineStateMachine) -> None:
        machine.transition_to(PipelineState.SEARCHING)
        machine.transition_to(PipelineState.LOADING_THUMBNAILS)
        result = machine.notify_thumbnail_loading_completed()

        assert result is True
        assert machine.current_state == PipelineState.DISPLAYING

    def test_completed_from_idle_is_ignored(self, machine: PipelineStateMachine) -> None:
        result = machine.notify_thumbnail_loading_completed()

        assert result is False
        assert machine.current_state == PipelineState.IDLE


class TestClearResults:
    """clear_results の状態遷移テスト。"""

    def test_clear_from_error_goes_to_idle(self, machine: PipelineStateMachine) -> None:
        machine.transition_to(PipelineState.ERROR)
        result = machine.clear_results()

        assert result is True
        assert machine.current_state == PipelineState.IDLE

    def test_clear_from_searching_goes_to_canceled(
        self,
        machine: PipelineStateMachine,
    ) -> None:
        machine.transition_to(PipelineState.SEARCHING)
        result = machine.clear_results()

        assert result is True
        assert machine.current_state == PipelineState.CANCELED

    def test_clear_from_displaying_goes_to_canceled(
        self,
        machine: PipelineStateMachine,
    ) -> None:
        machine.transition_to(PipelineState.SEARCHING)
        machine.transition_to(PipelineState.DISPLAYING)
        result = machine.clear_results()

        assert result is True
        assert machine.current_state == PipelineState.CANCELED

    def test_clear_from_canceled_is_noop(self, machine: PipelineStateMachine) -> None:
        machine.transition_to(PipelineState.CANCELED)
        result = machine.clear_results()

        # CANCELED → CANCELED は同一遷移なので False
        assert result is False
        assert machine.current_state == PipelineState.CANCELED


class TestPipelineStateEnumValues:
    """PipelineState Enum の値テスト (後方互換性)。"""

    def test_idle_value(self) -> None:
        assert PipelineState.IDLE.value == "idle"

    def test_searching_value(self) -> None:
        assert PipelineState.SEARCHING.value == "searching"

    def test_loading_thumbnails_value(self) -> None:
        assert PipelineState.LOADING_THUMBNAILS.value == "loading_thumbnails"

    def test_displaying_value(self) -> None:
        assert PipelineState.DISPLAYING.value == "displaying"

    def test_error_value(self) -> None:
        assert PipelineState.ERROR.value == "error"

    def test_canceled_value(self) -> None:
        assert PipelineState.CANCELED.value == "canceled"

    def test_all_six_states_present(self) -> None:
        assert len(list(PipelineState)) == 6
