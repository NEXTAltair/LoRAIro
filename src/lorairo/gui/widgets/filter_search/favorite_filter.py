# src/lorairo/gui/widgets/filter_search/favorite_filter.py
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

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....utils.log import logger

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

        # UI 構築
        self.favorite_filters_list = QListWidget()
        self.favorite_filters_list.setMaximumHeight(150)

        self.button_save_filter = QPushButton("保存")
        self.button_load_filter = QPushButton("読込")
        self.button_delete_filter = QPushButton("削除")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.button_save_filter)
        button_layout.addWidget(self.button_load_filter)
        button_layout.addWidget(self.button_delete_filter)

        group_layout = QVBoxLayout()
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
            logger.debug("Refreshed favorite filters list: {} items", len(filter_names))
        except Exception as e:
            logger.error("Failed to refresh favorite filters list: {}", e, exc_info=True)

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

        filter_name = selected_items[0].text()

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
