"""クロップ作成 request の共有型 (`lorairo.domain.crop_request`) の単体テスト (#1343)。"""

from __future__ import annotations

import pytest

from lorairo.domain.crop_request import (
    DEFAULT_CROP_ORIGIN,
    CropCreateRequest,
    CropRect,
)


@pytest.mark.unit
class TestCropRectLongEdge:
    """`CropRect.long_edge` は幅・高さの大きい方を返す。"""

    def test_returns_width_when_landscape(self) -> None:
        assert CropRect(x=0, y=0, width=800, height=600).long_edge == 800

    def test_returns_height_when_portrait(self) -> None:
        assert CropRect(x=0, y=0, width=600, height=800).long_edge == 800

    def test_returns_edge_when_square(self) -> None:
        assert CropRect(x=0, y=0, width=512, height=512).long_edge == 512


@pytest.mark.unit
class TestCropRectHasPositiveSize:
    """`CropRect.has_positive_size` は幅・高さがともに 1px 以上かを返す。"""

    def test_true_for_positive_size(self) -> None:
        assert CropRect(x=0, y=0, width=1, height=1).has_positive_size() is True

    @pytest.mark.parametrize(
        ("width", "height"),
        [(0, 10), (10, 0), (0, 0), (-1, 10), (10, -1)],
    )
    def test_false_for_non_positive_size(self, width: int, height: int) -> None:
        assert CropRect(x=0, y=0, width=width, height=height).has_positive_size() is False


@pytest.mark.unit
class TestCropRectFitsWithin:
    """`CropRect.fits_within` は親画像の範囲内に収まるかを返す。"""

    def test_true_when_inside(self) -> None:
        assert CropRect(x=10, y=20, width=100, height=50).fits_within(1024, 768) is True

    def test_true_when_exactly_fills_image(self) -> None:
        assert CropRect(x=0, y=0, width=1024, height=768).fits_within(1024, 768) is True

    def test_false_when_right_edge_exceeds(self) -> None:
        assert CropRect(x=1000, y=0, width=100, height=50).fits_within(1024, 768) is False

    def test_false_when_bottom_edge_exceeds(self) -> None:
        assert CropRect(x=0, y=700, width=100, height=100).fits_within(1024, 768) is False

    @pytest.mark.parametrize(("x", "y"), [(-1, 0), (0, -1)])
    def test_false_for_negative_origin(self, x: int, y: int) -> None:
        assert CropRect(x=x, y=y, width=10, height=10).fits_within(1024, 768) is False

    def test_false_for_zero_size(self) -> None:
        assert CropRect(x=0, y=0, width=0, height=10).fits_within(1024, 768) is False


@pytest.mark.unit
class TestCropCreateRequestDefaults:
    """`CropCreateRequest` の既定値。"""

    def test_origin_defaults_to_manual(self) -> None:
        request = CropCreateRequest(parent_image_id=1, rect=CropRect(x=0, y=0, width=10, height=10))
        assert request.origin == "manual"
        assert request.origin == DEFAULT_CROP_ORIGIN

    def test_tags_and_rating_default_to_empty(self) -> None:
        request = CropCreateRequest(parent_image_id=1, rect=CropRect(x=0, y=0, width=10, height=10))
        assert request.tags == ()
        assert request.rating is None

    def test_origin_can_be_overridden_for_detector(self) -> None:
        request = CropCreateRequest(
            parent_image_id=1,
            rect=CropRect(x=0, y=0, width=10, height=10),
            origin="yolo-face",
        )
        assert request.origin == "yolo-face"
