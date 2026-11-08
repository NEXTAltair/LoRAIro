"""2 枚の画像を左右に並べ、現在のタグ / キャプションの差分を見る比較画面 (Issue #1399 / #1484)。

読み取り専用。比較してもタグや採用状態は変えない。

- 差分計算と左右の選択状態は Qt 非依存の ``services/image_comparison.py`` が持ち、
  この画面は結果の表示と操作の受け付けだけを行う。
- 左右の注釈とプレビューは ``ImageComparisonWorker`` が 1 回の要求ごとにまとめて読む。
  要求ごとに世代番号を進め、古い世代の結果や、表示対象と画像 ID が合わない結果は捨てる。
  読み込み中は左右の表示を空にし、古い画像と新しい注釈が並ぶ瞬間を作らない。
- 画面を閉じる・アプリを終える・データセットが切り替わるときは世代を進めて worker を止める。
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
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
from .image_preview import ImagePreviewWidget

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager

_SIDE_LABELS = {Side.LEFT: "左", Side.RIGHT: "右"}
_WORKER_PREFIX = "image_comparison_"


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
    return f'<div style="color:{theme.INK_FAINT}; font-style: italic;">{html.escape(text)}</div>'


def _plain_html(text: str) -> str:
    return f'<div style="white-space: pre-wrap;">{html.escape(text)}</div>'


class _ComparisonSidePanel(QWidget):
    """片側の画像・出所・タグを表示するパネル。"""

    def __init__(self, side: Side, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.side = side
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.preview = ImagePreviewWidget(self)
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
        sides.addWidget(self._panels[Side.LEFT])
        sides.addWidget(self._panels[Side.RIGHT])
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
        return tabs

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
