from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.gui.widgets.date_histogram_widget import DateHistogramWidget


def _group_title_qss() -> str:
    """DS Group ヘッダ (uppercase ラベル) 用の QLabel QSS。"""
    return (
        f"font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_BOLD};"
        f" color: {theme.INK}; letter-spacing: {theme.LETTER_CAPS};"
    )


def _group_sub_qss() -> str:
    """DS Group ヘッダの mono サブコード用 QLabel QSS。"""
    return (
        f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
        f" color: {theme.INK_FAINT};"
    )


def _facet_radio_qss() -> str:
    """DS Facet 行 (radio) 用の QRadioButton QSS。borders-not-shadows・accent 塗り。"""
    return (
        f"QRadioButton {{ font-size: {theme.FONT_SIZE_SMALL}px; color: {theme.INK};"
        f" spacing: 7px; padding: 2px 4px; }}"
        f" QRadioButton::indicator {{ width: 13px; height: 13px; }}"
        f" QRadioButton::indicator:unchecked {{ border: 1px solid {theme.LINE_STRONG};"
        f" border-radius: 7px; background: {theme.CARD}; }}"
        f" QRadioButton::indicator:checked {{ border: 1px solid {theme.ACCENT};"
        f" border-radius: 7px; background: {theme.ACCENT}; }}"
    )


def _model_list_qss() -> str:
    """モデルフィルタリスト用の DS QListWidget QSS。"""
    return (
        f"QListWidget {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
        f" background: {theme.CARD}; font-size: {theme.FONT_SIZE_SMALL}px; }}"
        f" QListWidget::item {{ padding: 3px 5px; }}"
        f" QListWidget::item:selected {{ background: {theme.ACCENT_SOFT};"
        f" color: {theme.ACCENT_HOVER}; }}"
    )


class SearchFacetsSidebar(QWidget):
    """検索ファセットサイドバーウィジェット。

    手動編集・レビュー状態・エラー状態・モデル・登録日のファセットフィルタを提供する。
    ファセット値が変化したとき facets_changed シグナルを発火する。

    ビジュアルは Wireframes v12 / Design System の Group + Facet 文法に整合
    (token・borders-not-shadows、uppercase Group ヘッダ + mono サブコード)。
    """

    facets_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._created_at_range: tuple[datetime.datetime, datetime.datetime] | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """UIコンポーネントを初期化・配置する。"""
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setStyleSheet(f"background: {theme.PAPER};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        # 手動編集セクション (annotations state · MANUAL_EDIT)
        manual_box, self._manual_edit_group, self._manual_edit_buttons = self._make_radio_group(
            "手動編集", "is_edited_manually", ["全て", "あり", "なし"]
        )
        layout.addWidget(manual_box)
        layout.addWidget(self._make_separator())

        # レビュー状態セクション
        reviewed_box, self._reviewed_group, self._reviewed_buttons = self._make_radio_group(
            "レビュー", "reviewed_at", ["全て", "未レビュー", "済み"]
        )
        layout.addWidget(reviewed_box)
        layout.addWidget(self._make_separator())

        # エラー状態セクション
        error_box, self._error_group, self._error_buttons = self._make_radio_group(
            "エラー状態", "ErrorRecord", ["全て", "あり", "なし"]
        )
        layout.addWidget(error_box)
        layout.addWidget(self._make_separator())

        # モデルセクション (検索 input + 複数選択リスト)
        model_group, model_layout = self._make_group("モデル", "Model.name")
        self._model_search = QLineEdit()
        self._model_search.setPlaceholderText("モデル名で検索…")
        self._model_search.setClearButtonEnabled(True)
        self._model_search.textChanged.connect(self._filter_model_list)
        model_layout.addWidget(self._model_search)
        self._model_list = QListWidget()
        self._model_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._model_list.setMaximumHeight(140)
        self._model_list.setStyleSheet(_model_list_qss())
        model_layout.addWidget(self._model_list)
        layout.addWidget(model_group)
        layout.addWidget(self._make_separator())

        # 登録日セクション
        date_group, date_layout = self._make_group("登録日", "Image.created_at")
        self._histogram = DateHistogramWidget()
        date_layout.addWidget(self._histogram)
        layout.addWidget(date_group)

        layout.addStretch()
        scroll_area.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_area)

        # シグナル接続
        self._manual_edit_group.buttonClicked.connect(lambda _: self._emit_facets_changed())
        self._reviewed_group.buttonClicked.connect(lambda _: self._emit_facets_changed())
        self._error_group.buttonClicked.connect(lambda _: self._emit_facets_changed())
        self._model_list.itemSelectionChanged.connect(self._emit_facets_changed)
        self._histogram.range_selected.connect(self._on_range_selected)

    def _make_group(self, title: str, sub: str | None = None) -> tuple[QWidget, QVBoxLayout]:
        """DS Group コンテナ (uppercase ラベル + mono サブコード) を生成する。

        Args:
            title: グループ見出し。
            sub: 見出し右の mono サブコード (対応 DB カラム名など)。None なら省略。

        Returns:
            (グループ QWidget, 本体を積む QVBoxLayout) のタプル。
        """
        group = QWidget()
        outer = QVBoxLayout(group)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet(_group_title_qss())
        header.addWidget(title_label)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setStyleSheet(_group_sub_qss())
            header.addWidget(sub_label)
        header.addStretch()
        outer.addLayout(header)

        return group, outer

    def _make_radio_group(
        self, title: str, sub: str, labels: list[str]
    ) -> tuple[QWidget, QButtonGroup, list[QRadioButton]]:
        """DS Group 内に排他ラジオ行を配置したセクションを生成する。

        Args:
            title: グループ見出し。
            sub: 見出し右の mono サブコード。
            labels: ラジオボタンのラベルリスト。先頭ボタンがデフォルト選択。

        Returns:
            (グループ QWidget, QButtonGroup, ラジオボタンリスト) のタプル。
        """
        group, layout = self._make_group(title, sub)
        radio_row = QHBoxLayout()
        radio_row.setContentsMargins(0, 0, 0, 0)
        radio_row.setSpacing(10)
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        buttons: list[QRadioButton] = []
        for i, label in enumerate(labels):
            rb = QRadioButton(label)
            rb.setStyleSheet(_facet_radio_qss())
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0:
                rb.setChecked(True)
            radio_row.addWidget(rb)
            btn_group.addButton(rb, i)
            buttons.append(rb)
        radio_row.addStretch()
        layout.addLayout(radio_row)
        return group, btn_group, buttons

    @staticmethod
    def _make_separator() -> QFrame:
        """DS Group 間の 1px 区切り線 (borders-not-shadows)。"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f"color: {theme.LINE}; background: {theme.LINE}; max-height: 1px;")
        return line

    def _filter_model_list(self, text: str) -> None:
        """モデル名検索入力でリスト項目の表示/非表示を切り替える。"""
        needle = text.strip().lower()
        for i in range(self._model_list.count()):
            item = self._model_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _get_radio_value(self, btn_group: QButtonGroup, values: list[object]) -> object:
        """選択中ラジオボタンに対応する値を返す。

        Args:
            btn_group: 対象の QButtonGroup。
            values: ボタンインデックスに対応する値リスト。

        Returns:
            選択中インデックスに対応する値。インデックス範囲外なら values[0]。
        """
        idx = btn_group.checkedId()
        if idx < 0 or idx >= len(values):
            return values[0]
        return values[idx]

    def _on_range_selected(self, start: datetime.datetime, end: datetime.datetime) -> None:
        """ヒストグラムの range_selected シグナルを受け取って facets_changed を発火する。"""
        self._created_at_range = (start, end)
        self._emit_facets_changed()

    def _emit_facets_changed(self) -> None:
        """現在のファセット値を facets_changed シグナルで emit する。"""
        self.facets_changed.emit(self.get_facet_values())

    def get_facet_values(self) -> dict[str, object]:
        """現在のすべての facet 値を返す。

        Returns:
            以下のキーを持つ辞書:
                manual_edit_filter: True/False/None
                reviewed_at_filter: "unreviewed"/"reviewed"/None
                error_state_filter: "has_error"/"no_error"/None
                model_filter: litellm_model_id のリスト / None
                created_at_range: (start, end) タプル / None
        """
        manual_edit_filter = self._get_radio_value(self._manual_edit_group, [None, True, False])
        reviewed_at_filter = self._get_radio_value(self._reviewed_group, [None, "unreviewed", "reviewed"])
        error_state_filter = self._get_radio_value(self._error_group, [None, "has_error", "no_error"])

        selected_items = self._model_list.selectedItems()
        model_filter: list[str] | None = (
            [item.text() for item in selected_items] if selected_items else None
        )

        return {
            "manual_edit_filter": manual_edit_filter,
            "reviewed_at_filter": reviewed_at_filter,
            "error_state_filter": error_state_filter,
            "model_filter": model_filter,
            "created_at_range": self._created_at_range,
        }

    def update_models(self, model_ids: list[str]) -> None:
        """モデルフィルタ用リストに model_ids を設定する。

        Args:
            model_ids: litellm_model_id のリスト。
        """
        self._model_list.clear()
        self._model_list.addItems(model_ids)
        self._filter_model_list(self._model_search.text())

    def update_histogram(self, bins: list[tuple[datetime.datetime, datetime.datetime, int]]) -> None:
        """DATE ヒストグラムにデータを渡す。

        Args:
            bins: (bin_start, bin_end, count) のリスト。
        """
        self._histogram.update_histogram(bins)

    def clear_all(self) -> None:
        """すべての facet を初期値（全て）にリセットする。"""
        # ラジオボタンを先頭（全て）に戻す
        for buttons in (self._manual_edit_buttons, self._reviewed_buttons, self._error_buttons):
            buttons[0].setChecked(True)
        self._model_search.clear()
        self._model_list.clearSelection()
        self._created_at_range = None
        self._histogram.clear()
