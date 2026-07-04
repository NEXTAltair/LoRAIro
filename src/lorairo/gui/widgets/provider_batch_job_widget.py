"""Provider Batch job monitoring widget.

ADR 0076 §3: 作成入口 (ステージング + モデルピッカー + Submit) を Annotate の dispatch
射影へ移し、本 widget は **純粋な監視台帳** に徹する。

- 上: 同期ジョブ台帳 (SyncJobLedgerWidget、ADR 0066、runtime 挿入)
- 下: Provider Batch 追跡カード台帳 (Issue #1103 — カード再設計)

Issue #1103: フラットな 5 列テーブル + 生テキスト詳細 + 右クリック復旧メニューを廃止し、
ジョブ 1 件 = 1 追跡カード (``ProviderBatchJobCard``) に置き換えた。アクションは必ず
カード footer に帰属し (右クリック隠蔽なし)、詳細フィールドはカード展開
(progressive disclosure) へ移した。デザイン SSoT は claude.ai/design「LoRAIro-01」の
``Jobs Tab - Provider Batch Redesign.html``。

残す操作は lifecycle / 事故復旧系に限る (ADR 0076 §1): 進行中カード =「状態を確認」/
「キャンセル」、完了・未回収カード =「結果を取得」(fetch → import 自動連鎖)。
作成入口 (Submit フォーム・モデルピッカー・ステージング) は持たない。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.gui.widgets.provider_batch_job_card import ProviderBatchJobCard
from lorairo.gui.widgets.sync_job_ledger_widget import SyncJobLedgerWidget
from lorairo.services.job_ledger_service import JobLedgerService
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.utils.log import logger

_COMPLETED_STATUS = "completed"
_IMPORTED_STATUS = "imported"


class ProviderBatchJobWidget(QWidget):
    """Provider Batch job 監視台帳 widget (ADR 0076 §3 — 監視専用)."""

    sync_job_cancel_requested = Signal(str)  # ADR 0066 §4: 同期ジョブ行のキャンセル (job_id)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("providerBatchJobWidget")

        self._workflow_service: Any = None
        self._repository: Any = None
        self._cards: dict[int, ProviderBatchJobCard] = {}
        self._expanded_job_ids: set[int] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.splitterRight = QSplitter(Qt.Orientation.Vertical)
        self.splitterRight.setChildrenCollapsible(False)
        root.addWidget(self.splitterRight, 1)

        # ADR 0066: 統一 Jobs lifecycle ビュー — 同期ジョブ台帳セクション (拡張方式)
        self._job_ledger: JobLedgerService | None = None
        self._sync_jobs_widget = SyncJobLedgerWidget(parent=self.splitterRight)
        self.splitterRight.insertWidget(0, self._sync_jobs_widget)
        self._sync_jobs_widget.cancel_requested.connect(self.sync_job_cancel_requested)

        self.batchBandWidget = self._build_batch_band()
        self.splitterRight.addWidget(self.batchBandWidget)

        self.labelStatus = QLabel("Ready")
        self.labelStatus.setObjectName("labelProviderBatchStatus")
        root.addWidget(self.labelStatus)

    # -- Provider Batch バンドの構築 (Issue #1103) ------------------------------

    def _build_batch_band(self) -> QWidget:
        """PROVIDER BATCH バンド (帯見出し + エラーバナー + カードリスト + 導線ヒント) を組む。"""
        band = QWidget()
        band.setObjectName("providerBatchBand")
        layout = QVBoxLayout(band)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_band_header())

        self._error_banner = self._build_error_banner()
        self._error_banner.setVisible(False)
        layout.addWidget(self._error_banner)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(12)

        self.emptyStateWidget = self._build_empty_state()
        self._card_layout.addWidget(self.emptyStateWidget)
        self._card_layout.addStretch(1)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setWidget(self._card_container)
        layout.addWidget(self._scroll_area, 1)

        # 監視専用の明示 (ADR 0076 §3 / Phase 4c): 作成導線は Annotate タブ
        self.labelMonitorOnlyHint = QLabel(
            "ここは監視専用台帳 — 新規バッチの作成は Annotate タブの「⇄ バッチAPIで送信」から (ADR 0076 §3)"
        )
        self.labelMonitorOnlyHint.setObjectName("labelProviderBatchMonitorOnlyHint")
        self.labelMonitorOnlyHint.setWordWrap(True)
        self.labelMonitorOnlyHint.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: 10px; font-family: {theme.FONT_MONO_CSS}; }}"
        )
        layout.addWidget(self.labelMonitorOnlyHint)
        return band

    def _build_band_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setSpacing(8)
        header.setStyleSheet(f"border-bottom: 1px solid {theme.LINE_STRONG};")

        title = QLabel("PROVIDER BATCH")
        title.setObjectName("labelBandTitle")
        title.setStyleSheet(
            f"QLabel {{ color: {theme.INK_SOFT}; font-weight: 700; letter-spacing: 2px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-family: {theme.FONT_MONO_CSS};"
            f" border: none; }}"
        )
        layout.addWidget(title)

        subtitle = QLabel("非同期バッチ — provider 側で進行中のジョブ (監視専用)")
        subtitle.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL}px; border: none; }}"
        )
        layout.addWidget(subtitle)

        self.labelJobCount = QLabel("· 0")
        self.labelJobCount.setStyleSheet(
            f"QLabel {{ color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
        )
        layout.addWidget(self.labelJobCount)
        layout.addStretch(1)

        src = QLabel("provider_batch_jobs · DB 永続 · 作成は Annotate から (ADR 0076)")
        src.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: 10px;"
            f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
        )
        layout.addWidget(src)
        return header

    def _build_empty_state(self) -> QWidget:
        """0 件 empty state (テーブルの空白では表現しない)。"""
        empty = QFrame()
        empty.setObjectName("providerBatchEmptyState")
        empty.setStyleSheet(
            f"QFrame#providerBatchEmptyState {{ border: 1px dashed {theme.LINE_STRONG};"
            f" border-radius: {theme.RADIUS}px; background-color: {theme.PAPER}; }}"
        )
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(3)
        title = QLabel("進行中の非同期バッチはありません")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"QLabel {{ color: {theme.INK_SOFT}; font-weight: 600; border: none; }}")
        sub = QLabel("Annotate で「⇄ バッチAPIで送信」すると、ここに追跡カードが並びます")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"QLabel {{ color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
        )
        layout.addWidget(title)
        layout.addWidget(sub)
        return empty

    def _build_error_banner(self) -> QWidget:
        """状態確認失敗バナー (台帳は保持 · カードは最終既知状態のまま)。"""
        banner = QFrame()
        banner.setObjectName("providerBatchErrorBanner")
        banner.setStyleSheet(
            f"QFrame#providerBatchErrorBanner {{ background-color: {theme.ERR_SOFT};"
            f" border: 1px solid {theme.ERR_BORDER}; border-radius: {theme.RADIUS}px; }}"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        title = QLabel("状態を確認できませんでした")
        title.setStyleSheet(f"QLabel {{ color: {theme.ERR}; font-weight: 600; border: none; }}")
        layout.addWidget(title)
        self._error_banner_detail = QLabel("")
        self._error_banner_detail.setStyleSheet(
            f"QLabel {{ color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" font-family: {theme.FONT_MONO_CSS}; border: none; }}"
        )
        layout.addWidget(self._error_banner_detail)
        layout.addStretch(1)
        retry = QPushButton("↻ 再試行")
        retry.setObjectName("buttonProviderBatchRetry")
        retry.clicked.connect(self.refresh_jobs)
        layout.addWidget(retry)
        return banner

    # -- 依存注入 ---------------------------------------------------------------

    def set_dependencies(self, workflow_service: Any, repository: Any) -> None:
        """Inject services used by the monitoring widget.

        ADR 0076 §3: 作成入口を撤去したため model_source / model_repository は不要。
        監視・lifecycle / 復旧操作に必要な workflow_service と repository のみ受ける。

        Args:
            workflow_service: refresh / cancel / fetch / import を提供する workflow service。
            repository: ジョブ・項目の一覧 / 詳細を提供する provider_batch_repo。
        """
        self._workflow_service = workflow_service
        self._repository = repository
        self.refresh_jobs()

    def get_sync_jobs_widget(self) -> SyncJobLedgerWidget:
        """同期ジョブ台帳セクション widget を返す。"""
        return self._sync_jobs_widget

    def set_job_ledger(self, job_ledger: JobLedgerService) -> None:
        """同期ジョブ台帳 (ADR 0066) を注入し、初期表示を行う。

        Args:
            job_ledger: WorkerService が所有する in-memory 台帳。
        """
        self._job_ledger = job_ledger
        self.refresh_sync_jobs()

    @Slot()
    def refresh_sync_jobs(self) -> None:
        """同期ジョブ台帳セクション (サマリ帯・ステージ進捗・履歴) を再描画する。"""
        if self._job_ledger is None:
            return
        self._sync_jobs_widget.set_summary(self._job_ledger.summary())
        self._sync_jobs_widget.set_entries(self._job_ledger.list_entries())

    # -- カード台帳の再描画 -------------------------------------------------------

    def cards(self) -> dict[int, ProviderBatchJobCard]:
        """job_id → 追跡カードの対応を返す (テスト・タブ内配線用)。"""
        return dict(self._cards)

    @Slot()
    def refresh_jobs(self, update_label: bool = True) -> None:
        """ジョブ一覧を再取得し追跡カード台帳を再構築する。"""
        if self._repository is None:
            return
        try:
            jobs = self._repository.list_provider_batch_jobs(limit=100, offset=0)
        except Exception as e:
            # 台帳は保持 (最終既知状態のカードを残す)、バナーで stale を明示
            logger.warning(f"バッチAPI job list failed: {e}")
            self._error_banner_detail.setText(f"{e} — 最終既知状態を表示しています")
            self._error_banner.setVisible(True)
            self.labelStatus.setText("バッチAPIジョブを取得できません")
            return
        self._error_banner.setVisible(False)
        self._rebuild_cards(jobs)
        self.labelJobCount.setText(f"· {len(jobs)}")
        if update_label:
            self.labelStatus.setText(f"バッチAPIジョブ {len(jobs)} 件を読み込みました")

    def _rebuild_cards(self, jobs: list[Any]) -> None:
        for card in self._cards.values():
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for index, job in enumerate(jobs):
            card = ProviderBatchJobCard(job, parent=self._card_container)
            card.check_requested.connect(self.check_job_status)
            card.cancel_requested.connect(self.cancel_job)
            card.expand_toggled.connect(self._on_card_expand_toggled)
            # empty state の後・stretch の前に挿入
            self._card_layout.insertWidget(index + 1, card)
            self._cards[int(job.id)] = card
            if int(job.id) in self._expanded_job_ids:
                card.set_expanded(True)
                self._load_card_items(int(job.id))

        self.emptyStateWidget.setVisible(not self._cards)

    def select_job(self, job_id: int) -> None:
        """指定ジョブのカードを可視位置へスクロールする。"""
        card = self._cards.get(job_id)
        if card is not None:
            self._scroll_area.ensureWidgetVisible(card)

    @Slot(int, bool)
    def _on_card_expand_toggled(self, job_id: int, expanded: bool) -> None:
        if expanded:
            self._expanded_job_ids.add(job_id)
            self._load_card_items(job_id)
        else:
            self._expanded_job_ids.discard(job_id)

    def _load_card_items(self, job_id: int) -> None:
        """展開されたカードの項目テーブルへ項目一覧を読み込む。"""
        card = self._cards.get(job_id)
        if card is None or self._repository is None:
            return
        try:
            items = self._repository.list_provider_batch_items(job_id, status=None)
        except Exception as e:
            logger.warning(f"バッチAPI item list failed (job {job_id}): {e}")
            return
        card.set_items(list(items))

    # -- lifecycle / 復旧操作 (カード footer 帰属) --------------------------------

    def _handle_action_error(self, action: str, error: Exception) -> None:
        logger.opt(exception=True).error(f"バッチAPI {action} failed: {error}")
        QMessageBox.critical(self, "バッチAPI", str(error))
        self.labelStatus.setText(f"{action} に失敗しました")

    def _get_job(self, job_id: int) -> Any | None:
        if self._repository is None:
            return None
        return self._repository.get_provider_batch_job(job_id)

    @staticmethod
    def _job_status(job: Any) -> str:
        return str(getattr(job, "status", "") or "")

    @staticmethod
    def _job_imported(job: Any) -> bool:
        return ProviderBatchJobWidget._job_status(job) == _IMPORTED_STATUS or (
            getattr(job, "imported_at", None) is not None
        )

    def _status_message_for_job(self, job_id: int, job: Any) -> str:
        status = self._job_status(job)
        provider_status = str(getattr(job, "provider_status", "") or status)
        if status in {"submitted", "validating"}:
            return f"バッチAPIジョブ {job_id} は検証中です ({provider_status})"
        if status in {"running", "canceling"}:
            return f"バッチAPIジョブ {job_id} は処理中です ({provider_status})"
        if status == "failed":
            return f"バッチAPIジョブ {job_id} は失敗しました ({provider_status})"
        if status == "expired":
            return f"バッチAPIジョブ {job_id} は期限切れです ({provider_status})"
        if status == "canceled":
            return f"バッチAPIジョブ {job_id} はキャンセル済みです ({provider_status})"
        return f"バッチAPIジョブ {job_id} の状態を確認しました ({provider_status})"

    @staticmethod
    def _import_result_message(job_id: int, result: Any) -> str:
        imported_count = int(getattr(result, "imported_count", 0))
        skipped_count = int(getattr(result, "skipped_count", 0))
        error_count = int(getattr(result, "error_count", 0))
        total_count = int(getattr(result, "total_count", 0))
        if skipped_count or error_count:
            return (
                f"バッチAPIジョブ {job_id} の処理完了を確認し、DB保存を実行しました: "
                f"保存 {imported_count}/{total_count} 件, スキップ {skipped_count} 件, エラー {error_count} 件"
            )
        return f"バッチAPIジョブ {job_id} の処理完了を確認し、DB保存が完了しました: {imported_count}/{total_count} 件"

    @Slot(int)
    def check_job_status(self, job_id: int) -> None:
        """状態を確認する。完了していれば fetch → import まで自動連鎖する。

        進行中カードの「↻ 状態を確認」と完了・未回収カードの「↓ 結果を取得」は
        同じ経路 (refresh → completed なら fetch + import)。fetch 済みで import が
        失敗した事故復旧も、status が completed のまま残るため再実行で回収できる。
        """
        if self._workflow_service is None:
            return
        try:
            current_job = self._get_job(job_id)
            if current_job is not None and self._job_imported(current_job):
                self.labelStatus.setText(f"バッチAPIジョブ {job_id} は保存済みです")
                return
            job = self._workflow_service.refresh(job_id)
            if self._job_imported(job):
                message = f"バッチAPIジョブ {job_id} は保存済みです"
            elif self._job_status(job) == _COMPLETED_STATUS:
                fetch_result = self._workflow_service.fetch_results(job_id)
                import_result = self._workflow_service.import_results(job_id, fetch_result)
                message = self._import_result_message(job_id, import_result)
            else:
                message = self._status_message_for_job(job_id, job)
            self.refresh_jobs(update_label=False)
            self.select_job(job_id)
            self.labelStatus.setText(message)
        except ProviderBatchError as e:
            # #1150: 想定内の業務エラーでも事後診断できるよう WARNING で記録する
            # (従来はダイアログ + labelStatus のみでログ痕跡ゼロだった)。
            logger.warning(f"バッチAPI status check failed (job {job_id}): {e}")
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("refresh", e)

    @Slot(int)
    def cancel_job(self, job_id: int) -> None:
        """ジョブのキャンセルを要求する。"""
        if self._workflow_service is None:
            return
        try:
            self._workflow_service.cancel(job_id)
            self.refresh_jobs(update_label=False)
            self.select_job(job_id)
            self.labelStatus.setText(f"バッチAPIジョブ {job_id} のキャンセルを要求しました")
        except ProviderBatchError as e:
            # #1150: 想定内の業務エラーでも事後診断できるよう WARNING で記録する。
            logger.warning(f"バッチAPI cancel failed (job {job_id}): {e}")
            QMessageBox.warning(self, "バッチAPI", str(e))
            self.labelStatus.setText(str(e))
        except Exception as e:
            self._handle_action_error("cancel", e)
