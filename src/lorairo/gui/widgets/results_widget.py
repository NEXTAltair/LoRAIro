"""Frame 5 · Results 読み取り専用トリアージ表示ウィジェット。

``QualityIssueDetectionService`` が算出した ``BatchTriageSummary`` /
``ImageTriageResult`` を受け取り、サマリ band・issue カード・per-image 行を
描画する。検出ロジックは持たず表示に専念する (MVC の View)。
"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QPixmap, QResizeEvent, QShowEvent
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

# issue 種別の user-facing ラベル (per-row バッジ用の短縮形。#1139)。
_ISSUE_LABELS: dict[IssueType, str] = {
    IssueType.EMPTY_TAGS: "タグ無し",
    IssueType.NO_SCORE: "スコア無し",
    IssueType.UNKNOWN_TIER: "品質ラベル未対応",
    IssueType.RATING_DISAGREEMENT: "レーティング不一致",
    IssueType.SCORER_DISAGREEMENT: "品質スコア不一致",
}

# issue カード見出し用の説明的ラベル (初見でも意味が分かる日本語。#1139)。
_ISSUE_CARD_LABELS: dict[IssueType, str] = {
    IssueType.EMPTY_TAGS: "タグがありません",
    IssueType.NO_SCORE: "品質スコアがありません",
    IssueType.UNKNOWN_TIER: "品質ラベルを段階に変換できません",
    IssueType.RATING_DISAGREEMENT: "レーティング判定が割れています",
    IssueType.SCORER_DISAGREEMENT: "品質スコアの判定が割れています",
}

# 対処ガイド (カードの1行アクション文 + バッジ/見出しのツールチップ。#1139)。
_ISSUE_GUIDANCE: dict[IssueType, str] = {
    IssueType.EMPTY_TAGS: "タグを付与するか、アノテーションをやり直してください。",
    IssueType.NO_SCORE: "品質スコアラーを実行してください。",
    IssueType.UNKNOWN_TIER: (
        "このモデルのラベルは品質段階マップに未登録です (ADR 0028)。"
        "画像を確認して手動で品質を確定してください。"
    ),
    IssueType.RATING_DISAGREEMENT: (
        "複数の AI モデルでレーティング判定が割れています。"
        "画像を確認し、正しいレーティングを手動で確定してください。"
    ),
    IssueType.SCORER_DISAGREEMENT: (
        "複数の AI モデルで品質スコアの判定が割れています。画像を確認し、品質を手動で確定してください。"
    ),
}


def _rating_evidence(result: ImageTriageResult) -> str:
    """rating 不一致の実値サマリ (``wd-rating=PG / moderation=R``) を組み立てる (#1139)。"""
    parts = [f"{r.model}={r.normalized_rating}" for r in result.ratings if r.normalized_rating]
    return " / ".join(parts)


def _scorer_evidence(result: ImageTriageResult) -> str:
    """scorer 不一致の実値サマリ (``aesthetic=最高品質 / technical=良品質``) を組み立てる (#1139)。"""
    parts: list[str] = []
    for scorer in result.scorers:
        value = scorer.tier.label if scorer.tier is not None else (scorer.label or "?")
        parts.append(f"{scorer.model}={value}")
    return " / ".join(parts)


def _unknown_tier_evidence(result: ImageTriageResult) -> str:
    """tier 変換不能な scorer の実値サマリ (``model=label(未対応)``) を組み立てる (#1139)。"""
    parts = [f"{s.model}={s.label or '?'}(未対応)" for s in result.scorers if s.tier is None]
    return " / ".join(parts)


# issue 種別 → 実値サマリ builder (該当画像の row データから組み立てる。#1139)。
_EVIDENCE_BUILDERS: dict[IssueType, Callable[[ImageTriageResult], str]] = {
    IssueType.RATING_DISAGREEMENT: _rating_evidence,
    IssueType.SCORER_DISAGREEMENT: _scorer_evidence,
    IssueType.UNKNOWN_TIER: _unknown_tier_evidence,
}


def _issue_evidence(issue: IssueType, results: list[ImageTriageResult]) -> str | None:
    """当該 issue の代表例 (先頭該当画像) の実値サマリを ``例: #id ...`` 形式で返す (#1139)。

    実値を持たない issue (タグ無し / スコア無し) は None。
    """
    builder = _EVIDENCE_BUILDERS.get(issue)
    if builder is None:
        return None
    for result in results:
        if issue in result.issues:
            body = builder(result)
            if body:
                return f"例: #{result.image_id} {body}"
    return None


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._root = QVBoxLayout(self)
        # 描画順の image_id を保持 (内部アクセサ _row_order が返す)。
        self._row_image_ids: list[int] = []
        # CLEAN 監査 (OK箱) の再描画・引き直し用に直近の入力を保持する。
        self._summary_cache: BatchTriageSummary | None = None
        self._results_cache: list[ImageTriageResult] = []
        self._clean_plan: CleanAuditPlan | None = None
        self._staged_image_ids: frozenset[int] = frozenset()
        self._force_resample: bool = False
        # image_id -> 行内サムネイルの画像パス (#1104) と表示用ファイル名 (#1545)。
        self._image_paths: dict[int, str] = {}
        self._image_names: dict[int, str] = {}
        # 遅延ロード対象のサムネイル一覧 (可視域だけデコードするため保持する。#1104)。
        self._row_thumbnails: list[_RowThumbnail] = []
        # 行のチャンク分割構築の状態 (#1140)。世代トークンで stale コールバックを弾く。
        self._render_generation: int = 0
        self._pending_results: list[ImageTriageResult] = []
        self._rows_layout: QVBoxLayout | None = None
        self._scroll_area: QScrollArea | None = None
        self._summary_labels: dict[str, QLabel] = {}
        self._summary_flow: _FlowChipRow | None = None
        self._clean_audit_band: QWidget | None = None
        self._clean_audit_host_layout: QVBoxLayout | None = None
        self._row_widgets: dict[int, list[QFrame]] = {}
        self._main_row_widgets: dict[int, QFrame] = {}
        self._focused_image_id: int | None = None
        self.clear()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    @property
    def focused_image_id(self) -> int | None:
        """現在キーボードフォーカスされている行の image_id を返す (#1545)。"""
        return self._focused_image_id

    def set_focused_image_id(self, image_id: int | None, *, ensure_visible: bool = True) -> None:
        """フォーカス行を設定し、スタイルとスクロール可視域を更新する (#1545)。"""
        if image_id is not None and image_id not in self._row_image_ids:
            return
        prev_id = self._focused_image_id
        self._focused_image_id = image_id
        by_id = {r.image_id: r for r in self._results_cache}
        if prev_id is not None and prev_id != image_id:
            prev_res = by_id.get(prev_id)
            if prev_res is not None:
                for row in self._row_widgets.get(prev_id, []):
                    self._apply_row_state(row, prev_res)
        if image_id is not None:
            self._ensure_row_built(image_id)
            curr_res = by_id.get(image_id)
            if curr_res is not None:
                for row in self._row_widgets.get(image_id, []):
                    self._apply_row_state(row, curr_res)
            if ensure_visible and self._scroll_area is not None:
                target_row = self._main_row_widgets.get(image_id)
                if target_row is not None:
                    self._scroll_area.ensureWidgetVisible(target_row)

    def focus_next_row(self) -> int | None:
        """フォーカスを次の行へ進める (#1545)。"""
        if not self._row_image_ids:
            return None
        if self._focused_image_id not in self._row_image_ids:
            target = self._row_image_ids[0]
        else:
            idx = self._row_image_ids.index(self._focused_image_id)
            target = self._row_image_ids[min(idx + 1, len(self._row_image_ids) - 1)]
        self.set_focused_image_id(target, ensure_visible=True)
        return self._focused_image_id

    def focus_previous_row(self) -> int | None:
        """フォーカスを前の行へ戻す (#1545)。"""
        if not self._row_image_ids:
            return None
        if self._focused_image_id not in self._row_image_ids:
            target = self._row_image_ids[0]
        else:
            idx = self._row_image_ids.index(self._focused_image_id)
            target = self._row_image_ids[max(idx - 1, 0)]
        self.set_focused_image_id(target, ensure_visible=True)
        return self._focused_image_id

    def accept_focused_row(self) -> int | None:
        """現在フォーカスされている行を accept するシグナルを発火する (#1545)。"""
        if not self._row_image_ids:
            return None
        if self._focused_image_id not in self._row_image_ids:
            self.set_focused_image_id(self._row_image_ids[0], ensure_visible=True)
        if self._focused_image_id is not None:
            self.accept_requested.emit(self._focused_image_id)
        return self._focused_image_id

    def handle_navigation_key(self, key: int) -> bool:
        """キーボードナビゲーション操作を処理する (#1545)。"""
        if not self._row_image_ids:
            return False
        if key in (Qt.Key.Key_Down, Qt.Key.Key_J):
            self.focus_next_row()
            return True
        if key in (Qt.Key.Key_Up, Qt.Key.Key_K):
            self.focus_previous_row()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_A):
            self.accept_focused_row()
            return True
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """上下キーでフォーカス行を移動し、Enter/Space で accept する (#1545)。"""
        if self.handle_navigation_key(event.key()):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """QScrollArea が上下キーや Space を奪うのを防ぎ行操作へ委譲する (#1545)。"""
        if (
            watched is self._scroll_area
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and self.handle_navigation_key(event.key())
        ):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def set_image_reviewed(self, image_id: int, *, reviewed: bool = True) -> bool:
        """単一画像の reviewed 状態をインプレース更新する (#1545)。

        全行ウィジェットの再構築・スクロール位置のリセット・CLEAN 監査サンプルの再抽選を
        行わずに、対象行のボタン/スタイルとサマリ帯のカウントのみを更新する。

        Args:
            image_id: 対象画像 ID。
            reviewed: True なら accept 済み、False なら未 accept。

        Returns:
            表示キャッシュ内に対象画像が存在し更新できた場合 True、存在しなければ False。
        """
        return self.set_images_reviewed([image_id], reviewed=reviewed)

    def set_images_reviewed(self, image_ids: list[int], *, reviewed: bool = True) -> bool:
        """複数画像の reviewed 状態をインプレースで一括更新する (#1545)。

        Args:
            image_ids: 対象画像 ID リスト。
            reviewed: True なら accept 済み、False なら未 accept。

        Returns:
            表示キャッシュ内に対象画像が 1 件以上存在し更新できた場合 True。
        """
        if not image_ids or not self._results_cache:
            return False

        target_ids = set(image_ids)
        matched = False
        clean_affected = False
        updated_by_id: dict[int, ImageTriageResult] = {}

        new_results: list[ImageTriageResult] = []
        for result in self._results_cache:
            if result.image_id in target_ids:
                matched = True
                if not result.issues:
                    clean_affected = True
                updated = replace(result, reviewed=reviewed)
                new_results.append(updated)
                updated_by_id[result.image_id] = updated
            else:
                new_results.append(result)

        if not matched:
            return False

        saved_scroll = (
            self._scroll_area.verticalScrollBar().value() if self._scroll_area is not None else None
        )

        self._results_cache = new_results
        if self._pending_results:
            self._pending_results = [updated_by_id.get(r.image_id, r) for r in self._pending_results]

        self._summary_cache = QualityIssueDetectionService().summarize(self._results_cache)
        self._update_summary_band(self._summary_cache)

        for image_id, updated in updated_by_id.items():
            self._update_row_widgets_for_image(image_id, updated)

        if clean_affected:
            self._clean_plan = self._resolve_clean_plan(self._results_cache, self._clean_plan)
            self._rebuild_clean_audit_band()

        if self._scroll_area is not None and saved_scroll is not None:
            self._scroll_area.verticalScrollBar().setValue(saved_scroll)

        return True

    def display(
        self,
        summary: BatchTriageSummary,
        results: list[ImageTriageResult],
        image_paths: dict[int, str] | None = None,
        image_names: dict[int, str] | None = None,
    ) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。

        Args:
            summary: バッチ全体のサマリ。
            results: 画像別トリアージ結果。``needs_review`` を優先して縦に並べる。
            image_paths: image_id -> 行内サムネイル用の画像パス (#1104)。省略時は
                サムネイルをプレースホルダ表示にする (View は DB を持たないため、
                パス解決は呼び出し元 ``ResultsTabWidget`` が担う)。
            image_names: image_id -> 行ラベルに表示するファイル名 (#1545)。
        """
        prev_staged_ids = self._staged_image_ids
        prev_clean_plan = self._clean_plan
        prev_focused_id = self._focused_image_id
        prev_scroll_val = (
            self._scroll_area.verticalScrollBar().value() if self._scroll_area is not None else 0
        )

        self._reset()
        self._summary_cache = summary
        self._results_cache = list(results)
        self._image_paths = dict(image_paths) if image_paths else {}
        self._image_names = dict(image_names) if image_names else {}

        if not results:
            self._staged_image_ids = frozenset()
            self._clean_plan = None
            self._focused_image_id = None
            self._build_empty_state()
            return

        new_staged_ids = frozenset(r.image_id for r in results)
        same_staged_set = (new_staged_ids == prev_staged_ids) and not self._force_resample
        self._staged_image_ids = new_staged_ids

        # CLEAN 監査 (OK箱) の抜き取りプランを算出する。
        # ステージング集合が同一で引き直し指示が無ければ既存サンプルを維持する (#1545)。
        self._clean_plan = self._resolve_clean_plan(results, prev_clean_plan if same_staged_set else None)

        # needs_review (issue 有) を先頭に安定ソートする。
        ordered = sorted(results, key=lambda r: not r.needs_review)
        if len(ordered) >= _VIRTUALIZE_THRESHOLD:
            # 大規模 degrade 時は本体の per-image 行を描画しないため、未描画行に対する
            # キーボードフォーカス移動や Enter/Space accept 発火を無効化する (#1545 Codex P2)。
            self._row_image_ids = []
            self._focused_image_id = None
        else:
            self._row_image_ids = [r.image_id for r in ordered]
            if same_staged_set and prev_focused_id in self._row_image_ids:
                self._focused_image_id = prev_focused_id
            else:
                self._focused_image_id = self._row_image_ids[0] if self._row_image_ids else None

        self._root.addWidget(self._build_summary_band(summary))
        issue_band = self._build_issue_band(summary, ordered)
        if issue_band is not None:
            self._root.addWidget(issue_band)

        # 大規模時は per-row 描画を諦め、サマリ + issue 集約 + 集約ノーティスを表示する
        # (#1140、数千 chip の一括構築を避け絞り込みへ誘導。wireframes Results@500)。
        # ただし clean-audit の抜き取り監査バンド (少数行 + 一括 accept) は残す
        # (degrade でも「確認して accept」導線を失わない。Codex #1143 P2-2)。
        if len(ordered) >= _VIRTUALIZE_THRESHOLD:
            # ノーティス + clean-audit バンドは QScrollArea に収める。ルート直付けだと
            # 抜き取り行 (最大 30) がウィンドウ高を超えたときにスクロールできない
            # (Codex #1143 2巡目 P2)。
            degrade_container = QWidget()
            degrade_layout = QVBoxLayout(degrade_container)
            degrade_layout.setContentsMargins(0, 0, 0, 0)
            degrade_layout.addWidget(self._build_scale_notice(len(ordered)))
            self._clean_audit_host_layout = degrade_layout
            band = self._build_clean_audit_band(ordered)
            if band is not None:
                degrade_layout.addWidget(band)
                self._clean_audit_band = band
            degrade_layout.addStretch(1)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(degrade_container)
            scroll.installEventFilter(self)
            # clean-audit の抜き取り行サムネイルをスクロールで可視域に入った時にロードする。
            scroll.verticalScrollBar().valueChanged.connect(self._load_visible_thumbnails)
            self._scroll_area = scroll
            self._root.addWidget(scroll, stretch=1)
            if same_staged_set and prev_scroll_val > 0:
                scroll.verticalScrollBar().setValue(prev_scroll_val)
            QTimer.singleShot(0, self, self._load_visible_thumbnails)
            return

        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.addStretch(1)  # 末尾 stretch。行はこの前に挿入していく。

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_container)
        scroll.installEventFilter(self)
        # スクロールで新たに可視域へ入った行のサムネイルを追ってデコードする (#1104)。
        scroll.verticalScrollBar().valueChanged.connect(self._load_visible_thumbnails)
        self._scroll_area = scroll
        self._root.addWidget(scroll, stretch=1)

        self._clean_audit_host_layout = self._root
        band = self._build_clean_audit_band(ordered)
        if band is not None:
            self._root.addWidget(band)
            self._clean_audit_band = band

        # 行はチャンク分割で構築し、GUI スレッドを長時間ブロックしない (#1140)。
        # 初回チャンクは同期構築して初期表示を出し、残りはイベントループ復帰後に足す。
        self._rows_layout = rows_layout
        self._pending_results = list(ordered)
        self._build_next_row_chunk(self._render_generation)
        if same_staged_set and prev_scroll_val > 0:
            scroll.verticalScrollBar().setValue(prev_scroll_val)
        # 先頭スクリーン分のサムネイルをレイアウト確定後にロードする (可視域のみ、#1104)。
        QTimer.singleShot(0, self, self._load_visible_thumbnails)

    @staticmethod
    def _resolve_clean_plan(
        results: list[ImageTriageResult],
        prev_plan: CleanAuditPlan | None,
    ) -> CleanAuditPlan:
        """CLEAN 監査プランを算出する。既存サンプルが有効なら引き直さず維持する (#1545)。"""
        clean_ids = [r.image_id for r in results if not r.issues and not r.reviewed]
        if not clean_ids:
            return CleanAuditPlan(clean_image_ids=[], sample_image_ids=[])
        if prev_plan is not None and prev_plan.sample_image_ids:
            clean_set = set(clean_ids)
            kept_sample = [sid for sid in prev_plan.sample_image_ids if sid in clean_set]
            if kept_sample and clean_set <= set(prev_plan.clean_image_ids):
                return CleanAuditPlan(clean_image_ids=clean_ids, sample_image_ids=kept_sample)
        return QualityIssueDetectionService.build_clean_audit(results)

    def _ensure_row_built(self, image_id: int) -> None:
        """チャンク未構築の行へフォーカス移動した際に対象行まで同期構築する (#1545)。"""
        layout = self._rows_layout
        if layout is None:
            return
        while self._pending_results and image_id not in self._main_row_widgets:
            result = self._pending_results.pop(0)
            layout.insertWidget(layout.count() - 1, self._build_row(result))

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
                layout.addWidget(self._build_row(result, is_audit_sample=True))

        accept = QPushButton(f"✓ 確認して accept ({clean_count})")
        accept.setObjectName("resultsAcceptCleanButton")
        accept.clicked.connect(self._on_clean_accept_clicked)
        layout.addWidget(accept)
        return band

    def _rebuild_clean_audit_band(self) -> None:
        """スクロール領域や一覧行を壊さずに CLEAN 監査バンドだけを再構築する (#1545)。"""
        if self._clean_audit_band is not None:
            old_band = self._clean_audit_band
            self._row_thumbnails = [t for t in self._row_thumbnails if not old_band.isAncestorOf(t)]
            for image_id, rows in list(self._row_widgets.items()):
                self._row_widgets[image_id] = [r for r in rows if not old_band.isAncestorOf(r)]
            if self._clean_audit_host_layout is not None:
                self._clean_audit_host_layout.removeWidget(old_band)
            old_band.setObjectName("")
            old_band.setParent(None)
            old_band.deleteLater()
            self._clean_audit_band = None

        band = self._build_clean_audit_band(self._results_cache)
        if band is not None and self._clean_audit_host_layout is not None:
            if self._clean_audit_host_layout is self._root:
                self._root.addWidget(band)
            else:
                self._clean_audit_host_layout.insertWidget(
                    max(0, self._clean_audit_host_layout.count() - 1), band
                )
            self._clean_audit_band = band

    def _resample_clean(self) -> None:
        """抜き取りサンプルを引き直す (CLEAN 監査プランのみ再抽選してバンドを更新する)。"""
        if self._summary_cache is not None and self._results_cache:
            self._clean_plan = QualityIssueDetectionService.build_clean_audit(self._results_cache)
            self._rebuild_clean_audit_band()
            self._load_visible_thumbnails()

    def _on_clean_accept_clicked(self) -> None:
        """CLEAN 監査バンドの一括 accept ボタン押下ハンドラ。"""
        if self._clean_plan is None or not self._clean_plan.clean_image_ids:
            return
        self._on_clean_accept(
            list(self._clean_plan.clean_image_ids),
            list(self._clean_plan.sample_image_ids),
        )

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
        self._staged_image_ids = frozenset()
        self._clean_plan = None
        self._focused_image_id = None
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
        self._image_names = {}
        # 破棄されるサムネイル参照を先に手放す (スクロール再評価が stale を触らないよう)。
        self._row_thumbnails = []
        # 世代を進めて進行中のチャンク構築コールバックを無効化し、pending をクリアする (#1140)。
        self._render_generation += 1
        self._pending_results = []
        self._rows_layout = None
        self._scroll_area = None
        self._summary_labels = {}
        self._summary_flow = None
        self._clean_audit_band = None
        self._clean_audit_host_layout = None
        self._row_widgets = {}
        self._main_row_widgets = {}
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
        self._summary_flow = flow
        self._summary_labels = {}

        for key, text, color in self._summary_parts(summary):
            label = QLabel(text)
            label.setObjectName(f"resultsSummary_{key}")
            label.setStyleSheet(f"color: {color}; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
            flow.add_widget(label)
            self._summary_labels[key] = label
        return band

    def _summary_parts(self, summary: BatchTriageSummary) -> list[tuple[str, str, str]]:
        """サマリ帯の各項目 (キー, 表示テキスト, 色) を返す。"""
        issue_total = sum(summary.issue_counts.values())
        tier_text = self._format_tier_distribution(summary)
        return [
            ("batch", f"バッチ: {summary.batch_size} 件", theme.INK_SOFT),
            ("needs_review", f"要レビュー: {summary.needs_review_count}", theme.WARN),
            ("clean", f"clean: {summary.clean_count}", theme.OK),
            ("accepted", f"accepted: {summary.accepted_count}/{summary.batch_size}", theme.OK),
            ("tier", f"tier: {tier_text}", theme.INK_SOFT),
            ("issue_total", f"issue 総数: {issue_total}", theme.INK_SOFT),
        ]

    def _update_summary_band(self, summary: BatchTriageSummary) -> None:
        """サマリ band のラベル文言をインプレース更新する (#1545)。"""
        if not self._summary_labels:
            return
        for key, text, _color in self._summary_parts(summary):
            label = self._summary_labels.get(key)
            if label is not None:
                label.setText(text)
        if self._summary_flow is not None:
            self._summary_flow._adjust_height()

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
        """1 issue 種別のカードを構築する (#1139: 説明的見出し + 実値 + 対処ガイド)。"""
        card = QFrame()
        card.setObjectName(f"resultsIssueCard_{issue.value}")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        # 見出しは初見でも意味が分かる説明的ラベル (#1139)。対処ガイドは tooltip にも出す。
        heading = _ISSUE_CARD_LABELS.get(issue, _ISSUE_LABELS.get(issue, issue.value))
        guidance = _ISSUE_GUIDANCE.get(issue)
        header = QLabel(f"{heading} ({count})")
        header.setObjectName("resultsIssueCardHeader")
        # DS: issue 種別は重大度で色分けした chip 文法
        header.setStyleSheet(theme.chip_qss(_ISSUE_CHIP_KINDS.get(issue, "warn")))
        if guidance:
            header.setToolTip(guidance)
        layout.addWidget(header)

        # 実値サマリ (どのモデルが何と判定したか) を1行添える (#1139)。
        evidence = _issue_evidence(issue, results)
        if evidence:
            evidence_label = QLabel(evidence)
            evidence_label.setObjectName("resultsIssueCardEvidence")
            evidence_label.setWordWrap(True)
            evidence_label.setStyleSheet(f"color: {theme.INK_FAINT}; font-family: {theme.FONT_MONO_CSS};")
            layout.addWidget(evidence_label)

        # 対処ガイド (1行アクション文) を添える (#1139)。
        if guidance:
            guidance_label = QLabel(guidance)
            guidance_label.setObjectName("resultsIssueCardGuidance")
            guidance_label.setWordWrap(True)
            guidance_label.setStyleSheet(f"color: {theme.INK_SOFT};")
            layout.addWidget(guidance_label)

        image_ids = [r.image_id for r in results if issue in r.issues]
        id_text = ", ".join(f"#{image_id}" for image_id in image_ids)
        ids_label = QLabel(id_text)
        ids_label.setWordWrap(True)
        layout.addWidget(ids_label)
        return card

    def _build_row(self, result: ImageTriageResult, *, is_audit_sample: bool = False) -> QWidget:
        """1 画像分の per-image 行を構築する。"""
        row = QFrame()
        row.setObjectName(f"resultsRow_{result.image_id}")
        row.setFrameShape(QFrame.Shape.StyledPanel)
        row.setProperty("imageId", result.image_id)
        row.setProperty("auditSample", is_audit_sample)
        self._row_widgets.setdefault(result.image_id, []).append(row)
        if not is_audit_sample:
            self._main_row_widgets[result.image_id] = row
        self._apply_row_state(row, result)

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

    def _apply_row_state(self, row: QFrame, result: ImageTriageResult) -> None:
        """行フレームのプロパティとスタイルシートを状態に合わせて適用する (#1545)。"""
        is_focused = not bool(row.property("auditSample")) and self._focused_image_id == result.image_id
        row.setProperty("needsReview", result.needs_review)
        row.setProperty("accepted", result.reviewed)
        row.setProperty("focused", is_focused)

        border_color = (
            theme.ACCENT if is_focused else (theme.WARN_BORDER if result.needs_review else theme.LINE)
        )
        border_width = 2 if is_focused else theme.BORDER_WIDTH
        bg_rule = f" background-color: {theme.WARN_SOFT};" if result.needs_review else ""

        if result.needs_review or is_focused:
            row.setStyleSheet(
                f"QFrame#resultsRow_{result.image_id} {{"
                f" border: {border_width}px solid {border_color};"
                f"{bg_rule} border-radius: {theme.RADIUS}px; }}"
            )
        else:
            row.setStyleSheet("")

    def _resolve_row_filename(self, result: ImageTriageResult) -> str | None:
        """行ラベルに表示する画像ファイル名を解決する (#1545)。"""
        if result.filename and result.filename.strip():
            return Path(result.filename).name
        named = self._image_names.get(result.image_id)
        if named and named.strip():
            return Path(named).name
        path_str = self._image_paths.get(result.image_id)
        if path_str and path_str.strip():
            return Path(path_str).name
        return None

    def _create_row_action_button(self, image_id: int, *, reviewed: bool) -> QPushButton:
        """reviewed 状態に応じた行アクションボタン (accept / 取消) を構築する。"""
        if reviewed:
            undo = QPushButton("↩ 取消")
            undo.setObjectName(f"resultsUnacceptButton_{image_id}")
            undo.clicked.connect(lambda _checked=False, iid=image_id: self.unaccept_requested.emit(iid))
            return undo
        accept = QPushButton("✓ accept")
        accept.setObjectName(f"resultsAcceptButton_{image_id}")
        accept.clicked.connect(lambda _checked=False, iid=image_id: self.accept_requested.emit(iid))
        return accept

    def _update_row_widgets_for_image(self, image_id: int, result: ImageTriageResult) -> None:
        """指定 image_id の既存行ウィジェットを破棄せずインプレース更新する (#1545)。"""
        for row in list(self._row_widgets.get(image_id, [])):
            self._apply_row_state(row, result)
            header = row.findChild(QWidget, f"resultsRowHeader_{image_id}")
            if header is None or header.layout() is None:
                continue
            header_layout = header.layout()
            assert header_layout is not None
            for btn_name in (
                f"resultsAcceptButton_{image_id}",
                f"resultsUnacceptButton_{image_id}",
            ):
                old_btn = header.findChild(QPushButton, btn_name)
                if old_btn is not None:
                    header_layout.removeWidget(old_btn)
                    old_btn.setObjectName("")
                    old_btn.setParent(None)
                    old_btn.deleteLater()
            header_layout.addWidget(self._create_row_action_button(image_id, reviewed=result.reviewed))

    def _build_row_header(self, result: ImageTriageResult) -> QWidget:
        """image_id / ファイル名 / uuid 短縮 / WxH + accept ボタンの行を構築する。"""
        header = QWidget()
        header.setObjectName(f"resultsRowHeader_{result.image_id}")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        uuid_short = result.uuid[:8] if result.uuid else "-"
        dimensions = self._format_dimensions(result.width, result.height)
        filename = self._resolve_row_filename(result)
        if filename:
            ident_text = f"#{result.image_id}  {filename}  {uuid_short}  {dimensions}"
        else:
            ident_text = f"#{result.image_id}  {uuid_short}  {dimensions}"
        ident = QLabel(ident_text)
        ident.setObjectName(f"resultsRowIdent_{result.image_id}")
        layout.addWidget(ident)
        layout.addStretch(1)

        layout.addWidget(self._create_row_action_button(result.image_id, reviewed=result.reviewed))
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
            # バッジは短縮形なので、意味と対処を tooltip で補う (#1139)。
            guidance = _ISSUE_GUIDANCE.get(issue)
            if guidance:
                badge.setToolTip(guidance)
            layout.addWidget(badge)
        layout.addStretch(1)
        return line
