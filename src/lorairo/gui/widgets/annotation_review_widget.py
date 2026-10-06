"""A read-only Clef review ledger for the selected image's annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..workers.annotation_review_worker import AnnotationReviewWorker, AnnotationReviewWorkerResult
from ..workers.manager import WorkerManager
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewResult, AnnotationReviewService


class AnnotationReviewWidget(QWidget):
    """Own review display, single-flight lifecycle, and stale-result rejection.

    This widget has no annotation write operation. Image selection and annotation
    reloads invalidate results; a fresh service snapshot also protects against
    edits from another process while a request is running.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service: AnnotationReviewService | None = None
        self._manager: WorkerManager | None = None
        self._image_id: int | None = None
        self._generation = 0
        self._inflight_id: str | None = None
        self._closing = False
        self._unavailable_reason: str | None = None
        self._build_ui()
        self.set_image(None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, theme.SPACE_1, 0, theme.SPACE_1)
        layout.setSpacing(theme.SPACE_1)
        header = QHBoxLayout()
        title = QLabel("画像との整合性", self)
        title.setStyleSheet(f"font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
        header.addWidget(title, 1)
        self.evaluate_button = QPushButton("Clef で確認", self)
        self.evaluate_button.setObjectName("buttonReviewAnnotations")
        self.evaluate_button.setToolTip(
            "選択画像と既存の有効なタグ・キャプションを Cloudflare に送信して評価します。"
        )
        self.evaluate_button.clicked.connect(self._on_evaluate_requested)
        header.addWidget(self.evaluate_button)
        self.cancel_button = QPushButton("中止", self)
        self.cancel_button.clicked.connect(self._on_cancel_requested)
        self.cancel_button.setVisible(False)
        header.addWidget(self.cancel_button)
        layout.addLayout(header)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setObjectName("labelAnnotationReviewStatus")
        layout.addWidget(self.status_label)
        self.notice_label = QLabel("画像・有効なタグ・キャプションを Cloudflare に送信します。", self)
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(self.notice_label)
        self.results_table = QTableWidget(0, 4, self)
        self.results_table.setObjectName("tableAnnotationReviewResults")
        self.results_table.setHorizontalHeaderLabels(["種類", "既存の内容", "判定", "Clef 一致確率"])
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setWordWrap(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setMinimumHeight(120)
        self.results_table.setMaximumHeight(240)
        self.results_table.setVisible(False)
        layout.addWidget(self.results_table)
        self.model_label = QLabel(self)
        self.model_label.setTextFormat(Qt.TextFormat.PlainText)
        self.model_label.setWordWrap(True)
        self.model_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        self.model_label.setVisible(False)
        layout.addWidget(self.model_label)

    def set_service(
        self, service: AnnotationReviewService, worker_manager: WorkerManager | None = None
    ) -> None:
        """Inject the review service; construction never triggers a cloud request."""
        self._service = service
        self._unavailable_reason = None
        if self._manager is None:
            self._manager = worker_manager if worker_manager is not None else WorkerManager(self)
            self._manager.worker_terminal.connect(self._on_worker_terminal)
        self.set_image(self._image_id)

    def set_unavailable_reason(self, reason: str) -> None:
        """Explain an optional configuration error without breaking the search tab."""
        self._service = None
        self._unavailable_reason = reason
        self.set_image(self._image_id)
        self.setVisible(True)

    @Slot(object)
    def set_image(self, image_id: int | None) -> None:
        """Invalidate even same-image reloads so annotation edits cannot retain results."""
        self._generation += 1
        self._image_id = image_id
        if self._manager is not None and self._inflight_id is not None:
            self._manager.request_cancel_worker(self._inflight_id, reason=CancelReason.USER_REQUESTED)
        self.results_table.setRowCount(0)
        self.results_table.setVisible(False)
        self.model_label.clear()
        self.model_label.setVisible(False)
        self.cancel_button.setVisible(False)
        self._show_idle_state()

    def _show_idle_state(self) -> None:
        if self._unavailable_reason is not None:
            message = f"未評価 — 設定を確認してください: {self._unavailable_reason}"
        elif self._image_id is None:
            message = "未評価 — 画像を選択してください。"
        elif self._service is None:
            message = "未評価 — Clef の評価サービスが利用できません。"
        elif self._inflight_id is not None:
            message = "未評価 — 前の評価を停止しています。"
        else:
            message = "未評価 — ボタンを押すと既存の内容を確認します。"
        self._set_status(message, theme.INK_SOFT)
        self._update_button_state()

    def _update_button_state(self) -> None:
        self.evaluate_button.setEnabled(
            not self._closing
            and self._image_id is not None
            and self._service is not None
            and self._inflight_id is None
        )

    def _set_status(self, message: str, color: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};")

    @Slot()
    def _on_evaluate_requested(self) -> None:
        if self._closing or self._service is None or self._manager is None:
            return
        if self._image_id is None or self._inflight_id is not None:
            return
        self._generation += 1
        self.results_table.setRowCount(0)
        self.results_table.setVisible(False)
        self.model_label.setVisible(False)
        self._inflight_id = f"annotation_review_{id(self)}_{self._generation}"
        self._set_status("Cloudflare で評価中…", theme.INFO)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self._update_button_state()
        worker = AnnotationReviewWorker(self._service, self._image_id, self._generation)
        if not self._manager.start_worker(self._inflight_id, worker):
            self._inflight_id = None
            self.cancel_button.setVisible(False)
            self._set_status("評価に失敗しました — ワーカーを開始できません。", theme.ERR)
            self._update_button_state()

    @Slot()
    def _on_cancel_requested(self) -> None:
        if self._manager is None or self._inflight_id is None:
            return
        self._generation += 1
        self._manager.request_cancel_worker(self._inflight_id, reason=CancelReason.USER_REQUESTED)
        self.cancel_button.setEnabled(False)
        self._set_status("評価を停止しています…", theme.INFO)

    @Slot(object)
    def _on_worker_terminal(self, event: WorkerTerminalEvent) -> None:
        if event.worker_id != self._inflight_id:
            return
        worker_generation = int(event.worker_id.rsplit("_", 1)[1])
        self._inflight_id = None
        self.cancel_button.setVisible(False)
        self._update_button_state()
        if self._closing:
            return
        if worker_generation != self._generation:
            self._show_idle_state()
            return
        if event.outcome != WorkerOutcome.SUCCEEDED:
            if event.outcome == WorkerOutcome.CANCELED:
                self._set_status("未評価 — 評価を中止しました。", theme.INK_SOFT)
            else:
                self._set_status(
                    f"評価に失敗しました — {event.error or 'もう一度お試しください。'}", theme.ERR
                )
            return
        result = event.result
        if not isinstance(result, AnnotationReviewWorkerResult):
            self._set_status("評価に失敗しました — 結果を読み取れません。", theme.ERR)
            return
        self._accept_review_result(result)

    def _accept_review_result(self, result: AnnotationReviewWorkerResult) -> None:
        """Apply only a result whose generation, image, and DB fingerprint still match."""
        if result.generation != self._generation or result.review.image_id != self._image_id:
            self._show_idle_state()
            return
        service = self._service
        if service is None or self._image_id is None:
            return
        try:
            current_snapshot = service.prepare_review(self._image_id)
        except Exception:
            self._set_status(
                "未評価 — 現在の内容を確認できません。画像を再読み込みしてください。", theme.WARN
            )
            return
        if result.review.fingerprint != current_snapshot.fingerprint:
            self._set_status("未評価 — 内容が変更されました。もう一度評価してください。", theme.WARN)
            return
        self._display_result(result.review)

    def _display_result(self, result: AnnotationReviewResult) -> None:
        if result.status == "stale":
            self._set_status("未評価 — 内容が変更されました。もう一度評価してください。", theme.WARN)
            return
        statuses = {
            "ok": ("目安内", theme.INK),
            "warning": ("⚠ 要確認", theme.WARN),
            "failed": ("評価失敗", theme.ERR),
            "unevaluated": ("未評価", theme.INK_FAINT),
        }
        self.results_table.setRowCount(len(result.items))
        for row, review_item in enumerate(result.items):
            label, color = statuses[review_item.status]
            values = (
                "タグ" if review_item.kind == "tag" else "キャプション",
                review_item.text,
                label,
                f"{review_item.probability:.1%}" if review_item.probability is not None else "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (2, 3):
                    item.setForeground(QColor(color))
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(review_item.error or review_item.text)
                self.results_table.setItem(row, column, item)
        self.results_table.resizeRowsToContents()
        self.results_table.setVisible(bool(result.items))
        warnings = sum(item.status == "warning" for item in result.items)
        failed = sum(item.status in ("failed", "unevaluated") for item in result.items)
        if result.status == "cancelled":
            self._set_status("評価を中止しました — 未評価の項目があります。", theme.WARN)
        elif result.status == "failed":
            self._set_status(f"評価に失敗しました — {result.error or '結果を取得できません。'}", theme.ERR)
        elif result.status == "partial":
            self._set_status(
                f"一部を評価できませんでした — 要確認 {warnings} 件 / 失敗・未評価 {failed} 件", theme.WARN
            )
        elif not result.items:
            self._set_status("未評価 — 評価対象の有効なタグ・キャプションがありません。", theme.INK_SOFT)
        else:
            self._set_status(
                f"評価完了 — 要確認 {warnings} 件 / {len(result.items)} 件",
                theme.WARN if warnings else theme.INK,
            )
        threshold = self._service.warning_threshold if self._service is not None else 0.2
        self.model_label.setText(
            f"{result.model_name}\n一致確率が {threshold * 100:g}% 未満を要確認と表示します。結果は確認の目安です。"
        )
        self.model_label.setVisible(True)

    def shutdown(self) -> None:
        """Stop boundedly and let WorkerManager safely retain an unresponsive thread."""
        if self._closing:
            return
        self._closing = True
        self._generation += 1
        self._update_button_state()
        if self._manager is not None:
            self._manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)
