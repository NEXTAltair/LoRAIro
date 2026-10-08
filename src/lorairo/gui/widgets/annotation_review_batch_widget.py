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
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.annotation_review_service import ReviewCandidateSource
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
    target_selection_requested = Signal()
    target_list_requested = Signal()
    running_status_changed = Signal(str)
    review_result_saved = Signal(int)

    MAX_IMAGES = 500

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("アノテーションチェック", parent)
        self._service: AnnotationReviewService | None = None
        self._store: AnnotationReviewStore | None = None
        self._manager: WorkerManager | None = None
        self._image_ids: tuple[int, ...] = ()
        self._running_image_ids: tuple[int, ...] = ()
        self._image_names: dict[int, str] = {}
        self._running_image_names: dict[int, str] = {}
        self._running_candidate_source: ReviewCandidateSource | None = None
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
        layout.setSpacing(theme.SPACE_2)
        self.instructions_label = QLabel(
            "1. 対象を準備: 検索で画像を選択 →「選択をステージングへ」→ 対象一覧を確認\n"
            "2. この画面で「チェックを実行」を押して、画像とアノテーションの一致を確認",
            self,
        )
        self.instructions_label.setWordWrap(True)
        layout.addWidget(self.instructions_label)
        target_bar = QHBoxLayout()
        self.scope_label = QLabel(self)
        self.scope_label.setWordWrap(True)
        self.scope_label.setStyleSheet(f"font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
        target_bar.addWidget(self.scope_label, 1)
        self.select_targets_button = QPushButton("検索で対象画像を選ぶ", self)
        self.select_targets_button.clicked.connect(self.target_selection_requested)
        target_bar.addWidget(self.select_targets_button)
        self.target_list_button = QPushButton("対象一覧を開く", self)
        self.target_list_button.setToolTip("アノテーション画面でステージした画像を確認・削除できます。")
        self.target_list_button.clicked.connect(self.target_list_requested)
        target_bar.addWidget(self.target_list_button)
        layout.addLayout(target_bar)
        self.start_button = QPushButton("チェックを実行", self)
        self.start_button.setObjectName("buttonStartAnnotationReviewBatch")
        self.start_button.setStyleSheet(
            f"QPushButton:enabled {{ background: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border-color: {theme.ACCENT}; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
            f"QPushButton:enabled:hover {{ background: {theme.ACCENT_HOVER}; }}"
        )
        self.start_button.clicked.connect(self._on_start_requested)
        self.cancel_button = QPushButton("中止", self)
        self.cancel_button.clicked.connect(self._on_cancel_requested)
        self.cancel_button.setVisible(False)
        self.target_names_label = QLabel(self)
        self.target_names_label.setTextFormat(Qt.TextFormat.PlainText)
        self.target_names_label.setWordWrap(True)
        self.target_names_label.setStyleSheet(f"color: {theme.INK_SOFT};")
        layout.addWidget(self.target_names_label)
        self._build_candidate_controls(layout)
        self.notice_label = QLabel(
            "ローカルの Clef でチェックします。画像は外部へ送信されません。"
            "必要なファイルは「設定 → 基本設定 → Clef（ローカル）」で選択してください。"
            "初回のモデル読み込みには時間がかかります。バックグラウンドで進むため、他のタブで作業できます。"
            "実行時の対象と候補条件は固定されます。結果は保存され、タグ・キャプションは自動では変更されません。",
            self,
        )
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(self.notice_label)
        run_bar = QHBoxLayout()
        run_bar.addWidget(self.start_button)
        run_bar.addWidget(self.cancel_button)
        run_bar.addStretch(1)
        layout.addLayout(run_bar)
        self.status_label = QLabel("未実行 — 対象画像を準備してから、チェックを実行してください。", self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.history_label = QLabel("保存済みのチェック結果はありません。", self)
        layout.addWidget(self.history_label)
        self.results_table = QTableWidget(0, 6, self)
        self.results_table.setObjectName("tableAnnotationReviewBatchResults")
        self.results_table.setHorizontalHeaderLabels(
            ["画像", "状態", "要確認", "追加候補", "失敗・未評価", "チェック日時"]
        )
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
        self.details_table.setHorizontalHeaderLabels(["種類", "内容・追加候補", "判定", "Clef 一致確率"])
        self._configure_table(self.details_table)
        self.details_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.details_table.setMinimumHeight(95)
        self.details_table.setMaximumHeight(170)
        self.details_table.setVisible(False)
        layout.addWidget(self.details_table)

    def _build_candidate_controls(self, layout: QVBoxLayout) -> None:
        self.candidate_checkbox = QCheckBox("タグの追加候補も探す", self)
        self.candidate_checkbox.setObjectName("checkBoxAnnotationReviewCandidates")
        self.candidate_checkbox.toggled.connect(self._on_candidate_options_changed)
        layout.addWidget(self.candidate_checkbox)
        candidate_row = QHBoxLayout()
        candidate_row.addWidget(QLabel("キーワード", self))
        self.candidate_keyword_edit = QLineEdit(self)
        self.candidate_keyword_edit.setObjectName("lineEditAnnotationReviewCandidateKeyword")
        self.candidate_keyword_edit.setPlaceholderText("例: hair")
        self.candidate_keyword_edit.textChanged.connect(self._on_candidate_options_changed)
        candidate_row.addWidget(self.candidate_keyword_edit, 1)
        candidate_row.addWidget(QLabel("関連タグ (AND)", self))
        self.candidate_tags_edit = QLineEdit(self)
        self.candidate_tags_edit.setObjectName("lineEditAnnotationReviewCandidateTags")
        self.candidate_tags_edit.setPlaceholderText("例: 1girl, portrait")
        self.candidate_tags_edit.setToolTip(
            "カンマ区切りの関連タグすべてと共起するタグから候補を探します。"
        )
        self.candidate_tags_edit.textChanged.connect(self._on_candidate_options_changed)
        candidate_row.addWidget(self.candidate_tags_edit, 1)
        candidate_row.addWidget(QLabel("候補上限", self))
        self.candidate_limit_spin = QSpinBox(self)
        self.candidate_limit_spin.setObjectName("spinBoxAnnotationReviewCandidateLimit")
        self.candidate_limit_spin.setRange(1, 64)
        self.candidate_limit_spin.setValue(32)
        candidate_row.addWidget(self.candidate_limit_spin)
        layout.addLayout(candidate_row)
        self.candidate_help_label = QLabel(self)
        self.candidate_help_label.setWordWrap(True)
        self.candidate_help_label.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        layout.addWidget(self.candidate_help_label)
        self._update_candidate_help()

    def _update_candidate_help(self) -> None:
        threshold = getattr(self._service, "suggestion_threshold", 0.8)
        if not isinstance(threshold, int | float):
            threshold = 0.8
        self.candidate_help_label.setText(
            "キーワードまたは関連タグを指定してください。既存タグを除く候補を評価し、"
            f"一致確率 {threshold:.0%} 以上を「追加候補」として表示します。"
            "採用は画像を開いて手動で行います。"
        )

    def _candidate_source(self) -> ReviewCandidateSource | None:
        """Return the explicitly selected candidate conditions for the next run."""
        if not self.candidate_checkbox.isChecked():
            return None
        keyword = self.candidate_keyword_edit.text().strip()
        selected_tags = tuple(
            dict.fromkeys(tag.strip() for tag in self.candidate_tags_edit.text().split(",") if tag.strip())
        )
        if not keyword and not selected_tags:
            raise ValueError("追加候補を探すには、キーワードまたは関連タグを指定してください。")
        return ReviewCandidateSource(keyword, selected_tags, self.candidate_limit_spin.value())

    @Slot()
    def _on_candidate_options_changed(self) -> None:
        self._update_controls()

    def _set_running_status(self, message: str) -> None:
        """Publish active progress so it remains visible when this tab is hidden."""
        self.status_label.setText(message)
        self.running_status_changed.emit(f"アノテーションチェック: {message}")

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
        self._update_candidate_help()
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

    def set_image_names(self, image_names: dict[int, str]) -> None:
        """Display staged filenames without reading images or querying the DB."""
        self._image_names = image_names.copy()
        self._update_controls()

    def _update_controls(self) -> None:
        active = self._inflight_id is not None
        if active:
            self.scope_label.setText(
                f"チェック対象 {len(self._running_image_ids)} 枚（実行時に固定）"
                f" / 現在のステージ {len(self._image_ids)} 枚"
            )
            self.start_button.setText(f"{len(self._running_image_ids)} 枚をチェック中")
        else:
            self.scope_label.setText(
                f"対象: ステージ済み {len(self._image_ids)} 枚"
                if self._image_ids
                else "対象: 0 枚 — 検索画面から画像を追加してください。"
            )
            self.start_button.setText("チェックを実行")
        displayed_ids = self._running_image_ids if active else self._image_ids
        names = self._running_image_names if active else self._image_names
        labels = [
            f"{names[image_id]} (ID: {image_id})" if names.get(image_id) else f"画像 {image_id}"
            for image_id in displayed_ids
        ]
        self.target_names_label.setText(
            "対象画像: "
            + " / ".join(labels[:3])
            + (f" / ほか {len(labels) - 3} 枚" if len(labels) > 3 else "")
            if labels
            else "現在の選択画像や、保存済み結果の画像は自動では対象に入りません。"
        )
        self.target_names_label.setToolTip("\n".join(labels))
        self.target_list_button.setEnabled(bool(self._image_ids))
        self.target_list_button.setText("次回の対象一覧を開く" if active else "対象一覧を開く")
        self.select_targets_button.setText("次回の対象画像を選ぶ" if active else "検索で対象画像を選ぶ")
        self.start_button.setToolTip("ステージに追加した画像をローカルの Clef でチェックします。")
        candidates_enabled = self.candidate_checkbox.isChecked()
        candidate_conditions_valid = not candidates_enabled or bool(
            self.candidate_keyword_edit.text().strip()
            or any(tag.strip() for tag in self.candidate_tags_edit.text().split(","))
        )
        self.candidate_checkbox.setEnabled(not active and not self._closing)
        for control in (self.candidate_keyword_edit, self.candidate_tags_edit, self.candidate_limit_spin):
            control.setEnabled(candidates_enabled and not active and not self._closing)
        if (
            self.status_label.text().startswith(
                ("未実行", "一度にチェックできる画像は", "追加候補を探すには")
            )
            and not active
        ):
            self.status_label.setText(
                f"未実行 — 対象 {len(self._image_ids)} 枚を確認して、「チェックを実行」を押してください。"
                if self._image_ids
                else "未実行 — 検索で画像を選び、「選択をステージングへ」で対象に追加してください。"
            )
        self.start_button.setEnabled(
            not self._closing
            and not active
            and self._service is not None
            and self._store is not None
            and 0 < len(self._image_ids) <= self.MAX_IMAGES
            and candidate_conditions_valid
        )
        if len(self._image_ids) > self.MAX_IMAGES and not active:
            self.status_label.setText(f"一度にチェックできる画像は {self.MAX_IMAGES} 枚までです。")
        elif not active and not candidate_conditions_valid:
            self.status_label.setText("追加候補を探すには、キーワードまたは関連タグを指定してください。")
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
        try:
            candidate_source = self._candidate_source()
        except ValueError as error:
            self.status_label.setText(str(error))
            return
        self._generation += 1
        self._running_image_ids = self._image_ids
        self._running_image_names = self._image_names.copy()
        self._running_candidate_source = candidate_source
        self._processed_ids.clear()
        self._inflight_id = f"annotation_review_batch_{id(self)}_{self._generation}"
        worker = AnnotationReviewBatchWorker(
            self._service,
            self._store,
            self._running_image_ids,
            self._generation,
            candidate_source=candidate_source,
        )
        self._worker = worker
        self._cancel_requested = False
        worker.per_image_finished.connect(self._on_image_finished)
        worker.progress_updated.connect(self._on_progress)
        self.progress_bar.setRange(0, len(self._running_image_ids))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self._set_running_status(
            f"準備中 — 対象 {len(self._running_image_ids)} 枚の画像とアノテーションを読み込んでいます。"
        )
        self._update_controls()
        if not self._manager.start_worker(self._inflight_id, worker):
            self._inflight_id = None
            self._worker = None
            self.progress_bar.setVisible(False)
            self.status_label.setText("チェックを開始できませんでした。もう一度お試しください。")
            self.running_status_changed.emit("")
            self._update_controls()

    def _request_cancel(self) -> None:
        if self._manager is not None and self._inflight_id is not None:
            self._cancel_requested = True
            self._manager.request_cancel_worker(self._inflight_id, reason=CancelReason.USER_REQUESTED)

    @Slot()
    def _on_cancel_requested(self) -> None:
        if self._closing or self._inflight_id is None:
            return
        self._request_cancel()
        self.cancel_button.setEnabled(False)
        self._set_running_status("チェックを停止しています… 保存済みの結果は保持されます。")

    @Slot(object)
    def _on_progress(self, progress: WorkerProgress) -> None:
        if self._closing or self._inflight_id is None or self.sender() is not self._worker:
            return
        self.progress_bar.setValue(progress.processed_count)
        if not self._cancel_requested:
            self._set_running_status(progress.status_message)

    @Slot(object)
    def _on_image_finished(self, result: AnnotationReviewBatchImageResult) -> None:
        if self._closing:
            return
        # A saved result can arrive after settings have changed. Other views
        # still need to invalidate their cached badges and recheck currentness.
        if result.saved:
            self.review_result_saved.emit(result.review.image_id)
        if result.generation != self._generation or self._inflight_id is None:
            return
        if result.review.image_id not in self._running_image_ids:
            return
        self._processed_ids.add(result.review.image_id)
        self._results_revision += 1
        done = len(self._processed_ids)
        self.progress_bar.setValue(done)
        self._set_running_status(
            f"{'チェックを停止しています…' if self._cancel_requested else 'チェック中…'}"
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
                saved = StoredReviewResult(
                    review,
                    self._service.warning_threshold,
                    datetime.now(UTC),
                    suggestion_threshold=review.suggestion_threshold,
                    candidate_source=review.candidate_source,
                )
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
        self.running_status_changed.emit("")
        if self._closing:
            return
        self._update_controls()
        self.refresh()
        if generation != self._generation:
            self.status_label.setText("設定を更新しました。保存済みの結果を現在の内容と照合しました。")
        elif event.outcome == WorkerOutcome.CANCELED:
            self.status_label.setText("チェックを中止しました。保存済みの結果は保持されています。")
        elif event.outcome != WorkerOutcome.SUCCEEDED:
            self.status_label.setText(f"チェックに失敗しました: {event.error or '結果を取得できません。'}")
        elif not isinstance(event.result, AnnotationReviewBatchWorkerResult):
            self.status_label.setText(
                "チェック結果を読み取れませんでした。保存結果を再読み込みしてください。"
            )
        else:
            result = event.result
            processed_count = result.processed_count
            done = processed_count if processed_count is not None else len(result.reviews)
            self.progress_bar.setValue(done)
            if result.cancelled:
                self.status_label.setText(
                    f"チェックを中止しました — {done} 枚を処理しました。保存済みの結果は保持されています。"
                )
            else:
                self.status_label.setText(
                    f"チェックが終了しました — {done} / {len(result.image_ids)} 枚。"
                    "警告・失敗・未評価の画像と追加候補を確認してください。"
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
            self.history_label.setText("保存済みのチェック結果を読み込めませんでした。")

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
            self.history_label.setText("保存済みのチェック結果を読み込めませんでした。再表示してください。")
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
            suggestions = sum(item.status == "suggestion" for item in review.items)
            incomplete = sum(item.status in ("failed", "unevaluated") for item in review.items)
            values = (
                f"画像 {review.image_id}",
                label,
                str(warnings) if review.status != "stale" else "—",
                str(suggestions) if review.status != "stale" else "—",
                str(incomplete),
                record.checked_at.strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, review.image_id)
                cell.setToolTip(review.error or label)
                if column in (1, 2, 4):
                    cell.setForeground(QColor(color))
                self.results_table.setItem(row, column, cell)
            if review.image_id == selected:
                selected_row = row
        self.results_table.blockSignals(False)
        self.history_label.setText(
            f"チェック結果 {len(records)} 枚"
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
            return "内容・設定が変更 — 再チェックが必要", theme.WARN
        if review.status == "failed":
            return "チェック失敗", theme.ERR
        if review.status in ("partial", "cancelled"):
            return "中止・一部未評価" if review.status == "cancelled" else "一部未評価", theme.WARN
        if review.status == "unevaluated":
            return "未評価", theme.INK_SOFT
        if any(item.status == "warning" for item in review.items):
            return "⚠ 要確認", theme.WARN
        if any(item.status == "suggestion" for item in review.items):
            return "追加候補あり", theme.INFO
        return "警告なし", theme.INK

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
                f" / 追加候補: 一致確率 {record.suggestion_threshold:.0%} 以上"
                if any(item.kind == "suggestion" for item in review.items)
                else ""
            )
            + (
                "\n現在の内容と照合しています。"
                if self._loading_currentness and review.image_id not in self._fresh_image_ids
                else "\n内容・設定が変わったため、過去の確率は表示していません。"
                if review.status == "stale"
                else ""
            )
        )
        labels = {
            "ok": "警告なし",
            "warning": "⚠ 要確認",
            "suggestion": "追加候補",
            "failed": "チェック失敗",
            "unevaluated": "未評価",
        }
        kinds = {"tag": "既存タグ", "caption": "キャプション", "suggestion": "追加候補"}
        self.details_table.setRowCount(len(review.items))
        for row, result in enumerate(review.items):
            values = (
                "候補タグ"
                if result.kind == "suggestion" and result.status != "suggestion"
                else kinds[result.kind],
                result.text,
                "採用候補外"
                if result.kind == "suggestion" and result.status == "ok"
                else labels[result.status],
                f"{result.probability:.1%}" if result.probability is not None else "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(result.error or result.text)
                if result.status == "warning":
                    cell.setForeground(QColor(theme.WARN))
                elif result.status == "suggestion":
                    cell.setForeground(QColor(theme.INFO))
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
        self.running_status_changed.emit("")
        self._render_timer.stop()
        self._generation += 1
        self._update_controls()
        if self._manager is not None:
            self._manager.cancel_all_workers(reason=CancelReason.SHUTDOWN, total_grace_ms=1000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)
