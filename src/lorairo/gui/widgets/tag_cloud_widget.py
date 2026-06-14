"""キーワード連動の共起タグクラウドウィジェット（Map フレーム）。

任意のキーワード（部分一致）でマッチした画像群の共起タグを、頻度に応じた
フォントサイズで雲状に表示する。タグクリックで AND 絞り込み（ドリルダウン）し、
関連タグを辿って探索する。探索専用でステージング導線は持たない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QObject, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.tag_cloud_service import CloudResult, TagCloudService

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager

# フォントサイズ範囲（weight 0..1 をこの px 範囲へマッピング）
_FONT_SIZE_MIN = 10
_FONT_SIZE_MAX = 30
# キーワード入力のデバウンス（ms）
_DEBOUNCE_MS = 250


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
    """クリック可能なタグクラウド用ラベル。"""

    clicked = Signal(str)

    def __init__(self, tag: str, count: int, weight: float, parent: QWidget | None = None) -> None:
        super().__init__(tag, parent)
        self._tag = tag
        font_px = int(_FONT_SIZE_MIN + weight * (_FONT_SIZE_MAX - _FONT_SIZE_MIN))
        font = QFont("sans-serif", -1)
        font.setPixelSize(font_px)
        # ウェイトが高いほど太字寄りに
        font.setWeight(QFont.Weight.DemiBold if weight >= 0.5 else QFont.Weight.Normal)
        self.setFont(font)
        # 頻度ティアで色付け
        color = theme.ACCENT if weight >= 0.66 else (theme.INK if weight >= 0.33 else theme.INK_SOFT)
        self.setStyleSheet(f"color:{color};padding:1px 3px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{tag} ({count}件) — クリックで絞り込み")

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
            f"background:{theme.ACCENT_SOFT};border:1px solid {theme.ACCENT_BORDER};"
            f"border-radius:{theme.RADIUS_CHIP}px;"
        )
        name = QLabel(tag)
        name.setFont(QFont("monospace", 9))
        name.setStyleSheet(f"color:{theme.ACCENT_HOVER};border:none;background:transparent;")
        layout.addWidget(name)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{theme.ACCENT_HOVER};}}"
            f"QPushButton:hover{{color:{theme.ERR};}}"
        )
        close_btn.clicked.connect(lambda: self.removed.emit(self._tag))
        layout.addWidget(close_btn)


class _CloudWorker(QThread):
    """バックグラウンドで初回タグロード+集計を実行するスレッド。"""

    finished = Signal(object)  # CloudResult
    error = Signal(str)

    def __init__(
        self,
        service: TagCloudService,
        keyword: str,
        selected_tags: list[str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._keyword = keyword
        self._selected_tags = selected_tags

    def run(self) -> None:
        try:
            result = self._service.build_cloud(self._keyword, self._selected_tags)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class TagCloudWidget(QWidget):
    """マップタブのルートウィジェット（キーワード連動共起タグクラウド）。"""

    def __init__(self, db_manager: ImageDatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db_manager
        self._service = TagCloudService(db_manager)
        self._keyword = ""
        self._selected_tags: list[str] = []
        self._worker: _CloudWorker | None = None
        self._loaded_once = False

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._recompute)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 上部: キーワード入力 + リセット/再読込
        top = QHBoxLayout()
        top.setSpacing(6)
        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("キーワードを入力（部分一致）して関連タグを探索…")
        self._keyword_edit.setClearButtonEnabled(True)
        self._keyword_edit.textChanged.connect(self._on_keyword_changed)
        top.addWidget(self._keyword_edit, 1)

        self._reset_btn = QPushButton("リセット")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self._on_reset)
        top.addWidget(self._reset_btn)

        self._reload_btn = QPushButton("↺ 再読込")
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.setToolTip("DB を読み直してクラウドを更新")
        self._reload_btn.clicked.connect(self._on_reload)
        top.addWidget(self._reload_btn)
        root.addLayout(top)

        # ドリルダウンチップ列
        self._chip_bar = QWidget()
        self._chip_layout = FlowLayout(self._chip_bar, spacing=4)
        root.addWidget(self._chip_bar)

        # ステータス
        self._status_label = QLabel("")
        self._status_label.setFont(QFont("monospace", 9))
        self._status_label.setStyleSheet(f"color:{theme.INK_FAINT};")
        root.addWidget(self._status_label)

        # クラウド本体（スクロール可）
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._cloud_container = QWidget()
        self._cloud_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._cloud_layout = FlowLayout(self._cloud_container, spacing=8)
        self._scroll.setWidget(self._cloud_container)
        root.addWidget(self._scroll, 1)

        self._show_placeholder()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_keyword_changed(self, text: str) -> None:
        self._keyword = text
        # キーワードを変えたらドリルダウンはリセット
        self._selected_tags = []
        self._debounce.start()

    def _on_reset(self) -> None:
        self._keyword_edit.clear()
        self._keyword = ""
        self._selected_tags = []
        self._debounce.stop()
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
            self._show_placeholder()
            return
        self._status_label.setText("集計中...")
        if not self._loaded_once:
            # 初回はタグ全ロードが走るためバックグラウンドで
            self._start_worker()
        else:
            # キャッシュ済みなら同期で十分軽い
            result = self._service.build_cloud(self._keyword, self._selected_tags)
            self._apply_result(result)

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        worker = _CloudWorker(self._service, self._keyword, list(self._selected_tags), parent=self)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        self._worker = worker
        worker.start()

    def _on_worker_finished(self, result: CloudResult) -> None:
        self._loaded_once = True
        self._apply_result(result)

    def _on_worker_error(self, msg: str) -> None:
        self._status_label.setText(f"エラー: {msg}")
        logger.error(f"TagCloud 計算エラー: {msg}")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _apply_result(self, result: CloudResult) -> None:
        self._refresh_chips()
        self._clear_layout(self._cloud_layout)
        for entry in result.entries:
            label = _TagCloudLabel(entry.tag, entry.count, entry.weight)
            label.clicked.connect(self._on_tag_clicked)
            self._cloud_layout.addWidget(label)
        if result.entries:
            self._status_label.setText(
                f"該当 {result.matched_images}枚 / 全 {result.total_images}枚 · {len(result.entries)}タグ"
            )
        else:
            self._status_label.setText(
                f"該当なし（全 {result.total_images}枚） — 別のキーワードを試してください"
            )

    def _refresh_chips(self) -> None:
        self._clear_layout(self._chip_layout)
        for tag in self._selected_tags:
            chip = _DrillChip(tag)
            chip.removed.connect(self._on_chip_removed)
            self._chip_layout.addWidget(chip)

    def _show_placeholder(self) -> None:
        self._clear_layout(self._cloud_layout)
        self._clear_layout(self._chip_layout)
        placeholder = QLabel("キーワードを入力すると、共起タグがクラウド表示されます")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(f"color:{theme.INK_FAINT};")
        placeholder.setFont(QFont("monospace", 11))
        self._cloud_layout.addWidget(placeholder)
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
