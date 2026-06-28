"""ステージング集合内タグの集計表示・絞り込み・行内アクションウィジェット（Issue #947）。

Epic #942 の左ペイン StagingTagPanel。
StagingTagAggregationService を消費してタグ×件数を一覧表示し、
絞り込み・ソート・行内アクションを提供する。
配線は後続 #949 が行うため、本ウィジェットはシグナル emit まで担当する。

依存: StagingTagAggregationService（Issue #945、ADR 0080 S0）
"""

from __future__ import annotations

from loguru import logger
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.staging_tag_aggregation import StagingTagAggregationService, TagCount

# ------------------------------------------------------------------
# ソートモード定数
# ------------------------------------------------------------------
_SORT_COUNT = 0
_SORT_NAME = 1
_SORT_MANUAL_ONLY = 2

_SORT_LABELS: list[str] = ["件数順", "名前順", "手動のみ"]


class StagingTagPanel(QWidget):
    """ステージング集合内タグの集計表示・絞り込み・行内アクションウィジェット。

    StagingTagAggregationService が返す TagCount リストをもとに、
    タグ×件数バー・ソート切替・インクリメンタル検索・行内アクションを提供する。
    ロジックは service に委譲し、ウィジェット自体は薄く保つ。

    2層色分け (ADR 0080):
        - 橙 (ACCENT 系) : 出力一時オーバーレイ操作 (overlay_*)
        - 青 (INFO 系) : DB 永続操作 (db_reject_everywhere_requested)

    Signals:
        filter_tag_changed: タグ行クリックで str を、リセットで None を emit。
        overlay_exclude_requested: ⊘ 出力除外ボタンクリックでタグ文字列を emit（橙）。
        overlay_replace_requested: ⇄ 置換確定でタグペア (from_tag, to_tag) を emit（橙）。
        db_reject_everywhere_requested: ✎ reject(DB) ボタンクリックでタグ文字列を emit（青）。
    """

    # 公開シグナル契約（#949 が配線）
    filter_tag_changed = Signal(object)  # str | None
    overlay_exclude_requested = Signal(str)
    overlay_replace_requested = Signal(str, str)
    db_reject_everywhere_requested = Signal(str)

    def __init__(
        self,
        service: StagingTagAggregationService,
        parent: QWidget | None = None,
    ) -> None:
        """StagingTagPanel を初期化する。

        Args:
            service: タグ集計サービス。画像 ID リストからタグ件数を集計する。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service = service

        # ステージング集合（load_tags で更新）
        self._image_ids: list[int] = []
        # 集計結果の全件（フィルタ前）
        self._all_tags: list[TagCount] = []
        # 現在表示中のタグ（フィルタ・ソート後）
        self._displayed_tags: list[TagCount] = []
        # 現在アクティブな絞り込みタグ
        self._active_filter_tag: str | None = None

        self._setup_ui()
        self._connect_signals()
        self._update_action_bar_visibility()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """UI コンポーネントを構築する。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ヘッダ: パネル名 + リセットボタン
        header = QHBoxLayout()
        header.setSpacing(6)
        title_label = QLabel("タグ集計")
        title_label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_H2}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
            f" color: {theme.INK};"
        )
        header.addWidget(title_label, 1)

        self._reset_btn = QPushButton("全 N 枚に戻す")
        self._reset_btn.setObjectName("resetFilterBtn")
        self._reset_btn.setToolTip("タグ絞り込みを解除して全ステージング画像を表示する")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.PAPER_SHADE}; color: {theme.INK_SOFT};"
            f" border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 3px 10px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background: {theme.LINE}; color: {theme.INK}; }}"
        )
        header.addWidget(self._reset_btn)
        root.addLayout(header)

        # 検索 + ソート行
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("tagSearchEdit")
        self._search_edit.setPlaceholderText("タグ名で絞り込み…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 4px 6px; background: {theme.CARD}; color: {theme.INK};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QLineEdit:focus {{ border-color: {theme.ACCENT}; }}"
        )
        ctrl_row.addWidget(self._search_edit, 1)

        self._sort_combo = QComboBox()
        self._sort_combo.setObjectName("sortCombo")
        for label in _SORT_LABELS:
            self._sort_combo.addItem(label)
        self._sort_combo.setCurrentIndex(_SORT_COUNT)
        self._sort_combo.setToolTip("ソート順を切り替える")
        self._sort_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 3px 6px; background: {theme.CARD}; color: {theme.INK};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
        )
        ctrl_row.addWidget(self._sort_combo)
        root.addLayout(ctrl_row)

        # サマリラベル
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("summaryLabel")
        self._summary_label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_META}px;")
        root.addWidget(self._summary_label)

        # タグリスト
        self._list_widget = QListWidget()
        self._list_widget.setObjectName("tagListWidget")
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list_widget.setStyleSheet(
            f"QListWidget {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" background: {theme.CARD}; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {theme.LINE}; }}"
            f" QListWidget::item:selected {{ background: {theme.ACCENT_SOFT};"
            f" color: {theme.ACCENT_HOVER}; }}"
            f" QListWidget::item:hover {{ background: {theme.PAPER_SHADE}; }}"
        )
        root.addWidget(self._list_widget, 1)

        # 行内アクションバー（選択行あり時のみ表示）
        self._action_bar = QWidget()
        self._action_bar.setObjectName("actionBar")
        action_layout = QVBoxLayout(self._action_bar)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.setSpacing(4)

        # アクション対象タグ表示
        self._action_tag_label = QLabel("")
        self._action_tag_label.setObjectName("actionTagLabel")
        self._action_tag_label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_MEDIUM};"
            f" color: {theme.INK};"
        )
        action_layout.addWidget(self._action_tag_label)

        # ボタン行（⊘ 出力除外 / ✎ reject(DB)）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        # ⊘ 出力除外（橙 = 出力一時オーバーレイ）
        self._exclude_btn = QPushButton("⊘ 出力除外")
        self._exclude_btn.setObjectName("excludeBtn")
        self._exclude_btn.setToolTip("選択タグをこのエクスポートから除外する（一時オーバーレイ）")
        self._exclude_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exclude_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: 1px solid {theme.ACCENT_BORDER}; border-radius: {theme.RADIUS}px;"
            f" padding: 4px 8px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT}; }}"
        )
        btn_row.addWidget(self._exclude_btn)

        # ✎ reject(DB)（青 = DB 永続）
        self._db_reject_btn = QPushButton("✎ reject(DB)")
        self._db_reject_btn.setObjectName("dbRejectBtn")
        self._db_reject_btn.setToolTip("選択タグを全画像で DB 永続 reject する（取り消し不可）")
        self._db_reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._db_reject_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.INFO_SOFT}; color: {theme.INFO};"
            f" border: 1px solid {theme.INFO_BORDER}; border-radius: {theme.RADIUS}px;"
            f" padding: 4px 8px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background: {theme.INFO}; color: {theme.TEXT_ON_ACCENT}; }}"
        )
        btn_row.addWidget(self._db_reject_btn)
        btn_row.addStretch(1)
        action_layout.addLayout(btn_row)

        # ⇄ 置換行（from→to 入力）
        replace_row = QHBoxLayout()
        replace_row.setSpacing(4)
        replace_label = QLabel("⇄ 置換:")
        replace_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        replace_row.addWidget(replace_label)

        self._replace_to_edit = QLineEdit()
        self._replace_to_edit.setObjectName("replaceToEdit")
        self._replace_to_edit.setPlaceholderText("新しいタグ名を入力…")
        self._replace_to_edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 3px 6px; background: {theme.CARD}; color: {theme.INK};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QLineEdit:focus {{ border-color: {theme.ACCENT}; }}"
        )
        replace_row.addWidget(self._replace_to_edit, 1)

        self._replace_btn = QPushButton("置換")
        self._replace_btn.setObjectName("replaceBtn")
        self._replace_btn.setToolTip("選択タグを入力したタグに置換する（一時オーバーレイ）")
        self._replace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replace_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: 1px solid {theme.ACCENT_BORDER}; border-radius: {theme.RADIUS}px;"
            f" padding: 3px 10px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT}; }}"
        )
        replace_row.addWidget(self._replace_btn)
        action_layout.addLayout(replace_row)

        root.addWidget(self._action_bar)

    def _connect_signals(self) -> None:
        """内部シグナルを接続する。"""
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._list_widget.currentItemChanged.connect(self._on_item_selection_changed)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._reset_btn.clicked.connect(self._on_reset_clicked)
        self._exclude_btn.clicked.connect(self._on_exclude_clicked)
        self._db_reject_btn.clicked.connect(self._on_db_reject_clicked)
        self._replace_btn.clicked.connect(self._on_replace_clicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_tags(self, image_ids: list[int]) -> None:
        """ステージング集合の画像 ID を設定してタグ集計を更新する。

        StagingTagAggregationService に委譲してタグ件数を集計し、
        リストを再描画する。

        Args:
            image_ids: ステージング中の画像 ID リスト。
        """
        self._image_ids = list(image_ids)
        self._all_tags = self._service.aggregate(self._image_ids)
        logger.debug(f"StagingTagPanel.load_tags: images={len(image_ids)}, tags={len(self._all_tags)}")
        # アクティブフィルタをリセットして再描画
        self._active_filter_tag = None
        self._reset_btn.setText(f"全 {len(self._image_ids)} 枚に戻す")
        self._refresh_list()

    def get_image_ids(self) -> list[int]:
        """現在のステージング画像 ID リストを返す。

        Returns:
            ステージング中の画像 ID のコピー。
        """
        return list(self._image_ids)

    def get_displayed_tags(self) -> list[TagCount]:
        """現在表示中の TagCount リストを返す（フィルタ・ソート後）。

        Returns:
            表示中の TagCount リストのコピー。
        """
        return list(self._displayed_tags)

    # ------------------------------------------------------------------
    # Internal: filtering / sorting / rendering
    # ------------------------------------------------------------------

    def _apply_filter_and_sort(self, tags: list[TagCount]) -> list[TagCount]:
        """タグリストを検索文字列とソートモードで絞り込み・並べ替える。

        Args:
            tags: フィルタ前の TagCount リスト。

        Returns:
            フィルタ・ソート済みの TagCount リスト。
        """
        query = self._search_edit.text().strip().lower()
        sort_mode = self._sort_combo.currentIndex()

        # ソートモードが「手動のみ」なら手動タグだけ先に絞る
        if sort_mode == _SORT_MANUAL_ONLY:
            tags = [t for t in tags if t.manual]

        # テキスト検索（部分一致）
        if query:
            tags = [t for t in tags if query in t.tag.lower()]

        # ソート
        if sort_mode == _SORT_NAME:
            tags = sorted(tags, key=lambda t: t.tag)
        elif sort_mode == _SORT_MANUAL_ONLY:
            # 手動のみ: 件数降順・同数はタグ名昇順（aggregate() 済みのソートを維持）
            pass
        else:
            # 件数降順（aggregate() 既にソート済みだが明示的に）
            tags = sorted(tags, key=lambda t: (-t.count, t.tag))

        return tags

    def _refresh_list(self) -> None:
        """タグリストを再描画する。"""
        self._displayed_tags = self._apply_filter_and_sort(list(self._all_tags))

        # リスト更新前に選択変更シグナルが飛ばないよう一時ブロック
        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        self._list_widget.blockSignals(False)

        max_count = max((t.count for t in self._displayed_tags), default=1)

        for tag_count in self._displayed_tags:
            item = QListWidgetItem()
            # データとして TagCount を保持
            item.setData(Qt.ItemDataRole.UserRole, tag_count)
            # 表示テキスト: [✎] tag_name (N)
            manual_mark = " ✎" if tag_count.manual else ""
            display = f"{tag_count.tag}{manual_mark}  ({tag_count.count})"
            item.setText(display)
            # 件数バーをツールチップで表示
            bar_ratio = tag_count.count / max_count if max_count > 0 else 0
            bar_chars = round(bar_ratio * 20)
            bar_str = "█" * bar_chars + "░" * (20 - bar_chars)
            item.setToolTip(
                f"{tag_count.tag}\n件数: {tag_count.count}\n"
                f"割合: {bar_str}\n"
                f"{'手動タグ ✎' if tag_count.manual else 'AI タグ'}"
            )
            self._list_widget.addItem(item)

        # サマリ更新
        shown = len(self._displayed_tags)
        total = len(self._all_tags)
        filter_note = f" (絞り込み中: {shown})" if shown < total else ""
        self._summary_label.setText(f"{total} タグ{filter_note} / {len(self._image_ids)} 枚")

        self._update_action_bar_visibility()

    # ------------------------------------------------------------------
    # Internal: action bar
    # ------------------------------------------------------------------

    def _update_action_bar_visibility(self) -> None:
        """選択行があるときだけアクションバーを表示する。"""
        current = self._list_widget.currentItem()
        has_selection = current is not None
        self._action_bar.setVisible(has_selection)
        if has_selection:
            tag_count: TagCount = current.data(Qt.ItemDataRole.UserRole)
            self._action_tag_label.setText(f"操作対象: {tag_count.tag}")
            # 置換入力をクリア（新しい選択ごとにリセット）
            self._replace_to_edit.clear()

    def _get_selected_tag(self) -> str | None:
        """選択中のタグ文字列を返す。選択なしなら None。

        Returns:
            選択中のタグ文字列。選択なしなら None。
        """
        current = self._list_widget.currentItem()
        if current is None:
            return None
        tag_count: TagCount = current.data(Qt.ItemDataRole.UserRole)
        return tag_count.tag

    # ------------------------------------------------------------------
    # Slots: internal handlers
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_search_changed(self, _text: str) -> None:
        """検索テキスト変更でリストを再フィルタする。"""
        self._refresh_list()

    @Slot(int)
    def _on_sort_changed(self, _index: int) -> None:
        """ソート切替でリストを再ソートする。"""
        self._refresh_list()

    @Slot()
    def _on_item_selection_changed(self) -> None:
        """行選択変更でアクションバーを更新する。"""
        self._update_action_bar_visibility()

    @Slot(object)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """タグ行クリックで filter_tag_changed を emit する。

        Args:
            item: クリックされたリストアイテム。
        """
        tag_count: TagCount = item.data(Qt.ItemDataRole.UserRole)
        self._active_filter_tag = tag_count.tag
        logger.debug(f"StagingTagPanel: filter_tag_changed emit tag={tag_count.tag!r}")
        self.filter_tag_changed.emit(tag_count.tag)

    @Slot()
    def _on_reset_clicked(self) -> None:
        """「全 N 枚に戻す」ボタンで filter_tag_changed(None) を emit する。"""
        self._active_filter_tag = None
        # setCurrentRow(-1) で current item と selection を両方クリアする
        self._list_widget.setCurrentRow(-1)
        self._update_action_bar_visibility()
        logger.debug("StagingTagPanel: filter_tag_changed emit None (reset)")
        self.filter_tag_changed.emit(None)

    @Slot()
    def _on_exclude_clicked(self) -> None:
        """⊘ 出力除外ボタンで overlay_exclude_requested を emit する（橙=出力一時）。"""
        tag = self._get_selected_tag()
        if tag is None:
            return
        logger.debug(f"StagingTagPanel: overlay_exclude_requested emit tag={tag!r}")
        self.overlay_exclude_requested.emit(tag)

    @Slot()
    def _on_db_reject_clicked(self) -> None:
        """✎ reject(DB) ボタンで db_reject_everywhere_requested を emit する（青=DB永続）。"""
        tag = self._get_selected_tag()
        if tag is None:
            return
        logger.debug(f"StagingTagPanel: db_reject_everywhere_requested emit tag={tag!r}")
        self.db_reject_everywhere_requested.emit(tag)

    @Slot()
    def _on_replace_clicked(self) -> None:
        """⇄ 置換ボタンで overlay_replace_requested を emit する（橙=出力一時）。

        to_tag が空、または from_tag と同じ場合は何もしない。
        """
        from_tag = self._get_selected_tag()
        if from_tag is None:
            return
        to_tag = self._replace_to_edit.text().strip()
        if not to_tag:
            logger.debug("StagingTagPanel: 置換先タグが空のため overlay_replace_requested を送らない")
            return
        if from_tag == to_tag:
            logger.debug("StagingTagPanel: from_tag == to_tag のため overlay_replace_requested を送らない")
            return
        logger.debug(f"StagingTagPanel: overlay_replace_requested emit from={from_tag!r}, to={to_tag!r}")
        self.overlay_replace_requested.emit(from_tag, to_tag)
