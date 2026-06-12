"""タグベースクラスタ散布図ウィジェット（Wireframes v11 · Map フレーム）。

左サイドバー: クラスタリスト・色分け・表示オプション
右メインエリア: 2D 散布図（QPainter）+ ラッソ選択
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.tag_cluster_service import (
    OUTLIER_CLUSTER_ID,
    ClusterInfo,
    ClusterResult,
    DotInfo,
    TagClusterService,
)

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager

_DOT_RADIUS = 5
_HOVER_RADIUS = 8
_LASSO_COLOR = QColor(theme.ACCENT)
_SELECTION_COLOR = QColor(theme.ACCENT)
_GRID_COLOR = QColor(0, 0, 0, 13)


class _PlotWorker(QThread):
    """バックグラウンドでクラスタ計算を実行するスレッド。"""

    finished = Signal(object)  # ClusterResult
    error = Signal(str)

    def __init__(self, service: TagClusterService, n_clusters: int) -> None:
        super().__init__()
        self._service = service
        self._n_clusters = n_clusters

    def run(self) -> None:
        try:
            result = self._service.build_cluster_result(self._n_clusters)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class _ScatterPlot(QWidget):
    """散布図描画 + ラッソ選択ウィジェット。"""

    selection_changed = Signal(list)  # list[int] image_ids

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._dots: list[DotInfo] = []
        self._clusters: dict[int, ClusterInfo] = {}
        self._color_by = "cluster"  # "cluster" | "tier"
        self._show_labels = True
        self._show_hulls = True

        self._lasso_points: list[QPointF] = []
        self._is_lassoing = False
        self._selected_ids: set[int] = set()
        self._hover_id: int | None = None

    def set_result(self, result: ClusterResult) -> None:
        """クラスタ結果をセットして再描画。"""
        self._dots = result.dots
        self._clusters = {c.id: c for c in result.clusters}
        self._selected_ids.clear()
        self._lasso_points.clear()
        self.update()

    def set_color_by(self, mode: str) -> None:
        self._color_by = mode
        self.update()

    def set_show_labels(self, show: bool) -> None:
        self._show_labels = show
        self.update()

    def set_show_hulls(self, show: bool) -> None:
        self._show_hulls = show
        self.update()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        self.selection_changed.emit([])
        self.update()

    def select_cluster(self, cluster_id: int) -> None:
        """クラスタ全選択。"""
        cl = self._clusters.get(cluster_id)
        if cl is None:
            return
        self._selected_ids = set(cl.image_ids)
        self.selection_changed.emit(list(self._selected_ids))
        self.update()

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_lassoing = True
            self._lasso_points = [QPointF(event.position())]
            self._selected_ids.clear()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._is_lassoing:
            self._lasso_points.append(QPointF(pos))
            self.update()
        else:
            # ホバー検出
            hit = self._hit_test(pos)
            if hit != self._hover_id:
                self._hover_id = hit
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_lassoing:
            self._is_lassoing = False
            if len(self._lasso_points) > 2:
                self._compute_lasso_selection()
            self._lasso_points.clear()
            self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor(theme.PAPER))
        self._draw_grid(painter, w, h)

        if not self._dots:
            self._draw_empty(painter, w, h)
            painter.end()
            return

        # 凸包（hull）
        if self._show_hulls:
            self._draw_hulls(painter, w, h)

        # クラスタラベル
        if self._show_labels:
            self._draw_labels(painter, w, h)

        # 点
        for dot in self._dots:
            self._draw_dot(painter, dot, w, h)

        # ラッソ
        if self._is_lassoing and len(self._lasso_points) > 1:
            pen = QPen(_LASSO_COLOR, 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(196, 74, 47, 25)))
            poly = QPolygonF(self._lasso_points)
            painter.drawPolygon(poly)

        painter.end()

    def resizeEvent(self, _event: QResizeEvent) -> None:
        self.update()

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_grid(self, painter: QPainter, w: int, h: int) -> None:
        pen = QPen(_GRID_COLOR, 1)
        painter.setPen(pen)
        step_x = w / 10
        step_y = h / 10
        for i in range(1, 10):
            x = int(i * step_x)
            painter.drawLine(x, 0, x, h)
        for i in range(1, 10):
            y = int(i * step_y)
            painter.drawLine(0, y, w, y)

    def _draw_empty(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QColor(theme.INK_FAINT))
        painter.setFont(QFont("monospace", 11))
        painter.drawText(
            QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "タグなし画像のみ\nクラスタ計算不可"
        )

    def _dot_pos(self, dot: DotInfo, w: int, h: int) -> QPointF:
        return QPointF(dot.x * w, dot.y * h)

    def _dot_color(self, dot: DotInfo) -> QColor:
        cl = self._clusters.get(dot.cluster_id)
        if cl is None:
            return QColor(theme.INK_FAINT)
        return QColor(cl.color)

    def _draw_dot(self, painter: QPainter, dot: DotInfo, w: int, h: int) -> None:
        pos = self._dot_pos(dot, w, h)
        color = self._dot_color(dot)
        r = _HOVER_RADIUS if dot.image_id == self._hover_id else _DOT_RADIUS
        selected = dot.image_id in self._selected_ids
        if selected:
            painter.setPen(QPen(_SELECTION_COLOR, 2))
            painter.setBrush(QBrush(color.lighter(130)))
        else:
            painter.setPen(QPen(color.darker(140), 1))
            painter.setBrush(QBrush(color))
        painter.drawEllipse(pos, r, r)

    def _draw_labels(self, painter: QPainter, w: int, h: int) -> None:
        font = QFont("monospace", 8)
        painter.setFont(font)
        for cl in self._clusters.values():
            if not cl.image_ids:
                continue
            # クラスタ重心
            xs = [d.x for d in self._dots if d.cluster_id == cl.id]
            ys = [d.y for d in self._dots if d.cluster_id == cl.id]
            if not xs:
                continue
            cx = sum(xs) / len(xs) * w
            cy = sum(ys) / len(ys) * h
            color = QColor(cl.color)
            painter.setPen(QPen(color.darker(160), 1))
            painter.drawText(QPointF(cx + 6, cy - 4), cl.label)

    def _draw_hulls(self, painter: QPainter, w: int, h: int) -> None:
        for cl in self._clusters.values():
            pts = [self._dot_pos(d, w, h) for d in self._dots if d.cluster_id == cl.id]
            if len(pts) < 3:
                continue
            hull_pts = self._convex_hull(pts)
            if len(hull_pts) < 3:
                continue
            color = QColor(cl.color)
            color.setAlpha(30)
            border = QColor(cl.color)
            border.setAlpha(80)
            painter.setPen(QPen(border, 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF(hull_pts))

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _hit_test(self, pos: QPointF) -> int | None:
        w, h = self.width(), self.height()
        best: int | None = None
        best_dist = _HOVER_RADIUS * _HOVER_RADIUS * 2.0
        for dot in self._dots:
            dp = self._dot_pos(dot, w, h)
            dist = (dp.x() - pos.x()) ** 2 + (dp.y() - pos.y()) ** 2
            if dist < best_dist:
                best_dist = dist
                best = dot.image_id
        return best

    def _compute_lasso_selection(self) -> None:
        w, h = self.width(), self.height()
        poly = QPolygonF(self._lasso_points)
        for dot in self._dots:
            dp = self._dot_pos(dot, w, h)
            if poly.containsPoint(dp, Qt.FillRule.OddEvenFill):
                self._selected_ids.add(dot.image_id)
        self.selection_changed.emit(list(self._selected_ids))

    @staticmethod
    def _convex_hull(points: list[QPointF]) -> list[QPointF]:
        """Graham scan による凸包。"""
        pts = [(p.x(), p.y()) for p in points]
        pts.sort()
        if len(pts) <= 2:
            return [QPointF(x, y) for x, y in pts]

        def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
            return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))

        lower: list[tuple[float, float]] = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper: list[tuple[float, float]] = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
        # 膨らます（余白）
        cx = sum(x for x, _ in hull) / len(hull)
        cy = sum(y for _, y in hull) / len(hull)
        expanded = []
        for x, y in hull:
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy) or 1
            expanded.append(QPointF(x + dx / dist * 12, y + dy / dist * 12))
        return expanded


class _SidebarClusterRow(QWidget):
    """サイドバーのクラスタ1行。"""

    clicked = Signal(int)  # cluster_id

    def __init__(self, cluster: ClusterInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cluster_id = cluster.id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        # カラードット
        dot_label = QLabel()
        dot_label.setFixedSize(10, 10)
        dot_label.setStyleSheet(
            f"background:{cluster.color};border-radius:5px;border:1px solid {QColor(cluster.color).darker(150).name()};"
        )
        layout.addWidget(dot_label)

        # ラベル
        text = f"{cluster.label} ({len(cluster.image_ids)})"
        name_label = QLabel(text)
        name_label.setFont(QFont("monospace", 9))
        name_label.setStyleSheet(f"color:{theme.INK};")
        name_label.setWordWrap(False)
        layout.addWidget(name_label, stretch=1)

        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"クリックでクラスタ {cluster.label} を全選択")

    def mousePressEvent(self, _event: QMouseEvent) -> None:
        self.clicked.emit(self._cluster_id)


class TagMapWidget(QWidget):
    """マップタブのルートウィジェット。

    Signals:
        images_staged: ステージングに追加する画像 ID リスト。
    """

    images_staged = Signal(list)  # list[int]

    def __init__(self, db_manager: ImageDatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db_manager
        self._service = TagClusterService(db_manager)
        self._worker: _PlotWorker | None = None
        self._result: ClusterResult | None = None
        self._n_clusters = 7

        self._build_ui()
        # 初回はタブアクティブ時に遅延ロード
        QTimer.singleShot(0, self._load_clusters)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 散布図はサイドバーのボタン接続より先に生成する
        self._plot = _ScatterPlot()

        # 左サイドバー
        sidebar = self._build_sidebar()
        root.addWidget(sidebar, 0)

        # 右: 散布図
        self._plot.selection_changed.connect(self._on_selection_changed)
        root.addWidget(self._plot, 1)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        panel.setStyleSheet(f"background:{theme.PAPER_SHADE};border-right:1px solid {theme.LINE};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ヘッダー
        title = QLabel("MAP · タグクラスタ")
        title.setFont(QFont("monospace", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{theme.INK};letter-spacing:1px;")
        layout.addWidget(title)

        # 状態ラベル
        self._status_label = QLabel("クラスタ計算中...")
        self._status_label.setFont(QFont("monospace", 9))
        self._status_label.setStyleSheet(f"color:{theme.INK_FAINT};")
        layout.addWidget(self._status_label)

        # クラスタリスト (スクロール可)
        cluster_section_label = QLabel("クラスタ")
        cluster_section_label.setFont(QFont("monospace", 8))
        cluster_section_label.setStyleSheet(
            f"color:{theme.INK_FAINT};text-transform:uppercase;letter-spacing:2px;margin-top:6px;"
        )
        layout.addWidget(cluster_section_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        self._cluster_list_widget = QWidget()
        self._cluster_list_layout = QVBoxLayout(self._cluster_list_widget)
        self._cluster_list_layout.setContentsMargins(0, 0, 0, 0)
        self._cluster_list_layout.setSpacing(1)
        self._cluster_list_layout.addStretch()
        scroll.setWidget(self._cluster_list_widget)
        scroll.setMinimumHeight(140)
        scroll.setMaximumHeight(260)
        layout.addWidget(scroll)

        # 選択情報
        sel_label = QLabel("選択")
        sel_label.setFont(QFont("monospace", 8))
        sel_label.setStyleSheet(
            f"color:{theme.INK_FAINT};text-transform:uppercase;letter-spacing:2px;margin-top:6px;"
        )
        layout.addWidget(sel_label)

        self._sel_count_label = QLabel("0 枚選択中")
        self._sel_count_label.setFont(QFont("monospace", 10))
        self._sel_count_label.setStyleSheet(f"color:{theme.INK};font-weight:bold;")
        layout.addWidget(self._sel_count_label)

        # 選択クリアボタン
        clear_btn = QPushButton("選択解除")
        clear_btn.setFont(QFont("monospace", 9))
        clear_btn.setStyleSheet(
            f"QPushButton{{background:{theme.PAPER_SHADE};border:1px solid {theme.LINE_STRONG};"
            f"border-radius:3px;padding:3px 8px;}}"
            f"QPushButton:hover{{background:{theme.LINE};}}"
        )
        clear_btn.clicked.connect(self._plot.clear_selection)
        layout.addWidget(clear_btn)

        # Stage ボタン
        self._stage_btn = QPushButton("▶ Annotate へ")
        self._stage_btn.setFont(QFont("monospace", 10, QFont.Weight.Bold))
        self._stage_btn.setEnabled(False)
        self._stage_btn.setStyleSheet(
            f"QPushButton{{background:{theme.ACCENT};color:white;border:none;"
            f"border-radius:3px;padding:5px 10px;}}"
            f"QPushButton:hover{{background:{theme.ACCENT_HOVER};}}"
            f"QPushButton:disabled{{background:{theme.LINE};color:{theme.INK_FAINT};}}"
        )
        self._stage_btn.clicked.connect(self._on_stage_clicked)
        layout.addWidget(self._stage_btn)

        # 再計算ボタン
        reload_btn = QPushButton("↺ 再計算")
        reload_btn.setFont(QFont("monospace", 9))
        reload_btn.setStyleSheet(
            f"QPushButton{{background:{theme.PAPER_SHADE};border:1px solid {theme.LINE_STRONG};"
            f"border-radius:3px;padding:3px 8px;}}"
            f"QPushButton:hover{{background:{theme.LINE};}}"
        )
        reload_btn.clicked.connect(self._load_clusters)
        layout.addWidget(reload_btn)

        layout.addStretch()
        return panel

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_clusters(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._status_label.setText("クラスタ計算中...")
        self._worker = _PlotWorker(self._service, self._n_clusters)
        self._worker.finished.connect(self._on_cluster_ready)
        self._worker.error.connect(self._on_cluster_error)
        self._worker.start()

    def _on_cluster_ready(self, result: ClusterResult) -> None:
        self._result = result
        self._plot.set_result(result)
        self._refresh_cluster_list(result)
        n_cl = len([c for c in result.clusters if c.id != OUTLIER_CLUSTER_ID])
        self._status_label.setText(
            f"{result.total_images}枚 · {result.tagged_images}枚タグあり · {n_cl}クラスタ"
        )
        logger.debug(f"Map: クラスタ結果受信 total={result.total_images}")

    def _on_cluster_error(self, msg: str) -> None:
        self._status_label.setText(f"エラー: {msg}")
        logger.error(f"Map クラスタ計算エラー: {msg}")

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------

    def _refresh_cluster_list(self, result: ClusterResult) -> None:
        # 既存ウィジェットを削除
        while self._cluster_list_layout.count() > 1:
            item = self._cluster_list_layout.takeAt(0)
            if item:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        for cl in result.clusters:
            row = _SidebarClusterRow(cl)
            row.clicked.connect(self._plot.select_cluster)
            self._cluster_list_layout.insertWidget(self._cluster_list_layout.count() - 1, row)

    def _on_selection_changed(self, image_ids: list[int]) -> None:
        n = len(image_ids)
        self._sel_count_label.setText(f"{n} 枚選択中")
        self._stage_btn.setEnabled(n > 0)
        self._stage_btn.setText(f"▶ {n}枚を Annotate へ" if n > 0 else "▶ Annotate へ")

    def _on_stage_clicked(self) -> None:
        if self._result is None:
            return
        # ScatterPlot の選択 ID をシグナルで通知
        plot = self._plot
        ids = list(plot._selected_ids)
        if ids:
            self.images_staged.emit(ids)
            logger.debug(f"Map: {len(ids)}枚をステージングへ送信")
