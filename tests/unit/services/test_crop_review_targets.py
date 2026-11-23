"""クロップ子画像を review 対象 ID へ解決する Qt-free service (#1603)。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.services.crop_review_targets import resolve_crop_child_image_ids

pytestmark = pytest.mark.unit


def _db_manager(existing: list[int], children: list[int]) -> Mock:
    db_manager = Mock()
    db_manager.image_repo.get_candidate_image_ids.side_effect = lambda ids: [
        i for i in ids if i in existing
    ]
    db_manager.crop_relation_repo.get_child_image_ids.return_value = children
    return db_manager


def test_parent_children_are_returned_in_order_without_duplicates():
    db_manager = _db_manager([5], [12, 11, 12])
    assert resolve_crop_child_image_ids(db_manager, 5) == [12, 11]
    db_manager.crop_relation_repo.get_child_image_ids.assert_called_once_with(5)


def test_all_children_skip_parent_existence_check():
    db_manager = _db_manager([], [3, 4])
    assert resolve_crop_child_image_ids(db_manager) == [3, 4]
    db_manager.image_repo.get_candidate_image_ids.assert_not_called()
    db_manager.crop_relation_repo.get_child_image_ids.assert_called_once_with(None)


def test_parent_without_children_is_an_empty_selection():
    assert resolve_crop_child_image_ids(_db_manager([5], []), 5) == []


def test_unknown_parent_raises_not_found_before_reading_relations():
    db_manager = _db_manager([], [])
    with pytest.raises(ImageNotFoundError) as error:
        resolve_crop_child_image_ids(db_manager, 99)
    assert error.value.image_id == 99
    db_manager.crop_relation_repo.get_child_image_ids.assert_not_called()
