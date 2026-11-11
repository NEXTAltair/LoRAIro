"""2 枚の画像を左右に並べ、現在のタグ / キャプションの差分を見る比較画面 (Issue #1399 / #1484 / #1494)。

読み取り専用。比較してもタグや採用状態は変えない。

- 差分計算と左右の選択状態は Qt 非依存の ``services/image_comparison.py`` が持ち、
  この画面は結果の表示と操作の受け付けだけを行う。
- 左右のプレビューは ``ComparisonImageViewport`` で表示し、同期オン時は片側のズーム倍率と
  画像内の相対中心座標 ``(rx, ry)`` (``[0.0, 1.0] x [0.0, 1.0]``) を反対側へ反映する (#1494)。
- 左右の注釈とプレビューは ``ImageComparisonWorker`` が 1 回の要求ごとにまとめて読む。
  要求ごとに世代番号を進め、古い世代の結果や、表示対象と画像 ID が合わない結果は捨てる。
  読み込み中は左右の表示を空にし、古い画像と新しい注釈が並ぶ瞬間を作らない。
- 画面を閉じる・アプリを終える・データセットが切り替わるときは世代を進めて worker を止める。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QContextMenuEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...database.db_core import resolve_stored_path
from ...services.image_comparison import (
    Availability,
    CaptionDiff,
    ComparisonSelection,
    DiffKind,
    GenerationMetadataDiff,
    ImageComparisonService,
    ImageMetadataSource,
    Side,
    TagDiff,
)
from ...utils.log import logger
from .. import theme
from ..workers.image_comparison_worker import (
    ImageComparisonLoadResult,
    ImageComparisonWorker,
    LoadedComparisonSide,
)
from ..workers.manager import WorkerManager
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager

_SIDE_LABELS = {Side.LEFT: "左", Side.RIGHT: "右"}
_WORKER_PREFIX = "image_comparison_"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _missing_message(availability: Availability, subject: str) -> str:
    """片側 (または両側) に情報が無いときの説明文。"""
    if availability is Availability.LEFT_MISSING:
        return f"左の画像に{subject}が無いため比較できません"
    if availability is Availability.RIGHT_MISSING:
        return f"右の画像に{subject}が無いため比較できません"
    return f"左右どちらの画像にも{subject}がありません"


def _caption_side_html(diff: CaptionDiff, side: Side) -> str:
    """キャプション差分の片側を HTML にする (原文を整形せずに表示する)。"""
    highlight = theme.ERR_SOFT if side is Side.LEFT else theme.OK_SOFT
    parts: list[str] = []
    for segment in diff.segments:
        text = segment.left if side is Side.LEFT else segment.right
        if not text:
            continue
        escaped = html.escape(text)
        if segment.kind is DiffKind.EQUAL:
            parts.append(escaped)
        else:
            parts.append(f'<span style="background-color:{highlight};">{escaped}</span>')
    return f'<div style="white-space: pre-wrap;">{"".join(parts)}</div>'


def _placeholder_html(text: str) -> str:
    return f'<div style="color:{theme.INK_MUTED}; font-style: italic;">{html.escape(text)}</div>'


def _plain_html(text: str) -> str:
    return f'<div style="white-space: pre-wrap;">{html.escape(text)}</div>'


class ComparisonImageViewport(QGraphicsView):
    """比較画面の片側プレビュービューポート (ズーム / パン対応、Issue #1494)。

    ``zoom_factor == 1.0`` をビュー全体へのフィット基準とし、表示中心を画像サイズに対する
    相対座標 ``(rx, ry)`` (``[0.0, 1.0] x [0.0, 1.0]``) で保持する。解像度が異なる 2 枚の
    画像を比較するときも、同じ相対位置 ``(rx, ry)`` と同じ倍率 ``zoom_factor`` で揃えられる。

    Signals:
        view_changed (float, float, float): ``(zoom_factor, rx, ry)`` が変化したときに発火する。
    """

    view_changed = Signal(float, float, float)

    ZOOM_STEP = 1.25
    MIN_ZOOM = 0.25
    MAX_ZOOM = 16.0

    def __init__(self, parent: QWidget | None = None) -> None:
        """ビューポートを初期化する。"""
        super().__init__(parent)
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.pixmap_item: QGraphicsPixmapItem | None = None
        self._current_image_path: Path | None = None
        self._current_pixmap: QPixmap | None = None

        self._zoom_factor: float = 1.0
        self._relative_center: tuple[float, float] = (0.5, 0.5)
        self._updating_transform: bool = False
        self._drag_last_pos: QPointF | None = None

    # -- 画像の設定・クリア ------------------------------------------------

    def show_decoded_image(self, image: QImage | None, image_path: Path | None = None) -> None:
        """デコード済みの QImage を表示し、表示倍率と中心を初期状態に戻す。"""
        self.clear_preview()
        if image is None or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self.pixmap_item = self.graphics_scene.addPixmap(pixmap)
        self._current_image_path = image_path
        self._current_pixmap = pixmap
        self._zoom_factor = 1.0
        self._relative_center = (0.5, 0.5)
        self._apply_view_transform()

    def clear_preview(self) -> None:
        """プレビューを空にする。"""
        self._updating_transform = True
        try:
            self.graphics_scene.clear()
            self.resetTransform()
        finally:
            self._updating_transform = False
        self.pixmap_item = None
        self._current_image_path = None
        self._current_pixmap = None
        self._drag_last_pos = None
        self._zoom_factor = 1.0
        self._relative_center = (0.5, 0.5)

    # -- ズーム / 相対中心 API --------------------------------------------

    @property
    def zoom_factor(self) -> float:
        """フィット基準に対する現在のズーム倍率 (1.0 が全体表示)。"""
        return self._zoom_factor

    def set_zoom_factor(self, factor: float, *, emit_signal: bool = True) -> None:
        """ズーム倍率を設定する。"""
        clamped = _clamp(factor, self.MIN_ZOOM, self.MAX_ZOOM)
        self._zoom_factor = clamped
        self._apply_view_transform()
        if emit_signal:
            rx, ry = self._relative_center
            self.view_changed.emit(self._zoom_factor, rx, ry)

    def zoom_in(self) -> None:
        """1 段階ズームインする。"""
        self.set_zoom_factor(self._zoom_factor * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        """1 段階ズームアウトする。"""
        self.set_zoom_factor(self._zoom_factor / self.ZOOM_STEP)

    def get_relative_center(self) -> tuple[float, float]:
        """表示中心の相対座標 ``(rx, ry)`` (各軸 ``0.0``〜``1.0``) を返す。"""
        return self._relative_center

    @property
    def relative_center(self) -> tuple[float, float]:
        """表示中心の相対座標 ``(rx, ry)``。"""
        return self._relative_center

    def set_relative_center(self, rx: float, ry: float, *, emit_signal: bool = True) -> None:
        """表示中心の相対座標 ``(rx, ry)`` を設定する。"""
        self._relative_center = (_clamp01(rx), _clamp01(ry))
        self._apply_view_transform()
        if emit_signal:
            self.view_changed.emit(self._zoom_factor, self._relative_center[0], self._relative_center[1])

    def pan_by_relative(self, drx: float, dry: float) -> None:
        """相対座標差分 ``(drx, dry)`` だけパンする。"""
        rx, ry = self._relative_center
        self.set_relative_center(rx + drx, ry + dry)

    def reset_view(self, *, emit_signal: bool = True) -> None:
        """倍率 1.0・中心 (0.5, 0.5) の全体表示に戻す。"""
        self._zoom_factor = 1.0
        self._relative_center = (0.5, 0.5)
        self._apply_view_transform()
        if emit_signal:
            self.view_changed.emit(1.0, 0.5, 0.5)

    def get_scene_center(self) -> QPointF:
        """現在の画像のピクセル座標系での表示中心を返す。"""
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return QPointF(0.0, 0.0)
        rx, ry = self._relative_center
        return QPointF(rx * self._current_pixmap.width(), ry * self._current_pixmap.height())

    # -- 内部変換・イベント ------------------------------------------------

    def _apply_view_transform(self) -> None:
        if self.pixmap_item is None or self._current_pixmap is None or self._current_pixmap.isNull():
            return
        w = float(self._current_pixmap.width())
        h = float(self._current_pixmap.height())
        if w <= 0.0 or h <= 0.0:
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        base_scale = min(vw / w, vh / h)
        scale = base_scale * self._zoom_factor
        rx, ry = self._relative_center

        self._updating_transform = True
        try:
            # 端の領域へパンしてもスクロールバー上限で中心が押し戻されないよう余白を設ける
            self.graphics_scene.setSceneRect(QRectF(-w * 2.0, -h * 2.0, w * 5.0, h * 5.0))
            self.resetTransform()
            self.scale(scale, scale)
            self.centerOn(rx * w, ry * h)
        finally:
            self._updating_transform = False

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """ユーザーによるスクロール操作時に相対中心を更新・クランプ反映する。"""
        super().scrollContentsBy(dx, dy)
        if self._updating_transform or self._current_pixmap is None or self._current_pixmap.isNull():
            return
        w = float(self._current_pixmap.width())
        h = float(self._current_pixmap.height())
        if w <= 0.0 or h <= 0.0:
            return
        center = self.mapToScene(self.viewport().rect().center())
        raw_rx = center.x() / w
        raw_ry = center.y() / h
        clamped_rx = _clamp01(raw_rx)
        clamped_ry = _clamp01(raw_ry)
        self._relative_center = (clamped_rx, clamped_ry)
        if abs(raw_rx - clamped_rx) > 1e-6 or abs(raw_ry - clamped_ry) > 1e-6:
            self._updating_transform = True
            try:
                self.centerOn(clamped_rx * w, clamped_ry * h)
            finally:
                self._updating_transform = False
        self.view_changed.emit(self._zoom_factor, clamped_rx, clamped_ry)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """マウスホイールでズームする。"""
        delta_y = event.angleDelta().y()
        if delta_y > 0:
            self.zoom_in()
            event.accept()
            return
        if delta_y < 0:
            self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左ドラッグ開始でパン操作を始める。"""
        if event.button() == Qt.MouseButton.LeftButton and self._has_current_image():
            self._drag_last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """左ドラッグ中に相対中心を更新する。"""
        if (
            self._drag_last_pos is not None
            and self._current_pixmap is not None
            and not self._current_pixmap.isNull()
        ):
            w = float(self._current_pixmap.width())
            h = float(self._current_pixmap.height())
            if w > 0.0 and h > 0.0:
                prev_scene = self.mapToScene(self._drag_last_pos.toPoint())
                curr_scene = self.mapToScene(event.position().toPoint())
                delta_scene = prev_scene - curr_scene
                self._drag_last_pos = event.position()
                rx, ry = self._relative_center
                self.set_relative_center(rx + delta_scene.x() / w, ry + delta_scene.y() / h)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """左ドラッグ終了でカーソルを戻す。"""
        if event.button() == Qt.MouseButton.LeftButton and self._drag_last_pos is not None:
            self._drag_last_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズ時も現在のズーム倍率と相対中心を維持する。"""
        super().resizeEvent(event)
        self._apply_view_transform()

    def showEvent(self, event: QShowEvent) -> None:
        """表示時に現在のズーム倍率と相対中心を反映する。"""
        super().showEvent(event)
        self._apply_view_transform()

    # -- クリップボードへの画像コピー (読み取り専用) ----------------------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """右クリックで画像コピーメニューを表示する。"""
        menu = QMenu(self)
        copy_action = QAction("画像をコピー", menu)
        copy_action.setEnabled(self._has_current_image())
        copy_action.triggered.connect(self.copy_current_image_to_clipboard)
        menu.addAction(copy_action)
        menu.exec(event.globalPos())

    def _has_current_image(self) -> bool:
        return self._current_pixmap is not None and not self._current_pixmap.isNull()

    def copy_current_image_to_clipboard(self) -> bool:
        """現在表示中の画像をクリップボードへコピーする。"""
        if not self._has_current_image():
            return False
        pixmap: QPixmap | None = None
        if self._current_image_path is not None and self._current_image_path.exists():
            loaded = QPixmap(str(self._current_image_path))
            if not loaded.isNull():
                pixmap = loaded
        if pixmap is None:
            pixmap = self._current_pixmap
        if pixmap is None or pixmap.isNull():
            return False
        QApplication.clipboard().setPixmap(pixmap)
        return True


class _ComparisonSidePanel(QWidget):
    """片側の画像・出所・タグを表示するパネル。"""

    def __init__(self, side: Side, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.side = side
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.preview = ComparisonImageViewport(self)
        self.preview.setObjectName(f"{side.value}ComparisonPreview")
        layout.addWidget(self.preview, 1)

        self.provenance_label = QLabel(self)
        self.provenance_label.setObjectName(f"{side.value}ProvenanceLabel")
        self.provenance_label.setWordWrap(True)
        self.provenance_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.provenance_label)

        self.tags_view = QPlainTextEdit(self)
        self.tags_view.setObjectName(f"{side.value}TagsView")
        self.tags_view.setReadOnly(True)
        self.tags_view.setMaximumHeight(90)
        layout.addWidget(self.tags_view)

    @property
    def viewport(self) -> ComparisonImageViewport:
        """片側の画像ビューポート。"""
        return self.preview

    def show_loading(self) -> None:
        """読み込み中の表示にする (古い画像と注釈を残さない)。"""
        self.preview.clear_preview()
        self.provenance_label.setText("読み込み中…")
        self.tags_view.setPlainText("")

    def show_side(self, loaded: LoadedComparisonSide) -> None:
        """読み込んだ片側を表示する。"""
        snapshot = loaded.snapshot
        image_path = resolve_stored_path(snapshot.stored_image_path) if snapshot.stored_image_path else None
        self.preview.show_decoded_image(loaded.preview, image_path)
        lines = snapshot.provenance_lines()
        if snapshot.found and loaded.preview is None:
            lines.append("プレビューを読み込めませんでした")
        self.provenance_label.setText("\n".join(lines))
        if snapshot.tags:
            self.tags_view.setPlainText(", ".join(snapshot.tag_names))
            tooltip_lines = [f"{t.tag}: {', '.join(t.origins)}" for t in snapshot.tags[:200]]
            self.tags_view.setToolTip("\n".join(tooltip_lines))
        else:
            self.tags_view.setPlainText("(タグなし)" if snapshot.found else "")
            self.tags_view.setToolTip("")


class ImageComparisonDialog(QDialog):
    """2 枚の画像の現在の注釈を左右に並べて比べる、読み取り専用の画面。"""

    def __init__(self, service: ImageComparisonService, parent: QWidget | None = None) -> None:
        """比較サービスを受け取り、画面を組み立てる。

        Args:
            service: 読み取り専用の比較サービス。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setObjectName("imageComparisonDialog")
        self.setWindowTitle("画像の比較")
        self.setModal(False)
        self.resize(1200, 860)

        self._service = service
        self._selection: ComparisonSelection | None = None
        self._generation = 0
        self._inflight_worker_id: str | None = None
        self._cache: dict[int, LoadedComparisonSide] = {}
        self._current: ImageComparisonLoadResult | None = None
        self._shutting_down = False
        self._syncing_controls = False
        self._syncing_viewport = False

        self._worker_manager = WorkerManager(self)
        self._worker_manager.worker_terminal.connect(self._on_worker_terminal)

        self._build_ui()

    # -- 組み立て ----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self._combos: dict[Side, QComboBox] = {}
        self._prev_buttons: dict[Side, QToolButton] = {}
        self._next_buttons: dict[Side, QToolButton] = {}
        self._pin_checks: dict[Side, QCheckBox] = {}
        for side in (Side.LEFT, Side.RIGHT):
            if side is Side.RIGHT:
                self._swap_button = QPushButton("⇄ 左右を入れ替え", self)
                self._swap_button.setObjectName("swapComparisonButton")
                self._swap_button.clicked.connect(self._on_swap_clicked)
                controls.addWidget(self._swap_button)
                controls.addStretch(1)
            controls.addWidget(QLabel(f"{_SIDE_LABELS[side]}:", self))
            prev_button = QToolButton(self)
            prev_button.setText("◀")
            prev_button.setToolTip(f"{_SIDE_LABELS[side]}を前の候補にする")
            prev_button.setObjectName(f"{side.value}PrevButton")
            prev_button.clicked.connect(lambda _=False, s=side: self._on_step(s, -1))
            combo = QComboBox(self)
            combo.setObjectName(f"{side.value}CandidateCombo")
            combo.setMinimumContentsLength(18)
            combo.currentIndexChanged.connect(lambda _index, s=side: self._on_combo_changed(s))
            next_button = QToolButton(self)
            next_button.setText("▶")
            next_button.setToolTip(f"{_SIDE_LABELS[side]}を次の候補にする")
            next_button.setObjectName(f"{side.value}NextButton")
            next_button.clicked.connect(lambda _=False, s=side: self._on_step(s, 1))
            pin = QCheckBox("固定", self)
            pin.setObjectName(f"{side.value}PinCheck")
            pin.setToolTip(f"{_SIDE_LABELS[side]}の画像を固定し、反対側だけを切り替える")
            pin.toggled.connect(lambda checked, s=side: self._on_pin_toggled(s, checked))
            for widget in (prev_button, combo, next_button, pin):
                controls.addWidget(widget)
            self._combos[side] = combo
            self._prev_buttons[side] = prev_button
            self._next_buttons[side] = next_button
            self._pin_checks[side] = pin
            if side is Side.LEFT:
                controls.addStretch(1)

        self.chkSyncView = QCheckBox("表示を同期", self)
        self.chkSyncView.setObjectName("chkSyncView")
        self.chkSyncView.setToolTip("左右のズーム倍率と相対表示位置を同期する")
        self.chkSyncView.setChecked(True)
        self.chkSyncView.toggled.connect(self._on_sync_toggled)
        self._sync_check = self.chkSyncView
        controls.addWidget(self.chkSyncView)

        self.btnZoomOut = QToolButton(self)
        self.btnZoomOut.setText("-")
        self.btnZoomOut.setToolTip("縮小")
        self.btnZoomOut.setObjectName("btnZoomOut")
        self.btnZoomOut.clicked.connect(self.zoom_out)
        self._zoom_out_button = self.btnZoomOut
        controls.addWidget(self.btnZoomOut)

        self.btnZoomIn = QToolButton(self)
        self.btnZoomIn.setText("+")
        self.btnZoomIn.setToolTip("拡大")
        self.btnZoomIn.setObjectName("btnZoomIn")
        self.btnZoomIn.clicked.connect(self.zoom_in)
        self._zoom_in_button = self.btnZoomIn
        controls.addWidget(self.btnZoomIn)

        self.btnResetZoom = QPushButton("1:1 / リセット", self)
        self.btnResetZoom.setToolTip("表示倍率と位置を全体表示に戻す")
        self.btnResetZoom.setObjectName("btnResetZoom")
        self.btnResetZoom.clicked.connect(self.reset_view)
        self._reset_zoom_button = self.btnResetZoom
        controls.addWidget(self.btnResetZoom)

        self._reload_button = QPushButton("再読み込み", self)
        self._reload_button.setObjectName("reloadComparisonButton")
        self._reload_button.setToolTip("DB の現在の注釈を読み直す")
        self._reload_button.clicked.connect(self.reload)
        controls.addWidget(self._reload_button)
        layout.addLayout(controls)

        self._status_label = QLabel(self)
        self._status_label.setObjectName("comparisonStatusLabel")
        layout.addWidget(self._status_label)

        vertical = QSplitter(Qt.Orientation.Vertical, self)
        sides = QSplitter(Qt.Orientation.Horizontal, vertical)
        self._panels = {
            Side.LEFT: _ComparisonSidePanel(Side.LEFT, sides),
            Side.RIGHT: _ComparisonSidePanel(Side.RIGHT, sides),
        }
        for side, panel in self._panels.items():
            panel.preview.view_changed.connect(
                lambda zoom, rx, ry, s=side: self._on_viewport_changed(s, zoom, rx, ry)
            )
            sides.addWidget(panel)
        vertical.addWidget(sides)
        vertical.addWidget(self._build_diff_tabs(vertical))
        vertical.setStretchFactor(0, 3)
        vertical.setStretchFactor(1, 2)
        layout.addWidget(vertical, 1)

    def _build_diff_tabs(self, parent: QWidget) -> QTabWidget:
        tabs = QTabWidget(parent)
        tabs.setObjectName("comparisonDiffTabs")

        tag_page = QWidget(tabs)
        tag_layout = QVBoxLayout(tag_page)
        self._tag_message = QLabel(tag_page)
        self._tag_message.setObjectName("tagDiffMessage")
        self._tag_message.setWordWrap(True)
        tag_layout.addWidget(self._tag_message)
        grid = QGridLayout()
        self._tag_headers: dict[str, QLabel] = {}
        self._tag_lists: dict[str, QListWidget] = {}
        for column, key in enumerate(("left_only", "common", "right_only")):
            header = QLabel(tag_page)
            tag_list = QListWidget(tag_page)
            tag_list.setObjectName(f"tagDiff_{key}")
            grid.addWidget(header, 0, column)
            grid.addWidget(tag_list, 1, column)
            self._tag_headers[key] = header
            self._tag_lists[key] = tag_list
        tag_layout.addLayout(grid, 1)
        tabs.addTab(tag_page, "タグの差分")

        caption_page = QWidget(tabs)
        caption_layout = QVBoxLayout(caption_page)
        self._caption_message = QLabel(caption_page)
        self._caption_message.setObjectName("captionDiffMessage")
        self._caption_message.setWordWrap(True)
        caption_layout.addWidget(self._caption_message)
        browsers = QHBoxLayout()
        self._caption_browsers: dict[Side, QTextBrowser] = {}
        for side in (Side.LEFT, Side.RIGHT):
            browser = QTextBrowser(caption_page)
            browser.setObjectName(f"{side.value}CaptionBrowser")
            browser.setOpenLinks(False)
            browsers.addWidget(browser)
            self._caption_browsers[side] = browser
        caption_layout.addLayout(browsers, 1)
        tabs.addTab(caption_page, "キャプションの差分")

        tabs.addTab(self._build_generation_diff_page(tabs), "生成メタデータの差分")
        self._diff_tabs = tabs
        return tabs

    def _build_generation_diff_page(self, parent: QWidget) -> QWidget:
        generation_page = QWidget(parent)
        generation_layout = QVBoxLayout(generation_page)

        self._generation_message = QLabel(generation_page)
        self._generation_message.setObjectName("generationDiffMessage")
        self._generation_message.setWordWrap(True)
        generation_layout.addWidget(self._generation_message)

        self._generation_table = QTableWidget(0, 4, generation_page)
        self._generation_table.setObjectName("generationDiffTable")
        self._generation_table.setHorizontalHeaderLabels(["項目", "状態", "左", "右"])
        self._generation_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._generation_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._generation_table.verticalHeader().setVisible(False)
        header = self._generation_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        generation_layout.addWidget(self._generation_table, 2)

        prompt_grid = QGridLayout()
        self._prompt_browsers: dict[Side, QTextBrowser] = {}
        self._negative_prompt_browsers: dict[Side, QTextBrowser] = {}
        prompt_grid.addWidget(QLabel("正プロンプト差分:", generation_page), 0, 0, 1, 2)
        for col, side in enumerate((Side.LEFT, Side.RIGHT)):
            browser = QTextBrowser(generation_page)
            browser.setObjectName(f"{side.value}PromptBrowser")
            browser.setOpenLinks(False)
            browser.setMaximumHeight(90)
            prompt_grid.addWidget(browser, 1, col)
            self._prompt_browsers[side] = browser
        prompt_grid.addWidget(QLabel("負プロンプト差分:", generation_page), 2, 0, 1, 2)
        for col, side in enumerate((Side.LEFT, Side.RIGHT)):
            browser = QTextBrowser(generation_page)
            browser.setObjectName(f"{side.value}NegativePromptBrowser")
            browser.setOpenLinks(False)
            browser.setMaximumHeight(70)
            prompt_grid.addWidget(browser, 3, col)
            self._negative_prompt_browsers[side] = browser
        generation_layout.addLayout(prompt_grid, 1)

        self._raw_metadata_toggle = QToolButton(generation_page)
        self._raw_metadata_toggle.setObjectName("rawMetadataToggle")
        self._raw_metadata_toggle.setText("原データを表示")
        self._raw_metadata_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._raw_metadata_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._raw_metadata_toggle.setCheckable(True)
        self._raw_metadata_toggle.setChecked(False)
        self._raw_metadata_toggle.toggled.connect(self._toggle_raw_metadata)
        generation_layout.addWidget(self._raw_metadata_toggle)

        self._raw_metadata_container = QWidget(generation_page)
        self._raw_metadata_container.setObjectName("rawMetadataContainer")
        self._raw_metadata_container.setVisible(False)
        raw_layout = QHBoxLayout(self._raw_metadata_container)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        self._raw_metadata_views: dict[Side, QPlainTextEdit] = {}
        for side in (Side.LEFT, Side.RIGHT):
            raw_view = QPlainTextEdit(self._raw_metadata_container)
            raw_view.setObjectName(f"{side.value}RawMetadataView")
            raw_view.setReadOnly(True)
            raw_view.setMaximumHeight(120)
            raw_layout.addWidget(raw_view)
            self._raw_metadata_views[side] = raw_view
        generation_layout.addWidget(self._raw_metadata_container)

        return generation_page

    def _toggle_raw_metadata(self, expanded: bool) -> None:
        self._raw_metadata_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._raw_metadata_container.setVisible(expanded)

    def generation_field_row(self, key: str) -> tuple[str, str, str] | None:
        """生成メタデータの項目キーに対応する表の (状態, 左, 右) を返す。"""
        for row in range(self._generation_table.rowCount()):
            key_item = self._generation_table.item(row, 0)
            if key_item is not None and key_item.data(Qt.ItemDataRole.UserRole) == key:
                status_item = self._generation_table.item(row, 1)
                left_item = self._generation_table.item(row, 2)
                right_item = self._generation_table.item(row, 3)
                return (
                    status_item.text() if status_item else "",
                    left_item.text() if left_item else "",
                    right_item.text() if right_item else "",
                )
        return None

    # -- 公開 API ----------------------------------------------------------

    def set_candidates(self, image_ids: list[int]) -> None:
        """比較の候補を設定し、先頭 2 枚を左右に置いて読み込む。

        Raises:
            ValueError: 重複を除いた候補が 2 枚未満のとき。
        """
        self._selection = ComparisonSelection(image_ids)
        self._shutting_down = False
        self._cache.clear()
        self._populate_combos()
        self._request_load()

    @property
    def selection(self) -> ComparisonSelection | None:
        """現在の左右の選択状態。"""
        return self._selection

    @property
    def current_result(self) -> ImageComparisonLoadResult | None:
        """表示中の比較結果。読み込み中や未表示なら None。"""
        return self._current

    @property
    def generation(self) -> int:
        """現在の要求の世代番号。"""
        return self._generation

    def viewport(self, side: Side) -> ComparisonImageViewport:
        """指定した側の画像ビューポートを返す。"""
        return self._panels[side].preview

    @property
    def left_viewport(self) -> ComparisonImageViewport:
        """左側の画像ビューポート。"""
        return self._panels[Side.LEFT].preview

    @property
    def right_viewport(self) -> ComparisonImageViewport:
        """右側の画像ビューポート。"""
        return self._panels[Side.RIGHT].preview

    @property
    def sync_enabled(self) -> bool:
        """左右のズーム / パン同期が有効かどうか。"""
        return self.chkSyncView.isChecked()

    def is_sync_enabled(self) -> bool:
        """左右のズーム / パン同期が有効かどうかを返す。"""
        return self.chkSyncView.isChecked()

    def set_sync_enabled(self, enabled: bool) -> None:
        """左右のズーム / パン同期のオン / オフを切り替える。"""
        self.chkSyncView.setChecked(enabled)

    @Slot()
    def zoom_in(self) -> None:
        """拡大ボタン操作 (同期オン時は両側、オフ時は左側に適用)。"""
        self._panels[Side.LEFT].preview.zoom_in()

    @Slot()
    def zoom_out(self) -> None:
        """縮小ボタン操作 (同期オン時は両側、オフ時は左側に適用)。"""
        self._panels[Side.LEFT].preview.zoom_out()

    @Slot()
    def reset_view(self) -> None:
        """表示リセットボタン操作 (同期オン時は両側、オフ時は左側を 1:1 に戻す)。"""
        self._panels[Side.LEFT].preview.reset_view()

    @Slot()
    def reload(self) -> None:
        """DB の現在の注釈を読み直す。"""
        if self._selection is None:
            return
        self._cache.clear()
        self._request_load()

    def stop_loading(self) -> None:
        """世代を進めて実行中の読み込みを捨てる (画面を閉じる・データセット切替のとき)。"""
        self._generation += 1
        self._current = None
        self._cache.clear()
        if self._inflight_worker_id is not None:
            self._worker_manager.request_cancel_worker(
                self._inflight_worker_id, reason=CancelReason.SHUTDOWN
            )
        self._inflight_worker_id = None

    def shutdown(self) -> None:
        """アプリ終了時に worker を止める。"""
        self._shutting_down = True
        self._generation += 1
        self._current = None
        self._cache.clear()
        self._inflight_worker_id = None
        self._worker_manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """閉じたら読み込みを止め、保持しているプレビューを手放す。"""
        self.stop_loading()
        super().closeEvent(event)

    # -- ビューポート同期 --------------------------------------------------

    def _on_viewport_changed(self, source_side: Side, zoom: float, rx: float, ry: float) -> None:
        """片側のビューポート変化を、同期オン時に反対側へ伝播する。"""
        if self._syncing_viewport or not self.chkSyncView.isChecked():
            return
        target_side = Side.RIGHT if source_side is Side.LEFT else Side.LEFT
        target = self._panels[target_side].preview
        self._syncing_viewport = True
        try:
            target.set_zoom_factor(zoom, emit_signal=False)
            target.set_relative_center(rx, ry, emit_signal=False)
        finally:
            self._syncing_viewport = False

    def _on_sync_toggled(self, checked: bool) -> None:
        """同期をオフからオンに戻したとき、左の表示状態へ右を即座に揃える。"""
        if not checked or self._syncing_viewport:
            return
        left = self._panels[Side.LEFT].preview
        rx, ry = left.get_relative_center()
        self._on_viewport_changed(Side.LEFT, left.zoom_factor, rx, ry)

    # -- 操作 --------------------------------------------------------------

    def _populate_combos(self) -> None:
        if self._selection is None:
            return
        self._syncing_controls = True
        try:
            for combo in self._combos.values():
                combo.clear()
                for image_id in self._selection.candidates:
                    combo.addItem(f"画像 ID {image_id}", image_id)
        finally:
            self._syncing_controls = False
        self._sync_controls()

    def _sync_controls(self) -> None:
        """選択状態をコンボ・固定・ボタンへ反映する。"""
        if self._selection is None:
            return
        self._syncing_controls = True
        try:
            many = len(self._selection.candidates) > 2
            for side in (Side.LEFT, Side.RIGHT):
                pinned = self._selection.is_pinned(side)
                combo = self._combos[side]
                combo.setCurrentIndex(combo.findData(self._selection.image_id(side)))
                combo.setEnabled(not pinned and many)
                self._prev_buttons[side].setEnabled(not pinned and many)
                self._next_buttons[side].setEnabled(not pinned and many)
                self._pin_checks[side].setChecked(pinned)
        finally:
            self._syncing_controls = False

    def _on_swap_clicked(self) -> None:
        if self._selection is None:
            return
        self._selection.swap()
        self._sync_controls()
        self._request_load()

    def _on_step(self, side: Side, delta: int) -> None:
        if self._selection is None or not self._selection.step(side, delta):
            return
        self._sync_controls()
        self._request_load()

    def _on_combo_changed(self, side: Side) -> None:
        if self._syncing_controls or self._selection is None:
            return
        image_id = self._combos[side].currentData()
        changed = isinstance(image_id, int) and self._selection.set_side(side, image_id)
        # 反対側と同じ画像や固定中で変えられなかったときもコンボを状態に戻す
        self._sync_controls()
        if changed:
            self._request_load()

    def _on_pin_toggled(self, side: Side, checked: bool) -> None:
        if self._syncing_controls or self._selection is None:
            return
        self._selection.set_pinned(side, checked)
        self._sync_controls()

    # -- 読み込み ----------------------------------------------------------

    def _request_load(self) -> None:
        """現在の左右で読み込みを要求する。古い要求は世代で無効にする。"""
        if self._selection is None or self._shutting_down:
            return
        self._generation += 1
        generation = self._generation
        left_id = self._selection.left_id
        right_id = self._selection.right_id
        if self._inflight_worker_id is not None:
            self._worker_manager.request_cancel_worker(
                self._inflight_worker_id, reason=CancelReason.REFINEMENT_REPLACED
            )
        self._current = None
        for panel in self._panels.values():
            panel.show_loading()
        self._clear_diff("読み込み中…")
        self._status_label.setText(f"読み込み中… (左: 画像 ID {left_id} / 右: 画像 ID {right_id})")

        cached = {i: self._cache[i] for i in (left_id, right_id) if i in self._cache}
        worker = ImageComparisonWorker(
            self._service, generation=generation, left_id=left_id, right_id=right_id, cached=cached
        )
        worker.finished.connect(self._on_worker_finished)
        worker_id = f"{_WORKER_PREFIX}{generation}"
        self._inflight_worker_id = worker_id
        self._worker_manager.start_worker(worker_id, worker)

    def _is_current(self, result: ImageComparisonLoadResult) -> bool:
        if self._shutting_down or self._selection is None:
            return False
        if result.generation != self._generation:
            return False
        return (result.left.snapshot.image_id, result.right.snapshot.image_id) == (
            self._selection.left_id,
            self._selection.right_id,
        )

    @Slot(object)
    def _on_worker_finished(self, result: ImageComparisonLoadResult) -> None:
        """最新の要求で、左右が表示対象と一致する結果だけを表示する。"""
        if not self._is_current(result):
            logger.debug(f"古い比較結果を破棄: generation={result.generation}")
            return
        # キャッシュは表示中の 2 枚だけにし、プレビューのメモリを溜めない
        self._cache = {
            result.left.snapshot.image_id: result.left,
            result.right.snapshot.image_id: result.right,
        }
        self._current = result
        self._panels[Side.LEFT].show_side(result.left)
        self._panels[Side.RIGHT].show_side(result.right)
        self._show_tag_diff(result.comparison.tags)
        self._show_caption_diff(result.comparison.caption, result)
        self._show_generation_diff(result.comparison.generation, result)
        self._status_label.setText(
            f"左: 画像 ID {result.left.snapshot.image_id} / 右: 画像 ID {result.right.snapshot.image_id}"
            "  (読み取り専用。比較してもタグや採用状態は変わりません)"
        )

    @Slot(object)
    def _on_worker_terminal(self, event: WorkerTerminalEvent) -> None:
        if event.worker_id != self._inflight_worker_id:
            return
        self._inflight_worker_id = None
        if event.outcome is WorkerOutcome.SUCCEEDED or self._shutting_down:
            return
        if event.worker_id != f"{_WORKER_PREFIX}{self._generation}":
            return
        if event.outcome is WorkerOutcome.FAILED:
            logger.warning(f"比較対象の読み込みに失敗: {event.error}")
            self._status_label.setText("比較対象の読み込みに失敗しました。再読み込みしてください。")
            for panel in self._panels.values():
                panel.provenance_label.setText("読み込みに失敗しました")
            self._clear_diff("読み込みに失敗しました")

    # -- 差分の表示 --------------------------------------------------------

    def _clear_diff(self, message: str) -> None:
        self._tag_message.setText(message)
        self._tag_message.setVisible(True)
        for key, tag_list in self._tag_lists.items():
            tag_list.clear()
            self._tag_headers[key].setText(self._tag_header_text(key, None))
        self._caption_message.setText(message)
        self._caption_message.setVisible(True)
        for browser in self._caption_browsers.values():
            browser.clear()
        self._generation_message.setText(message)
        self._generation_message.setVisible(True)
        self._generation_table.setRowCount(0)
        for browser in self._prompt_browsers.values():
            browser.clear()
        for browser in self._negative_prompt_browsers.values():
            browser.clear()
        for raw_view in self._raw_metadata_views.values():
            raw_view.setPlainText("")

    @staticmethod
    def _tag_header_text(key: str, count: int | None) -> str:
        label = {"left_only": "左だけ", "common": "共通", "right_only": "右だけ"}[key]
        return label if count is None else f"{label} ({count})"

    def _show_tag_diff(self, diff: TagDiff) -> None:
        values = {"left_only": diff.left_only, "common": diff.common, "right_only": diff.right_only}
        both = diff.availability is Availability.BOTH
        for key, tag_list in self._tag_lists.items():
            tag_list.clear()
            tag_list.addItems(list(values[key]))
            self._tag_headers[key].setText(self._tag_header_text(key, len(values[key]) if both else None))
        if not both:
            self._tag_message.setText(_missing_message(diff.availability, "タグ"))
        elif diff.identical:
            self._tag_message.setText("左右のタグは同じです")
        else:
            self._tag_message.setText("")
        self._tag_message.setVisible(bool(self._tag_message.text()))

    def _show_caption_diff(self, diff: CaptionDiff, result: ImageComparisonLoadResult) -> None:
        if diff.availability is Availability.BOTH:
            for side, browser in self._caption_browsers.items():
                browser.setHtml(_caption_side_html(diff, side))
            self._caption_message.setText("左右のキャプションは同じです" if diff.identical else "")
        else:
            # 片側だけある場合は、ある側の原文をそのまま見せ、無い側は「なし」と明示する
            snapshots = {Side.LEFT: result.left.snapshot, Side.RIGHT: result.right.snapshot}
            for side, browser in self._caption_browsers.items():
                caption = snapshots[side].caption
                browser.setHtml(
                    _plain_html(caption) if caption else _placeholder_html("(キャプションなし)")
                )
            self._caption_message.setText(_missing_message(diff.availability, "キャプション"))
        self._caption_message.setVisible(bool(self._caption_message.text()))

    def _show_generation_diff(
        self, diff: GenerationMetadataDiff, result: ImageComparisonLoadResult
    ) -> None:
        self._generation_table.setRowCount(len(diff.fields))
        left_brush = QBrush(QColor(theme.ERR_SOFT))
        right_brush = QBrush(QColor(theme.OK_SOFT))
        for row, field_diff in enumerate(diff.fields):
            label_item = QTableWidgetItem(field_diff.label)
            label_item.setData(Qt.ItemDataRole.UserRole, field_diff.key)
            status_item = QTableWidgetItem(field_diff.status_label)
            left_item = QTableWidgetItem(field_diff.left_display)
            right_item = QTableWidgetItem(field_diff.right_display)
            if field_diff.changed:
                left_item.setBackground(left_brush)
                right_item.setBackground(right_brush)
            for col, item in enumerate((label_item, status_item, left_item, right_item)):
                self._generation_table.setItem(row, col, item)

        snapshots = {
            Side.LEFT: result.left.snapshot.generation_metadata,
            Side.RIGHT: result.right.snapshot.generation_metadata,
        }
        self._update_prompt_browsers(
            self._prompt_browsers,
            diff.positive_prompt,
            {
                side: snapshots[side].positive_prompt if snapshots[side].has_metadata else None
                for side in (Side.LEFT, Side.RIGHT)
            },
        )
        self._update_prompt_browsers(
            self._negative_prompt_browsers,
            diff.negative_prompt,
            {
                side: snapshots[side].negative_prompt if snapshots[side].has_metadata else None
                for side in (Side.LEFT, Side.RIGHT)
            },
        )
        for side, raw_view in self._raw_metadata_views.items():
            raw_view.setPlainText(snapshots[side].raw_sources_text())

        if diff.availability is not Availability.BOTH:
            self._generation_message.setText(_missing_message(diff.availability, "生成メタデータ"))
        elif diff.identical:
            self._generation_message.setText("左右の生成メタデータは同じです")
        elif diff.differing_fields:
            self._generation_message.setText(
                f"差分あり: {len(diff.differing_fields)} 項目 / 同じ: {len(diff.matching_fields)} 項目"
            )
        else:
            self._generation_message.setText("原データを確認してください")
        self._generation_message.setVisible(bool(self._generation_message.text()))

    @staticmethod
    def _update_prompt_browsers(
        browsers: dict[Side, QTextBrowser],
        prompt_diff: CaptionDiff,
        texts: dict[Side, str | None],
    ) -> None:
        if prompt_diff.availability is Availability.BOTH:
            for side, browser in browsers.items():
                browser.setHtml(_caption_side_html(prompt_diff, side))
            return
        for side, browser in browsers.items():
            text = texts[side]
            browser.setHtml(_plain_html(text) if text else _placeholder_html("なし"))


class ImageComparisonLauncher(QObject):
    """比較画面を開く入口。画面は 1 つだけ持ち、開き直すと候補を差し替える。"""

    def __init__(
        self,
        metadata_source: ImageMetadataSource | None,
        parent_widget: QWidget,
        dataset_state_manager: DatasetStateManager | None = None,
    ) -> None:
        """入口を作る。

        Args:
            metadata_source: 画像メタデータの取得元 (``ImageDatabaseManager``)。
            parent_widget: 比較画面の親。
            dataset_state_manager: データセット切替を検知して画面を閉じるために使う。
        """
        super().__init__(parent_widget)
        self._metadata_source = metadata_source
        self._parent_widget = parent_widget
        self._dialog: ImageComparisonDialog | None = None
        if dataset_state_manager is not None:
            dataset_state_manager.dataset_changed.connect(self._on_dataset_changed)

    @property
    def dialog(self) -> ImageComparisonDialog | None:
        """作成済みの比較画面。"""
        return self._dialog

    def open(self, image_ids: list[int]) -> bool:
        """候補の先頭 2 枚で比較画面を開く。

        Returns:
            開いたら True。取得元が無い・異なる画像が 2 枚未満なら False。
        """
        if self._metadata_source is None:
            logger.warning("DB 未接続のため画像の比較を開けません")
            return False
        if len(dict.fromkeys(image_ids)) < 2:
            return False
        if self._dialog is None:
            service = ImageComparisonService(self._metadata_source)
            self._dialog = ImageComparisonDialog(service, self._parent_widget)
        self._dialog.set_candidates(image_ids)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        logger.info(f"画像の比較を開きました: 候補 {len(dict.fromkeys(image_ids))} 枚")
        return True

    @Slot(str)
    def _on_dataset_changed(self, _dataset_path: str) -> None:
        """データセット (プロジェクト) が切り替わったら、古い DB の比較を閉じる。"""
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.close()

    def shutdown(self) -> None:
        """アプリ終了時に比較画面の worker を止めて閉じる。"""
        if self._dialog is None:
            return
        self._dialog.shutdown()
        self._dialog.close()
