"""JSONL 矩形 provider (``JsonlCropRectProvider``) のユニットテスト (Issue #1340 / ADR 0103)。"""

from pathlib import Path

import pytest

from lorairo.domain.crop_rect_provider import CropRectProvider
from lorairo.domain.crop_request import CropRect
from lorairo.public_api.exceptions import ResultSetTooLargeError
from lorairo.services.crop_rect_jsonl_provider import JsonlCropRectProvider

pytestmark = pytest.mark.unit


def _write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "rects.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parses_rows_grouped_by_parent_in_first_appearance_order(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '{"image_id": 7, "x": 0, "y": 0, "width": 10, "height": 20}',
        "",
        '{"image_id": 3, "x": 1, "y": 2, "width": 3, "height": 4, "origin": "yolo", "score": 0.5}',
        '{"image_id": 7, "x": 5, "y": 6, "width": 7, "height": 8}',
    )

    provider = JsonlCropRectProvider.from_path(path, default_origin="manual", max_rows=500)

    assert isinstance(provider, CropRectProvider)
    assert provider.row_count == 3
    assert provider.line_errors == ()
    assert provider.parent_image_ids == (7, 3)
    first, second = provider.candidates_for(7)
    assert (first.line, first.rect, first.origin, first.score) == (
        1,
        CropRect(0, 0, 10, 20),
        "manual",
        None,
    )
    assert (second.line, second.rect) == (4, CropRect(5, 6, 7, 8))
    (only,) = provider.candidates_for(3)
    assert (only.line, only.origin, only.score) == (3, "yolo", 0.5)
    assert provider.candidates_for(999) == ()


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"image_id": 1, "x": 0', "invalid JSON"),
        ("[1, 2, 3]", "JSON object"),
        ('{"image_id": 1, "x": 0, "y": 0, "width": 10}', "height"),
        ('{"image_id": 1, "x": 0.5, "y": 0, "width": 10, "height": 10}', "x"),
        ('{"image_id": "1", "x": 0, "y": 0, "width": 10, "height": 10}', "image_id"),
        ('{"image_id": 0, "x": 0, "y": 0, "width": 10, "height": 10}', "image_id"),
        ('{"image_id": 1, "x": 0, "y": 0, "width": 10, "height": 10, "w": 1}', "w"),
        ('{"image_id": 1, "x": 0, "y": 0, "width": 10, "height": 10, "origin": ""}', "origin"),
    ],
)
def test_invalid_rows_become_line_errors_without_aborting(tmp_path: Path, line: str, expected: str) -> None:
    path = _write(tmp_path, '{"image_id": 1, "x": 0, "y": 0, "width": 4, "height": 4}', line)

    provider = JsonlCropRectProvider.from_path(path, default_origin="manual", max_rows=500)

    assert provider.row_count == 2
    assert provider.parent_image_ids == (1,)
    (error,) = provider.line_errors
    assert error.line == 2
    assert expected in error.message


def test_line_error_keeps_image_id_when_readable(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"image_id": 9, "x": -1, "y": 0, "width": "a", "height": 4}')

    provider = JsonlCropRectProvider.from_path(path, default_origin="manual", max_rows=500)

    (error,) = provider.line_errors
    assert error.image_id == 9


def test_rejects_more_rows_than_limit_before_parsing(tmp_path: Path) -> None:
    path = _write(tmp_path, *(["not json"] * 3))

    with pytest.raises(ResultSetTooLargeError) as raised:
        JsonlCropRectProvider.from_path(path, default_origin="manual", max_rows=2)

    assert (raised.value.matched, raised.value.limit) == (3, 2)
