"""StagingStateManager のユニットテスト (Epic #867 / #876, ADR 0074)。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.gui.state.staging_state import StagingStateManager


def _dsm_with(metadata_by_id: dict[int, dict[str, str]], selected: list[int] | None = None) -> MagicMock:
    """get_image_by_id / selected_image_ids を備えた DatasetStateManager モックを返す。"""
    dsm = MagicMock()
    dsm.get_image_by_id.side_effect = lambda image_id: metadata_by_id.get(image_id)
    dsm.selected_image_ids = selected or []
    return dsm


@pytest.fixture
def metadata() -> dict[int, dict[str, str]]:
    return {i: {"stored_image_path": f"/data/{i}.webp"} for i in range(1, 6)}


@pytest.mark.unit
def test_add_image_ids_dedupes_and_preserves_order(metadata):
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(metadata))

    manager.add_image_ids([3, 1, 3, 2])

    assert manager.get_image_ids() == [3, 1, 2]
    assert manager.count() == 3


@pytest.mark.unit
def test_add_image_ids_emits_changed_signal(qtbot, metadata):
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(metadata))

    with qtbot.waitSignal(manager.staged_images_changed, timeout=1000) as blocker:
        manager.add_image_ids([1, 2])

    assert blocker.args[0] == [1, 2]


@pytest.mark.unit
def test_add_without_dataset_state_manager_is_noop():
    manager = StagingStateManager()
    manager.add_image_ids([1, 2])  # 例外なし
    assert manager.count() == 0


@pytest.mark.unit
def test_remove_image_ids(metadata):
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(metadata))
    manager.add_image_ids([1, 2, 3])

    manager.remove_image_ids([2])

    assert manager.get_image_ids() == [1, 3]


@pytest.mark.unit
def test_clear_emits_cleared_and_empty_changed(qtbot, metadata):
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(metadata))
    manager.add_image_ids([1, 2])

    with qtbot.waitSignal(manager.staging_cleared, timeout=1000):
        with qtbot.waitSignal(manager.staged_images_changed, timeout=1000) as changed:
            manager.clear()

    assert changed.args[0] == []
    assert manager.count() == 0


@pytest.mark.unit
def test_add_selected_images_uses_dataset_state_selection(metadata):
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(metadata, selected=[2, 4]))

    manager.add_selected_images()

    assert manager.get_image_ids() == [2, 4]


@pytest.mark.unit
def test_max_staging_images_cap():
    big_metadata = {i: {"stored_image_path": f"/d/{i}.webp"} for i in range(1, 600)}
    manager = StagingStateManager()
    manager.set_dataset_state_manager(_dsm_with(big_metadata))

    manager.add_image_ids(list(big_metadata.keys()))

    assert manager.count() == StagingStateManager.MAX_STAGING_IMAGES
