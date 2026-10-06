"""Run explicit Clef checks for a frozen selection and browse saved warnings."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from weakref import ref

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.annotation_review_store import StoredReviewResult
from .. import theme
from ..workers.annotation_review_batch_worker import (
    AnnotationReviewBatchImageResult,
    AnnotationReviewBatchWorker,
    AnnotationReviewBatchWorkerResult,
)
from ..workers.annotation_review_results_loader import (
    AnnotationReviewResultsLoaded,
    AnnotationReviewResultsLoader,
)
from ..workers.base import WorkerProgress
from ..workers.manager import WorkerManager
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore


class AnnotationReviewBatchWidget(QGroupBox):
    """Keep active scope independent of staging and saved results independent of selection."""

    manual_review_requested = Signal(int)

    MAX_IMAGES = 500

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("アノテーション確認", parent)
        self._service: AnnotationReviewService | None = None
        self._store: AnnotationReviewStore | None = None
        self._manager: WorkerManager | None = None
        self._image_ids: tuple[int, ...] = ()
        self._running_image_ids: tuple[int, ...] = ()
        self._generation = 0
        self._inflight_id: str | None = None
        self._worker: AnnotationReviewBatchWorker | None = None
        self._cancel_requested = False
        self._load_inflight_id: str | None = None
        self._load_sequence = 0
        self._load_pending = False
        self._results_revision = 0
        self._loading_currentness = False
        self._fresh_image_ids: set[int] = set()
        self._processed_ids: set[int] = set()
        self._unsaved_image_ids: set[int] = set()
        self._saved_results: dict[int, StoredReviewResult] = {}
        self._selected_image_id: int | None = None
        self._closing = False
        self._unavailable_reason: str | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(100)
        self._render_timer.timeout.connect(self._render_results)
        self._build_ui()
        self._update_controls()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(theme.SPACE_1)
        run_bar = QHBoxLayout()
        self.scope_label = QLabel(self)
        self.scope_label.setWordWrap(True)
        run_bar.addWidget(self.scope_label, 1)
        self.start_button = QPushButton("ステージ済み画像を確認", self)
        self.start_button.setObjectName("buttonStartAnnotationReviewBatch")
        self.start_button.clicked.connect(self._on_start_requested)
        run_bar.addWidget(self.start_button)
        self.cancel_button = QPushButton("中止", self)
        self.cancel_button.clicked.connect(self._on_cancel_requested)
        self.cancel_button.setVisible(False)
        run_bar.addWidget(self.cancel_button)
        layout.addLayout(run_bar)
        notice = QLabel(
            "開始時の画像・有効なタグ・キャプションを Cloudflare に送信します。"
            "結果は画像ごとに保存されます。警告は手動で確認してください。",
            self,
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(notice)
        self.status_label = QLabel("未実行 — ステージ済み画像を確認できます。", self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.history_label = QLabel("保存済みの確認結果はありません。", self)
        layout.addWidget(self.history_label)
        self.results_table = QTableWidget(0, 5, self)
        self.results_table.setObjectName("tableAnnotationReviewBatchResults")
        self.results_table.setHorizontalHeaderLabels(["画像", "状態", "要確認", "失敗・未評価", "確認日時"])
        self._configure_table(self.results_table)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setMinimumHeight(100)
        self.results_table.setMaximumHeight(210)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.cellDoubleClicked.connect(self._on_result_double_clicked)
        layout.addWidget(self.results_table)
        details_bar = QHBoxLayout()
        self.detail_label = QLabel("画像を選ぶと、タグ・キャプションごとの結果を表示します。", self)
        self.detail_label.setWordWrap(True)
        details_bar.addWidget(self.detail_label, 1)
        self.manual_review_button = QPushButton("画像を開いて手動確認", self)
        self.manual_review_button.setEnabled(False)
        self.manual_review_button.clicked.connect(self._on_manual_review_requested)
        details_bar.addWidget(self.manual_review_button)
        layout.addLayout(details_bar)
        self.details_table = QTableWidget(0, 4, self)
        self.details_table.setObjectName("tableAnnotationReviewBatchItems")
        self.details_table.setHorizontalHeaderLabels(["種類", "既存の内容", "判定", "Clef 一致確率"])
        self._configure_table(self.details_table)
        self.details_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.details_table.setMinimumHeight(95)
        self.details_table.setMaximumHeight(170)
        self.details_table.setVisible(False)
        layout.addWidget(self.details_table)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def set_services(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        worker_manager: WorkerManager | None = None,
        *,
        load_history: bool = True,
    ) -> None:
        """Reload settings without accepting a result from the previous configuration."""
        self._generation += 1
        self._request_cancel()
        self._service = service
        self._store = store
        self._unavailable_reason = None
        self._saved_results.clear()
        self._unsaved_image_ids.clear()
        self._render_results()
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

            # QObject emits destroyed before destroying child managers. No widget
            # method is called here, so deletion also drains or parks live threads.
            self.destroyed.connect(stop_on_destroy)
        if load_history:
            self.refresh()
        self._update_controls()

    def set_unavailable_reason(self, reason: str) -> None:
        self._generation += 1
        self._request_cancel()
        self._service = None
        self._unavailable_reason = reason
        self._loading_currentness = False
        self._saved_results = {
            image_id: replace(
                saved,
                review=replace(
                    saved.review,
                    status="stale",
                    items=tuple(
                        replace(item, probability=None, status="unevaluated") for item in saved.review.items
                    ),
                ),
            )
            for image_id, saved in self._saved_results.items()
        }
        self._render_results()
        self.status_label.setText(f"設定を確認してください: {reason}")
        self._update_controls()

    @Slot(list)
    def set_image_ids(self, image_ids: list[int]) -> None:
        """Update the next run's scope; never mutate or cancel the active scope."""
        self._image_ids = tuple(dict.fromkeys(image_ids))
        self._update_controls()

    def _update_controls(self) -> None:
        active = self._inflight_id is not None
        if active:
            self.scope_label.setText(
                f"確認対象 {len(self._running_image_ids)} 枚（開始時に固定）"
                f" / 現在のステージ {len(self._image_ids)} 枚"
            )
        else:
            self.scope_label.setText(f"ステージ済み {len(self._image_ids)} 枚")
        self.start_button.setEnabled(
            not self._closing
            and not active
            and self._service is not None
            and self._store is not None
            and 0 < len(self._image_ids) <= self.MAX_IMAGES
        )
        if len(self._image_ids) > self.MAX_IMAGES and not active:
            self.status_label.setText(f"一度に確認できる画像は {self.MAX_IMAGES} 枚までです。")
        self.cancel_button.setVisible(active)

    @Slot()
    def _on_start_requested(self) -> None:
        if (
            self._closing
            or self._inflight_id is not None
            or self._service is None
            or self._store is None
            or self._manager is None
            or not 0 < len(self._image_ids) <= self.MAX_IMAGES
        ):
            return
        self._generation += 1
        self._running_image_ids = self._image_ids
        self._processed_ids.clear()
        self._inflight_id = f"annotation_review_batch_{id(self)}_{self._generation}"
        worker = AnnotationReviewBatchWorker(
            self._service, self._store, self._running_image_ids, self._generation
        )
        self._worker = worker
        self._cancel_requested = False
        worker.per_image_finished.connect(self._on_image_finished)
        worker.progress_updated.connect(self._on_progress)
        self.progress_bar.setRange(0, len(self._running_image_ids))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("確認対象を準備しています…")
        self._update_controls()
        if not self._manager.start_worker(self._inflight_id, worker):
            self._inflight_id = None
            self._worker = None
            self.progress_bar.setVisible(False)
            self.status_label.setText("確認を開始できませんでした。もう一度お試しください。")
            self._update_controls()

    def _request_cancel(self) -> None:
        if self._manager is not None and self._inflight_id is not None:
            self._cancel_requested = True
            self._manager.request_cancel_worker(self._inflight_id, reason=CancelReason.USER_REQUESTED)

    @Slot()
    def _on_cancel_requested(self) -> None:
        self._request_cancel()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("確認を停止しています… 保存済みの結果は保持されます。")

    @Slot(object)
    def _on_progress(self, progress: WorkerProgress) -> None:
        if self._closing or self._inflight_id is None or self.sender() is not self._worker:
            return
        self.progress_bar.setValue(progress.processed_count)
        if not self._cancel_requested:
            self.status_label.setText(progress.status_message)

    @Slot(object)
    def _on_image_finished(self, result: AnnotationReviewBatchImageResult) -> None:
        if self._closing or result.generation != self._generation or self._inflight_id is None:
            return
        if result.review.image_id not in self._running_image_ids:
            return
        self._processed_ids.add(result.review.image_id)
        self._results_revision += 1
        done = len(self._processed_ids)
        self.progress_bar.setValue(done)
        self.status_label.setText(
            f"{'確認を停止しています…' if self._cancel_requested else '確認中…'}"
            f" {done} / {len(self._running_image_ids)} 枚を処理しました。"
        )
        if self._store is not None and self._service is not None:
            # The worker supplies a saved result whose fingerprint/settings were
            # checked in its thread. Streaming does no GUI-thread DB or file IO.
            saved = result.stored
            if result.saved:
                self._unsaved_image_ids.discard(result.review.image_id)
            else:
                self._unsaved_image_ids.add(result.review.image_id)
            if saved is None:
                review = result.review
                if result.saved:
                    review = replace(
                        review,
                        status="stale",
                        items=tuple(
                            replace(item, probability=None, status="unevaluated") for item in review.items
                        ),
                    )
                else:
                    review = replace(
                        review,
                        items=tuple(
                            replace(item, probability=None, status="failed") for item in review.items
                        ),
                    )
                saved = StoredReviewResult(review, self._service.warning_threshold, datetime.now(UTC))
            self._saved_results[result.review.image_id] = saved
            self._fresh_image_ids.add(result.review.image_id)
            if not self._render_timer.isActive():
                self._render_timer.start()

    @Slot(object)
    def _on_worker_terminal(self, event: WorkerTerminalEvent) -> None:
        if event.worker_id == self._load_inflight_id:
            self._on_load_terminal(event)
            return
        if event.worker_id != self._inflight_id:
            return
        generation = int(event.worker_id.rsplit("_", 1)[1])
        self._inflight_id = None
        self._worker = None
        if self._closing:
            return
        self._update_controls()
        self.refresh()
        if generation != self._generation:
            self.status_label.setText("設定を更新しました。保存済みの結果を現在の内容と照合しました。")
        elif event.outcome == WorkerOutcome.CANCELED:
            self.status_label.setText("確認を中止しました。保存済みの結果は保持されています。")
        elif event.outcome != WorkerOutcome.SUCCEEDED:
            self.status_label.setText(f"確認に失敗しました: {event.error or '結果を取得できません。'}")
        elif not isinstance(event.result, AnnotationReviewBatchWorkerResult):
            self.status_label.setText("確認結果を読み取れませんでした。保存結果を再読み込みしてください。")
        else:
            result = event.result
            processed_count = result.processed_count
            done = processed_count if processed_count is not None else len(result.reviews)
            self.progress_bar.setValue(done)
            if result.cancelled:
                self.status_label.setText(
                    f"確認を中止しました — {done} 枚を処理しました。保存済みの結果は保持されています。"
                )
            else:
                self.status_label.setText(
                    f"確認が終了しました — {done} / {len(result.image_ids)} 枚。"
                    "警告・失敗・未評価の画像を確認してください。"
                )

    def refresh(self) -> None:
        """Read latest saved results, including images removed from staging."""
        if self._store is None or self._service is None or self._manager is None or self._closing:
            return
        if self._load_inflight_id is not None:
            self._load_pending = True
            return
        self._load_sequence += 1
        self._loading_currentness = True
        self._fresh_image_ids.clear()
        self._render_results()
        self._load_inflight_id = f"annotation_review_results_load_{id(self)}_{self._load_sequence}"
        loader = AnnotationReviewResultsLoader(
            self._service, self._store, self._generation, self._results_revision, self.MAX_IMAGES
        )
        if not self._manager.start_worker(self._load_inflight_id, loader):
            self._load_inflight_id = None
            self.history_label.setText("保存済みの確認結果を読み込めませんでした。")

    def _on_load_terminal(self, event: WorkerTerminalEvent) -> None:
        self._load_inflight_id = None
        if self._closing:
            return
        loaded = event.result
        if event.outcome == WorkerOutcome.SUCCEEDED and isinstance(loaded, AnnotationReviewResultsLoaded):
            if loaded.generation == self._generation:
                self._merge_loaded_results(loaded)
                self._loading_currentness = False
                self._render_results()
            else:
                self._load_pending = True
        elif event.outcome != WorkerOutcome.CANCELED:
            self.history_label.setText("保存済みの確認結果を読み込めませんでした。再表示してください。")
        if self._load_pending:
            self._load_pending = False
            self.refresh()

    def _merge_loaded_results(self, loaded: AnnotationReviewResultsLoaded) -> None:
        saved = loaded.results.copy()
        # Keep newer live rows when a history read started before their review
        # finished, and retain deleted-image failures that cannot be in the DB.
        retained = self._unsaved_image_ids.copy()
        if loaded.revision != self._results_revision:
            retained.update(self._processed_ids)
        saved.update(
            {
                image_id: self._saved_results[image_id]
                for image_id in retained
                if image_id in self._saved_results
            }
        )
        self._saved_results = saved

    @Slot()
    def _render_results(self) -> None:
        if self._closing:
            return
        self._render_timer.stop()
        saved = self._saved_results
        selected = self._selected_image_id
        records = sorted(
            saved.values(),
            key=lambda result: (
                result.checked_at.replace(tzinfo=UTC)
                if result.checked_at.tzinfo is None
                else result.checked_at
            ).timestamp(),
            reverse=True,
        )
        # The run limit also bounds the result table; older per-image results stay
        # in the project DB and remain available in each image's details panel.
        records = records[: self.MAX_IMAGES]
        self._saved_results = {record.review.image_id: record for record in records}
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(records))
        selected_row: int | None = None
        for row, record in enumerate(records):
            record = self._record_for_display(record)
            review = record.review
            label, color = self._review_state(record)
            if self._loading_currentness and review.image_id not in self._fresh_image_ids:
                label, color = "現在の内容と照合中…", theme.INK_SOFT
            if review.image_id in self._unsaved_image_ids:
                label, color = "画像なし — 結果を保存できません", theme.ERR
            warnings = sum(item.status == "warning" for item in review.items)
            incomplete = sum(item.status in ("failed", "unevaluated") for item in review.items)
            values = (
                f"画像 {review.image_id}",
                label,
                str(warnings) if review.status != "stale" else "—",
                str(incomplete),
                record.checked_at.strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, review.image_id)
                cell.setToolTip(review.error or label)
                if column in (1, 2, 3):
                    cell.setForeground(QColor(color))
                self.results_table.setItem(row, column, cell)
            if review.image_id == selected:
                selected_row = row
        self.results_table.blockSignals(False)
        self.history_label.setText(
            f"確認結果 {len(records)} 枚"
            + (f"（最新 {self.MAX_IMAGES} 枚を表示）" if len(records) == self.MAX_IMAGES else "")
            + (
                f" / 保存できなかった画像 {len(self._unsaved_image_ids)} 枚"
                if self._unsaved_image_ids
                else ""
            )
            + " — ステージから外した画像も保持されます。"
        )
        if selected_row is not None:
            self.results_table.selectRow(selected_row)
            self._show_selected_details()
        else:
            self._selected_image_id = None
            self._show_selected_details()

    @staticmethod
    def _review_state(record: StoredReviewResult) -> tuple[str, str]:
        review = record.review
        if review.status == "stale":
            return "内容・設定が変更 — 再確認が必要", theme.WARN
        if review.status == "failed":
            return "確認失敗", theme.ERR
        if review.status in ("partial", "cancelled"):
            return "中止・一部未評価" if review.status == "cancelled" else "一部未評価", theme.WARN
        if review.status == "unevaluated":
            return "未評価", theme.INK_SOFT
        if any(item.status == "warning" for item in review.items):
            return "⚠ 要確認", theme.WARN
        return "目安内", theme.INK

    def _record_for_display(self, record: StoredReviewResult) -> StoredReviewResult:
        """Hide a cached score until its current fingerprint has been checked."""
        if (
            not self._loading_currentness
            or record.review.image_id in self._fresh_image_ids
            or record.review.image_id in self._unsaved_image_ids
        ):
            return record
        return replace(
            record,
            review=replace(
                record.review,
                status="stale",
                items=tuple(
                    replace(item, probability=None, status="unevaluated") for item in record.review.items
                ),
            ),
        )

    @Slot()
    def _on_selection_changed(self) -> None:
        rows = self.results_table.selectionModel().selectedRows()
        cell = self.results_table.item(rows[0].row(), 0) if rows else None
        self._selected_image_id = int(cell.data(Qt.ItemDataRole.UserRole)) if cell is not None else None
        self._show_selected_details()

    def _show_selected_details(self) -> None:
        record = self._saved_results.get(self._selected_image_id) if self._selected_image_id else None
        self.manual_review_button.setEnabled(
            record is not None and self._selected_image_id not in self._unsaved_image_ids
        )
        if record is None:
            self.detail_label.setText("画像を選ぶと、タグ・キャプションごとの結果を表示します。")
            self.details_table.setRowCount(0)
            self.details_table.setVisible(False)
            return
        record = self._record_for_display(record)
        review = record.review
        self.detail_label.setText(
            f"画像 {review.image_id} / {review.model_name}"
            f" / 要確認: 一致確率 {record.warning_threshold:.0%} 未満"
            + (
                "\n現在の内容と照合しています。"
                if self._loading_currentness and review.image_id not in self._fresh_image_ids
                else "\n内容・設定が変わったため、過去の確率は表示していません。"
                if review.status == "stale"
                else ""
            )
        )
        labels = {"ok": "目安内", "warning": "⚠ 要確認", "failed": "確認失敗", "unevaluated": "未評価"}
        self.details_table.setRowCount(len(review.items))
        for row, result in enumerate(review.items):
            values = (
                "タグ" if result.kind == "tag" else "キャプション",
                result.text,
                labels[result.status],
                f"{result.probability:.1%}" if result.probability is not None else "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(result.error or result.text)
                if result.status == "warning":
                    cell.setForeground(QColor(theme.WARN))
                self.details_table.setItem(row, column, cell)
        self.details_table.resizeRowsToContents()
        self.details_table.setVisible(bool(review.items))

    @Slot()
    def _on_manual_review_requested(self) -> None:
        if self._selected_image_id is not None and self._selected_image_id not in self._unsaved_image_ids:
            self.manual_review_requested.emit(self._selected_image_id)

    @Slot(int, int)
    def _on_result_double_clicked(self, row: int, _column: int) -> None:
        cell = self.results_table.item(row, 0)
        if cell is not None:
            image_id = int(cell.data(Qt.ItemDataRole.UserRole))
            if image_id not in self._unsaved_image_ids:
                self.manual_review_requested.emit(image_id)

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._render_timer.stop()
        self._generation += 1
        self._update_controls()
        if self._manager is not None:
            self._manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)
