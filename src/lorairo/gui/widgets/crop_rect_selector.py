"""クロップ矩形選択ウィジェット (#1345)。

親画像の上でドラッグして切り出し矩形を作り、四隅・各辺の 8 ハンドルでサイズ調整、
枠内ドラッグで移動できる ``QGraphicsView`` ベースのウィジェット。

設計:
- scene 座標 = 元画像のピクセル座標にそろえる (``sceneRect`` = pixmap の矩形)。
  これにより矩形の保持・クランプ・:class:`CropRect` への変換がすべて実寸 px で完結し、
  表示倍率は ``fitInView`` による view 変換に任せられる。
- ズーム・パンは対象外 (#1345 の「対象外」)。スクロールバーは常時非表示。
- DB / サービスに依存しない。入力は画像パスのみ、出力は :class:`CropRect` の Signal。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from ...domain.crop_request import CropRect
from ...utils.log import logger
from .. import theme

# ドラッグ種別 (ハンドル名と衝突しない値にする)
_MODE_CREATE = "create"
_MODE_MOVE = "move"

# ハンドル名。文字 t/b/l/r の組み合わせで調整対象の辺を表す。
# 角を先に評価して、角と辺の当たり判定が重なる領域では角を優先する。
_HANDLE_ORDER: tuple[str, ...] = ("tl", "tr", "bl", "br", "t", "b", "l", "r")

# view 上での見かけのハンドル寸法 (px)。scene 座標へは表示倍率で換算する。
_HANDLE_DRAW_PX = 8.0
_HANDLE_HIT_PX = 14.0

# 選択枠の線幅 (cosmetic pen なので表示倍率によらず一定)
_SELECTION_PEN_WIDTH = 2


class CropRectSelectorWidget(QGraphicsView):
    """元画像上で切り出し矩形を選択するウィジェット。

    Signals:
        rect_changed (object): 選択矩形が変化した際に :class:`CropRect` または
            ``None`` (選択解除) を emit する。``Signal(object)`` なのは Qt の型
            登録なしに ``CropRect | None`` を運ぶため。

    Note:
        矩形の取得は :meth:`crop_rect` を使う。``QWidget.rect()`` (``QRect`` を返す)
        と衝突するため、公開名は ``rect`` ではなく ``crop_rect`` とした。
    """

    rect_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """ウィジェットを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        # ズーム・パンは対象外なのでスクロールバーとドラッグモードを無効化する
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(QColor(theme.PAPER_SHADE)))
        self.setMinimumSize(240, 180)

        self._pixmap: QPixmap | None = None
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._rect: CropRect | None = None
        self._drag_mode: str | None = None
        self._drag_anchor = QPointF()
        self._drag_start_rect: CropRect | None = None

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_image(self, path: Path) -> None:
        """表示する元画像を差し替える (選択矩形はクリアされる)。

        Args:
            path: 元画像のファイルパス。読み込めない場合は表示をクリアする。
        """
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            logger.warning(f"クロップ元画像の読み込みに失敗しました: {path}")
            self.clear_image()
            return
        self._scene.clear()
        self._pixmap = pixmap
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._set_rect_internal(None)
        self._fit()
        logger.debug(f"クロップ元画像を表示: {path.name} ({pixmap.width()}x{pixmap.height()})")

    def clear_image(self) -> None:
        """表示中の画像と選択矩形をクリアする。"""
        self._scene.clear()
        self._pixmap = None
        self._pixmap_item = None
        self._scene.setSceneRect(QRectF())
        self._set_rect_internal(None)

    def image_size(self) -> tuple[int, int] | None:
        """表示中の元画像の実寸を返す。

        Returns:
            ``(幅, 高さ)`` の px タプル。画像が未設定なら None。
        """
        if self._pixmap is None:
            return None
        return (self._pixmap.width(), self._pixmap.height())

    def source_pixmap(self) -> QPixmap | None:
        """表示中の元画像の QPixmap を返す (プレビュー切り出し用)。"""
        return self._pixmap

    def crop_rect(self) -> CropRect | None:
        """現在の選択矩形 (元画像ピクセル座標) を返す。未選択なら None。"""
        return self._rect

    def set_rect(self, rect: CropRect | None) -> None:
        """選択矩形をプログラムから設定する (画像範囲へクランプする)。

        Args:
            rect: 設定する矩形。None で選択解除。
        """
        if rect is None:
            self._set_rect_internal(None)
            return
        size = self.image_size()
        if size is not None:
            rect = self._clamp_rect(rect, size[0], size[1])
        self._set_rect_internal(rect)

    # ------------------------------------------------------------------
    # Qt イベント
    # ------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズに追従して画像全体を表示し続ける。"""
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event: QShowEvent) -> None:
        """表示時にビューポート実寸で再フィットする。"""
        super().showEvent(event)
        self._fit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左ボタン押下でハンドル調整 / 移動 / 新規作成のいずれかを開始する。"""
        if event.button() != Qt.MouseButton.LeftButton or self._pixmap is None:
            super().mousePressEvent(event)
            return
        point = self._clamped_scene_point(event.position())
        self._drag_start_rect = self._rect
        self._drag_anchor = point
        handle = self._hit_handle(point)
        if handle is not None:
            self._drag_mode = handle
        elif self._rect is not None and self._contains(self._rect, point):
            self._drag_mode = _MODE_MOVE
        else:
            self._drag_mode = _MODE_CREATE
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """ドラッグ中の矩形を更新する。"""
        if self._drag_mode is None:
            super().mouseMoveEvent(event)
            return
        point = self._clamped_scene_point(event.position())
        if self._drag_mode == _MODE_CREATE:
            self._set_rect_internal(self._rect_from_points(self._drag_anchor, point))
        elif self._drag_mode == _MODE_MOVE:
            self._set_rect_internal(self._moved_rect(point))
        else:
            self._set_rect_internal(self._resized_rect(self._drag_mode, point))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """ドラッグを終了する。潰れた矩形は選択解除として扱う。"""
        if self._drag_mode is None:
            super().mouseReleaseEvent(event)
            return
        self._drag_mode = None
        self._drag_start_rect = None
        if self._rect is not None and not self._rect.has_positive_size():
            self._set_rect_internal(None)
        event.accept()

    def drawForeground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        """選択矩形と 8 ハンドルを scene 座標で描画する。"""
        super().drawForeground(painter, rect)
        crop = self._rect
        if crop is None:
            return
        painter.save()
        pen = QPen(QColor(theme.ACCENT))
        pen.setCosmetic(True)  # 表示倍率によらず一定の線幅にする
        pen.setWidth(_SELECTION_PEN_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(crop.x, crop.y, crop.width, crop.height))

        handle_size = self._scene_length(_HANDLE_DRAW_PX)
        painter.setBrush(QBrush(QColor(theme.ACCENT)))
        half = handle_size / 2.0
        for center in self._handle_centers(crop).values():
            painter.drawRect(QRectF(center.x() - half, center.y() - half, handle_size, handle_size))
        painter.restore()

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _fit(self) -> None:
        """画像全体がビューポートに収まるようにフィットさせる。"""
        if self._pixmap_item is None:
            return
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _set_rect_internal(self, rect: CropRect | None) -> None:
        """矩形を差し替え、変化があれば再描画と Signal 発行を行う。"""
        if rect == self._rect:
            return
        self._rect = rect
        self.viewport().update()
        self.rect_changed.emit(rect)

    def _scene_length(self, view_px: float) -> float:
        """view 上の px 長を現在の表示倍率で scene 座標の長さへ換算する。"""
        scale = self.transform().m11()
        if scale <= 0.0:
            return view_px
        return view_px / scale

    def _clamped_scene_point(self, position: QPointF) -> QPointF:
        """ビューポート座標を画像範囲内の scene 座標へ変換する。"""
        scene_point = self.mapToScene(position.toPoint())
        size = self.image_size()
        if size is None:
            return scene_point
        width, height = size
        x = min(max(scene_point.x(), 0.0), float(width))
        y = min(max(scene_point.y(), 0.0), float(height))
        return QPointF(x, y)

    @staticmethod
    def _rect_from_points(first: QPointF, second: QPointF) -> CropRect:
        """2 点から正規化した (左上/幅高さが非負の) 矩形を作る。"""
        left = round(min(first.x(), second.x()))
        top = round(min(first.y(), second.y()))
        right = round(max(first.x(), second.x()))
        bottom = round(max(first.y(), second.y()))
        return CropRect(x=left, y=top, width=right - left, height=bottom - top)

    @staticmethod
    def _clamp_rect(rect: CropRect, image_width: int, image_height: int) -> CropRect:
        """矩形を画像範囲内へクランプする。"""
        x = min(max(rect.x, 0), image_width)
        y = min(max(rect.y, 0), image_height)
        width = min(max(rect.width, 0), image_width - x)
        height = min(max(rect.height, 0), image_height - y)
        return CropRect(x=x, y=y, width=width, height=height)

    @staticmethod
    def _contains(rect: CropRect, point: QPointF) -> bool:
        """点が矩形の内側 (枠上を含む) かを判定する。"""
        return rect.x <= point.x() <= rect.x + rect.width and rect.y <= point.y() <= rect.y + rect.height

    @staticmethod
    def _handle_centers(rect: CropRect) -> dict[str, QPointF]:
        """8 ハンドルの中心 (scene 座標) を角優先の順で返す。"""
        left = float(rect.x)
        top = float(rect.y)
        right = float(rect.x + rect.width)
        bottom = float(rect.y + rect.height)
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0
        positions = {
            "tl": QPointF(left, top),
            "tr": QPointF(right, top),
            "bl": QPointF(left, bottom),
            "br": QPointF(right, bottom),
            "t": QPointF(center_x, top),
            "b": QPointF(center_x, bottom),
            "l": QPointF(left, center_y),
            "r": QPointF(right, center_y),
        }
        return {name: positions[name] for name in _HANDLE_ORDER}

    def _hit_handle(self, point: QPointF) -> str | None:
        """点がどのハンドルを掴んだかを返す。掴んでいなければ None。"""
        if self._rect is None:
            return None
        tolerance = self._scene_length(_HANDLE_HIT_PX) / 2.0
        for name, center in self._handle_centers(self._rect).items():
            if abs(point.x() - center.x()) <= tolerance and abs(point.y() - center.y()) <= tolerance:
                return name
        return None

    def _moved_rect(self, point: QPointF) -> CropRect | None:
        """枠内ドラッグ中の矩形を、サイズを保ったまま平行移動する。"""
        start = self._drag_start_rect
        if start is None:
            return self._rect
        size = self.image_size()
        if size is None:
            return start
        image_width, image_height = size
        dx = round(point.x() - self._drag_anchor.x())
        dy = round(point.y() - self._drag_anchor.y())
        max_x = max(image_width - start.width, 0)
        max_y = max(image_height - start.height, 0)
        return CropRect(
            x=min(max(start.x + dx, 0), max_x),
            y=min(max(start.y + dy, 0), max_y),
            width=start.width,
            height=start.height,
        )

    def _resized_rect(self, handle: str, point: QPointF) -> CropRect | None:
        """ハンドルドラッグ中の矩形を、掴んだ辺だけ追従させて作り直す。"""
        start = self._drag_start_rect
        if start is None:
            return self._rect
        left = float(start.x)
        top = float(start.y)
        right = float(start.x + start.width)
        bottom = float(start.y + start.height)
        # ハンドル名に含まれる文字が、動かす辺を表す (例: "tl" は上辺と左辺)
        if "l" in handle:
            left = point.x()
        if "r" in handle:
            right = point.x()
        if "t" in handle:
            top = point.y()
        if "b" in handle:
            bottom = point.y()
        return self._rect_from_points(QPointF(left, top), QPointF(right, bottom))
