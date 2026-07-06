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


@pytest.mark.unit
class TestParseImageIdsFile:
    """--image-ids-file の入力パース (Issue #1216)。"""

    def test_parses_newline_and_comma_separated(self, tmp_path) -> None:
        from lorairo.cli._image_ids import parse_image_ids_file

        f = tmp_path / "ids.txt"
        f.write_text("1\n2, 3\n\n4\n")
        assert parse_image_ids_file(str(f)) == [1, 2, 3, 4]

    def test_dedupes_preserving_first_seen_order(self, tmp_path) -> None:
        from lorairo.cli._image_ids import parse_image_ids_file

        f = tmp_path / "ids.txt"
        f.write_text("3,1,3,2,1")
        assert parse_image_ids_file(str(f)) == [3, 1, 2]

    def test_missing_file_raises(self) -> None:
        from lorairo.cli._image_ids import parse_image_ids_file

        with pytest.raises(click.UsageError):
            parse_image_ids_file("/no/such/file.txt")

    def test_non_integer_raises(self, tmp_path) -> None:
        from lorairo.cli._image_ids import parse_image_ids_file

        f = tmp_path / "ids.txt"
        f.write_text("1,abc,2")
        with pytest.raises(click.UsageError):
            parse_image_ids_file(str(f))

    def test_empty_file_raises(self, tmp_path) -> None:
        from lorairo.cli._image_ids import parse_image_ids_file

        f = tmp_path / "ids.txt"
        f.write_text("\n\n , \n")
        with pytest.raises(click.UsageError):
            parse_image_ids_file(str(f))


@pytest.mark.unit
class TestResolveImageIdsInput:
    """--image-ids / --image-ids-file 排他解決 (Issue #1216)。"""

    def test_csv_input(self) -> None:
        from lorairo.cli._image_ids import resolve_image_ids_input

        ids, is_file = resolve_image_ids_input("1,2,3", None)
        assert ids == [1, 2, 3]
        assert is_file is False

    def test_file_input(self, tmp_path) -> None:
        from lorairo.cli._image_ids import resolve_image_ids_input

        f = tmp_path / "ids.txt"
        f.write_text("10,20")
        ids, is_file = resolve_image_ids_input(None, str(f))
        assert ids == [10, 20]
        assert is_file is True

    def test_both_specified_raises(self, tmp_path) -> None:
        from lorairo.cli._image_ids import resolve_image_ids_input

        f = tmp_path / "ids.txt"
        f.write_text("1")
        with pytest.raises(click.UsageError):
            resolve_image_ids_input("1,2", str(f))

    def test_neither_specified_raises(self) -> None:
        from lorairo.cli._image_ids import resolve_image_ids_input

        with pytest.raises(click.UsageError):
            resolve_image_ids_input(None, None)

    def test_csv_over_500_raises(self) -> None:
        from lorairo.cli._image_ids import resolve_image_ids_input

        csv = ",".join(str(i) for i in range(501))
        with pytest.raises(click.UsageError):
            resolve_image_ids_input(csv, None)

    def test_file_over_500_allowed(self, tmp_path) -> None:
        """ファイル入力は 500 超を許容する (チャンク処理前提、Issue #1216)。"""
        from lorairo.cli._image_ids import resolve_image_ids_input

        f = tmp_path / "ids.txt"
        f.write_text("\n".join(str(i) for i in range(600)))
        ids, is_file = resolve_image_ids_input(None, str(f))
        assert len(ids) == 600
        assert is_file is True
