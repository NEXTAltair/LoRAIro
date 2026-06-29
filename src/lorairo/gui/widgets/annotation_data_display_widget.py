"""
Annotation Data Display Widget

汎用アノテーション結果表示コンポーネント
タグ・キャプション・スコア情報の統一表示を提供
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QContextMenuEvent, QKeySequence, QMouseEvent, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.AnnotationDataDisplayWidget_ui import Ui_AnnotationDataDisplayWidget
from ...utils.log import logger
from .. import theme

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation


class SelectableTagChip(QLabel):
    """選択トグルできるタグ chip (Issue #814)。

    1 タグ 1 chip 表示のうえで、chip クリックで選択状態をトグルし、
    選択中の chip だけ (無選択なら全 chip) をカンマ区切りでコピーできる。

    ``QLabel.mousePressEvent`` への代入は mypy method-assign 違反になるため、
    サブクラスで override して ``clicked`` Signal を emit する。コピー対象は
    表示テキスト (翻訳後) ではなく ``canonical`` (danbooru canonical / 原文) を
    使う。タグは保存値が SSoT であり、言語切替に依らず一貫したコピー結果にする。
    """

    clicked = Signal()
    # refinement リコメンドの「この理由を無視」要求 (#931): (canonical, reason_code)
    refinement_ignore_requested = Signal(str, str)

    def __init__(self, display_text: str, canonical: str, parent: QWidget | None = None) -> None:
        super().__init__(display_text, parent)
        self.canonical = canonical
        self.base_qss = ""
        self.selected = False
        # refinement 表示状態 (#931)。set_refinement で更新する。
        self._base_text = display_text
        self._base_tooltip: str | None = None
        self.refinement: RefinementRecommendation | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Ctrl+C を chip フォーカス中に拾えるようクリックフォーカスを許可する。
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左クリックで選択トグル用の clicked を emit する。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_refinement(self, recommendation: RefinementRecommendation | None) -> None:
        """refinement リコメンドを反映する (#931)。

        needs_refinement かつ reason があれば ⚠ マーカーを表示テキストに前置し
        (高さは1行で不変)、ツールチップに reason message と suggestion を出す。
        リコメンドが無ければ元の表示・ツールチップへ戻す。

        Args:
            recommendation: 当該タグのリコメンド。無ければ None。
        """
        # 初回呼び出し時に元ツールチップ (翻訳脚注等) を退避する。
        if self._base_tooltip is None:
            self._base_tooltip = self.toolTip()
        self.refinement = recommendation
        if recommendation is not None and recommendation.needs_refinement and recommendation.reasons:
            self.setText(f"⚠ {self._base_text}")
            lines = [r.message for r in recommendation.reasons]
            suggestions = [s.tag for s in recommendation.suggestions if s.tag]
            if suggestions:
                lines.append("提案: " + ", ".join(suggestions))
            self.setToolTip("\n".join(lines))
        else:
            self.setText(self._base_text)
            self.setToolTip(self._base_tooltip)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """refinement がある chip は reason 単位の「無視」メニューを出す (#931)。

        リコメンドが無い chip は event を無視してコンテナ側のコピーメニューへ委ねる。
        """
        rec = self.refinement
        if rec is not None and rec.needs_refinement and rec.reasons:
            menu = QMenu(self)
            for reason in rec.reasons:
                action = menu.addAction(f"この理由を無視: {reason.code}")
                action.triggered.connect(
                    lambda _checked=False, code=reason.code: self.refinement_ignore_requested.emit(
                        self.canonical, code
                    )
                )
            menu.exec(event.globalPos())
            event.accept()
        else:
            event.ignore()


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
    - タグ・キャプション・スコア情報の統一表示
    - 読み取り専用表示
    - データクリア・更新機能
    """

    # シグナル
    data_loaded = Signal(AnnotationData)  # データロード完了
    data_cleared = Signal()  # データクリア完了
    # TagEdit soft-reject 導線 (Issue #792)。引数は canonical タグ文字列。
    tag_reject_requested = Signal(str)  # × でタグを soft-reject
    tag_restore_requested = Signal(str)  # soft-rejected タグを復活
    tag_add_requested = Signal(str)  # 手動タグ追加
    refinement_ignored = Signal(str, str)  # refinement リコメンドを無視 (canonical, reason_code) (#931)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)

        # 現在のデータ
        self.current_data: AnnotationData = AnnotationData()
        # TagEdit soft-reject 編集モード (Issue #792、既定は read-only)。
        self._tag_edit_enabled: bool = False
        self._rejected_tags: list[str] = []

        # UI初期化
        self._setup_widget_properties()
        self._setup_tags_compact_view()
        self._setup_caption_compact_view()
        self._setup_score_labels_compact_view()
        self._setup_quality_tier_badge()
        self._setup_ratings_table_view()
        self._adjust_content_heights()

        # 言語コンボボックスのシグナル接続
        self._lang_combo.currentTextChanged.connect(self._on_language_changed)

        logger.debug("AnnotationDataDisplayWidget initialized")

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # tableWidgetTagsは既にNoEditTriggersに設定済み（UIファイルで設定）
        # テキスト編集を読み取り専用に設定
        self.textEditCaption.setReadOnly(True)
        self.tableWidgetTags.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.tableWidgetTags.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tableWidgetTags.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableWidgetTags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tableWidgetTags.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableWidgetTags.customContextMenuRequested.connect(self._show_tags_table_context_menu)
        self.textEditCaption.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._make_label_copyable(self.labelScoreTypeValue)
        self._make_label_copyable(self.labelOverallValue)

    def _setup_tags_compact_view(self) -> None:
        # 折り返しチップ配置レイアウト (DS wireframe v12 TagChip)。
        # tag_cloud_service への module-load 連鎖を避けるため遅延 import する。
        from .tag_cloud_widget import FlowLayout

        # 言語切り替えバー（コンボボックス付き）を先頭に動的追加
        self._lang_bar = QWidget(self.groupBoxTags)
        lang_layout = QHBoxLayout(self._lang_bar)
        lang_layout.setContentsMargins(0, 0, 0, 2)
        lang_label = QLabel("言語:", self._lang_bar)
        lang_layout.addWidget(lang_label)
        self._lang_combo = QComboBox(self._lang_bar)
        self._lang_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lang_layout.addWidget(self._lang_combo)
        self._lang_bar.setVisible(False)  # merged_readerがない場合は非表示
        self.verticalLayoutTags.insertWidget(0, self._lang_bar)

        # チップ表示コンテナ (DS chip 文法・borders-not-shadows)
        self._tags_chip_container = QWidget(self.groupBoxTags)
        self._tags_chip_layout = FlowLayout(self._tags_chip_container, spacing=4)
        self._tags_chip_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # 高さ上限付きスクロール箱に収める (#835)。FlowLayout の minimumSizeHint は
        # 「最小幅で全チップ縦積み」の過大値を報告し、放置すると親の高さを膨張させて
        # スコアカード下に異常な余白 + 不要スクロールを生む。タグ数に依らず本箱で
        # 高さを上限まで (_TAGS_MAX_HEIGHT) に固定し、超過分は箱内スクロールにする。
        self._tags_scroll = QScrollArea(self.groupBoxTags)
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setWidget(self._tags_chip_container)
        self.verticalLayoutTags.insertWidget(1, self._tags_scroll)

        # 選択コピー導線 (Issue #814): chip クリックで選択、Ctrl+C / 右クリックで
        # 選択タグ (無選択なら全タグ) をカンマ区切りコピーする。
        self._tag_chips: list[SelectableTagChip] = []
        # refinement リコメンド保持 (#931): chip 再生成をまたいで ⚠ を復元する。
        self._last_refinements: dict[str, RefinementRecommendation] = {}
        self._tags_chip_container.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._tags_chip_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tags_chip_container.customContextMenuRequested.connect(self._show_tags_chip_context_menu)
        self._tags_chip_copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._tags_chip_container)
        self._tags_chip_copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._tags_chip_copy_shortcut.activated.connect(self.copy_selected_tags_to_clipboard)

        # 翻訳脚注 (非英語選択時のみ表示)
        self._tags_translation_note = QLabel(self.groupBoxTags)
        self._tags_translation_note.setWordWrap(True)
        self._tags_translation_note.setStyleSheet(
            f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL - 1}px;"
        )
        self._tags_translation_note.setVisible(False)
        self.verticalLayoutTags.insertWidget(2, self._tags_translation_note)

        # soft-rejected セクション (Issue #792、編集モードのみ表示)。
        # 取り消し線チップをクリックで復活する。
        self._rejected_note = QLabel(self.groupBoxTags)
        self._rejected_note.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_META}px;")
        self._rejected_note.setVisible(False)
        self.verticalLayoutTags.insertWidget(3, self._rejected_note)

        self._rejected_container = QWidget(self.groupBoxTags)
        self._rejected_layout = FlowLayout(self._rejected_container, spacing=4)
        self._rejected_container.setVisible(False)
        self.verticalLayoutTags.insertWidget(4, self._rejected_container)

        # 手動タグ追加入力 (Issue #792、編集モードのみ表示)。
        from PySide6.QtWidgets import QLineEdit

        self._tag_add_input = QLineEdit(self.groupBoxTags)
        self._tag_add_input.setObjectName("tagAddInput")
        self._tag_add_input.setPlaceholderText("手動タグを追加 (Enter で確定)…")
        self._tag_add_input.returnPressed.connect(self._on_tag_add_submitted)
        self._tag_add_input.setVisible(False)
        self.verticalLayoutTags.insertWidget(5, self._tag_add_input)

        # コピー / アクセシビリティ用のテキストバッキング (非表示)。
        # displayed_tags_text() と詳細コピーが参照する SSoT 文字列を保持する。
        self._tags_compact_label = QLabel(self.groupBoxTags)
        self._tags_compact_label.setWordWrap(True)
        self._tags_compact_label.setText("-")
        self._tags_compact_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._make_label_copyable(self._tags_compact_label)
        self._tags_compact_label.setVisible(False)
        self.verticalLayoutTags.insertWidget(3, self._tags_compact_label)

        self.tableWidgetTags.setVisible(False)

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

    def displayed_tags_text(self) -> str:
        """現在の言語選択で表示されているタグ文字列を返す。"""
        return self._tags_compact_label.text()

    def _on_tag_chip_clicked(self, chip: SelectableTagChip) -> None:
        """タグ chip クリックで選択状態をトグルし視覚強調を更新する (Issue #814)。"""
        chip.selected = not chip.selected
        self._apply_chip_selection_style(chip)

    def _apply_chip_selection_style(self, chip: SelectableTagChip) -> None:
        """chip の選択状態に応じて QSS を切り替える。

        非選択時は描画時の ``base_qss`` (DS chip 文法) に戻し、選択時は accent
        トークンで強調する。ハードコード hex/px は使わず theme トークンのみ参照する。
        """
        chip.setStyleSheet(self._selected_chip_qss() if chip.selected else chip.base_qss)

    @staticmethod
    def _selected_chip_qss() -> str:
        """選択中タグ chip 用の強調 QSS を theme トークンで生成する (Issue #814)。"""
        return (
            f"QLabel {{ background-color: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border: {theme.BORDER_WIDTH_ACCENT}px solid {theme.ACCENT};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 9px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: 600; }}"
        )

    @Slot()
    def copy_selected_tags_to_clipboard(self) -> bool:
        """選択中タグ (無選択なら全タグ) をカンマ区切りでクリップボードへコピーする。

        コピー値は表示テキスト (翻訳後) ではなく canonical 原文を使う。タグは
        保存値が SSoT であり、言語切替に依らず一貫したコピー結果にするため (Issue #814)。

        Returns:
            コピー対象が 1 件以上あれば True、タグが無ければ False。
        """
        selected = [chip.canonical for chip in self._tag_chips if chip.selected]
        targets = selected if selected else [chip.canonical for chip in self._tag_chips]
        targets = [tag for tag in targets if tag]
        if not targets:
            return False
        QApplication.clipboard().setText(", ".join(targets))
        return True

    @Slot(QPoint)
    def _show_tags_chip_context_menu(self, position: QPoint) -> None:
        """タグ chip コンテナの右クリックメニュー (選択タグのカンマ区切りコピー)。"""
        menu = QMenu(self._tags_chip_container)
        copy_action = menu.addAction("選択タグをコピー")
        copy_action.setEnabled(bool(self._tag_chips))
        copy_action.triggered.connect(self.copy_selected_tags_to_clipboard)
        menu.exec(self._tags_chip_container.mapToGlobal(position))

    @Slot(QPoint)
    def _show_tags_table_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self.tableWidgetTags)
        copy_action = menu.addAction("選択範囲をコピー")
        copy_action.setEnabled(bool(self.tableWidgetTags.selectedRanges()))
        copy_action.triggered.connect(self.copy_selected_tag_cells_to_clipboard)
        menu.exec(self.tableWidgetTags.viewport().mapToGlobal(position))

    @Slot(QPoint)
    def _show_ratings_table_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self.tableWidgetRatings)
        copy_action = menu.addAction("選択範囲をコピー")
        copy_action.setEnabled(bool(self.tableWidgetRatings.selectedRanges()))
        copy_action.triggered.connect(self.copy_selected_rating_cells_to_clipboard)
        menu.exec(self.tableWidgetRatings.viewport().mapToGlobal(position))

    @Slot()
    def copy_selected_tag_cells_to_clipboard(self) -> bool:
        """タグテーブルの選択セルを TSV としてクリップボードへコピーする。"""
        return self._copy_selected_table_cells_to_clipboard(
            self.tableWidgetTags, self._tag_table_item_clipboard_text
        )

    @Slot()
    def copy_selected_rating_cells_to_clipboard(self) -> bool:
        """rating 詳細テーブルの選択セルを TSV としてクリップボードへコピーする。"""
        return self._copy_selected_table_cells_to_clipboard(self.tableWidgetRatings)

    def _copy_selected_table_cells_to_clipboard(
        self,
        table: QTableWidget,
        formatter: Any | None = None,
    ) -> bool:
        ranges = table.selectedRanges()
        if not ranges:
            return False

        lines: list[str] = []
        for selected_range in ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                values: list[str] = []
                for column in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                    item = table.item(row, column)
                    values.append(formatter(item, column) if formatter else (item.text() if item else ""))
                lines.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(lines))
        return True

    @staticmethod
    def _tag_table_item_clipboard_text(item: QTableWidgetItem | None, column: int) -> str:
        """タグテーブルセルのコピー用文字列を返す。"""
        if item is None:
            return ""
        if column == 4:
            return "true" if item.checkState() == Qt.CheckState.Checked else "false"
        return item.text()

    def update_data(self, data: AnnotationData) -> None:
        """アノテーションデータで表示を更新"""
        try:
            self.current_data = data

            # 新しい画像データのため前画像の refinement 結果は破棄する (#931)。
            # 同一画像内の再描画 (言語切替等) は update_data を経由しないので保持される。
            self._last_refinements = {}

            # タグ表示更新
            self._update_tags_display(data.tags)

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

    def _update_tags_display(self, tags: list[dict[str, Any]]) -> None:
        """タグ表示をテーブルで更新

        Args:
            tags: タグ詳細情報リスト（Repository層から提供）
                  [{"tag": "1girl", "model_name": "wd-v1-4", "source": "AI",
                    "confidence_score": 0.95, "is_edited_manually": False}, ...]
        """
        try:
            self.tableWidgetTags.setRowCount(len(tags))
            self.tableWidgetTags.setSortingEnabled(False)  # 更新中はソート無効

            for row, tag_dict in enumerate(tags):
                # Tag列
                tag_item = QTableWidgetItem(tag_dict["tag"])
                self.tableWidgetTags.setItem(row, 0, tag_item)

                # Model列
                model_name = tag_dict.get("model_name", "-")
                model_item = QTableWidgetItem(model_name)
                self.tableWidgetTags.setItem(row, 1, model_item)

                # Source列
                source = tag_dict.get("source", "AI")
                source_item = QTableWidgetItem(source)
                self.tableWidgetTags.setItem(row, 2, source_item)

                # Confidence列
                confidence = tag_dict.get("confidence_score")
                if confidence is not None:
                    confidence_text = f"{confidence:.2f}"
                else:
                    confidence_text = "-"
                confidence_item = QTableWidgetItem(confidence_text)
                # 数値ソート用のデータ設定
                confidence_item.setData(Qt.ItemDataRole.UserRole, confidence if confidence else -1)
                self.tableWidgetTags.setItem(row, 3, confidence_item)

                # Edited列（チェックボックス）
                edited = tag_dict.get("is_edited_manually", False)
                checkbox_item = QTableWidgetItem()
                checkbox_item.setCheckState(Qt.CheckState.Checked if edited else Qt.CheckState.Unchecked)
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # 読み取り専用
                self.tableWidgetTags.setItem(row, 4, checkbox_item)

            self.tableWidgetTags.setSortingEnabled(True)  # ソート有効化
            self.tableWidgetTags.resizeColumnsToContents()

            # チップ表示・コンパクトラベルを現在の表示言語で描画する。
            # isHidden()で判定（isVisible()は親ウィジェット未表示時にFalseを返すため）
            current_lang = self._lang_combo.currentText() if not self._lang_bar.isHidden() else "english"
            self._refresh_tags_for_language(current_lang)

            logger.debug(f"Updated tags display: {len(tags)} rows")

        except Exception as e:
            logger.error(f"Error updating tags display: {e}")

    def initialize_language_selector(self, available_languages: list[str]) -> None:
        """言語コンボボックスを初期化する。

        Args:
            available_languages: 利用可能な言語リスト。空の場合はコンボボックスを非表示にする。
        """
        if not available_languages:
            self._lang_bar.setVisible(False)
            return

        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem("english")  # 常に先頭（原文）
        for lang in available_languages:
            if lang != "english":
                self._lang_combo.addItem(lang)
        self._lang_combo.blockSignals(False)
        self._lang_bar.setVisible(True)

    @Slot(str)
    def _on_language_changed(self, language: str) -> None:
        """言語コンボボックス変更時にタグ表示を更新する。"""
        self._refresh_tags_for_language(language)

    def _refresh_tags_for_language(self, language: str) -> None:
        """現在のタグデータを指定言語で再描画する。

        Args:
            language: 表示言語名。"english" または available_languages の要素。
                      翻訳がないタグは英語原文でフォールバック。
        """
        tags = self.current_data.tags
        translations = self.current_data.tag_translations
        use_english = language == "english" or not language

        tag_names: list[str] = []
        # チップ描画用メタ: (表示名, 原文, 翻訳ありか)
        chip_items: list[tuple[str, str, bool]] = []
        for row, tag_dict in enumerate(tags):
            tag_id = tag_dict.get("tag_id")
            original = tag_dict.get("tag", "")
            if use_english or tag_id is None:
                display = original
                has_translation = True  # 英語表示では翻訳欠落マークを付けない
            else:
                translated = translations.get(tag_id, {}).get(language)
                # 翻訳がなければ英語原文にフォールバック
                display = translated if translated else original
                has_translation = translated is not None
            tag_names.append(display)
            chip_items.append((display, original, has_translation))

            # テーブルのTag列（列0）も更新
            item = self.tableWidgetTags.item(row, 0)
            if item is not None:
                item.setText(display)

        self._tags_compact_label.setText(", ".join(n for n in tag_names if n) or "-")
        self._render_tag_chips(chip_items, is_translated=not use_english)

    def _render_tag_chips(self, chip_items: list[tuple[str, str, bool]], *, is_translated: bool) -> None:
        """タグチップを DS chip 文法で再描画する (borders-not-shadows)。

        Args:
            chip_items: (表示名, 原文, 翻訳ありか) のタプルリスト。
            is_translated: 非英語言語で表示中なら True。脚注表示と翻訳欠落の
                点線マーク (theme.tag_chip_untranslated_qss) の有効/無効を切り替える。
        """
        # 既存チップをクリア
        while self._tags_chip_layout.count():
            child = self._tags_chip_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        # 再描画で選択状態はリセットする (chip オブジェクトが入れ替わるため)。
        self._tag_chips = []

        visible_items = [(display, original, has_tr) for display, original, has_tr in chip_items if display]
        if not visible_items:
            placeholder = QLabel("-")
            placeholder.setStyleSheet(f"color: {theme.INK_FAINT};")
            self._tags_chip_layout.addWidget(placeholder)
            self._tags_translation_note.setVisible(False)
            return

        for display, original, has_tr in visible_items:
            chip = SelectableTagChip(display, original)
            if is_translated and not has_tr:
                chip.base_qss = theme.tag_chip_untranslated_qss()
                chip.setToolTip(f"{original} — 翻訳なし")
            else:
                chip.base_qss = theme.chip_qss("accent")
                if is_translated and display != original:
                    chip.setToolTip(f"{original} → {display}")
            chip.setStyleSheet(chip.base_qss)
            chip.clicked.connect(lambda c=chip: self._on_tag_chip_clicked(c))
            # refinement「この理由を無視」を上位へ中継 (#931)
            chip.refinement_ignore_requested.connect(self.refinement_ignored)
            self._tag_chips.append(chip)
            # 編集モードでは × ボタン付きコンテナで soft-reject 可能にする (Issue #792)。
            self._tags_chip_layout.addWidget(self._wrap_editable_chip(chip, original))

        if is_translated:
            self._tags_translation_note.setText(
                "表示のみ翻訳 · 保存値は danbooru canonical 固定 · 点線 = 翻訳なし"
            )
            self._tags_translation_note.setVisible(True)
        else:
            self._tags_translation_note.setVisible(False)

        # chip 再生成後、保持中の refinement 結果を再反映する (#931、言語切替/編集モードでも ⚠ 維持)。
        self._apply_refinements_to_chips()

    def apply_refinements(self, recommendations: dict[str, RefinementRecommendation]) -> None:
        """各タグ chip に refinement リコメンドを反映する (#931)。

        chip の canonical をキーにマップを引き、該当があれば ⚠ + ツールチップを表示、
        無ければリコメンド表示を消す。検索/エクスポート両タブの詳細ペインで共用される。

        言語切替や編集モード切替で chip が再生成されても ⚠ を失わないよう、最後に適用した
        結果を保持し、_render_tag_chips の末尾で自動的に再反映する。

        Args:
            recommendations: {canonical タグ: RefinementRecommendation}。
        """
        self._last_refinements = dict(recommendations)
        self._apply_refinements_to_chips()

    def _apply_refinements_to_chips(self) -> None:
        """保持中のリコメンド (_last_refinements) を現在の chip 群へ反映する (#931)。"""
        applied = 0
        for chip in self._tag_chips:
            rec = self._last_refinements.get(chip.canonical)
            chip.set_refinement(rec)
            if rec is not None:
                applied += 1
        logger.debug(f"refinement 反映: chip={len(self._tag_chips)}, 印付き={applied}")

    def _wrap_editable_chip(self, chip: QLabel, original: str) -> QWidget:
        """編集モード時にチップを × ボタン付きコンテナで包む (Issue #792)。

        read-only モードでは chip をそのまま返す。

        Args:
            chip: タグチップ QLabel。
            original: canonical タグ文字列 (soft-reject 対象)。

        Returns:
            編集モードなら × 付きコンテナ、そうでなければ chip。
        """
        if not self._tag_edit_enabled:
            return chip
        from PySide6.QtWidgets import QToolButton

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(chip)
        remove = QToolButton(container)
        remove.setObjectName("tagRejectButton")
        remove.setText("×")
        remove.setAutoRaise(True)
        remove.setToolTip(f"{original} を soft-reject (rejected_at に記録、行は残す)")
        remove.clicked.connect(lambda _checked=False, tag=original: self.tag_reject_requested.emit(tag))
        layout.addWidget(remove)
        return container

    def set_tag_edit_enabled(self, enabled: bool) -> None:
        """タグ soft-reject 編集モードを切り替える (Issue #792)。

        Args:
            enabled: True で × / 手動追加 / 復活セクションを表示する。
        """
        self._tag_edit_enabled = enabled
        self._tag_add_input.setVisible(enabled)
        self._refresh_tags_for_language(self._lang_combo.currentText() or "English")
        self._render_rejected_tags()

    def set_rejected_tags(self, rejected_tags: list[str]) -> None:
        """soft-rejected タグ一覧を設定し復活セクションを再描画する (Issue #792)。

        Args:
            rejected_tags: soft-reject 済み canonical タグ文字列のリスト。
        """
        self._rejected_tags = list(rejected_tags)
        self._render_rejected_tags()

    def _render_rejected_tags(self) -> None:
        """soft-rejected セクションを再描画する (クリックで復活)。"""
        while self._rejected_layout.count():
            child = self._rejected_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        show = self._tag_edit_enabled and bool(self._rejected_tags)
        self._rejected_note.setVisible(show)
        self._rejected_container.setVisible(show)
        if not show:
            return

        from PySide6.QtWidgets import QPushButton

        self._rejected_note.setText(f"soft-rejected · {len(self._rejected_tags)}（クリックで復活）")
        for tag in self._rejected_tags:
            # クリックで復活する flat ボタン (取り消し線 chip 風)。
            # QLabel.mousePressEvent への代入は mypy method-assign 違反になるため
            # QPushButton.clicked を使う。
            chip = QPushButton(tag)
            chip.setObjectName("rejectedTagChip")
            chip.setFlat(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(theme.tag_chip_untranslated_qss().replace("QLabel", "QPushButton"))
            chip.setToolTip(f"{tag} を復活 (rejected_at を解除)")
            chip.clicked.connect(lambda _checked=False, t=tag: self.tag_restore_requested.emit(t))
            self._rejected_layout.addWidget(chip)

    def _on_tag_add_submitted(self) -> None:
        """手動タグ追加入力の Enter ハンドラ (Issue #792)。"""
        text = self._tag_add_input.text().strip()
        if not text:
            return
        self._tag_add_input.clear()
        self.tag_add_requested.emit(text)

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
            # refinement リコメンド保持もクリア (#931)
            self._last_refinements = {}

            # UI要素クリア
            self.tableWidgetTags.setRowCount(0)

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

            self._tags_compact_label.setText("-")
            self._render_tag_chips([], is_translated=False)
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
        # tableWidgetTagsは既にNoEditTriggersに設定済み
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

    # タグチップ箱の高さ上限 (#835)。これを超えるタグは箱内スクロールにし、
    # annotationDataDisplay 全体の高さがタグ数で膨張しないようにする。
    _TAGS_MAX_HEIGHT = 220

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_caption_height()
        # 幅変化でタグチップの折り返し行数が変わるため箱の高さを追従させる (#835)
        self._adjust_tags_chip_height()

    def _adjust_content_heights(self) -> None:
        self._adjust_tags_height()
        self._adjust_tags_chip_height()
        self._adjust_caption_height()
        self._adjust_ratings_height()

    def _adjust_tags_chip_height(self) -> None:
        """タグチップ箱の高さを min(実幅での必要高さ, 上限) に収める (#835)。

        FlowLayout の minimumSizeHint (最小幅での全チップ縦積み) が親へ伝播して
        スクロール領域を膨張させるのを防ぐため、箱の高さを実寸ベースで明示する。
        タグが少なければ内容ぴったり、多ければ上限で頭打ち + 箱内スクロールになる。
        """
        if not self._tags_scroll.isVisible():
            return
        width = self._tags_scroll.viewport().width()
        if width <= 0:
            return
        # 収まるときに内側スクロールバーが出ないよう僅かな余裕を足す。
        needed = self._tags_chip_layout.heightForWidth(width) + 8
        self._tags_scroll.setFixedHeight(min(needed, self._TAGS_MAX_HEIGHT))

    def _adjust_tags_height(self) -> None:
        if not self.tableWidgetTags.isVisible():
            return
        self.tableWidgetTags.resizeRowsToContents()
        header_height = self.tableWidgetTags.horizontalHeader().height()
        rows_height = sum(
            self.tableWidgetTags.rowHeight(row) for row in range(self.tableWidgetTags.rowCount())
        )
        frame = self.tableWidgetTags.frameWidth() * 2
        padding = 6
        target = header_height + rows_height + frame + padding
        min_height = header_height + frame + padding
        if target < min_height:
            target = min_height
        self.tableWidgetTags.setFixedHeight(target)

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
