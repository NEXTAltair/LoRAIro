"""ModelSelectionStateManager のユニットテスト (#884 Phase 1, ADR 0076)。"""

import pytest

from lorairo.gui.state.model_selection_state import ModelSelectionStateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(qapp) -> ModelSelectionStateManager:
    return ModelSelectionStateManager()


def test_initial_state_is_empty(manager: ModelSelectionStateManager) -> None:
    assert manager.get_selected() == []
    assert manager.count() == 0
    assert manager.is_selected("openai/gpt-4o") is False


def test_set_selected_replaces_set_and_preserves_order(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["b", "a", "c"])
    assert manager.get_selected() == ["b", "a", "c"]
    assert manager.count() == 3
    assert manager.is_selected("a") is True


def test_set_selected_dedupes(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a", "a", "b"])
    assert manager.get_selected() == ["a", "b"]


def test_set_selected_dedupes_keeps_first_occurrence(manager: ModelSelectionStateManager) -> None:
    """後続重複は最初の出現順を保持する (first occurrence wins)。"""
    manager.set_selected(["a", "b", "a"])
    assert manager.get_selected() == ["a", "b"]


def test_set_selected_emits_only_on_change(qtbot, manager: ModelSelectionStateManager) -> None:
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_selected(["a", "b"])
    assert blocker.args == [["a", "b"]]

    # 同一集合 (順序同一) の再設定は emit しない
    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.set_selected(["a", "b"])
    assert received == []


def test_set_model_selected_toggles_one(qtbot, manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_model_selected("b", True)
    assert blocker.args == [["a", "b"]]

    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_model_selected("a", False)
    assert blocker.args == [["b"]]


def test_set_model_selected_noop_does_not_emit(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.set_model_selected("a", True)  # 既に選択
    manager.set_model_selected("z", False)  # 元々未選択
    assert received == []


def test_clear_emits_only_when_nonempty(qtbot, manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.clear()
    assert blocker.args == [[]]

    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.clear()  # 既に空
    assert received == []
