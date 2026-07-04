"""Frame 5 · Results 読み取り専用トリアージ表示ウィジェット。

``QualityIssueDetectionService`` が算出した ``BatchTriageSummary`` /
``ImageTriageResult`` を受け取り、サマリ band・issue カード・per-image 行を
描画する。検出ロジックは持たず表示に専念する (MVC の View)。
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    CleanAuditPlan,
    ImageTriageResult,
    IssueType,
    QualityIssueDetectionService,
    RatingView,
    ScorerView,
    TagView,
)
from lorairo.utils.log import logger

from .tag_cloud_widget import FlowLayout
from .tag_panel_widget import SelectableTagChip

# issue 種別の user-facing ラベル。
_ISSUE_LABELS: dict[IssueType, str] = {
    IssueType.EMPTY_TAGS: "タグ無し",
    IssueType.NO_SCORE: "スコア無し",
    IssueType.UNKNOWN_TIER: "未知の tier",
    IssueType.RATING_DISAGREEMENT: "rating 不一致",
    IssueType.SCORER_DISAGREEMENT: "scorer 不一致",
}

# 低信頼度タグを視覚的に弱める閾値 (表示上の dim 判定のみ。issue 化はしない)。
_DIM_CONFIDENCE: float = 0.5

# #1140 フリーズ対策。全行 + タグ chip を一括構築すると 100 枚 × 数十 chip で GUI
# スレッドが数分ブロックするため、行はチャンク分割して構築し chip 数も行内で上限を設ける。
_ROW_CHUNK_SIZE: int = 15  # 1 タイマーティックで構築する行数 (初回チャンクは同期構築)
_MAX_TAG_CHIPS_PER_ROW: int = 15  # 1 行に出すタグ chip の上限 (超過は「他 N件」ラベルへ畳む)
# これ以上の件数では per-row 描画を諦め、サマリ + issue 集約のみ表示へ degrade する
# (wireframes v12 Results@500: 仮想スクロール + 同種 issue 集約)。
_VIRTUALIZE_THRESHOLD: int = 500

# DS v12 ResultsScreen (Issue #791): 構造的 issue 種別 → chip 文法の kind。
# 空タグは欠落 = err、その他の不一致/欠落は warn。
_ISSUE_CHIP_KINDS: dict[IssueType, theme.ChipKind] = {
    IssueType.EMPTY_TAGS: "err",
    IssueType.NO_SCORE: "warn",
    IssueType.UNKNOWN_TIER: "warn",
    IssueType.RATING_DISAGREEMENT: "warn",
    IssueType.SCORER_DISAGREEMENT: "warn",
}


class _FlowChipRow(QWidget):
    """chip / ラベルを ``FlowLayout`` で折り返し配置する自己完結の行ウィジェット。

    ``FlowLayout`` を素の ``QWidget`` に載せると、その ``minimumSizeHint``
    (最小幅で全アイテムを縦積みした過大値) が親へ伝播し、``widgetResizable`` な
    ``QScrollArea`` を膨張させて末尾に異常な余白を生む
    (docs/lessons-learned.md 「FlowLayout in widgetResizable scroll inflates
    minimumSizeHint」/ Issue #835 / #1025)。

    ここでは縦 ``SizePolicy`` を ``Fixed`` にし、``resizeEvent`` / ``showEvent`` で
    実幅の ``heightForWidth`` を ``setFixedHeight`` に反映することで高さをこの
    ウィジェット内に閉じ、過大な最小サイズが親へ漏れないようにする。
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._flow = FlowLayout(self, spacing=spacing)
        # 高さは resizeEvent で実幅ベースに固定する。横は親幅まで伸ばす。
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add_widget(self, widget: QWidget) -> None:
        """chip / ラベルを行末に追加する。"""
        self._flow.addWidget(widget)

    def _adjust_height(self) -> None:
        """実幅での折り返し必要高さを ``setFixedHeight`` で確定する。"""
        width = self.width()
        if width <= 0:
            return
        # chip 追加直後はレイアウト未 activation で子が hidden のことがあり、
        # QWidgetItem.sizeHint() が (0,0) を返して heightForWidth=0 → 潰れる
        # (#1025)。同期計測の前に hidden の子を明示的に可視化して実寸を得る。
        for i in range(self._flow.count()):
            item = self._flow.itemAt(i)
            child = item.widget() if item is not None else None
            if child is not None and child.isHidden():
                child.setVisible(True)
        self.setFixedHeight(self._flow.heightForWidth(width))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_height()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._adjust_height()


class _RowThumbnail(QLabel):
    """結果行の小サムネイル (Issue #1104)。

    viewport に実際に見えている行だけを遅延デコードする (``maybe_load``)。
    ``showEvent`` はウィジェット階層の表示時に全行で発火してしまうため、それだけを
    トリガにすると大きな staged セットで Results を開いた瞬間に全行を同期デコードして
    UI が固まる。``visibleRegion`` の交差判定でスクロール可視域に入った行のみ読み込み、
    親 (``ResultsWidget``) がスクロール時に ``maybe_load`` を再評価する。

    パスが無い・ファイル欠落・デコード失敗のいずれでもクラッシュせずプレースホルダ
    文言を出す。
    """

    _SIZE = 56

    def __init__(self, image_id: int, path: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._loaded = False
        self.setObjectName(f"resultsRowThumb_{image_id}")
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # DS: hairline border の枠。読み込み前/失敗時はプレースホルダ文言をこの枠内に出す。
        self.setStyleSheet(
            f"QLabel {{ border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS}px; color: {theme.INK_FAINT}; }}"
        )
        self.setText("…")

    def maybe_load(self) -> None:
        """viewport に見えていれば (まだなら) デコードする。見えていなければ何もしない。"""
        if self._loaded:
            return
        # スクロールで viewport 外にクリップされている行は visibleRegion が空になる。
        if self.visibleRegion().isEmpty():
            return
        self._loaded = True
        self._load()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # 表示直後はレイアウト未確定で visibleRegion が不正確なことがあるため、
        # イベントループ復帰後に可視判定する (先頭スクリーン分の初期ロード)。
        # context に self を渡し破棄後の stale コールバックを防ぐ (#1140)。
        QTimer.singleShot(0, self, self.maybe_load)

    def _load(self) -> None:
        """パスから QPixmap を読み込む。失敗時はプレースホルダ文言を残す。"""
        if not self._path:
            self.setText("no img")
            self.setToolTip("プレビュー画像がありません")
            return
        path = Path(self._path)
        if not path.exists():
            self.setText("欠落")
            self.setToolTip(f"画像ファイルが見つかりません: {self._path}")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.setText("不可")
            self.setToolTip(f"画像を読み込めません: {self._path}")
            return
        self.setText("")
        self.setToolTip(self._path)
        self.setPixmap(
            pixmap.scaled(
                self._SIZE,
                self._SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class ResultsWidget(QWidget):
    """Frame 5 · Results 読み取り専用トリアージ表示。objectName = "resultsWidget"。"""

    accept_requested = Signal(int)  # image_id (この画像を accept = reviewed_at 設定)
    unaccept_requested = Signal(int)  # image_id (accept を取り消す = reviewed_at 解除)
    accept_clean_requested = Signal(list)  # list[int] (問題なし画像を一括 accept)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsWidget")
        self._root = QVBoxLayout(self)
        # 描画順の image_id を保持 (内部アクセサ _row_order が返す)。
        self._row_image_ids: list[int] = []
        # CLEAN 監査 (OK箱) の再描画・引き直し用に直近の入力を保持する。
        self._summary_cache: BatchTriageSummary | None = None
        self._results_cache: list[ImageTriageResult] = []
        self._clean_plan: CleanAuditPlan | None = None
        # image_id -> 行内サムネイルの画像パス (#1104)。display で受け取る。
        self._image_paths: dict[int, str] = {}
        # 遅延ロード対象のサムネイル一覧 (可視域だけデコードするため保持する。#1104)。
        self._row_thumbnails: list[_RowThumbnail] = []
        # 行のチャンク分割構築の状態 (#1140)。世代トークンで stale コールバックを弾く。
        self._render_generation: int = 0
        self._pending_results: list[ImageTriageResult] = []
        self._rows_layout: QVBoxLayout | None = None
        self.clear()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def display(
        self,
        summary: BatchTriageSummary,
        results: list[ImageTriageResult],
        image_paths: dict[int, str] | None = None,
    ) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。

        Args:
            summary: バッチ全体のサマリ。
            results: 画像別トリアージ結果。``needs_review`` を優先して縦に並べる。
            image_paths: image_id -> 行内サムネイル用の画像パス (#1104)。省略時は
                サムネイルをプレースホルダ表示にする (View は DB を持たないため、
                パス解決は呼び出し元 ``ResultsTabWidget`` が担う)。
        """
        self._reset()
        self._summary_cache = summary
        self._results_cache = list(results)
        self._image_paths = dict(image_paths) if image_paths else {}

        if not results:
            self._clean_plan = None
            self._build_empty_state()
            return

        # CLEAN 監査 (OK箱) の抜き取りプランを算出する (毎回 display で引き直す)。
        self._clean_plan = QualityIssueDetectionService.build_clean_audit(results)

        # needs_review (issue 有) を先頭に安定ソートする。
        ordered = sorted(results, key=lambda r: not r.needs_review)
        self._row_image_ids = [r.image_id for r in ordered]

        self._root.addWidget(self._build_summary_band(summary))
        issue_band = self._build_issue_band(summary, ordered)
        if issue_band is not None:
            self._root.addWidget(issue_band)

        # 大規模時は per-row 描画を諦め、サマリ + issue 集約 + 集約ノーティスを表示する
        # (#1140、数千 chip の一括構築を避け絞り込みへ誘導。wireframes Results@500)。
        # ただし clean-audit の抜き取り監査バンド (少数行 + 一括 accept) は残す
        # (degrade でも「確認して accept」導線を失わない。Codex #1143 P2-2)。
        if len(ordered) >= _VIRTUALIZE_THRESHOLD:
            self._root.addWidget(self._build_scale_notice(len(ordered)))
            band = self._build_clean_audit_band(ordered)
            if band is not None:
                self._root.addWidget(band)
            self._root.addStretch(1)
            # clean-audit の抜き取り行サムネイルを可視域ロード対象として評価する。
            QTimer.singleShot(0, self, self._load_visible_thumbnails)
            return

        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.addStretch(1)  # 末尾 stretch。行はこの前に挿入していく。

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_container)
        # スクロールで新たに可視域へ入った行のサムネイルを追ってデコードする (#1104)。
        scroll.verticalScrollBar().valueChanged.connect(self._load_visible_thumbnails)
        self._root.addWidget(scroll, stretch=1)

        band = self._build_clean_audit_band(ordered)
        if band is not None:
            self._root.addWidget(band)

        # 行はチャンク分割で構築し、GUI スレッドを長時間ブロックしない (#1140)。
        # 初回チャンクは同期構築して初期表示を出し、残りはイベントループ復帰後に足す。
        self._rows_layout = rows_layout
        self._pending_results = list(ordered)
        self._build_next_row_chunk(self._render_generation)
        # 先頭スクリーン分のサムネイルをレイアウト確定後にロードする (可視域のみ、#1104)。
        QTimer.singleShot(0, self, self._load_visible_thumbnails)

    def _build_next_row_chunk(self, generation: int) -> None:
        """pending から最大 ``_ROW_CHUNK_SIZE`` 行を構築し、残があれば次を予約する (#1140)。"""
        # 別の display / clear で作り直された後の stale コールバックは破棄する。
        if generation != self._render_generation:
            return
        layout = self._rows_layout
        if layout is None:
            return
        built = 0
        while self._pending_results and built < _ROW_CHUNK_SIZE:
            result = self._pending_results.pop(0)
            # 末尾 stretch の手前に挿入する (行の順序を保つ)。
            layout.insertWidget(layout.count() - 1, self._build_row(result))
            built += 1
        if self._pending_results:
            # context に self を渡し、ウィジェット破棄後に stale コールバックが
            # 発火して削除済み C++ オブジェクトへ触れるのを防ぐ (#1140)。
            QTimer.singleShot(0, self, lambda g=generation: self._build_next_row_chunk(g))
        else:
            # 全行構築完了。可視域のサムネイルをロードする。
            self._load_visible_thumbnails()

    def _build_scale_notice(self, count: int) -> QWidget:
        """大規模件数での per-row 省略を知らせる集約ノーティスを構築する (#1140)。"""
        notice = QLabel(
            f"対象 {count} 件は多いため、行ごとの表示を省略しています "
            f"(≥ {_VIRTUALIZE_THRESHOLD} 件)。上のサマリと issue バンドで全体の傾向を確認し、"
            "検索・フィルタで絞り込んでから個別の結果を確認してください。"
        )
        notice.setObjectName("resultsScaleNotice")
        notice.setWordWrap(True)
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return notice

    def _load_visible_thumbnails(self) -> None:
        """viewport に見えているサムネイルだけを (まだなら) デコードする (#1104)。"""
        for thumb in self._row_thumbnails:
            thumb.maybe_load()

    def _build_clean_audit_band(self, results: list[ImageTriageResult]) -> QWidget | None:
        """CLEAN 監査 (OK箱) バンドを構築する (clean が無ければ None)。

        無確認で一括 accept される clean 集合の手前に「ランダム抽出を目視 → 一括 accept」
        のゲートを挟む。抽出行を目視して問題があれば引き直す / 個別 accept を見送る。
        """
        plan = self._clean_plan
        if plan is None or not plan.clean_image_ids:
            return None

        clean_count = len(plan.clean_image_ids)
        sample_count = len(plan.sample_image_ids)

        band = QFrame()
        band.setObjectName("resultsCleanAuditBand")
        band.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(band)

        header = QLabel(
            f"CLEAN 監査: 無確認で承認されようとしている {clean_count} 件。"
            f"一括 accept の前にランダム {sample_count} 件を確認:"
        )
        header.setObjectName("resultsCleanAuditHeader")
        header.setWordWrap(True)
        layout.addWidget(header)

        resample = QPushButton("↻ 引き直す")
        resample.setObjectName("resultsResampleButton")
        resample.clicked.connect(self._resample_clean)
        layout.addWidget(resample)

        # 抽出された clean 画像のアノテーションを行表示する (目視して bad-path を拾う)。
        by_id = {r.image_id: r for r in results}
        for image_id in plan.sample_image_ids:
            result = by_id.get(image_id)
            if result is not None:
                layout.addWidget(self._build_row(result))

        accept = QPushButton(f"✓ 確認して accept ({clean_count})")
        accept.setObjectName("resultsAcceptCleanButton")
        clean_ids = list(plan.clean_image_ids)
        sample_ids = list(plan.sample_image_ids)
        accept.clicked.connect(
            lambda _checked=False, ids=clean_ids, sampled=sample_ids: self._on_clean_accept(ids, sampled)
        )
        layout.addWidget(accept)
        return band

    def _resample_clean(self) -> None:
        """抜き取りサンプルを引き直す (直近の入力で再描画する)。"""
        if self._summary_cache is not None and self._results_cache:
            # サムネイルのパスは display で消える前に退避してから再描画する (#1104)。
            self.display(self._summary_cache, self._results_cache, self._image_paths)

    def _on_clean_accept(self, clean_ids: list[int], sample_ids: list[int]) -> None:
        """CLEAN 監査の確認後一括 accept。監査ログを残してから accept を要求する。"""
        # ユーザー操作の監査記録 (誰が抜き取り確認して何件 accept したか)。INFO で1回。
        logger.info(
            f"clean 抜き取り監査 accept: 確認 {len(sample_ids)} 件 / 一括 accept {len(clean_ids)} 件 "
            f"(sampled={sample_ids})"
        )
        self.accept_clean_requested.emit(clean_ids)

    def clear(self) -> None:
        """空状態 (ステージング 0 件) を表示する。"""
        self._reset()
        self._build_empty_state()

    def _row_order(self) -> list[int]:
        """描画順の image_id リストを返す (テスト・後続結線用の内部アクセサ)。"""
        return list(self._row_image_ids)

    # ------------------------------------------------------------------
    # 内部ヘルパ
    # ------------------------------------------------------------------
    def _reset(self) -> None:
        """前回描画の子ウィジェットをすべて破棄する。"""
        self._row_image_ids = []
        # キャッシュも初期化する (display が直後に再設定する / clear 後は空に保つ)。
        self._summary_cache = None
        self._results_cache = []
        self._clean_plan = None
        self._image_paths = {}
        # 破棄されるサムネイル参照を先に手放す (スクロール再評価が stale を触らないよう)。
        self._row_thumbnails = []
        # 世代を進めて進行中のチャンク構築コールバックを無効化し、pending をクリアする (#1140)。
        self._render_generation += 1
        self._pending_results = []
        self._rows_layout = None
        while self._root.count():
            item = self._root.takeAt(0)
            if item is None:
                continue
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _build_empty_state(self) -> None:
        """ステージング 0 件のプレースホルダを構築する。"""
        placeholder = QLabel("ステージングに画像がありません")
        placeholder.setObjectName("resultsEmptyState")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(placeholder)
        self._root.addStretch(1)

    def _build_summary_band(self, summary: BatchTriageSummary) -> QWidget:
        """バッチサマリ band を構築する。"""
        band = QFrame()
        band.setObjectName("resultsSummaryBand")
        band.setFrameShape(QFrame.Shape.StyledPanel)
        # DS: サマリ帯は paper-shade 地 + hairline border
        band.setStyleSheet(
            f"QFrame#resultsSummaryBand {{ background-color: {theme.PAPER_SHADE};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; border-radius: {theme.RADIUS}px; }}"
        )
        outer = QVBoxLayout(band)
        # 狭幅でサマリ項目が折り返せるよう FlowLayout 化する (#1105)。
        flow = _FlowChipRow()
        outer.addWidget(flow)

        issue_total = sum(summary.issue_counts.values())
        tier_text = self._format_tier_distribution(summary)
        # (テキスト, tone 色) — flagged=warn / clean=ok を DS tone で色付け
        parts: list[tuple[str, str]] = [
            (f"バッチ: {summary.batch_size} 件", theme.INK_SOFT),
            (f"要レビュー: {summary.needs_review_count}", theme.WARN),
            (f"clean: {summary.clean_count}", theme.OK),
            (f"accepted: {summary.accepted_count}/{summary.batch_size}", theme.OK),
            (f"tier: {tier_text}", theme.INK_SOFT),
            (f"issue 総数: {issue_total}", theme.INK_SOFT),
        ]
        for text, color in parts:
            label = QLabel(text)
            label.setStyleSheet(f"color: {color}; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
            flow.add_widget(label)
        return band

    def _format_tier_distribution(self, summary: BatchTriageSummary) -> str:
        """tier 分布を ``best quality:1, ...`` 形式に整形する。"""
        # 高品質 tier から順に並べる (QualityTier は値が高いほど高品質)。
        ordered_tiers = sorted(summary.tier_distribution.keys(), reverse=True)
        parts = [f"{tier.label}:{summary.tier_distribution[tier]}" for tier in ordered_tiers]
        if summary.no_tier_count:
            parts.append(f"tier不能:{summary.no_tier_count}")
        return ", ".join(parts) if parts else "なし"

    def _build_issue_band(
        self, summary: BatchTriageSummary, results: list[ImageTriageResult]
    ) -> QWidget | None:
        """issue 種別ごとのカード band を構築する (0 件種別は出さない)。"""
        active = {issue: count for issue, count in summary.issue_counts.items() if count > 0}
        if not active:
            return None

        band = QFrame()
        band.setObjectName("resultsIssueBand")
        outer = QVBoxLayout(band)
        outer.setContentsMargins(0, 0, 0, 0)
        # 狭幅で issue カードが折り返せるよう FlowLayout 化する (#1105)。
        flow = _FlowChipRow()
        outer.addWidget(flow)
        for issue, count in active.items():
            flow.add_widget(self._build_issue_card(issue, count, results))
        return band

    def _build_issue_card(self, issue: IssueType, count: int, results: list[ImageTriageResult]) -> QWidget:
        """1 issue 種別のカード (ラベル + 件数 + 該当 image_id) を構築する。"""
        card = QFrame()
        card.setObjectName(f"resultsIssueCard_{issue.value}")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        label = _ISSUE_LABELS.get(issue, issue.value)
        header = QLabel(f"{label} ({count})")
        header.setObjectName("resultsIssueCardHeader")
        # DS: issue 種別は重大度で色分けした chip 文法
        header.setStyleSheet(theme.chip_qss(_ISSUE_CHIP_KINDS.get(issue, "warn")))
        layout.addWidget(header)

        image_ids = [r.image_id for r in results if issue in r.issues]
        id_text = ", ".join(f"#{image_id}" for image_id in image_ids)
        ids_label = QLabel(id_text)
        ids_label.setWordWrap(True)
        layout.addWidget(ids_label)
        return card

    def _build_row(self, result: ImageTriageResult) -> QWidget:
        """1 画像分の per-image 行を構築する。"""
        row = QFrame()
        row.setObjectName(f"resultsRow_{result.image_id}")
        row.setFrameShape(QFrame.Shape.StyledPanel)
        if result.needs_review:
            row.setProperty("needsReview", True)
        if result.reviewed:
            row.setProperty("accepted", True)
        # DS: flagged (要レビュー) 行は warn border + warn-soft 地で強調
        if result.needs_review:
            row.setStyleSheet(
                f"QFrame#resultsRow_{result.image_id} {{"
                f" border: {theme.BORDER_WIDTH}px solid {theme.WARN_BORDER};"
                f" background-color: {theme.WARN_SOFT}; border-radius: {theme.RADIUS}px; }}"
            )
        # 行は [サムネイル | アノテーション縦積み] の横並び (#1104)。
        outer = QHBoxLayout(row)
        thumb = _RowThumbnail(result.image_id, self._image_paths.get(result.image_id))
        # 可視域だけ遅延ロードするためスクロール再評価の対象に登録する。
        self._row_thumbnails.append(thumb)
        outer.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignTop)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_row_header(result))
        layout.addWidget(self._build_tags_line(result.tags))
        layout.addWidget(self._build_caption_line(result))
        layout.addWidget(self._build_quality_line(result))
        layout.addWidget(self._build_rating_line(result))
        if result.issues:
            layout.addWidget(self._build_issue_badges(result.issues))
        outer.addWidget(content, stretch=1)
        return row

    def _build_row_header(self, result: ImageTriageResult) -> QWidget:
        """image_id / uuid 短縮 / WxH + accept ボタンの行を構築する。"""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        uuid_short = result.uuid[:8] if result.uuid else "-"
        dimensions = self._format_dimensions(result.width, result.height)
        ident = QLabel(f"#{result.image_id}  {uuid_short}  {dimensions}")
        ident.setObjectName(f"resultsRowIdent_{result.image_id}")
        layout.addWidget(ident)
        layout.addStretch(1)

        # accept 済みなら undo、未 accept なら accept ボタンを出す。
        if result.reviewed:
            undo = QPushButton("↩ 取消")
            undo.setObjectName(f"resultsUnacceptButton_{result.image_id}")
            undo.clicked.connect(
                lambda _checked=False, image_id=result.image_id: self.unaccept_requested.emit(image_id)
            )
            layout.addWidget(undo)
        else:
            accept = QPushButton("✓ accept")
            accept.setObjectName(f"resultsAcceptButton_{result.image_id}")
            accept.clicked.connect(
                lambda _checked=False, image_id=result.image_id: self.accept_requested.emit(image_id)
            )
            layout.addWidget(accept)
        return header

    def _format_dimensions(self, width: int | None, height: int | None) -> str:
        """``WxH`` 文字列を構築する。欠損は ``?``。"""
        w = str(width) if width is not None else "?"
        h = str(height) if height is not None else "?"
        return f"{w}×{h}"

    def _build_tags_line(self, tags: list[TagView]) -> QWidget:
        """タグ行を構築する (低 conf は dim プロパティ付与)。

        タグ chip 列は狭幅で折り返せるよう ``FlowLayout`` で並べる (#1105)。
        """
        line = _FlowChipRow()
        line.add_widget(QLabel("tags:"))
        if not tags:
            line.add_widget(QLabel("(なし)"))
            return line
        # 1 行のタグ数は上限で切り、超過は「他 N件」へ畳む (#1140: 数十 chip/行の
        # 一括生成 + FlowLayout 再レイアウト嵐を抑える)。
        shown = tags[:_MAX_TAG_CHIPS_PER_ROW]
        for tag_view in shown:
            line.add_widget(self._build_tag_chip(tag_view))
        overflow = len(tags) - len(shown)
        if overflow > 0:
            more = QLabel(f"他 {overflow}件")
            more.setObjectName("resultsTagsOverflow")
            more.setStyleSheet(theme.chip_qss("muted"))
            line.add_widget(more)
        return line

    def _build_tag_chip(self, tag_view: TagView) -> QWidget:
        """1 タグの chip。confidence 付き、低 conf は dim 表示。

        検索/エクスポートタブと視覚統一するため、独自 QLabel ではなく共通の
        ``SelectableTagChip`` (ADR 0083 / #987) を read-only で使う (#1104)。表示名は
        confidence 付き、コピー対象 (Ctrl+C / Ctrl+クリック) は canonical タグを渡す。
        結果タブは DB 非依存の View なので、編集系の右クリックメニューは
        ``PreventContextMenu`` で抑止し、``clicked`` (soft-reject トグル) も接続しない。
        """
        if tag_view.confidence_score is not None:
            text = f"{tag_view.tag} ({tag_view.confidence_score:.2f})"
        else:
            text = tag_view.tag
        # 結果タブの TagView は canonical を別持ちしない (タグ文字列自体が canonical)。
        chip = SelectableTagChip(text, tag_view.tag)
        is_dim = tag_view.confidence_score is not None and tag_view.confidence_score < _DIM_CONFIDENCE
        chip.setProperty("dim", is_dim)
        # DS: タグは accent chip 文法、低 conf は muted で弱める (base_qss = 共通部品の既定)
        chip.base_qss = theme.chip_qss("muted" if is_dim else "accent")
        chip.setStyleSheet(chip.base_qss)
        # 編集系メニュー (翻訳/種別/refinement) は DB 配線が要るため read-only では抑止する。
        chip.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        # Ctrl+クリックで canonical をクリップボードへコピー (検索/エクスポートと同じ導線)。
        chip.ctrl_clicked.connect(lambda c=chip: QApplication.clipboard().setText(c.canonical))
        return chip

    def _build_caption_line(self, result: ImageTriageResult) -> QWidget:
        """caption 行 (語数付き)。"""
        caption = result.caption if result.caption else "(なし)"
        return QLabel(f"caption: {caption} [{result.caption_word_count} 語]")

    def _build_quality_line(self, result: ImageTriageResult) -> QWidget:
        """canonical_tier + scorer pills の行を構築する。"""
        line = QWidget()
        layout = QHBoxLayout(line)
        layout.setContentsMargins(0, 0, 0, 0)

        tier_text = result.canonical_tier.label if result.canonical_tier is not None else "tier不能"
        layout.addWidget(QLabel(f"tier: {tier_text}"))
        for scorer in result.scorers:
            layout.addWidget(self._build_scorer_pill(scorer))
        layout.addStretch(1)
        return line

    def _build_scorer_pill(self, scorer: ScorerView) -> QWidget:
        """scorer pill (model: label)。"""
        label = scorer.label if scorer.label else "?"
        pill = QLabel(f"{scorer.model}: {label}")
        pill.setProperty("dim", scorer.tier is None)
        # DS: scorer は中立 badge、tier 不能は muted chip
        pill.setStyleSheet(theme.chip_qss("muted") if scorer.tier is None else theme.badge_qss())
        return pill

    def _build_rating_line(self, result: ImageTriageResult) -> QWidget:
        """canonical_rating + モデル別 rating の行。不一致は強調。"""
        line = QWidget()
        layout = QHBoxLayout(line)
        layout.setContentsMargins(0, 0, 0, 0)

        canonical = result.canonical_rating if result.canonical_rating else "-"
        layout.addWidget(QLabel(f"rating: {canonical}"))
        for rating in result.ratings:
            layout.addWidget(self._build_rating_chip(rating, result.canonical_rating))
        layout.addStretch(1)
        return line

    def _build_rating_chip(self, rating: RatingView, canonical_rating: str | None) -> QWidget:
        """1 モデルの rating chip。canonical と不一致なら強調プロパティを付与。"""
        value = rating.normalized_rating if rating.normalized_rating else "-"
        chip = QLabel(f"{rating.model}: {value}")
        disagree = (
            rating.normalized_rating is not None
            and canonical_rating is not None
            and rating.normalized_rating != canonical_rating
        )
        chip.setProperty("disagree", disagree)
        # DS: canonical と不一致な rating は warn chip、一致は中立 badge
        chip.setStyleSheet(theme.chip_qss("warn") if disagree else theme.badge_qss())
        return chip

    def _build_issue_badges(self, issues: list[IssueType]) -> QWidget:
        """その行の issue バッジ群を構築する。"""
        line = QWidget()
        layout = QHBoxLayout(line)
        layout.setContentsMargins(0, 0, 0, 0)
        for issue in issues:
            badge = QLabel(_ISSUE_LABELS.get(issue, issue.value))
            badge.setProperty("issueBadge", True)
            # DS: 行内 issue バッジも重大度の chip 文法
            badge.setStyleSheet(theme.chip_qss(_ISSUE_CHIP_KINDS.get(issue, "warn")))
            layout.addWidget(badge)
        layout.addStretch(1)
        return line
