# src/lorairo/gui/widgets/favorite_filter.py
"""お気に入りフィルタ Panel (ADR 0036 §6)。

保存・読込・削除ボタンと QListWidget を内包し、FavoriteFiltersService を
依存注入で受け取る。Parent (FilterSearchPanel) は以下のシグナルを購読する:

- `save_requested`: 保存ボタンクリック (現在条件を要求するためのリクエスト)
- `load_requested(str)`: 名前指定でロード要求
- `delete_requested(str)`: 名前指定で削除要求

実体の I/O (FavoriteFiltersService 呼び出し) はこのウィジェット内で完結する。
condition の取得・適用は Parent コールバックで委ねる。
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...gui import theme
from ...utils.log import logger

ConditionsGetter = Callable[[], dict[str, Any]]
ConditionsApplier = Callable[[dict[str, Any]], None]


class FavoriteFilterPanel(QGroupBox):
    """お気に入りフィルタの一覧表示 + 保存/読込/削除を担う Panel。

    Parent はこのパネルを composition で保持し、以下を渡す:

    - `set_favorite_filters_service()`: ストレージ Service
    - `set_conditions_getter()`: 現在の検索条件を辞書で取得するコールバック
    - `set_conditions_applier()`: 条件を UI に適用するコールバック
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("お気に入りフィルター", parent)
        self.setCheckable(True)
        self.setChecked(False)  # 初期状態は折りたたみ

        self.favorite_filters_service: Any = None
        self._conditions_getter: ConditionsGetter | None = None
        self._conditions_applier: ConditionsApplier | None = None

        # DS v12: 保存クエリを chip 一覧で表示 (#815)。QListWidget は back-compat の
        # 隠し backing として残し (count/item/setCurrentRow が既存テスト・mediator
        # property の contract)、表示は chip FlowLayout で行う。
        from .tag_cloud_widget import FlowLayout

        self.favorite_filters_list = QListWidget()
        self.favorite_filters_list.setMaximumHeight(150)
        self.favorite_filters_list.setVisible(False)  # chip 表示が主、list は backing

        self._chip_container = QWidget()
        self._chip_layout = FlowLayout(self._chip_container, spacing=4)
        self._empty_label = QLabel("保存済みのお気に入りはありません")
        self._empty_label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL}px;")

        # ☆ お気に入りに保存 (DS の保存導線)
        self.button_save_filter = QPushButton("☆ お気に入りに保存")
        # back-compat: 読込/削除は chip クリック・× に集約したが、既存テスト・
        # アクセシビリティ用に残す。
        self.button_load_filter = QPushButton("読込")
        self.button_delete_filter = QPushButton("削除")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.button_save_filter)
        button_layout.addWidget(self.button_load_filter)
        button_layout.addWidget(self.button_delete_filter)

        group_layout = QVBoxLayout()
        group_layout.addWidget(self._empty_label)
        group_layout.addWidget(self._chip_container)
        group_layout.addWidget(self.favorite_filters_list)
        group_layout.addLayout(button_layout)
        self.setLayout(group_layout)

        # シグナル接続 (内部完結)
        self.button_save_filter.clicked.connect(self._on_save_clicked)
        self.button_load_filter.clicked.connect(self._on_load_clicked)
        self.button_delete_filter.clicked.connect(self._on_delete_clicked)
        self.favorite_filters_list.itemDoubleClicked.connect(self._on_filter_double_clicked)

        logger.debug("FavoriteFilterPanel initialized")

    # === Public API ===

    def set_favorite_filters_service(self, service: Any) -> None:
        """FavoriteFiltersService を設定する。

        Args:
            service: FavoriteFiltersService インスタンス。

        Raises:
            ValueError: service が None の場合。
        """
        if service is None:
            raise ValueError("FavoriteFiltersService cannot be None")

        self.favorite_filters_service = service
        self._refresh_list()
        logger.info("FavoriteFiltersService set successfully")

    def set_conditions_getter(self, getter: ConditionsGetter) -> None:
        """現在の検索条件を返すコールバックを設定する。"""
        self._conditions_getter = getter

    def set_conditions_applier(self, applier: ConditionsApplier) -> None:
        """条件を UI に適用するコールバックを設定する。"""
        self._conditions_applier = applier

    # === Internal ===

    def _refresh_list(self) -> None:
        """お気に入りフィルター一覧を更新。"""
        if not self.favorite_filters_service:
            return

        self.favorite_filters_list.clear()
        try:
            filter_names = self.favorite_filters_service.list_filters()
            for name in filter_names:
                self.favorite_filters_list.addItem(name)
            # chip サマリ用に条件を一括取得 (N 回 load_filter する 2 回読みを回避)
            conditions_map = self.favorite_filters_service.get_all_filters()
            self._render_chips(filter_names, conditions_map)
            logger.debug("Refreshed favorite filters list: {} items", len(filter_names))
        except Exception as e:
            logger.error("Failed to refresh favorite filters list: {}", e, exc_info=True)

    def _render_chips(self, filter_names: list[str], conditions_map: dict[str, Any]) -> None:
        """保存クエリを DS chip で再描画する (#815)。

        各 chip = 名前 + 条件サマリ (mono) + × 削除。chip クリックで適用。

        Args:
            filter_names: 表示する保存フィルタ名のリスト。
            conditions_map: フィルタ名→条件辞書のマップ (サマリ表示用)。
        """
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._empty_label.setVisible(not filter_names)
        self._chip_container.setVisible(bool(filter_names))
        for name in filter_names:
            self._chip_layout.addWidget(self._build_query_chip(name, conditions_map.get(name)))

    def _build_query_chip(self, name: str, conditions: dict[str, Any] | None) -> QWidget:
        """保存クエリ 1 件分の chip (名前 + サマリ + × 削除、クリックで適用)。"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        summary = self._summarize_conditions(conditions)
        label = f"★ {name}" + (f"  {summary}" if summary else "")
        chip = QPushButton(label, container)
        chip.setObjectName("favoriteQueryChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"{name} を適用" + (f" ({summary})" if summary else ""))
        chip.setStyleSheet(
            f"QPushButton {{ background-color: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 2px 9px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ border-color: {theme.ACCENT}; }}"
        )
        chip.clicked.connect(lambda _checked=False, n=name: self._load_by_name(n))
        layout.addWidget(chip)

        remove = QToolButton(container)
        remove.setObjectName("favoriteQueryChipRemove")
        remove.setText("×")
        remove.setAutoRaise(True)
        remove.setToolTip(f"{name} を削除")
        remove.clicked.connect(lambda _checked=False, n=name: self._delete_by_name(n))
        layout.addWidget(remove)
        return container

    def _summarize_conditions(self, conditions: dict[str, Any] | None) -> str:
        """保存フィルタ条件の短い mono サマリを返す (#815、chip sub 用)。"""
        if not isinstance(conditions, dict) or not conditions:
            return ""
        parts: list[str] = []
        keywords = conditions.get("keywords") or []
        if keywords:
            joined = ",".join(str(k) for k in keywords[:2])
            parts.append(joined + ("…" if len(keywords) > 2 else ""))
        resolution = conditions.get("resolution_filter")
        if resolution:
            parts.append(f"{resolution}px")
        if conditions.get("date_filter_enabled"):
            parts.append("期間指定")
        if conditions.get("only_untagged"):
            parts.append("untagged")
        return " · ".join(parts)

    def _on_save_clicked(self) -> None:
        """保存ボタンクリックハンドラ。"""
        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        if self._conditions_getter is None:
            QMessageBox.warning(self, "エラー", "条件取得コールバックが設定されていません。")
            return

        conditions = self._conditions_getter()
        if not conditions:
            QMessageBox.warning(self, "保存失敗", "保存する条件がありません。")
            return

        filter_name, ok = QInputDialog.getText(
            self,
            "フィルター保存",
            "フィルター名を入力してください:",
        )
        if not ok or not filter_name.strip():
            return
        filter_name = filter_name.strip()

        if self.favorite_filters_service.filter_exists(filter_name):
            reply = QMessageBox.question(
                self,
                "上書き確認",
                f"フィルター '{filter_name}' は既に存在します。上書きしますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            success = self.favorite_filters_service.save_filter(filter_name, conditions)
            if success:
                QMessageBox.information(self, "保存完了", f"フィルター '{filter_name}' を保存しました。")
                self._refresh_list()
            else:
                QMessageBox.warning(self, "保存失敗", "フィルターの保存に失敗しました。")
        except Exception as e:
            logger.error("Failed to save filter: {}", e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの保存中にエラーが発生しました:\n{e}")

    def _on_load_clicked(self) -> None:
        """読込ボタンクリックハンドラ。"""
        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        selected_items = self.favorite_filters_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "読込失敗", "読み込むフィルターを選択してください。")
            return

        self._load_by_name(selected_items[0].text())

    def _on_filter_double_clicked(self, item: QListWidgetItem) -> None:
        """フィルターダブルクリックハンドラ。"""
        self._load_by_name(item.text())

    def _load_by_name(self, filter_name: str) -> None:
        """フィルター名から読み込んで applier に渡す。"""
        if not self.favorite_filters_service or self._conditions_applier is None:
            return

        try:
            conditions = self.favorite_filters_service.load_filter(filter_name)
            if conditions:
                self._conditions_applier(conditions)
                QMessageBox.information(self, "読込完了", f"フィルター '{filter_name}' を適用しました。")
                logger.info("Loaded and applied favorite filter: {}", filter_name)
            else:
                QMessageBox.warning(
                    self,
                    "読込失敗",
                    f"フィルター '{filter_name}' の読み込みに失敗しました。",
                )
        except Exception as e:
            logger.error("Failed to load filter '{}': {}", filter_name, e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの読み込み中にエラーが発生しました:\n{e}")

    def _on_delete_clicked(self) -> None:
        """削除ボタンクリックハンドラ。"""
        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        selected_items = self.favorite_filters_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "削除失敗", "削除するフィルターを選択してください。")
            return

        self._delete_by_name(selected_items[0].text())

    def _delete_by_name(self, filter_name: str) -> None:
        """フィルター名から削除する (chip × / 削除ボタン 共通、#815)。"""
        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        reply = QMessageBox.question(
            self,
            "削除確認",
            f"フィルター '{filter_name}' を削除しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            success = self.favorite_filters_service.delete_filter(filter_name)
            if success:
                QMessageBox.information(self, "削除完了", f"フィルター '{filter_name}' を削除しました。")
                self._refresh_list()
            else:
                QMessageBox.warning(self, "削除失敗", "フィルターの削除に失敗しました。")
        except Exception as e:
            logger.error("Failed to delete filter '{}': {}", filter_name, e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの削除中にエラーが発生しました:\n{e}")
