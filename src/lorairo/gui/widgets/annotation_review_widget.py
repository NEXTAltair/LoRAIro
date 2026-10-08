"""A read-only Clef review ledger for the selected image's annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from weakref import ref

from PySide6.QtCore import Qt, Signal, Slot
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
from ..workers.annotation_review_saved_worker import SavedImageReview, SavedImageReviewWorker
from ..workers.annotation_review_worker import AnnotationReviewWorker, AnnotationReviewWorkerResult
from ..workers.manager import WorkerManager
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent

if TYPE_CHECKING:
    from ...services.annotation_review_adoption_service import AnnotationReviewAdoptionService
    from ...services.annotation_review_service import AnnotationReviewResult, AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore, StoredReviewResult


class AnnotationReviewWidget(QWidget):
    """Own review display, single-flight lifecycle, and stale-result rejection.

    This widget has no annotation write operation. Saved results survive image
    selection; matching the current fingerprint protects against annotation edits.
    """

    review_result_saved = Signal(int)
    result_displayed = Signal(object)
    annotations_changed = Signal(int)
    running_status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service: AnnotationReviewService | None = None
        self._store: AnnotationReviewStore | None = None
        self._manager: WorkerManager | None = None
        self._image_id: int | None = None
        self._generation = 0
        self._inflight_id: str | None = None
        self._closing = False
        self._unavailable_reason: str | None = None
        self._saved: StoredReviewResult | None = None
        self._adoption: AnnotationReviewAdoptionService | None = None
        self._load_id: str | None = None
        self._load_sequence = 0
        self._load_pending = False
        self._build_ui()
        self.set_image(None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, theme.SPACE_1, 0, theme.SPACE_1)
        layout.setSpacing(theme.SPACE_1)
        header = QHBoxLayout()
        title = QLabel("アノテーションチェック", self)
        title.setStyleSheet(f"font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
        header.addWidget(title, 1)
        self.evaluate_button = QPushButton("この画像をチェック", self)
        self.evaluate_button.setObjectName("buttonReviewAnnotations")
        self.evaluate_button.setToolTip(
            "選択画像と既存の有効なタグ・キャプションをローカルの Clef で評価します。"
        )
        self.evaluate_button.clicked.connect(self._on_evaluate_requested)
        header.addWidget(self.evaluate_button)
        self.cancel_button = QPushButton("中止", self)
        self.cancel_button.clicked.connect(self._on_cancel_requested)
        self.cancel_button.setVisible(False)
        header.addWidget(self.cancel_button)
        layout.addLayout(header)
        self.scope_label = QLabel(self)
        self.scope_label.setTextFormat(Qt.TextFormat.PlainText)
        self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setObjectName("labelAnnotationReviewStatus")
        layout.addWidget(self.status_label)
        self.notice_label = QLabel(
            "ローカルの Clef でチェックします。画像は外部へ送信されません。"
            "初回のモデル読み込みには時間がかかります。"
            "必要なファイルは「設定 → 基本設定 → Clef（ローカル）」で選択してください。",
            self,
        )
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
        self.suggestions_label = QLabel(
            "未付与候補の判定 —「追加候補」のタグを選んで手動で採用できます。", self
        )
        self.suggestions_label.setVisible(False)
        layout.addWidget(self.suggestions_label)
        self.suggestions_table = QTableWidget(0, 4, self)
        self.suggestions_table.setObjectName("tableAnnotationReviewSuggestions")
        self.suggestions_table.setHorizontalHeaderLabels(["未付与タグ", "Clef 一致確率", "判定", "操作"])
        self.suggestions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.suggestions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.suggestions_table.setMaximumHeight(180)
        self.suggestions_table.setVisible(False)
        layout.addWidget(self.suggestions_table)
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
            manager = self._manager
            owner_ref = ref(self)

            def stop_on_destroy() -> None:
                owner = owner_ref()
                if owner is not None:
                    owner._closing = True
                manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

            self.destroyed.connect(stop_on_destroy)
        self.set_image(self._image_id)

    def set_unavailable_reason(self, reason: str) -> None:
        """Explain an optional configuration error without breaking the search tab."""
        self._service = None
        self._unavailable_reason = reason
        self.set_image(self._image_id)
        self.setVisible(True)

    def set_store(self, store: AnnotationReviewStore) -> None:
        """Restore the project's saved result when returning to an image."""
        self._store = store
        self._restore_saved_result()

    def set_adoption_service(self, service: AnnotationReviewAdoptionService) -> None:
        self._adoption = service

    @Slot(object)
    def set_image(self, image_id: int | None) -> None:
        """Invalidate even same-image reloads so annotation edits cannot retain results."""
        self._generation += 1
        self._image_id = image_id
        self._saved = None
        self.result_displayed.emit(None)
        self.suggestions_table.setRowCount(0)
        self.suggestions_table.setVisible(False)
        self.suggestions_label.setVisible(False)
        self.scope_label.setText(
            f"対象: 表示中の画像 1 枚（ID: {image_id}）。ステージ済み画像は含みません。"
            if image_id is not None
            else "対象: 画像を選択してください。"
        )
        if self._manager is not None and self._inflight_id is not None:
            self._manager.request_cancel_worker(self._inflight_id, reason=CancelReason.USER_REQUESTED)
        self.results_table.setRowCount(0)
        self.results_table.setVisible(False)
        self.model_label.clear()
        self.model_label.setVisible(False)
        self.cancel_button.setVisible(False)
        self._show_idle_state()
        self._restore_saved_result()

    def _restore_saved_result(self) -> bool:
        if (
            self._store is None
            or self._service is None
            or self._image_id is None
            or self._closing
            or self._manager is None
        ):
            return False
        if self._load_id is not None:
            self._load_pending = True
            self._manager.request_cancel_worker(self._load_id, reason=CancelReason.USER_REQUESTED)
            return True
        self._load_sequence += 1
        self._load_id = f"saved_review_{id(self)}_{self._load_sequence}"
        worker = SavedImageReviewWorker(self._service, self._store, self._image_id, self._generation)
        if not self._manager.start_worker(self._load_id, worker):
            self._load_id = None
            self._set_status("保存済みのチェック結果を読み込めませんでした。", theme.WARN)
            return False
        return True

    @Slot()
    def refresh_saved_result(self) -> None:
        self._saved = None
        self.result_displayed.emit(None)
        self.results_table.setRowCount(0)
        self.results_table.setVisible(False)
        self.model_label.setVisible(False)
        if self._inflight_id is None:
            self._set_status("保存済みの判定を照合中…", theme.INK_SOFT)
        self.suggestions_table.setVisible(False)
        self.suggestions_label.setVisible(False)
        self._restore_saved_result()

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
            message = "未チェック —「この画像をチェック」で開始します。処理中も他の画像を操作できます。"
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
        self._saved = None
        self.result_displayed.emit(None)
        self.suggestions_table.setRowCount(0)
        self.suggestions_table.setVisible(False)
        self.suggestions_label.setVisible(False)
        self.results_table.setRowCount(0)
        self.results_table.setVisible(False)
        self.model_label.setVisible(False)
        self._inflight_id = f"annotation_review_{id(self)}_{self._generation}"
        self._set_status("ローカルの Clef で評価中… 初回はモデル読み込みに時間がかかります。", theme.INFO)
        self.running_status_changed.emit(f"アノテーションチェック: 画像 {self._image_id} を処理中")
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self._update_button_state()
        worker = AnnotationReviewWorker(self._service, self._image_id, self._generation, store=self._store)
        if not self._manager.start_worker(self._inflight_id, worker):
            self._inflight_id = None
            self.running_status_changed.emit("")
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
        self.running_status_changed.emit("アノテーションチェック: 停止中")

    @Slot(object)
    def _on_worker_terminal(self, event: WorkerTerminalEvent) -> None:
        if event.worker_id == self._load_id:
            self._load_id = None
            if self._load_pending and not self._closing:
                self._load_pending = False
                self._restore_saved_result()
            else:
                self._accept_saved_review(event)
            return
        if event.worker_id != self._inflight_id:
            return
        worker_generation = int(event.worker_id.rsplit("_", 1)[1])
        self._inflight_id = None
        self.running_status_changed.emit("")
        if isinstance(event.result, AnnotationReviewWorkerResult) and self._store is not None:
            self.review_result_saved.emit(event.result.review.image_id)
        if self._closing:
            return
        self.cancel_button.setVisible(False)
        self._update_button_state()
        if worker_generation != self._generation:
            self._show_idle_state()
            self._restore_saved_result()
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

    def _accept_saved_review(self, event: WorkerTerminalEvent) -> None:
        self._load_id = None
        loaded = event.result
        if self._closing or not isinstance(loaded, SavedImageReview):
            if not self._closing and event.outcome == WorkerOutcome.FAILED:
                self._set_status("保存済みのチェック結果を読み込めませんでした。", theme.WARN)
            return
        if loaded.generation == self._generation and loaded.image_id == self._image_id:
            self._saved = loaded.saved
            if loaded.saved is not None and self._inflight_id is None:
                self._display_result(loaded.saved.review)
            elif self._inflight_id is None:
                self._show_idle_state()
        return

    def _accept_review_result(self, result: AnnotationReviewWorkerResult) -> None:
        """Apply only a result whose generation, image, and DB fingerprint still match."""
        if result.generation != self._generation or result.review.image_id != self._image_id:
            self._show_idle_state()
            return
        service = self._service
        if service is None or self._image_id is None:
            return
        if self._store is not None:
            if not self._restore_saved_result():
                self._set_status("確認は終了しましたが、保存結果を表示できませんでした。", theme.WARN)
        else:
            self._display_result(result.review)

    def _display_result(self, result: AnnotationReviewResult) -> None:
        self.result_displayed.emit(result)
        self.suggestions_table.setRowCount(0)
        self.suggestions_table.setVisible(False)
        self.suggestions_label.setVisible(False)
        if result.status == "stale":
            self.results_table.setRowCount(0)
            self.results_table.setVisible(False)
            self.model_label.setVisible(False)
            self._set_status(
                "古い判定 — 内容や設定が変更されました。もう一度チェックしてください。", theme.WARN
            )
            return
        statuses = {
            "ok": ("警告なし", theme.INK),
            "warning": ("⚠ 要確認", theme.WARN),
            "failed": ("評価失敗", theme.ERR),
            "unevaluated": ("未評価", theme.INK_FAINT),
        }
        existing_items = tuple(item for item in result.items if item.kind != "suggestion")
        self.results_table.setRowCount(len(existing_items))
        for row, review_item in enumerate(existing_items):
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
        self._display_suggestions(result)
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
        elif result.status == "unevaluated" or not result.items:
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

    def _display_suggestions(self, result: AnnotationReviewResult) -> None:
        suggestions = tuple(item for item in result.items if item.kind == "suggestion")
        self.suggestions_table.setRowCount(len(suggestions))
        for row, item in enumerate(suggestions):
            self.suggestions_table.setItem(row, 0, QTableWidgetItem(item.text))
            self.suggestions_table.setItem(
                row, 1, QTableWidgetItem(f"{item.probability:.1%}" if item.probability is not None else "—")
            )
            state = {
                "suggestion": "追加候補",
                "ok": "候補外",
                "failed": "評価失敗",
                "unevaluated": "未評価",
            }.get(item.status, "未評価")
            self.suggestions_table.setItem(row, 2, QTableWidgetItem(state))
            button = QPushButton("採用", self.suggestions_table)
            button.setEnabled(
                self._adoption is not None and self._saved is not None and item.status == "suggestion"
            )
            button.clicked.connect(
                lambda checked=False, candidate_id=item.candidate_id: self._adopt_candidate(candidate_id)
            )
            self.suggestions_table.setCellWidget(row, 3, button)
        self.suggestions_table.setVisible(bool(suggestions))
        self.suggestions_label.setVisible(bool(suggestions))

    def _adopt_candidate(self, candidate_id: str) -> None:
        if self._adoption is None or self._saved is None or self._image_id is None:
            return
        if not self._adoption.adopt(self._image_id, candidate_id, self._saved.checked_at):
            self._set_status(
                "採用できませんでした — 内容が変わっていないか、再チェックしてください。", theme.WARN
            )
            self.refresh_saved_result()
            return
        self.annotations_changed.emit(self._image_id)
        self.refresh_saved_result()

    def shutdown(self) -> None:
        """Stop boundedly and let WorkerManager safely retain an unresponsive thread."""
        if self._closing:
            return
        self._closing = True
        self._load_pending = False
        self.running_status_changed.emit("")
        self._generation += 1
        self._update_button_state()
        if self._manager is not None:
            self._manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)
