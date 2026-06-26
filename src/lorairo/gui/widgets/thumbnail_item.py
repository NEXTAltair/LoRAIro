# src/lorairo/gui/widgets/thumbnail_item.py

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from .. import theme

if TYPE_CHECKING:
    from .thumbnail_selector_widget import ThumbnailSelectorWidget


class ThumbnailItem(QGraphicsObject):
    """
    サムネイル画像を表示するGraphicsアイテム。

    Qt Graphics Viewフレームワークを使用してサムネイル画像を描画し、
    マウスイベントによる選択状態の管理と視覚的フィードバックを提供する。

    Attributes:
        pixmap (QPixmap): 表示する画像データ
        image_path (Path): 画像ファイルのパス
        image_id (int): データベース内での画像ID
        parent_widget (ThumbnailSelectorWidget): 親ウィジェット
    """

    def __init__(self, pixmap: QPixmap, image_path: Path, image_id: int, parent: ThumbnailSelectorWidget):
        """
        ThumbnailItemを初期化する。

        Args:
            pixmap (QPixmap): 表示する画像データ（既にスケール済み）
            image_path (Path): 元画像ファイルのパス
            image_id (int): データベース内での一意な画像ID
            parent (ThumbnailSelectorWidget): 親となるサムネイルセレクターウィジェット
        """
        super().__init__()
        self.pixmap = pixmap
        self.image_path = image_path
        self.image_id = image_id
        self.parent_widget = parent
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._is_selected = False

    def isSelected(self) -> bool:
        """
        現在の選択状態をDatasetStateManagerから動的に取得する。

        Returns:
            bool: このアイテムが選択されている場合True
        """
        if self.parent_widget.dataset_state:
            return self.parent_widget.dataset_state.is_image_selected(self.image_id)
        return False

    def setSelected(self, selected: bool) -> None:
        """
        アイテムの選択状態を設定し、必要に応じて再描画をトリガーする。

        Args:
            selected (bool): 設定する選択状態
        """
        current_selected = self.isSelected()
        if current_selected != selected:
            self.update()  # 再描画をトリガー

    def boundingRect(self) -> QRectF:
        """
        このアイテムの境界矩形を返す（Qt Graphics View必須メソッド）。

        Returns:
            QRectF: pixmapのサイズに基づく境界矩形
        """
        return QRectF(self.pixmap.rect())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        rect = self.boundingRect()
        painter.drawPixmap(rect.toRect(), self.pixmap)
        self._paint_overlays(painter, rect)
        if self.isSelected():
            pen = QPen(QColor(theme.ACCENT), 3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _paint_overlays(self, painter: QPainter, rect: QRectF) -> None:
        """サムネ四隅に score / rating / 解像度 のバッジを描画する (DS Thumbnail)。

        右上=score / 右下=rating / 左下=解像度。メタデータが無い角は省略する。
        """
        if self.parent_widget.dataset_state is None:
            return
        metadata = self.parent_widget.dataset_state.get_image_by_id(self.image_id)
        if not metadata:
            return

        score_text, rating_text, resolution_text = self._overlay_texts(metadata)
        if score_text is not None:
            self._draw_badge(painter, rect, score_text, "top-right")
        if rating_text is not None:
            self._draw_badge(painter, rect, rating_text, "bottom-right")
        if resolution_text is not None:
            self._draw_badge(painter, rect, resolution_text, "bottom-left")

    @staticmethod
    def _overlay_texts(metadata: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        """メタデータから (score, rating, 解像度) のバッジ文字列を組み立てる。

        Args:
            metadata: DatasetStateManager の画像メタデータ辞書。

        Returns:
            (score_text, rating_text, resolution_text) のタプル。
            表示すべき値が無い項目は None。
        """
        score_value = metadata.get("score_value")
        score_text = (
            f"{float(score_value):.1f}" if isinstance(score_value, int | float) and score_value else None
        )

        rating_value = metadata.get("rating_value")
        rating_text = rating_value if isinstance(rating_value, str) and rating_value else None

        width = metadata.get("width")
        height = metadata.get("height")
        resolution_text = f"{width}×{height}" if width and height else None

        return score_text, rating_text, resolution_text

    @staticmethod
    def _draw_badge(painter: QPainter, rect: QRectF, text: str, corner: str) -> None:
        """指定コーナーに DS トークン配色のバッジ (ink 地 + paper 文字) を描画する。

        Args:
            painter: 描画先 QPainter。
            rect: サムネの境界矩形。
            text: バッジに表示する文字列。
            corner: "top-right" / "bottom-right" / "bottom-left" のいずれか。
        """
        painter.save()
        font = QFont(theme.FONT_MONO_FAMILIES[0])
        font.setPixelSize(theme.FONT_SIZE_SMALL)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        pad_x, pad_y, margin = 4, 1, 3
        badge_w = metrics.horizontalAdvance(text) + pad_x * 2
        badge_h = metrics.height() + pad_y * 2

        if corner == "top-right":
            x = rect.right() - badge_w - margin
            y = rect.top() + margin
        elif corner == "bottom-right":
            x = rect.right() - badge_w - margin
            y = rect.bottom() - badge_h - margin
        else:  # bottom-left
            x = rect.left() + margin
            y = rect.bottom() - badge_h - margin
        badge_rect = QRectF(x, y, badge_w, badge_h)

        ink = QColor(theme.INK)
        ink.setAlpha(205)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawRoundedRect(badge_rect, 3, 3)

        painter.setPen(QColor(theme.PAPER))
        painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), text)
        painter.restore()
