"""Frame 5 · Results 読み取り専用トリアージ表示ウィジェット。

``QualityIssueDetectionService`` が算出した ``BatchTriageSummary`` /
``ImageTriageResult`` を受け取り、サマリ band・issue カード・per-image 行を
描画する。検出ロジックは持たず表示に専念する (MVC の View)。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    ImageTriageResult,
    IssueType,
    RatingView,
    ScorerView,
    TagView,
)

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


class ResultsWidget(QWidget):
    """Frame 5 · Results 読み取り専用トリアージ表示。objectName = "resultsWidget"。"""

    review_requested = Signal(int)  # image_id (Annotate へ遷移要求。Phase 6 で接続)
    accept_requested = Signal(int)  # image_id (この画像を accept = reviewed_at 設定)
    unaccept_requested = Signal(int)  # image_id (accept を取り消す = reviewed_at 解除)
    accept_clean_requested = Signal(list)  # list[int] (問題なし画像を一括 accept)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsWidget")
        self._root = QVBoxLayout(self)
        # 描画順の image_id を保持 (内部アクセサ _row_order が返す)。
        self._row_image_ids: list[int] = []
        self.clear()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def display(self, summary: BatchTriageSummary, results: list[ImageTriageResult]) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。

        Args:
            summary: バッチ全体のサマリ。
            results: 画像別トリアージ結果。``needs_review`` を優先して縦に並べる。
        """
        self._reset()

        if not results:
            self._build_empty_state()
            return

        # needs_review (issue 有) を先頭に安定ソートする。
        ordered = sorted(results, key=lambda r: not r.needs_review)
        self._row_image_ids = [r.image_id for r in ordered]

        self._root.addWidget(self._build_summary_band(summary))
        issue_band = self._build_issue_band(summary, ordered)
        if issue_band is not None:
            self._root.addWidget(issue_band)

        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        for result in ordered:
            rows_layout.addWidget(self._build_row(result))
        rows_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_container)
        self._root.addWidget(scroll, stretch=1)

        footer = self._build_bulk_footer(ordered)
        if footer is not None:
            self._root.addWidget(footer)

    def _build_bulk_footer(self, results: list[ImageTriageResult]) -> QWidget | None:
        """「問題なしを一括 accept」フッタを構築する (対象が無ければ None)。"""
        # 問題なし かつ 未 accept の画像を一括 accept 対象にする。
        clean_unaccepted = [r.image_id for r in results if not r.issues and not r.reviewed]
        if not clean_unaccepted:
            return None

        footer = QFrame()
        footer.setObjectName("resultsBulkFooter")
        layout = QHBoxLayout(footer)
        layout.addWidget(QLabel(f"問題なし {len(clean_unaccepted)} 件"))
        layout.addStretch(1)

        button = QPushButton(f"✓ 問題なしを一括 accept ({len(clean_unaccepted)})")
        button.setObjectName("resultsAcceptCleanButton")
        button.clicked.connect(
            lambda _checked=False, ids=clean_unaccepted: self.accept_clean_requested.emit(ids)
        )
        layout.addWidget(button)
        return footer

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
        layout = QHBoxLayout(band)

        issue_total = sum(summary.issue_counts.values())
        tier_text = self._format_tier_distribution(summary)
        parts = [
            f"バッチ: {summary.batch_size} 件",
            f"要レビュー: {summary.needs_review_count}",
            f"clean: {summary.clean_count}",
            f"accepted: {summary.accepted_count}/{summary.batch_size}",
            f"tier: {tier_text}",
            f"issue 総数: {issue_total}",
        ]
        for text in parts:
            label = QLabel(text)
            layout.addWidget(label)
        layout.addStretch(1)
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
        layout = QHBoxLayout(band)
        for issue, count in active.items():
            layout.addWidget(self._build_issue_card(issue, count, results))
        layout.addStretch(1)
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
        layout = QVBoxLayout(row)

        layout.addWidget(self._build_row_header(result))
        layout.addWidget(self._build_tags_line(result.tags))
        layout.addWidget(self._build_caption_line(result))
        layout.addWidget(self._build_quality_line(result))
        layout.addWidget(self._build_rating_line(result))
        if result.issues:
            layout.addWidget(self._build_issue_badges(result.issues))
        return row

    def _build_row_header(self, result: ImageTriageResult) -> QWidget:
        """image_id / uuid 短縮 / WxH + レビューボタンの行を構築する。"""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        uuid_short = result.uuid[:8] if result.uuid else "-"
        dimensions = self._format_dimensions(result.width, result.height)
        ident = QLabel(f"#{result.image_id}  {uuid_short}  {dimensions}")
        ident.setObjectName(f"resultsRowIdent_{result.image_id}")
        layout.addWidget(ident)
        layout.addStretch(1)

        button = QPushButton("▸ レビュー")  # "▸ レビュー"
        button.setObjectName(f"resultsReviewButton_{result.image_id}")
        # closure に image_id を束縛 (ループ変数キャプチャ問題を defaultarg で回避)。
        button.clicked.connect(
            lambda _checked=False, image_id=result.image_id: self.review_requested.emit(image_id)
        )
        layout.addWidget(button)

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
        """タグ行を構築する (低 conf は dim プロパティ付与)。"""
        line = QWidget()
        layout = QHBoxLayout(line)
        layout.setContentsMargins(0, 0, 0, 0)

        prefix = QLabel("tags:")
        layout.addWidget(prefix)
        if not tags:
            layout.addWidget(QLabel("(なし)"))
        for tag_view in tags:
            layout.addWidget(self._build_tag_chip(tag_view))
        layout.addStretch(1)
        return line

    def _build_tag_chip(self, tag_view: TagView) -> QWidget:
        """1 タグの chip。confidence 付き、低 conf は dim 表示。"""
        if tag_view.confidence_score is not None:
            text = f"{tag_view.tag} ({tag_view.confidence_score:.2f})"
        else:
            text = tag_view.tag
        chip = QLabel(text)
        is_dim = tag_view.confidence_score is not None and tag_view.confidence_score < _DIM_CONFIDENCE
        chip.setProperty("dim", is_dim)
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
        return chip

    def _build_issue_badges(self, issues: list[IssueType]) -> QWidget:
        """その行の issue バッジ群を構築する。"""
        line = QWidget()
        layout = QHBoxLayout(line)
        layout.setContentsMargins(0, 0, 0, 0)
        for issue in issues:
            badge = QLabel(_ISSUE_LABELS.get(issue, issue.value))
            badge.setProperty("issueBadge", True)
            layout.addWidget(badge)
        layout.addStretch(1)
        return line
