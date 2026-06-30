"""
Annotation Data Display Widget

汎用アノテーション結果表示コンポーネント
タグ・キャプション・スコア情報の統一表示を提供

タグ欄の責務は ADR 0083 / Issue #987 で ``TagPanelWidget`` へ切り出した。本ウィジェットは
``groupBoxTags`` 内に ``TagPanelWidget`` を埋め込み、タグ関連の public メソッド / Signal を
委譲再公開する薄い親として振る舞う (Caption / Score / Rating / QualityTier は本ウィジェットが保持)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMenu,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.AnnotationDataDisplayWidget_ui import Ui_AnnotationDataDisplayWidget
from ...utils.log import logger
from .. import theme
from .tag_panel_widget import SelectableTagChip, TagPanelWidget

# SelectableTagChip は ADR 0083 で tag_panel_widget へ移設した。後方互換のため本モジュール
# からも再公開する (既存 import: `from ...annotation_data_display_widget import SelectableTagChip`)。
__all__ = [
    "AnnotationData",
    "AnnotationDataDisplayWidget",
    "ImageDetails",
    "SelectableTagChip",
]

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation


@dataclass
class AnnotationData:
    """アノテーション表示用データ"""

    tags: list[dict[str, Any]] = field(default_factory=list)  # Repository層から提供される詳細情報
    caption: str = ""
    aesthetic_score: float | None = None
    overall_score: int = 0
    score_type: str = "Aesthetic"
    # ADR 0028: canonical scorer の categorical label を {model, label, ...} ペアで保持
    score_labels: list[dict[str, Any]] = field(default_factory=list)
    # Issue #334: model-native rating record を model 別に保持
    ratings: list[dict[str, Any]] = field(default_factory=list)
    # ADR 0029: 統一品質 tier (raw annotation からの derived view)
    quality_summary: dict[str, Any] = field(default_factory=dict)
    # 翻訳データ: {tag_id: {language: translated_text}}
    tag_translations: dict[int, dict[str, str]] = field(default_factory=dict)
    # 利用可能な言語リスト（get_tag_languages()から取得）
    available_languages: list[str] = field(default_factory=list)


@dataclass
class ImageDetails:
    """選択画像の詳細情報"""

    image_id: int | None = None
    file_name: str = ""
    file_path: str = ""
    image_size: str = ""  # "1920x1080" format
    file_size: str = ""  # "2.5 MB" format
    created_date: str = ""  # "2025-07-29 15:30:00" format
    rating_value: str = ""  # "PG", "R", etc. (解決済み: 手動優先・無ければAI)
    score_value: int = 0  # 0-1000 range (解決済み: 手動優先・無ければAI)
    # Issue #825: スコアカードの AI/手動セクション分離表示用
    ai_rating_value: str = ""  # AI 判定 rating (無ければ空)
    manual_rating_value: str = ""  # 手動 rating (無ければ空)
    ai_score_value: float | None = None  # AI スコア (DB値 0.0-10.0、無ければ None)
    manual_score_value: float | None = None  # 手動スコア (DB値 0.0-10.0、無ければ None)
    caption: str = ""  # Image caption text
    tags: str = ""  # Comma-separated tags
    # オリジナル画像メタデータ (Issue #813): 登録時にリサイズ/拡張子変換されるため original を表示
    original_extension: str = ""  # ".png" / ".jpg" 等 (Image.extension 由来)
    aspect_ratio: str = ""  # "16:9" 等 (original width:height の既約比)
    alpha_text: str = ""  # "あり (RGBA)" / "なし (RGB)" / "不明"
    annotation_data: AnnotationData | None = field(default=None)

    def __post_init__(self) -> None:
        if self.annotation_data is None:
            self.annotation_data = AnnotationData()


class AnnotationDataDisplayWidget(QWidget, Ui_AnnotationDataDisplayWidget):
    """
    アノテーション結果の汎用表示ウィジェット

    機能:
    - タグ (TagPanelWidget へ委譲) / キャプション / スコア情報の統一表示
    - 読み取り専用表示
    - データクリア・更新機能
    """

    # シグナル
    data_loaded = Signal(AnnotationData)  # データロード完了
    data_cleared = Signal()  # データクリア完了
    # タグ操作 (TagPanelWidget から委譲再公開、ADR 0083 §2)。引数は canonical タグ文字列。
    tag_reject_requested = Signal(str)  # 無効化・✕ 共通で soft-reject
    tag_restore_requested = Signal(str)  # soft-rejected タグを復活
    tag_add_requested = Signal(str)  # 手動タグ追加 (生入力)
    refinement_ignored = Signal(str, str)  # refinement リコメンドを無視 (canonical, reason_code) (#931)

    # タグチップ箱の高さ上限 (#835)。TagPanelWidget と同値を持ち、後方互換のため公開する。
    _TAGS_MAX_HEIGHT = 220

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)

        # 現在のデータ
        self.current_data: AnnotationData = AnnotationData()

        # UI初期化
        self._setup_tag_panel()
        self._setup_widget_properties()
        self._setup_caption_compact_view()
        self._setup_score_labels_compact_view()
        self._setup_quality_tier_badge()
        self._setup_ratings_table_view()
        self._adjust_content_heights()

        logger.debug("AnnotationDataDisplayWidget initialized")

    # ─── タグ欄 (TagPanelWidget 委譲) ──────────────────────────────────

    def _setup_tag_panel(self) -> None:
        """タグ欄を ``TagPanelWidget`` に委譲する (ADR 0083 / Issue #987)。

        .ui 由来の ``tableWidgetTags`` は TagPanelWidget が自前で持つため除去し、
        ``groupBoxTags`` の ``verticalLayoutTags`` に TagPanelWidget を埋め込む。
        後方互換のためタグ系の内部ウィジェット参照と Signal を本ウィジェットへ橋渡しする。
        """
        # .ui の旧タグテーブルを破棄する (TagPanelWidget 側の隠しテーブルへ一本化)。
        self.verticalLayoutTags.removeWidget(self.tableWidgetTags)
        self.tableWidgetTags.setParent(None)
        self.tableWidgetTags.deleteLater()

        self._tag_panel = TagPanelWidget(self.groupBoxTags)
        self.verticalLayoutTags.addWidget(self._tag_panel)

        # 後方互換: タグ系内部ウィジェットの参照を再公開する (既存テスト / 親が参照)。
        self.tableWidgetTags = self._tag_panel.tableWidgetTags
        self._lang_bar = self._tag_panel._lang_bar
        self._lang_combo = self._tag_panel._lang_combo
        self._tags_chip_container = self._tag_panel._tags_chip_container
        self._tags_chip_layout = self._tag_panel._tags_chip_layout
        self._tags_scroll = self._tag_panel._tags_scroll
        self._tags_translation_note = self._tag_panel._tags_translation_note
        self._tags_compact_label = self._tag_panel._tags_compact_label
        self._tag_add_input = self._tag_panel._tag_add_input

        # タグ操作 Signal を委譲再公開する (親 SelectedImageDetailsWidget の dispatch 維持)。
        self._tag_panel.tag_reject_requested.connect(self.tag_reject_requested)
        self._tag_panel.tag_restore_requested.connect(self.tag_restore_requested)
        self._tag_panel.tag_add_requested.connect(self.tag_add_requested)
        self._tag_panel.refinement_ignored.connect(self.refinement_ignored)

    @property
    def _tag_chips(self) -> list[SelectableTagChip]:
        """現在描画中のタグ chip (TagPanelWidget が再生成のたび差し替える)。"""
        return self._tag_panel._tag_chips

    @property
    def _last_refinements(self) -> dict[str, RefinementRecommendation]:
        """保持中の refinement リコメンド (TagPanelWidget が SSoT)。"""
        return self._tag_panel._last_refinements

    def initialize_language_selector(self, available_languages: list[str]) -> None:
        """言語コンボボックスを初期化する (TagPanelWidget へ委譲)。"""
        self._tag_panel.initialize_language_selector(available_languages)

    def set_tag_edit_enabled(self, enabled: bool) -> None:
        """タグ soft-reject 編集モードを切り替える (TagPanelWidget へ委譲)。"""
        self._tag_panel.set_tag_edit_enabled(enabled)

    def set_rejected_tags(self, rejected_tags: list[str]) -> None:
        """soft-rejected タグ一覧を設定する (TagPanelWidget へ委譲)。"""
        self._tag_panel.set_rejected_tags(rejected_tags)

    def apply_refinements(self, recommendations: dict[str, RefinementRecommendation]) -> None:
        """各タグ chip に refinement リコメンドを反映する (TagPanelWidget へ委譲、#931)。"""
        self._tag_panel.apply_refinements(recommendations)

    def displayed_tags_text(self) -> str:
        """現在の言語選択で表示されているタグ文字列を返す (TagPanelWidget へ委譲)。"""
        return self._tag_panel.displayed_tags_text()

    @Slot()
    def copy_selected_tags_to_clipboard(self) -> bool:
        """選択中タグ (無選択なら全タグ) をコピーする (TagPanelWidget へ委譲、#814)。"""
        return self._tag_panel.copy_selected_tags_to_clipboard()

    @Slot()
    def copy_selected_tag_cells_to_clipboard(self) -> bool:
        """タグテーブルの選択セルを TSV コピーする (TagPanelWidget へ委譲)。"""
        return self._tag_panel.copy_selected_tag_cells_to_clipboard()

    def _render_tag_chips(self, chip_items: list[tuple[str, str, bool]], *, is_translated: bool) -> None:
        """タグチップを再描画する (TagPanelWidget へ委譲、#931 のテスト互換)。"""
        self._tag_panel._render_tag_chips(chip_items, is_translated=is_translated)

    # ─── ウィジェット共通 ─────────────────────────────────────────────

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定 (タグ欄を除く)。"""
        self.textEditCaption.setReadOnly(True)
        self.textEditCaption.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._make_label_copyable(self.labelScoreTypeValue)
        self._make_label_copyable(self.labelOverallValue)

    def _setup_caption_compact_view(self) -> None:
        self._caption_compact_label = QLabel(self.groupBoxCaption)
        self._caption_compact_label.setWordWrap(True)
        self._caption_compact_label.setText("キャプションが表示されます")
        self._caption_compact_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._make_label_copyable(self._caption_compact_label)
        self.verticalLayoutCaption.insertWidget(0, self._caption_compact_label)
        self.textEditCaption.setVisible(False)

    def _setup_score_labels_compact_view(self) -> None:
        """スコアラベル compact pill コンテナの初期化 (ADR 0028)。

        各 scorer model 1 pill で `[model] label` 形式の QLabel を動的に配置する。
        score_labels が空のときは placeholder ("-") のみ表示し、container を hide する。
        """
        from PySide6.QtWidgets import QHBoxLayout

        self._score_labels_container = QWidget(self.groupBoxScoreLabels)
        layout = QHBoxLayout(self._score_labels_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addStretch(1)  # pill を左寄せするための末尾 stretch
        self._score_labels_layout = layout
        self._score_labels_container.setVisible(False)
        self.verticalLayoutScoreLabels.addWidget(self._score_labels_container)

    def _setup_quality_tier_badge(self) -> None:
        """品質 tier badge の初期化 (ADR 0029)。

        ``groupBoxScoreLabels`` 内、per-scorer pill コンテナの上に単一 QLabel を配置する。
        ``quality_summary`` が空のときは hide する。
        """
        self._quality_tier_label = QLabel(self.groupBoxScoreLabels)
        self._quality_tier_label.setText("品質: -")
        self._quality_tier_label.setVisible(False)
        self._make_label_copyable(self._quality_tier_label)
        # pill コンテナの前 (上) に挿入
        self.verticalLayoutScoreLabels.insertWidget(0, self._quality_tier_label)

    def _setup_ratings_table_view(self) -> None:
        """モデル別 rating record の read-only table を初期化する (Issue #334)。"""
        self.groupBoxRatings = QGroupBox("レーティング詳細", self)
        ratings_layout = QVBoxLayout(self.groupBoxRatings)
        ratings_layout.setSpacing(4)
        ratings_layout.setObjectName("verticalLayoutRatings")

        self.labelRatingsPlaceholder = QLabel("-", self.groupBoxRatings)
        self.labelRatingsPlaceholder.setWordWrap(True)
        self.labelRatingsPlaceholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._make_label_copyable(self.labelRatingsPlaceholder)
        ratings_layout.addWidget(self.labelRatingsPlaceholder)

        self.tableWidgetRatings = QTableWidget(self.groupBoxRatings)
        self.tableWidgetRatings.setObjectName("tableWidgetRatings")
        self.tableWidgetRatings.setColumnCount(5)
        for column, label in enumerate(["Model", "Normalized", "Raw", "Confidence", "Source"]):
            self.tableWidgetRatings.setHorizontalHeaderItem(column, QTableWidgetItem(label))
        self.tableWidgetRatings.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableWidgetRatings.setAlternatingRowColors(True)
        self.tableWidgetRatings.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableWidgetRatings.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tableWidgetRatings.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.tableWidgetRatings.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tableWidgetRatings.horizontalHeader().setStretchLastSection(True)
        self.tableWidgetRatings.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tableWidgetRatings.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableWidgetRatings.customContextMenuRequested.connect(self._show_ratings_table_context_menu)
        self._ratings_copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.tableWidgetRatings)
        self._ratings_copy_shortcut.activated.connect(self.copy_selected_rating_cells_to_clipboard)
        self.tableWidgetRatings.setVisible(False)
        ratings_layout.addWidget(self.tableWidgetRatings)

        self.verticalLayoutMain.addWidget(self.groupBoxRatings)
        # 親 (SelectedImageDetailsWidget) が本 widget を縦に展開させるため、末尾 stretch を
        # 置いて余剰高さを最下部に逃がす。これが無いと最後尾の groupBoxRatings が
        # 余白を吸収して「レーティング詳細」が過大表示される (#823)。
        self.verticalLayoutMain.addStretch(1)

    def _make_label_copyable(self, label: QLabel) -> None:
        """読み取り専用 QLabel を選択・コピー可能にする。"""
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(
            lambda position, target=label: self._show_label_context_menu(target, position)
        )

    def _show_label_context_menu(self, label: QLabel, position: QPoint) -> None:
        menu = QMenu(label)
        copy_action = menu.addAction("コピー")
        copy_action.setEnabled(bool(self._label_clipboard_text(label)))
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(self._label_clipboard_text(label))
        )
        menu.exec(label.mapToGlobal(position))

    @staticmethod
    def _label_clipboard_text(label: QLabel) -> str:
        """QLabel の選択テキストを優先し、未選択時は全テキストを返す。"""
        selected_text = label.selectedText()
        return selected_text if selected_text else label.text()

    @Slot(QPoint)
    def _show_ratings_table_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self.tableWidgetRatings)
        copy_action = menu.addAction("選択範囲をコピー")
        copy_action.setEnabled(bool(self.tableWidgetRatings.selectedRanges()))
        copy_action.triggered.connect(self.copy_selected_rating_cells_to_clipboard)
        menu.exec(self.tableWidgetRatings.viewport().mapToGlobal(position))

    @Slot()
    def copy_selected_rating_cells_to_clipboard(self) -> bool:
        """rating 詳細テーブルの選択セルを TSV としてクリップボードへコピーする。"""
        ranges = self.tableWidgetRatings.selectedRanges()
        if not ranges:
            return False

        lines: list[str] = []
        for selected_range in ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                values: list[str] = []
                for column in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                    item = self.tableWidgetRatings.item(row, column)
                    values.append(item.text() if item else "")
                lines.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(lines))
        return True

    # ─── データ更新 ──────────────────────────────────────────────────

    def update_data(self, data: AnnotationData) -> None:
        """アノテーションデータで表示を更新"""
        try:
            self.current_data = data

            # タグ表示更新 (TagPanelWidget へ委譲。新画像なので表示状態 / refinement はリセット)。
            self._tag_panel.set_tags(data.tags, data.tag_translations, data.available_languages)

            # キャプション表示更新
            self._update_caption_display(data.caption)

            # スコア表示更新
            self._update_scores_display(data.aesthetic_score, data.overall_score, data.score_type)

            # スコアラベル表示更新 (ADR 0028)
            self._update_score_labels_display(data.score_labels)

            # レーティング詳細表示更新 (Issue #334)
            self._update_ratings_display(data.ratings)

            # 品質 tier badge 更新 (ADR 0029)
            self._update_quality_tier_display(data.quality_summary)

            self._adjust_content_heights()

            self.data_loaded.emit(data)
            logger.debug(
                f"Annotation data updated - tags: {len(data.tags)}, "
                f"caption: {bool(data.caption)}, score_labels: {len(data.score_labels)}, "
                f"ratings: {len(data.ratings)}"
            )

        except Exception as e:
            logger.error(f"Error updating annotation data: {e}", exc_info=True)

    def _update_caption_display(self, caption: str) -> None:
        """キャプション表示を更新"""
        try:
            if caption:
                self._caption_compact_label.setText(caption)
                self.textEditCaption.setText(caption)
            else:
                placeholder = "キャプションが表示されます"
                self._caption_compact_label.setText(placeholder)
                self.textEditCaption.setText("")
                self.textEditCaption.setPlaceholderText(placeholder)

        except Exception as e:
            logger.error(f"Error updating caption display: {e}")

    def _update_scores_display(
        self, aesthetic_score: float | None, overall_score: int, score_type: str = "Aesthetic"
    ) -> None:
        """スコア表示を更新"""
        try:
            # スコアタイプラベル更新
            self.labelScoreType.setText(f"{score_type}:")

            # Aestheticスコア表示 (Issue #626: 0-10 表示尺度、小数1桁)
            if aesthetic_score is not None:
                self.labelScoreTypeValue.setText(f"{aesthetic_score:.1f}")
            else:
                self.labelScoreTypeValue.setText("-")

            # 総合スコア表示
            self.labelOverallValue.setText(str(overall_score))

        except Exception as e:
            logger.error(f"Error updating scores display: {e}")

    def _update_score_labels_display(self, score_labels: list[dict[str, Any]]) -> None:
        """スコアラベル compact pill 表示を更新する (ADR 0028)。

        各 scorer model 1 pill で ``[model] label`` 形式の QLabel を生成する。
        ADR 0028 に従い scalar shorthand は持たず、全 scorer を並列に列挙する
        (UC-C 不一致発見 / UC-A 多数決の前提)。

        Args:
            score_labels: ``[{"label": str, "model": str, ...}, ...]`` 構造の list。
                          空 list の場合は placeholder を表示し container を hide する。
        """
        try:
            layout = self._score_labels_layout
            # 既存 pill を削除 (末尾の stretch だけ残す)
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item is None:
                    break
                pill_widget = item.widget()
                if pill_widget is not None:
                    pill_widget.deleteLater()

            if not score_labels:
                self.labelScoreLabelsPlaceholder.setVisible(True)
                self._score_labels_container.setVisible(False)
                return

            self.labelScoreLabelsPlaceholder.setVisible(False)
            self._score_labels_container.setVisible(True)

            for entry in score_labels:
                model = entry.get("model", "Unknown")
                label = entry.get("label", "-")
                pill = QLabel(f"[{model}] {label}", self._score_labels_container)
                self._make_label_copyable(pill)
                pill.setStyleSheet(theme.badge_qss())
                # stretch の前 (= layout 末尾) に挿入
                layout.insertWidget(layout.count() - 1, pill)

            logger.debug(f"Updated score_labels display: {len(score_labels)} pills")

        except Exception as e:
            logger.error(f"Error updating score_labels display: {e}")

    def _update_quality_tier_display(self, summary: dict[str, Any]) -> None:
        """品質 tier badge を更新する (ADR 0029)。

        ``quality_summary`` は ``lorairo.domain.quality_tier.compute_quality_summary``
        が返す形状の dict。空 dict / ``no_score`` / ``unknown`` / 通常 tier の各ケースを
        graceful に扱う。

        Args:
            summary: ``compute_quality_summary`` 戻り値の dict。空 dict (= フィールド
                自体が無い旧データ互換) のときは badge を hide する。
        """
        try:
            tier = summary.get("tier") if summary else None
            if not tier:
                self._quality_tier_label.setVisible(False)
                return

            known_count = summary.get("known_count", 0)
            is_unanimous = summary.get("is_unanimous", False)

            if known_count == 0:
                # tier は "no score" / "unknown" sentinel
                self._quality_tier_label.setText(f"品質: {tier}")
            else:
                suffix = " (全 scorer 一致)" if is_unanimous else ""
                self._quality_tier_label.setText(f"品質: {tier} ({known_count} scorer){suffix}")

            self._quality_tier_label.setVisible(True)

        except Exception as e:
            logger.error(f"Error updating quality tier display: {e}")

    def _update_ratings_display(self, ratings: list[dict[str, Any]]) -> None:
        """モデル別 rating record を table 表示する (Issue #334)。"""
        try:
            self.tableWidgetRatings.setRowCount(len(ratings))
            self.tableWidgetRatings.setSortingEnabled(False)

            if not ratings:
                self.labelRatingsPlaceholder.setVisible(True)
                self.tableWidgetRatings.setVisible(False)
                return

            self.labelRatingsPlaceholder.setVisible(False)
            self.tableWidgetRatings.setVisible(True)

            for row, entry in enumerate(ratings):
                confidence = entry.get("confidence_score")
                confidence_text = f"{confidence:.2f}" if confidence is not None else "-"
                values = [
                    entry.get("model") or entry.get("model_name") or "Unknown",
                    entry.get("normalized_rating") or "-",
                    entry.get("raw_rating_value") or "-",
                    confidence_text,
                    entry.get("source") or "AI",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 3:
                        item.setData(Qt.ItemDataRole.UserRole, confidence if confidence is not None else -1)
                    self.tableWidgetRatings.setItem(row, column, item)

            self.tableWidgetRatings.setSortingEnabled(True)
            self.tableWidgetRatings.resizeColumnsToContents()
            self._adjust_ratings_height()

            logger.debug(f"Updated ratings display: {len(ratings)} rows")

        except Exception as e:
            logger.error(f"Error updating ratings display: {e}")

    @Slot()
    def clear_data(self) -> None:
        """表示データをクリア"""
        try:
            # データリセット
            self.current_data = AnnotationData()

            # タグ欄クリア (TagPanelWidget へ委譲)
            self._tag_panel.clear()

            self.textEditCaption.clear()
            self.textEditCaption.setPlaceholderText("キャプションが表示されます")
            self._caption_compact_label.setText("キャプションが表示されます")

            self.labelScoreTypeValue.setText("-")
            self.labelOverallValue.setText("0")

            # スコアラベル pill もクリア
            self._update_score_labels_display([])
            self._update_ratings_display([])
            # 品質 tier badge もクリア (ADR 0029)
            self._update_quality_tier_display({})

            self._adjust_content_heights()

            self.data_cleared.emit()
            logger.debug("Annotation data display cleared")

        except Exception as e:
            logger.error(f"Error clearing annotation data: {e}", exc_info=True)

    def get_current_data(self) -> AnnotationData:
        """現在表示中のデータを取得"""
        return self.current_data

    def set_read_only(self, read_only: bool) -> None:
        """読み取り専用モード設定"""
        self.textEditCaption.setReadOnly(read_only)

    def set_group_box_visibility(
        self,
        tags: bool = True,
        caption: bool = True,
        scores: bool = True,
        score_labels: bool = True,
        ratings: bool = True,
    ) -> None:
        """各グループボックスの表示/非表示制御 (Issue #284 / #334)。"""
        self.groupBoxTags.setVisible(tags)
        self.groupBoxCaption.setVisible(caption)
        self.groupBoxScores.setVisible(scores)
        self.groupBoxScoreLabels.setVisible(score_labels)
        self.groupBoxRatings.setVisible(ratings)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_caption_height()

    def _adjust_content_heights(self) -> None:
        self._adjust_caption_height()
        self._adjust_ratings_height()

    def _adjust_ratings_height(self) -> None:
        if not self.tableWidgetRatings.isVisible():
            return
        self.tableWidgetRatings.resizeRowsToContents()
        header_height = self.tableWidgetRatings.horizontalHeader().height()
        rows_height = sum(
            self.tableWidgetRatings.rowHeight(row) for row in range(self.tableWidgetRatings.rowCount())
        )
        frame = self.tableWidgetRatings.frameWidth() * 2
        padding = 6
        target = header_height + rows_height + frame + padding
        min_height = header_height + frame + padding
        if target < min_height:
            target = min_height
        self.tableWidgetRatings.setFixedHeight(target)

    def _adjust_caption_height(self) -> None:
        if not self.textEditCaption.isVisible():
            text = self._caption_compact_label.text()
            if not text:
                text = "キャプションが表示されます"
            width = self._caption_compact_label.width()
            if width <= 0:
                return
            rect = self._caption_compact_label.fontMetrics().boundingRect(
                0, 0, width, 10000, Qt.TextFlag.TextWordWrap, text
            )
            padding = 10
            min_height = int(self._caption_compact_label.fontMetrics().lineSpacing() * 2 + padding)
            target = int(rect.height() + padding + 0.5)
            if target < min_height:
                target = min_height
            self._caption_compact_label.setFixedHeight(target)
            return

        document = self.textEditCaption.document()
        document.setTextWidth(self.textEditCaption.viewport().width())
        doc_height = document.size().height()
        frame = self.textEditCaption.frameWidth() * 2
        padding = 10
        min_height = int(self.textEditCaption.fontMetrics().lineSpacing() * 3 + frame + padding)
        target = int(doc_height + frame + padding + 0.5)
        if target < min_height:
            target = min_height
        self.textEditCaption.setFixedHeight(target)


if __name__ == "__main__":
    # Tier2: ダミーデータ投入とシグナル受信ログの最小確認
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    # ログはコンソール優先
    initialize_logging({"level": "DEBUG", "file": None})
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("AnnotationDataDisplayWidget テスト (Tier2)")
    widget = AnnotationDataDisplayWidget()
    window.setCentralWidget(widget)
    window.resize(480, 360)

    # シグナル受信確認（デバッグログ）
    def _on_data_loaded(data: AnnotationData) -> None:
        from lorairo.utils.log import logger

        logger.debug(
            f"[Signal] data_loaded: tags={len(data.tags)}, caption={bool(data.caption)}, aesth={data.aesthetic_score}"
        )

    def _on_data_cleared() -> None:
        from lorairo.utils.log import logger

        logger.debug("[Signal] data_cleared")

    widget.data_loaded.connect(_on_data_loaded)
    widget.data_cleared.connect(_on_data_cleared)

    # ダミーデータを流し込み
    dummy = AnnotationData(
        tags=[
            {
                "tag": "1girl",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.95,
                "is_edited_manually": False,
            },
            {
                "tag": "flower",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.88,
                "is_edited_manually": False,
            },
            {
                "tag": "solo",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.92,
                "is_edited_manually": False,
            },
        ],
        caption="A girl holding flowers in a sunny field.",
        aesthetic_score=0.732,
        overall_score=780,
        score_type="Aesthetic",
    )
    widget.update_data(dummy)

    # 一度クリアして data_cleared 発火確認
    widget.clear_data()

    window.show()
    sys.exit(app.exec())
