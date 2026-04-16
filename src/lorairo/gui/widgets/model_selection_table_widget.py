"""
Model Selection Table Widget

モデル選択テーブル専用ウィジェット
アノテーション実行用のモデル選択機能を提供

機能:
- 4列テーブルでのモデル表示（選択/モデル名/プロバイダー/機能）
- SearchFilterService経由でのモデル取得・フィルタリング
- チェックボックスによる複数モデル選択
- 選択状況の表示とシグナル通知
"""

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem, QWidget

from ...gui.designer.ModelSelectionTableWidget_ui import Ui_ModelSelectionTableWidget
from ...utils.log import logger
from ..services.search_filter_service import SearchFilterService


@dataclass
class ModelSelectionInfo:
    """モデル選択情報（AnnotationSettingsから抽出）"""

    selected_models: list[str]
    total_available: int
    filtered_count: int


class ModelSelectionTableWidget(QWidget, Ui_ModelSelectionTableWidget):
    """
    モデル選択テーブルウィジェット

    機能:
    - 4列テーブル表示（選択/モデル名/プロバイダー/機能）
    - SearchFilterService経由でのデータ取得
    - フィルタリング機能
    - 選択状況の追跡と通知
    """

    # シグナル定義
    model_selection_changed = Signal(list)  # selected_model_names
    selection_count_changed = Signal(int, int)  # selected_count, total_count
    models_loaded = Signal(int)  # total_model_count

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)

        # 依存関係
        self.search_filter_service: SearchFilterService | None = None

        # モデルデータ
        self.all_models: list[dict[str, Any]] = []
        self.filtered_models: list[dict[str, Any]] = []

        # UI初期化
        self._setup_table_properties()
        self._setup_connections()

        logger.debug("ModelSelectionTableWidget initialized")

    def _setup_table_properties(self) -> None:
        """テーブルプロパティ設定（スタイルはQt Designerで定義済み）"""
        try:
            # ヘッダー設定
            header = self.tableWidgetModels.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 選択列
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # モデル名列
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # プロバイダー列
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 機能列

            # ソート設定：モデル名列（列1）で初期ソート
            self.tableWidgetModels.sortByColumn(1, Qt.SortOrder.AscendingOrder)

            logger.debug("Table properties configured (styles from Qt Designer)")

        except Exception as e:
            logger.error(f"Error setting up table properties: {e}", exc_info=True)

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # テーブルアイテム変更時の処理
        self.tableWidgetModels.itemChanged.connect(self._on_table_item_changed)
        logger.debug("Signal connections established")

    def set_search_filter_service(self, service: SearchFilterService) -> None:
        """SearchFilterService設定（既存パターンに準拠）"""
        self.search_filter_service = service
        logger.debug("SearchFilterService set for ModelSelectionTableWidget")

    def load_models(self) -> None:
        """モデル情報をSearchFilterService経由で取得

        Raises:
            RuntimeError: SearchFilterServiceが設定されていない場合
            Exception: モデル取得失敗時

        Note:
            このメソッドは初期化時に呼ばれるため、例外は呼び出し側で適切に処理される必要がある。
        """
        if not self.search_filter_service:
            error_msg = "SearchFilterService not available for model loading"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        try:
            # SearchFilterService経由でモデル取得
            self.all_models = self.search_filter_service.get_annotation_models_list()
            logger.info(f"Loaded {len(self.all_models)} models via SearchFilterService")

            # 初期表示更新
            self.filtered_models = self.all_models.copy()
            self._update_table_display()

            # モデル読み込み完了シグナル送信
            self.models_loaded.emit(len(self.all_models))

        except Exception as e:
            logger.critical(f"Failed to load models via SearchFilterService: {e}", exc_info=True)
            raise

    def apply_filters(
        self, function_types: list[str] | None = None, providers: list[str] | None = None
    ) -> None:
        """フィルタリング適用"""
        if not self.search_filter_service:
            logger.warning("SearchFilterService not available for filtering")
            return

        try:
            # SearchFilterService経由でフィルタリング
            self.filtered_models = self.search_filter_service.filter_models_by_criteria(
                models=self.all_models, function_types=function_types or [], providers=providers or []
            )

            # テーブル表示更新
            self._update_table_display()

            logger.debug(f"Applied filters: {len(self.filtered_models)} models displayed")

        except Exception as e:
            logger.error(f"Error applying filters: {e}", exc_info=True)
            # フォールバック：全モデル表示
            self.filtered_models = self.all_models.copy()
            self._update_table_display()

    def _update_table_display(self) -> None:
        """テーブル表示更新"""
        try:
            # テーブルクリア
            self.tableWidgetModels.setRowCount(0)

            # フィルタされたモデルを追加
            for row, model in enumerate(self.filtered_models):
                self.tableWidgetModels.insertRow(row)

                # 列1: チェックボックス（選択）
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)
                self.tableWidgetModels.setItem(row, 0, checkbox_item)

                # 列2: モデル名
                name_item = QTableWidgetItem(model.get("name", ""))
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 1, name_item)

                # 列3: プロバイダー
                provider_display = (
                    "ローカル" if model.get("is_local", False) else model.get("provider", "").title()
                )
                provider_item = QTableWidgetItem(provider_display)
                provider_item.setFlags(provider_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 2, provider_item)

                # 列4: 機能
                capabilities_text = ", ".join(model.get("capabilities", []))
                capability_item = QTableWidgetItem(capabilities_text)
                capability_item.setFlags(capability_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 3, capability_item)

            # 選択数表示更新
            self._update_selection_count()

            logger.debug(f"Table updated with {len(self.filtered_models)} models")

        except Exception as e:
            logger.error(f"Error updating table display: {e}", exc_info=True)

    def _update_selection_count(self) -> None:
        """選択数更新（シグナル送信のみ）"""
        try:
            selected_count = len(self.get_selected_models())
            total_count = len(self.filtered_models)

            # シグナル送信のみ（ラベル表示は削除済み）
            self.selection_count_changed.emit(selected_count, total_count)

        except Exception as e:
            logger.error(f"Error updating selection count: {e}")

    @Slot()
    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """テーブルアイテム変更時の処理"""
        try:
            # チェックボックス列（列0）の変更のみ処理
            if item.column() == 0:
                selected_models = self.get_selected_models()
                self._update_selection_count()

                # モデル選択変更シグナル送信
                self.model_selection_changed.emit(selected_models)

                logger.debug(f"Model selection changed: {len(selected_models)} models selected")

        except Exception as e:
            logger.error(f"Error handling table item change: {e}")

    def get_selected_models(self) -> list[str]:
        """選択されたモデル名のリストを取得"""
        selected_models = []

        try:
            for row in range(self.tableWidgetModels.rowCount()):
                checkbox_item = self.tableWidgetModels.item(row, 0)
                if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                    model_name_item = self.tableWidgetModels.item(row, 1)
                    if model_name_item:
                        selected_models.append(model_name_item.text())

        except Exception as e:
            logger.error(f"Error getting selected models: {e}")

        return selected_models

    def set_selected_models(self, model_names: list[str]) -> None:
        """指定されたモデルを選択状態に設定"""
        try:
            for row in range(self.tableWidgetModels.rowCount()):
                model_name_item = self.tableWidgetModels.item(row, 1)
                checkbox_item = self.tableWidgetModels.item(row, 0)

                if model_name_item and checkbox_item:
                    model_name = model_name_item.text()
                    is_selected = model_name in model_names
                    checkbox_item.setCheckState(
                        Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked
                    )

            logger.debug(f"Set {len(model_names)} models as selected")

        except Exception as e:
            logger.error(f"Error setting selected models: {e}")

    def get_selection_info(self) -> ModelSelectionInfo:
        """現在の選択情報を取得"""
        selected_models = self.get_selected_models()
        return ModelSelectionInfo(
            selected_models=selected_models,
            total_available=len(self.all_models),
            filtered_count=len(self.filtered_models),
        )


if __name__ == "__main__":
    # 単体実行とテスト表示
    import sys
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout

    from ...utils.log import initialize_logging

    # ログ設定（コンソール出力）
    initialize_logging({"level": "DEBUG", "file": None})

    app = QApplication(sys.argv)

    # メインウィンドウ作成
    main_window = QMainWindow()
    main_window.setWindowTitle("ModelSelectionTableWidget 単体テスト")
    main_window.resize(800, 600)

    # 中央ウィジェットとレイアウト
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)

    # ModelSelectionTableWidget作成
    table_widget = ModelSelectionTableWidget()
    layout.addWidget(table_widget)

    # 選択情報表示ボタン（テスト用）
    def show_selection_info() -> None:
        from lorairo.utils.log import logger

        info = table_widget.get_selection_info()
        logger.debug("\n=== 選択情報 ===")
        logger.debug(f"選択モデル: {info.selected_models}")
        logger.debug(f"全体数: {info.total_available}")
        logger.debug(f"表示数: {info.filtered_count}")
        logger.debug("================\n")

    btn_info = QPushButton("選択情報表示")
    btn_info.clicked.connect(show_selection_info)
    layout.addWidget(btn_info)

    # モックサービスとダミーデータ設定
    mock_service = Mock()

    dummy_models = [
        {
            "name": "gpt-4-vision-preview",
            "provider": "openai",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
        },
        {
            "name": "claude-3-sonnet",
            "provider": "anthropic",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
        },
        {
            "name": "wd-v1-4-swinv2-tagger-v3",
            "provider": "local",
            "capabilities": ["tags"],
            "requires_api_key": False,
            "is_local": True,
        },
        {
            "name": "clip-aesthetic-score",
            "provider": "local",
            "capabilities": ["scores"],
            "requires_api_key": False,
            "is_local": True,
        },
        {
            "name": "blip2-opt-2.7b",
            "provider": "local",
            "capabilities": ["caption"],
            "requires_api_key": False,
            "is_local": True,
        },
    ]

    # モックサービス設定
    mock_service.get_annotation_models_list.return_value = dummy_models
    mock_service.filter_models_by_criteria.return_value = dummy_models

    # サービス設定とモデルロード
    table_widget.set_search_filter_service(mock_service)
    table_widget.load_models()

    # シグナル接続（テスト用デバッグログ）
    def on_selection_changed(models: list[str]) -> None:
        from lorairo.utils.log import logger

        logger.debug(f"🔄 Selection changed: {models}")

    def on_count_changed(selected: int, total: int) -> None:
        from lorairo.utils.log import logger

        logger.debug(f"📊 Count changed: {selected}/{total}")

    def on_models_loaded(count: int) -> None:
        from lorairo.utils.log import logger

        logger.debug(f"✅ Models loaded: {count} models")

    table_widget.model_selection_changed.connect(on_selection_changed)
    table_widget.selection_count_changed.connect(on_count_changed)
    table_widget.models_loaded.connect(on_models_loaded)

    # ウィンドウ設定
    main_window.setCentralWidget(central_widget)
    main_window.show()

    from lorairo.utils.log import logger

    logger.info("🚀 ModelSelectionTableWidget 単体テスト起動")
    logger.info("📋 テスト項目:")
    logger.info("   - 4列テーブル表示（選択/モデル名/プロバイダー/機能）")
    logger.info("   - チェックボックスでの複数選択")
    logger.info("   - モデル名でのソート機能")
    logger.info("   - シグナル動作確認（デバッグログ出力）")
    logger.info("   - 選択情報表示ボタン")
    logger.info("💡 操作: チェックボックスをクリックして選択変更を確認してください")

    # アプリケーション実行
    sys.exit(app.exec())
