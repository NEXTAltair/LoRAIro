from __future__ import annotations

import datetime

from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui.widgets.date_histogram_widget import DateHistogramWidget


class SearchFacetsSidebar(QWidget):
    """検索ファセットサイドバーウィジェット。

    手動編集・レビュー状態・エラー状態・モデル・登録日のファセットフィルタを提供する。
    ファセット値が変化したとき facets_changed シグナルを発火する。
    """

    from PySide6.QtCore import Signal

    facets_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._created_at_range: tuple[datetime.datetime, datetime.datetime] | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """UIコンポーネントを初期化・配置する。"""
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 手動編集セクション
        manual_box, self._manual_edit_group, self._manual_edit_buttons = self._make_radio_section(
            "手動編集", ["全て", "あり", "なし"]
        )
        layout.addWidget(manual_box)

        # レビュー状態セクション
        reviewed_box, self._reviewed_group, self._reviewed_buttons = self._make_radio_section(
            "レビュー", ["全て", "未レビュー", "済み"]
        )
        layout.addWidget(reviewed_box)

        # エラー状態セクション
        error_box, self._error_group, self._error_buttons = self._make_radio_section(
            "エラー", ["全て", "あり", "なし"]
        )
        layout.addWidget(error_box)

        # モデルセクション
        model_box = QGroupBox("モデル")
        model_layout = QVBoxLayout(model_box)
        self._model_list = QListWidget()
        self._model_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._model_list.setMaximumHeight(120)
        model_layout.addWidget(self._model_list)
        layout.addWidget(model_box)

        # 登録日セクション
        date_box = QGroupBox("登録日")
        date_layout = QVBoxLayout(date_box)
        self._histogram = DateHistogramWidget()
        date_layout.addWidget(self._histogram)
        layout.addWidget(date_box)

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

    def _make_radio_section(
        self, title: str, labels: list[str]
    ) -> tuple[QGroupBox, QButtonGroup, list[QRadioButton]]:
        """ラジオボタングループを含む QGroupBox を生成する。

        Args:
            title: グループボックスのタイトル。
            labels: ラジオボタンのラベルリスト。先頭ボタンがデフォルト選択。

        Returns:
            (QGroupBox, QButtonGroup, ラジオボタンリスト) のタプル。
        """
        group_box = QGroupBox(title)
        layout = QHBoxLayout(group_box)
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        buttons: list[QRadioButton] = []
        for i, label in enumerate(labels):
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            layout.addWidget(rb)
            btn_group.addButton(rb, i)
            buttons.append(rb)
        return group_box, btn_group, buttons

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
        self._model_list.clearSelection()
        self._created_at_range = None
        self._histogram.clear()
