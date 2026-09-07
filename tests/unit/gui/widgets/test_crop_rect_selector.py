"""CropRectSelectorWidget の単体テスト (#1345)。

scene 座標 = 元画像ピクセル座標という前提のもとで、ドラッグによる矩形作成・
8 ハンドルでのリサイズ・枠内ドラッグでの移動・画像範囲へのクランプを検証する。

ビューポート座標は整数のため scene へ戻す際に丸め誤差が出る。表示倍率が 1 を
超える構成 (画像 400x300 をビュー 800x600 に fit) にしたうえで、数 px の許容差で
比較する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt

from lorairo.domain.crop_request import CropRect
from lorairo.gui.widgets.crop_rect_selector import CropRectSelectorWidget

pytestmark = [pytest.mark.unit, pytest.mark.gui]

IMAGE_WIDTH = 400
IMAGE_HEIGHT = 300
# ビューポート座標の丸めに由来する許容差 (scene px)
TOLERANCE = 3


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    """検証用の 400x300 PNG を作る。"""
    path = tmp_path / "parent.png"
    Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), (90, 120, 160)).save(path)
    return path


@pytest.fixture
def selector(qtbot, image_path: Path) -> CropRectSelectorWidget:
    """画像を読み込み済みの選択ウィジェット (表示済み)。"""
    widget = CropRectSelectorWidget()
    qtbot.addWidget(widget)
    widget.resize(800, 600)
    widget.set_image(image_path)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _view_pos(widget: CropRectSelectorWidget, x: float, y: float) -> QPoint:
    """scene (= 画像ピクセル) 座標をビューポート座標へ変換する。"""
    return widget.mapFromScene(QPointF(x, y))


def _drag(
    qtbot,
    widget: CropRectSelectorWidget,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    """scene 座標を指定してドラッグ操作 (press → move → release) を行う。"""
    start_pos = _view_pos(widget, *start)
    end_pos = _view_pos(widget, *end)
    qtbot.mousePress(widget.viewport(), Qt.MouseButton.LeftButton, pos=start_pos)
    qtbot.mouseMove(widget.viewport(), pos=end_pos)
    qtbot.mouseRelease(widget.viewport(), Qt.MouseButton.LeftButton, pos=end_pos)


def _assert_close(actual: int, expected: int, label: str) -> None:
    """丸め誤差を許容して座標を比較する。"""
    assert abs(actual - expected) <= TOLERANCE, f"{label}: {actual} != {expected} (±{TOLERANCE})"


class TestInitialState:
    def test_image_size_reflects_pixmap(self, selector):
        assert selector.image_size() == (IMAGE_WIDTH, IMAGE_HEIGHT)

    def test_no_rect_initially(self, selector):
        assert selector.crop_rect() is None

    def test_missing_image_clears_state(self, qtbot, selector, tmp_path):
        selector.set_rect(CropRect(10, 10, 50, 50))
        selector.set_image(tmp_path / "does_not_exist.png")
        assert selector.image_size() is None
        assert selector.crop_rect() is None


class TestSetRect:
    def test_set_rect_clamps_to_image(self, selector):
        selector.set_rect(CropRect(-20, -10, 1000, 900))
        rect = selector.crop_rect()
        assert rect == CropRect(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT)

    def test_set_rect_none_clears(self, selector):
        selector.set_rect(CropRect(10, 10, 50, 50))
        selector.set_rect(None)
        assert selector.crop_rect() is None

    def test_set_rect_emits_rect_changed(self, qtbot, selector):
        with qtbot.waitSignal(selector.rect_changed, timeout=1000) as blocker:
            selector.set_rect(CropRect(10, 20, 30, 40))
        assert blocker.args[0] == CropRect(10, 20, 30, 40)

    def test_same_rect_does_not_reemit(self, qtbot, selector):
        selector.set_rect(CropRect(10, 20, 30, 40))
        received: list[object] = []
        selector.rect_changed.connect(received.append)
        selector.set_rect(CropRect(10, 20, 30, 40))
        assert received == []


class TestDragCreatesRect:
    def test_drag_creates_rect(self, qtbot, selector):
        _drag(qtbot, selector, (50, 40), (250, 220))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 50, "x")
        _assert_close(rect.y, 40, "y")
        _assert_close(rect.width, 200, "width")
        _assert_close(rect.height, 180, "height")

    def test_drag_emits_rect_changed(self, qtbot, selector):
        with qtbot.waitSignal(selector.rect_changed, timeout=1000):
            _drag(qtbot, selector, (60, 50), (200, 160))

    def test_reverse_drag_is_normalized(self, qtbot, selector):
        _drag(qtbot, selector, (250, 220), (50, 40))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 50, "x")
        _assert_close(rect.y, 40, "y")
        assert rect.width > 0
        assert rect.height > 0

    def test_click_without_drag_clears_selection(self, qtbot, selector):
        pos = _view_pos(selector, 300, 250)
        qtbot.mousePress(selector.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        qtbot.mouseRelease(selector.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        assert selector.crop_rect() is None


class TestHandleResize:
    def test_corner_handle_resizes(self, qtbot, selector):
        selector.set_rect(CropRect(50, 40, 200, 180))
        _drag(qtbot, selector, (250, 220), (300, 260))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 50, "x")
        _assert_close(rect.y, 40, "y")
        _assert_close(rect.width, 250, "width")
        _assert_close(rect.height, 220, "height")

    def test_left_edge_handle_resizes_only_x(self, qtbot, selector):
        selector.set_rect(CropRect(50, 40, 200, 180))
        _drag(qtbot, selector, (50, 130), (30, 130))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 30, "x")
        _assert_close(rect.width, 220, "width")
        _assert_close(rect.y, 40, "y")
        _assert_close(rect.height, 180, "height")

    def test_bottom_edge_handle_resizes_only_height(self, qtbot, selector):
        selector.set_rect(CropRect(50, 40, 200, 180))
        _drag(qtbot, selector, (150, 220), (150, 260))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 50, "x")
        _assert_close(rect.width, 200, "width")
        _assert_close(rect.y, 40, "y")
        _assert_close(rect.height, 220, "height")


class TestMove:
    def test_drag_inside_moves_rect(self, qtbot, selector):
        selector.set_rect(CropRect(50, 40, 200, 180))
        _drag(qtbot, selector, (150, 130), (170, 150))
        rect = selector.crop_rect()
        assert rect is not None
        _assert_close(rect.x, 70, "x")
        _assert_close(rect.y, 60, "y")
        assert rect.width == 200
        assert rect.height == 180

    def test_move_keeps_rect_inside_image(self, qtbot, selector):
        selector.set_rect(CropRect(150, 100, 200, 180))
        bottom_right = selector.viewport().rect().bottomRight()
        start_pos = _view_pos(selector, 250, 190)
        qtbot.mousePress(selector.viewport(), Qt.MouseButton.LeftButton, pos=start_pos)
        qtbot.mouseMove(selector.viewport(), pos=bottom_right)
        qtbot.mouseRelease(selector.viewport(), Qt.MouseButton.LeftButton, pos=bottom_right)
        rect = selector.crop_rect()
        assert rect is not None
        assert rect.width == 200
        assert rect.height == 180
        assert rect.fits_within(IMAGE_WIDTH, IMAGE_HEIGHT)


class TestClamping:
    def test_created_rect_never_exceeds_image(self, qtbot, selector):
        viewport_rect = selector.viewport().rect()
        qtbot.mousePress(selector.viewport(), Qt.MouseButton.LeftButton, pos=_view_pos(selector, 20, 20))
        qtbot.mouseMove(selector.viewport(), pos=viewport_rect.bottomRight())
        qtbot.mouseRelease(selector.viewport(), Qt.MouseButton.LeftButton, pos=viewport_rect.bottomRight())
        rect = selector.crop_rect()
        assert rect is not None
        assert rect.fits_within(IMAGE_WIDTH, IMAGE_HEIGHT)

    def test_resize_past_image_edge_is_clamped(self, qtbot, selector):
        selector.set_rect(CropRect(100, 80, 200, 180))
        viewport_rect = selector.viewport().rect()
        qtbot.mousePress(selector.viewport(), Qt.MouseButton.LeftButton, pos=_view_pos(selector, 300, 260))
        qtbot.mouseMove(selector.viewport(), pos=viewport_rect.bottomRight())
        qtbot.mouseRelease(selector.viewport(), Qt.MouseButton.LeftButton, pos=viewport_rect.bottomRight())
        rect = selector.crop_rect()
        assert rect is not None
        assert rect.fits_within(IMAGE_WIDTH, IMAGE_HEIGHT)
        _assert_close(rect.x + rect.width, IMAGE_WIDTH, "right")
        _assert_close(rect.y + rect.height, IMAGE_HEIGHT, "bottom")
