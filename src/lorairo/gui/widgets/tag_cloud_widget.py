"""キーワード連動の共起タグ探索ウィジェット（Map フレーム）。

任意のキーワード（部分一致）でマッチした画像群の共起タグを、力学配置の
ネットワーク図、またはフォントサイズ可変のタグクラウドで可視化する。
タグ（ノード）クリックで AND 絞り込み（ドリルダウン）し、関連タグを辿って
探索する。探索専用でステージング導線は持たない。

Map Tab.html (Claude Design) の見た目を PySide6 + QPainter で再現する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import (
    QObject,
    QPointF,
    QRect,
    QRectF,
    QSignalBlocker,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.tag_cloud_service import GraphResult, TagCloudService

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


def _mono_font(point_size: int = -1) -> QFont:
    """DS mono フォント (JetBrains Mono、tokens/typography.css --font-mono) を返す。

    汎用 "monospace" の代わりに DS 確定の mono family を使う (Issue #794)。

    Args:
        point_size: ポイントサイズ。0 以下なら既定サイズのまま。

    Returns:
        DS mono family を設定した QFont。
    """
    font = QFont(theme.FONT_MONO_FAMILIES[0])
    if point_size > 0:
        font.setPointSize(point_size)
    return font


# キーワード入力のデバウンス（ms）
_DEBOUNCE_MS = 250
# 力学シミュレーションの更新間隔（ms）
_SIM_INTERVAL_MS = 16
# alpha がこの値を下回ったらシミュレーションを停止（収束）
_SIM_SETTLE = 0.05

# 頻度カラーランプの両端（暖色グレー → アクセント）
_RAMP_LOW = (154, 148, 136)
_RAMP_HIGH = (194, 94, 63)


def _ramp_color(t: float) -> QColor:
    """頻度 weight (0..1) を暖色グレー→アクセントのランプ色へ変換する。"""
    e = math.pow(max(0.0, min(1.0, t)), 0.85)
    r = round(_RAMP_LOW[0] + (_RAMP_HIGH[0] - _RAMP_LOW[0]) * e)
    g = round(_RAMP_LOW[1] + (_RAMP_HIGH[1] - _RAMP_LOW[1]) * e)
    b = round(_RAMP_LOW[2] + (_RAMP_HIGH[2] - _RAMP_LOW[2]) * e)
    return QColor(r, g, b)


class FlowLayout(QLayout):
    """折り返し配置レイアウト（Qt 公式 FlowLayout 例の最小実装）。"""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class _TagCloudLabel(QLabel):
    """クリック可能なタグクラウド用ラベル（頻度でフォントサイズ可変）。"""

    clicked = Signal(str)

    def __init__(self, tag: str, count: int, weight: float, parent: QWidget | None = None) -> None:
        super().__init__(f"{tag}", parent)
        self._tag = tag
        font_px = 13 + round(34 * math.pow(weight, 0.8))
        font = _mono_font()
        font.setPixelSize(font_px)
        font.setWeight(QFont.Weight.DemiBold if weight > 0.55 else QFont.Weight.Normal)
        self.setFont(font)
        self.setStyleSheet(f"color:{_ramp_color(weight).name()};padding:1px 2px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{tag} · {count}枚 — クリックで絞り込み")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._tag)


class _DrillChip(QWidget):
    """ドリルダウン中タグのチップ（× で解除）。"""

    removed = Signal(str)

    def __init__(self, tag: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tag = tag
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)
        self.setStyleSheet(
            f"background:{theme.ACCENT_SOFT};border:{theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f"border-radius:{theme.RADIUS_CHIP}px;"
        )
        name = QLabel(tag)
        name.setFont(_mono_font(theme.FONT_SIZE_META))
        name.setStyleSheet(f"color:{theme.ACCENT_HOVER};border:none;background:transparent;")
        layout.addWidget(name)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setToolTip(f"{self._tag} を除外から外す")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{theme.ACCENT_HOVER};}}"
            f"QPushButton:hover{{color:{theme.ERR};}}"
        )
        close_btn.clicked.connect(lambda: self.removed.emit(self._tag))
        layout.addWidget(close_btn)


@dataclass
class _Particle:
    """力学シミュレーションの粒子（1ノードの物理状態）。"""

    x: float
    y: float
    vx: float
    vy: float
    r: float
    pinned: bool = False


class NetworkGraphView(QWidget):
    """共起タグの力学配置ネットワーク図（QPainter 描画）。

    Signals:
        node_clicked: ノード（タグ）クリック時にタグ名を通知。
    """

    node_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._result: GraphResult | None = None
        self._particles: list[_Particle] = []
        self._hover = -1
        self._alpha = 1.0
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._is_panning: bool = False
        self._pan_start_pos: QPointF | None = None
        self._pressed_node: int = -1
        self._press_pos: QPointF | None = None
        self._is_dragging_node: bool = False
        self._show_canvas_overlays: bool = False
        self._last_drawn_labels: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(_SIM_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_graph(self, result: GraphResult) -> None:
        """グラフ結果をセットして力学配置を初期化・再開する。"""
        self._result = result
        self._hover = -1
        self._pressed_node = -1
        self._press_pos = None
        self._is_dragging_node = False
        self._is_panning = False
        self._pan_start_pos = None
        self._init_particles()
        self._alpha = 1.0
        if self._particles:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def stop(self) -> None:
        """シミュレーションを停止する。"""
        self._timer.stop()

    def reset_view(self) -> None:
        """ズーム・パン状態とノードのピン留めを初期状態にリセットする。"""
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._is_panning = False
        self._pan_start_pos = None
        self._pressed_node = -1
        self._press_pos = None
        self._is_dragging_node = False
        for p in self._particles:
            p.pinned = False
        if self._particles:
            self._alpha = max(self._alpha, 0.3)
            if not self._timer.isActive():
                self._timer.start()
        self.update()

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """スクリーン座標をワールド座標に変換する。"""
        return ((sx - self._pan_x) / self._zoom, (sy - self._pan_y) / self._zoom)

    def _world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """ワールド座標をスクリーン座標に変換する。"""
        return (wx * self._zoom + self._pan_x, wy * self._zoom + self._pan_y)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _init_particles(self) -> None:
        if self._result is None:
            self._particles = []
            return
        nodes = self._result.nodes
        n = len(nodes)
        w = max(self.width(), 200)
        h = max(self.height(), 200)
        cx, cy = w / 2, h / 2
        self._particles = []
        for i, node in enumerate(nodes):
            r = 8 + 19 * math.sqrt(node.weight)
            ang = i / max(n, 1) * math.tau
            x = cx + math.cos(ang) * (120 + 30 * (i % 3))
            y = cy + math.sin(ang) * (90 + 25 * (i % 3))
            self._particles.append(_Particle(x=x, y=y, vx=0.0, vy=0.0, r=r, pinned=False))

    def _tick(self) -> None:
        self._step()
        self.update()
        if self._alpha <= _SIM_SETTLE:
            self._timer.stop()

    def _step(self) -> None:
        if self._result is None or not self._particles:
            return
        ps = self._particles
        edges = self._result.edges
        w = max(self.width(), 200)
        h = max(self.height(), 200)
        cx, cy = w / 2, h / 2
        n = len(ps)

        # 斥力（O(n^2)、n<=50 なので許容）
        for i in range(n):
            a = ps[i]
            for j in range(i + 1, n):
                b = ps[j]
                dx, dy = a.x - b.x, a.y - b.y
                d2 = dx * dx + dy * dy
                if d2 < 0.01:
                    d2 = 0.01
                    dx, dy = 0.1, 0.1
                d = math.sqrt(d2)
                min_d = a.r + b.r + 22
                rep = 3600 / d2
                if d < min_d:
                    rep += (min_d - d) * 1.1 / d
                fx, fy = dx / d * rep, dy / d * rep
                a.vx += fx
                a.vy += fy
                b.vx -= fx
                b.vy -= fy

        # バネ（共起が強いほど近く・強く引く）
        for e in edges:
            a, b = ps[e.a], ps[e.b]
            dx, dy = b.x - a.x, b.y - a.y
            d = math.sqrt(dx * dx + dy * dy) or 0.01
            target = 175 - 80 * e.norm
            k = 0.010 + 0.045 * e.norm
            f = (d - target) * k
            fx, fy = dx / d * f, dy / d * f
            a.vx += fx
            a.vy += fy
            b.vx -= fx
            b.vy -= fy

        # 中心への重力
        for a in ps:
            a.vx += (cx - a.x) * 0.0045
            a.vy += (cy - a.y) * 0.0045

        self._integrate_particles(w, h)
        self._alpha *= 0.992

    def _integrate_particles(self, w: int, h: int) -> None:
        damp = 0.86
        alpha = self._alpha
        max_sp = 18 * alpha + 2
        for a in self._particles:
            if a.pinned:
                a.vx = 0.0
                a.vy = 0.0
                continue
            a.vx *= damp
            a.vy *= damp
            sp = math.hypot(a.vx, a.vy)
            if sp > max_sp:
                a.vx *= max_sp / sp
                a.vy *= max_sp / sp
            a.x += a.vx * alpha
            a.y += a.vy * alpha
            a.x = max(a.r + 6, min(w - a.r - 6, a.x))
            a.y = max(a.r + 6, min(h - a.r - 6, a.y))

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _node_at(self, x: float, y: float) -> int:
        wx, wy = self._screen_to_world(x, y)
        for i in range(len(self._particles) - 1, -1, -1):
            p = self._particles[i]
            if math.hypot(wx - p.x, wy - p.y) <= p.r + 2:
                return i
        return -1

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def resizeEvent(self, _event: object) -> None:
        # 収束後にリサイズされたら軽く揺らして再配置
        if self._particles and self._alpha <= _SIM_SETTLE:
            self._alpha = 0.5
            self._timer.start()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        new_zoom = max(0.5, min(3.0, self._zoom * factor))
        pos = event.position()
        wx, wy = self._screen_to_world(pos.x(), pos.y())
        self._zoom = new_zoom
        self._pan_x = pos.x() - wx * self._zoom
        self._pan_y = pos.y() - wy * self._zoom
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, _event: QMouseEvent) -> None:
        self.reset_view()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._pressed_node >= 0 and self._press_pos is not None:
            if (pos - self._press_pos).manhattanLength() >= 4 or self._is_dragging_node:
                self._is_dragging_node = True
                p = self._particles[self._pressed_node]
                p.pinned = True
                wx, wy = self._screen_to_world(pos.x(), pos.y())
                p.x, p.y = wx, wy
                p.vx, p.vy = 0.0, 0.0
                self._alpha = max(self._alpha, 0.25)
                if not self._timer.isActive():
                    self._timer.start()
                self.update()
            return

        if self._is_panning and self._pan_start_pos is not None:
            self._pan_x += pos.x() - self._pan_start_pos.x()
            self._pan_y += pos.y() - self._pan_start_pos.y()
            self._pan_start_pos = pos
            self.update()
            return

        idx = self._node_at(pos.x(), pos.y())
        if idx != self._hover:
            self._hover = idx
            self.setCursor(Qt.CursorShape.PointingHandCursor if idx >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._node_at(pos.x(), pos.y())
            if idx >= 0:
                self._pressed_node = idx
                self._press_pos = pos
                self._is_dragging_node = False
            else:
                self._is_panning = True
                self._pan_start_pos = pos
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._pan_start_pos = pos

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._pressed_node >= 0:
                if (
                    not self._is_dragging_node
                    and self._result is not None
                    and 0 <= self._pressed_node < len(self._result.nodes)
                ):
                    self.node_clicked.emit(self._result.nodes[self._pressed_node].tag)
                self._pressed_node = -1
                self._press_pos = None
                self._is_dragging_node = False
            if self._is_panning:
                self._is_panning = False
                self._pan_start_pos = None
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self._pan_start_pos = None

    def _click_at(self, x: float, y: float) -> None:
        """指定座標にノードがあれば node_clicked を発火する。"""
        if self._result is None:
            return
        idx = self._node_at(x, y)
        if idx >= 0:
            self.node_clicked.emit(self._result.nodes[idx].tag)

    def leaveEvent(self, _event: object) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(theme.CARD))
        if self._result is None or not self._particles:
            self._last_drawn_labels = []
            painter.end()
            return
        painter.save()
        painter.translate(self._pan_x, self._pan_y)
        painter.scale(self._zoom, self._zoom)
        self._draw_edges(painter)
        self._draw_nodes(painter)
        self._draw_labels(painter)
        painter.restore()
        if self._show_canvas_overlays:
            self._draw_legend(painter, h)
            self._draw_hint(painter, w)
        if 0 <= self._hover < len(self._particles):
            self._draw_tooltip(painter)
        painter.end()

    def _draw_edges(self, painter: QPainter) -> None:
        assert self._result is not None
        ps = self._particles
        hov = self._hover
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for e in self._result.edges:
            a, b = ps[e.a], ps[e.b]
            lit = hov < 0 or hov == e.a or hov == e.b
            if hov >= 0 and not lit:
                pen = QPen(QColor(185, 180, 165, 20), max(0.6, 0.6 + e.norm * 2))
            elif hov >= 0:
                pen = QPen(QColor(194, 94, 63, 140), 1.2 + e.norm * 4)
            else:
                alpha = int((0.16 + e.norm * 0.42) * 255)
                pen = QPen(QColor(155, 148, 136, alpha), 0.6 + e.norm * 3.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y))

    def _draw_nodes(self, painter: QPainter) -> None:
        assert self._result is not None
        ps = self._particles
        hov = self._hover
        neighbors = self._result.adjacency[hov] if hov >= 0 else None
        for i, p in enumerate(ps):
            node = self._result.nodes[i]
            dim = hov >= 0 and hov != i and not (neighbors is not None and i in neighbors)
            color = _ramp_color(node.weight)
            painter.setOpacity(0.28 if dim else 1.0)
            painter.setBrush(QBrush(color))
            if hov == i:
                painter.setPen(QPen(QColor(38, 36, 31), 2.5))
            else:
                painter.setPen(QPen(QColor(255, 255, 255, 191), 1))
            painter.drawEllipse(QPointF(p.x, p.y), p.r, p.r)
        painter.setOpacity(1.0)

    def _label_draw_order(self) -> list[int]:
        """ラベル描画の優先順インデックス一覧を返す。

        優先順:
        1. ホバー中のノード
        2. ホバー中ノードの直接隣接ノード（または選択中タグノード）
        3. 残りのノード（weight 降順）
        """
        if self._result is None or not self._particles:
            return []
        n = len(self._particles)
        nodes = self._result.nodes
        hov = self._hover if 0 <= self._hover < n else -1
        neighbors = self._result.adjacency[hov] if hov >= 0 else set()
        excluded = set(self._result.excluded_tags)

        order: list[int] = []
        seen: set[int] = set()

        if hov >= 0:
            order.append(hov)
            seen.add(hov)

        second_tier = sorted(
            (i for i in range(n) if i not in seen and (i in neighbors or nodes[i].tag in excluded)),
            key=lambda i: nodes[i].weight,
            reverse=True,
        )
        for i in second_tier:
            order.append(i)
            seen.add(i)

        remaining = sorted(
            (i for i in range(n) if i not in seen),
            key=lambda i: nodes[i].weight,
            reverse=True,
        )
        order.extend(remaining)
        return order

    def _draw_labels(self, painter: QPainter) -> None:
        assert self._result is not None
        ps = self._particles
        hov = self._hover if 0 <= self._hover < len(ps) else -1
        neighbors = self._result.adjacency[hov] if hov >= 0 else None
        placed_rects: list[QRectF] = []
        drawn_labels: list[str] = []

        for i in self._label_draw_order():
            p = ps[i]
            node = self._result.nodes[i]
            dim = hov >= 0 and hov != i and not (neighbors is not None and i in neighbors)
            if dim:
                continue
            fs = round(10 + 9 * node.weight + (1.5 if hov == i else 0))
            font = _mono_font()
            font.setPixelSize(fs)
            if hov == i or node.weight > 0.55:
                font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            ly = p.y + p.r + fs * 0.85 + 3

            tight = painter.fontMetrics().boundingRect(node.tag)
            tw = max(tight.width(), 1)
            th = max(tight.height(), fs)
            label_rect = QRectF(p.x - tw / 2, ly - fs, tw, th)

            if i != hov and any(label_rect.intersects(r) for r in placed_rects):
                continue
            placed_rects.append(label_rect)
            drawn_labels.append(node.tag)

            rect = QRectF(p.x - 120, ly - fs, 240, fs * 1.6)
            # 白ハロー（縁取りを控えめにして密集時の白飛びを防ぐ）
            painter.setPen(QPen(QColor(255, 255, 255, 190), 2))
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(rect.translated(ox, oy), Qt.AlignmentFlag.AlignHCenter, node.tag)
            painter.setPen(
                QColor(38, 36, 31) if hov == i else QColor(58, 52, 46 if node.weight > 0.55 else 76)
            )
            painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter, node.tag)

        self._last_drawn_labels = drawn_labels

    def _draw_legend(self, painter: QPainter, h: int) -> None:
        x, y = 12, h - 64
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.drawRoundedRect(QRectF(x, y, 156, 52), 6, 6)
        font = _mono_font()
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor(theme.INK_FAINT))
        painter.drawText(QPointF(x + 10, y + 14), "出現頻度  低 → 高")
        # ランプ
        for i in range(5):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(_ramp_color(i / 4)))
            painter.drawRect(QRectF(x + 10 + i * 26, y + 20, 26, 9))
        painter.setPen(QColor(theme.INK_SOFT))
        painter.drawText(QPointF(x + 10, y + 46), "線の太さ = 共起の強さ")

    def _draw_hint(self, painter: QPainter, w: int) -> None:
        text = "ノードをクリックで絞り込み・ホバーで近傍を強調"
        font = _mono_font()
        font.setPixelSize(10)
        painter.setFont(font)
        tw = painter.fontMetrics().horizontalAdvance(text) + 22
        x = w - tw - 12
        painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.drawRoundedRect(QRectF(x, 12, tw, 22), 11, 11)
        painter.setPen(QColor(theme.INK_FAINT))
        painter.drawText(QRectF(x, 12, tw, 22), Qt.AlignmentFlag.AlignCenter, text)

    def _draw_tooltip(self, painter: QPainter) -> None:
        assert self._result is not None
        idx = self._hover
        p = self._particles[idx]
        node = self._result.nodes[idx]
        deg = len(self._result.adjacency[idx])
        title = node.tag
        line = f"出現 {node.count:,} 枚 · 共起 {deg} タグ"
        hint = "クリックで AND 絞り込みに追加"
        font = _mono_font()
        font.setPixelSize(11)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = max(fm.horizontalAdvance(title), fm.horizontalAdvance(line), fm.horizontalAdvance(hint))
        bw = tw + 18
        bh = 56
        sx, sy = self._world_to_screen(p.x, p.y)
        tx = max(4.0, min(sx + 14, self.width() - bw - 4))
        ty = max(4.0, min(sy + 14, self.height() - bh - 4))
        painter.setBrush(QBrush(QColor(38, 36, 31)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(tx, ty, bw, bh), 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QPointF(tx + 9, ty + 17), title)
        painter.setPen(QColor(217, 211, 196))
        painter.drawText(QPointF(tx + 9, ty + 34), line)
        painter.setPen(QColor(154, 149, 138))
        painter.drawText(QPointF(tx + 9, ty + 50), hint)


class _GraphWorker(QThread):
    """バックグラウンドで初回タグロード+グラフ集計を実行するスレッド。"""

    finished = Signal(object)  # GraphResult
    error = Signal(str)

    def __init__(
        self,
        service: TagCloudService,
        keyword: str,
        selected_tags: list[str],
        max_nodes: int = 34,
        min_edge_weight: int = 2,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._keyword = keyword
        self._selected_tags = selected_tags
        self._max_nodes = max_nodes
        self._min_edge_weight = min_edge_weight

    def run(self) -> None:
        try:
            result = self._service.build_graph(
                self._keyword,
                self._selected_tags,
                max_nodes=self._max_nodes,
                min_edge_weight=self._min_edge_weight,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class TagCloudWidget(QWidget):
    """マップタブのルートウィジェット（キーワード連動の共起タグ探索）。"""

    # スタックページ
    _PAGE_MESSAGE = 0
    _PAGE_NETWORK = 1
    _PAGE_CLOUD = 2

    def __init__(self, db_manager: ImageDatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db_manager
        self._service = TagCloudService(db_manager)
        self._keyword = ""
        self._selected_tags: list[str] = []
        self._view = "network"  # "network" | "cloud"
        self._result: GraphResult | None = None
        self._worker: _GraphWorker | None = None
        self._loaded_once = False
        self._pending_recompute = False

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._recompute)

        self._build_ui()
        self._show_placeholder()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 上部: キーワード入力 + 表示フィルタ + 表示トグル + リセット/再読込
        top = QHBoxLayout()
        top.setSpacing(6)
        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("キーワードを入力（部分一致）して関連タグを探索…")
        self._keyword_edit.setClearButtonEnabled(True)
        self._keyword_edit.textChanged.connect(self._on_keyword_changed)
        top.addWidget(self._keyword_edit, 1)

        self._max_nodes_combo = QComboBox()
        self._max_nodes_combo.setObjectName("tagCloudMaxNodesCombo")
        self._max_nodes_combo.setToolTip("表示する最大ノード数")
        for label, value in [("15件", 15), ("30件", 30), ("34件 (標準)", 34), ("50件", 50)]:
            self._max_nodes_combo.addItem(label, value)
        self._max_nodes_combo.setCurrentIndex(2)
        self._max_nodes_combo.currentIndexChanged.connect(self._on_graph_filter_changed)
        top.addWidget(self._max_nodes_combo)

        self._min_edge_spin = QSpinBox()
        self._min_edge_spin.setObjectName("tagCloudMinEdgeSpin")
        self._min_edge_spin.setRange(1, 20)
        self._min_edge_spin.setValue(2)
        self._min_edge_spin.setPrefix("共起≥")
        self._min_edge_spin.setSuffix("回")
        self._min_edge_spin.setToolTip("エッジを表示する最小共起回数")
        self._min_edge_spin.valueChanged.connect(self._on_graph_filter_changed)
        top.addWidget(self._min_edge_spin)

        self._network_btn = self._make_toggle_btn("ネットワーク", "network", checked=True)
        self._cloud_btn = self._make_toggle_btn("クラウド", "cloud", checked=False)
        top.addWidget(self._network_btn)
        top.addWidget(self._cloud_btn)

        self._reset_btn = QPushButton("リセット")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setToolTip("キーワードと絞り込みを解除")
        self._reset_btn.clicked.connect(self._on_reset)
        top.addWidget(self._reset_btn)

        self._reload_btn = QPushButton("↺ 再読込")
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.setToolTip("DB を読み直して再集計")
        self._reload_btn.clicked.connect(self._on_reload)
        top.addWidget(self._reload_btn)
        root.addLayout(top)

        # ドリルダウンチップ列
        self._chip_bar = QWidget()
        self._chip_layout = FlowLayout(self._chip_bar, spacing=4)
        root.addWidget(self._chip_bar)

        # ステータス
        self._status_label = QLabel("")
        self._status_label.setFont(_mono_font(theme.FONT_SIZE_META))
        self._status_label.setStyleSheet(f"color:{theme.INK_SOFT};")
        root.addWidget(self._status_label)

        # ステージ（メッセージ / ネットワーク / クラウド の3ページ）
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            f"background:{theme.CARD};border:{theme.BORDER_WIDTH}px solid {theme.LINE};border-radius:{theme.RADIUS}px;"
        )

        self._message_label = QLabel()
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(f"color:{theme.INK_FAINT};")
        self._message_label.setFont(_mono_font(theme.FONT_SIZE_SMALL))
        self._stack.addWidget(self._message_label)  # PAGE_MESSAGE

        self._network_view = NetworkGraphView()
        self._graph_view = self._network_view
        self._network_view.node_clicked.connect(self._on_tag_clicked)
        self._stack.addWidget(self._network_view)  # PAGE_NETWORK

        self._cloud_scroll = QScrollArea()
        self._cloud_scroll.setWidgetResizable(True)
        self._cloud_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._cloud_container = QWidget()
        self._cloud_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._cloud_layout = FlowLayout(self._cloud_container, spacing=14)
        self._cloud_scroll.setWidget(self._cloud_container)
        self._stack.addWidget(self._cloud_scroll)  # PAGE_CLOUD

        root.addWidget(self._stack, 1)

        # 下部フッター: 凡例・操作ヒント（グラフ領域を遮蔽しない）
        self._footer_bar = QWidget()
        self._footer_bar.setObjectName("tagCloudFooterBar")
        footer_layout = QHBoxLayout(self._footer_bar)
        footer_layout.setContentsMargins(4, 2, 4, 2)
        footer_layout.setSpacing(12)

        self._legend_label = QLabel("出現頻度: 低 → 高 · 線の太さ = 共起の強さ")
        self._legend_label.setFont(_mono_font(theme.FONT_SIZE_META))
        self._legend_label.setStyleSheet(f"color:{theme.INK_FAINT};")
        footer_layout.addWidget(self._legend_label)

        footer_layout.addStretch(1)

        self._hint_label = QLabel(
            "クリック: 絞り込み · ドラッグ: ノード固定/パン · ホイール: ズーム · ダブルクリック: 表示リセット"
        )
        self._hint_label.setFont(_mono_font(theme.FONT_SIZE_META))
        self._hint_label.setStyleSheet(f"color:{theme.INK_FAINT};")
        footer_layout.addWidget(self._hint_label)

        root.addWidget(self._footer_bar)

    def _make_toggle_btn(self, text: str, view: str, checked: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(_mono_font(theme.FONT_SIZE_META))
        btn.setStyleSheet(
            f"QPushButton{{background:{theme.PAPER_SHADE};color:{theme.INK_SOFT};"
            f"border:{theme.BORDER_WIDTH}px solid {theme.LINE_STRONG};border-radius:4px;padding:5px 12px;}}"
            f"QPushButton:checked{{background:{theme.CARD};color:{theme.INK};"
            f"border-color:{theme.ACCENT};font-weight:{theme.FONT_WEIGHT_BOLD};}}"
        )
        btn.clicked.connect(lambda: self._on_view_changed(view))
        return btn

    def _current_max_nodes(self) -> int:
        data = self._max_nodes_combo.currentData()
        return int(data) if isinstance(data, int) else 34

    def _current_min_edge_weight(self) -> int:
        return int(self._min_edge_spin.value())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_keyword_changed(self, text: str) -> None:
        self._keyword = text
        # キーワードを変えたらドリルダウンはリセット
        self._selected_tags = []
        self._debounce.start()

    def _on_graph_filter_changed(self, *_args: object) -> None:
        self._recompute()

    def _on_view_changed(self, view: str) -> None:
        self._view = view
        self._network_btn.setChecked(view == "network")
        self._cloud_btn.setChecked(view == "cloud")
        if self._result is not None and self._result.nodes:
            self._render_active_view()

    def _on_reset(self) -> None:
        with QSignalBlocker(self._max_nodes_combo):
            idx = self._max_nodes_combo.findData(34)
            if idx >= 0:
                self._max_nodes_combo.setCurrentIndex(idx)
        with QSignalBlocker(self._min_edge_spin):
            self._min_edge_spin.setValue(2)
        self._keyword_edit.clear()
        self._keyword = ""
        self._selected_tags = []
        self._result = None
        self._debounce.stop()
        self._network_view.stop()
        self._graph_view.reset_view()
        self._show_placeholder()

    def _on_reload(self) -> None:
        self._service.refresh()
        self._loaded_once = False
        self._recompute()

    def _on_tag_clicked(self, tag: str) -> None:
        if tag in self._selected_tags:
            return
        self._selected_tags.append(tag)
        self._recompute()

    def _on_chip_removed(self, tag: str) -> None:
        if tag in self._selected_tags:
            self._selected_tags.remove(tag)
            self._recompute()

    # ------------------------------------------------------------------
    # Recompute
    # ------------------------------------------------------------------

    def _recompute(self) -> None:
        if not self._keyword.strip():
            self._pending_recompute = False
            self._show_placeholder()
            return
        self._status_label.setText("集計中...")
        if not self._loaded_once:
            self._start_worker()
        else:
            result = self._service.build_graph(
                self._keyword,
                self._selected_tags,
                max_nodes=self._current_max_nodes(),
                min_edge_weight=self._current_min_edge_weight(),
            )
            self._apply_result(result)

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._pending_recompute = True
            return
        self._pending_recompute = False
        worker = _GraphWorker(
            self._service,
            self._keyword,
            list(self._selected_tags),
            max_nodes=self._current_max_nodes(),
            min_edge_weight=self._current_min_edge_weight(),
            parent=self,
        )
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        self._worker = worker
        worker.start()

    def _on_worker_finished(self, result: GraphResult) -> None:
        self._loaded_once = True
        if not self._keyword.strip():
            self._pending_recompute = False
            self._show_placeholder()
            return
        if self._pending_recompute:
            self._pending_recompute = False
            self._recompute()
            return
        self._apply_result(result)

    def _on_worker_error(self, msg: str) -> None:
        self._status_label.setText(f"エラー: {msg}")
        logger.error(f"TagGraph 計算エラー: {msg}")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _apply_result(self, result: GraphResult) -> None:
        self._result = result
        self._refresh_chips()
        if not result.nodes:
            self._network_view.stop()
            kw = f"「{self._keyword}」" if self._keyword else "（条件）"
            self._message_label.setText(
                f"該当する画像がありません\n{kw} を含むタグが見つかりませんでした。"
            )
            self._stack.setCurrentIndex(self._PAGE_MESSAGE)
            self._status_label.setText(f"該当 0枚 / 全 {result.total_images:,}枚")
            return
        filtered = "絞り込み中" if (self._keyword or self._selected_tags) else "全件"
        self._status_label.setText(
            f"該当 {result.matched_images:,}枚 / 全 {result.total_images:,}枚 · "
            f"{result.tag_count}タグ · 表示 {len(result.nodes)}ノード / "
            f"{len(result.edges)}共起 · {filtered}"
        )
        self._render_active_view()

    def _render_active_view(self) -> None:
        if self._result is None:
            return
        if self._view == "network":
            self._stack.setCurrentIndex(self._PAGE_NETWORK)
            self._network_view.set_graph(self._result)
        else:
            self._network_view.stop()
            self._render_cloud(self._result)
            self._stack.setCurrentIndex(self._PAGE_CLOUD)

    def _render_cloud(self, result: GraphResult) -> None:
        self._clear_layout(self._cloud_layout)
        for node in result.nodes:
            label = _TagCloudLabel(node.tag, node.count, node.weight)
            label.clicked.connect(self._on_tag_clicked)
            self._cloud_layout.addWidget(label)

    def _refresh_chips(self) -> None:
        self._clear_layout(self._chip_layout)
        lead = QLabel("ドリルダウン:")
        lead.setFont(_mono_font(theme.FONT_SIZE_META))
        lead.setStyleSheet(f"color:{theme.INK_FAINT};")
        self._chip_layout.addWidget(lead)
        if not self._selected_tags:
            hint = QLabel("なし — ノードをクリックして絞り込み")
            hint.setFont(_mono_font(theme.FONT_SIZE_META))
            hint.setStyleSheet(
                f"color:{theme.INK_FAINT};border:{theme.BORDER_WIDTH}px dashed {theme.LINE_STRONG};"
                f"border-radius:{theme.RADIUS_CHIP}px;padding:2px 8px;"
            )
            self._chip_layout.addWidget(hint)
            return
        for tag in self._selected_tags:
            chip = _DrillChip(tag)
            chip.removed.connect(self._on_chip_removed)
            self._chip_layout.addWidget(chip)

    def _show_placeholder(self) -> None:
        self._clear_layout(self._chip_layout)
        self._refresh_chips()
        self._message_label.setText("キーワードを入力すると、共起タグの関係がネットワーク図で表示されます")
        self._stack.setCurrentIndex(self._PAGE_MESSAGE)
        self._status_label.setText("")

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()
