"""_image_ids 共有ヘルパーのユニットテスト。"""

from unittest.mock import MagicMock

import click
import pytest

from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.public_api.exceptions import ImageNotFoundError


@pytest.mark.unit
class TestParseImageIds:
    def test_parses_comma_separated_ints(self) -> None:
        assert parse_image_ids("1,2,3") == [1, 2, 3]

    def test_strips_whitespace(self) -> None:
        assert parse_image_ids(" 1 , 2 ") == [1, 2]

    def test_ignores_empty_segments(self) -> None:
        assert parse_image_ids("1,,2,") == [1, 2]

    def test_raises_usage_error_on_non_integer(self) -> None:
        with pytest.raises(click.UsageError):
            parse_image_ids("1,abc")

    def test_max_image_ids_constant_is_500(self) -> None:
        assert MAX_IMAGE_IDS == 500


@pytest.mark.unit
class TestValidateImageIdsExist:
    def test_passes_when_all_ids_found(self) -> None:
        container = MagicMock()
        container.db_manager.image_repo.get_images_by_filter.return_value = (
            [{"id": 1}, {"id": 2}],
            2,
        )
        validate_image_ids_exist(container, [1, 2])  # does not raise

    def test_raises_image_not_found_for_missing_id(self) -> None:
        container = MagicMock()
        container.db_manager.image_repo.get_images_by_filter.return_value = ([{"id": 1}], 1)
        with pytest.raises(ImageNotFoundError) as exc_info:
            validate_image_ids_exist(container, [1, 2])
        assert exc_info.value.image_id == 2
