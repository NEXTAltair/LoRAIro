"""
Annotation Control Widget

複数モデル選択・実行制御機能を提供
機能タイプ・実行環境によるフィルタリングと実行制御
"""

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ...gui.designer.AnnotationControlWidget_ui import Ui_AnnotationControlWidget
from ...services.annotator_lib_adapter import AnnotatorLibAdapter
from ...utils.log import logger


@dataclass
class AnnotationSettings:
    """アノテーション実行設定"""

    selected_function_types: list[str]  # ["caption", "tags", "scores"]
    selected_providers: list[str]  # ["web_api", "local"]
    selected_models: list[str]  # Model names
    use_low_resolution: bool = False
    batch_mode: bool = False


class AnnotationControlWidget(QWidget, Ui_AnnotationControlWidget):
    """
    アノテーション制御ウィジェット

    機能:
    - 機能タイプ選択（Caption/Tags/Scores）
    - 実行環境選択（Web API/ローカル）
    - モデル選択テーブル（200+モデル対応）
    - 実行制御とオプション設定
    """

    # シグナル
    annotation_started = Signal(AnnotationSettings)  # アノテーション開始
    settings_changed = Signal(AnnotationSettings)  # 設定変更
    models_refreshed = Signal(int)  # モデル一覧更新完了 (モデル数)

    def __init__(
        self,
        parent: QWidget | None = None,
        annotator_adapter: AnnotatorLibAdapter | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)  # type: ignore

        # 依存関係
        self.annotator_adapter = annotator_adapter

        # モデル情報
        self.all_models: list[dict[str, Any]] = []
        self.filtered_models: list[dict[str, Any]] = []

        # 現在の設定
        self.current_settings: AnnotationSettings = AnnotationSettings(
            selected_function_types=["caption", "tags", "scores"],
            selected_providers=["web_api", "local"],
            selected_models=[],
        )

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()
        self._setup_model_table()

        # モデル情報の初期ロード
        if self.annotator_adapter:
            self.load_models()

        logger.debug("AnnotationControlWidget initialized")

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # 機能タイプチェックボックス
        self.checkBoxCaption.toggled.connect(self._on_function_type_changed)
        self.checkBoxTagger.toggled.connect(self._on_function_type_changed)
        self.checkBoxScorer.toggled.connect(self._on_function_type_changed)

        # プロバイダーチェックボックス
        self.checkBoxWebAPI.toggled.connect(self._on_provider_changed)
        self.checkBoxLocal.toggled.connect(self._on_provider_changed)

        # オプションチェックボックス
        self.checkBoxLowResolution.toggled.connect(self._on_option_changed)
        self.checkBoxBatchMode.toggled.connect(self._on_option_changed)

        # 実行ボタン
        self.pushButtonStart.clicked.connect(self._on_execute_clicked)

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # チェックボックス共通スタイル
        checkbox_style = """
            QCheckBox {
                font-size: 10px;
                font-weight: normal;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #ccc;
                background-color: white;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #4CAF50;
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """

        # 各チェックボックスにスタイル適用
        checkboxes = [
            self.checkBoxCaption,
            self.checkBoxTagger,
            self.checkBoxScorer,
            self.checkBoxWebAPI,
            self.checkBoxLocal,
            self.checkBoxLowResolution,
            self.checkBoxBatchMode,
        ]
        for checkbox in checkboxes:
            checkbox.setStyleSheet(checkbox_style)

        # 実行ボタンスタイル
        self.pushButtonStart.setStyleSheet(""" # type: ignore
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                padding: 8px 16px;
                border: 2px solid #4CAF50;
                border-radius: 6px;
                background-color: #f0f8f0;
                color: #2E7D32;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #e8f5e8;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaa;
                border-color: #ddd;
            }
        """)

    def _setup_model_table(self) -> None:
        """モデル選択テーブルを設定"""
        try:
            # テーブル基本設定
            self.tableWidgetModels.setColumnCount(4)
            self.tableWidgetModels.setHorizontalHeaderLabels(["選択", "モデル名", "プロバイダー", "機能"])

            # ヘッダー設定
            header = self.tableWidgetModels.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 選択列
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # モデル名列
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # プロバイダー列
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 機能列

            # テーブルスタイル
            self.tableWidgetModels.setStyleSheet("""
                QTableWidget {
                    font-size: 9px;
                    gridline-color: #e0e0e0;
                    selection-background-color: #e3f2fd;
                }
                QTableWidget::item {
                    padding: 4px;
                }
                QHeaderView::section {
                    font-size: 9px;
                    font-weight: bold;
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    padding: 4px;
                }
            """)

            # 選択動作設定
            self.tableWidgetModels.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.tableWidgetModels.setAlternatingRowColors(True)

            logger.debug("Model selection table setup completed")

        except Exception as e:
            logger.error(f"Error setting up model table: {e}", exc_info=True)

    def set_annotator_adapter(self, adapter: AnnotatorLibAdapter) -> None:
        """AnnotatorLibAdapter設定"""
        self.annotator_adapter = adapter
        self.load_models()
        logger.debug("AnnotatorLibAdapter set for AnnotationControlWidget")

    def load_models(self) -> None:
        """モデル情報をAnnotatorLibAdapterから取得"""
        if not self.annotator_adapter:
            logger.warning("AnnotatorLibAdapter not available")
            return

        try:
            # AnnotatorLibAdapterからモデル情報取得
            models_metadata = self.annotator_adapter.get_available_models_with_metadata()

            # モデル情報を内部形式に変換
            self.all_models = []
            for model_data in models_metadata:
                model_info = {
                    "name": model_data.get("name", ""),
                    "provider": model_data.get("provider", "unknown"),
                    "capabilities": self._infer_capabilities(model_data),
                    "requires_api_key": model_data.get("requires_api_key", False),
                    "is_local": model_data.get("provider", "").lower() == "local",
                    "estimated_size_gb": model_data.get("estimated_size_gb"),
                }
                self.all_models.append(model_info)

            logger.info(f"Loaded {len(self.all_models)} models from AnnotatorLibAdapter")

            # フィルタリングしてテーブル更新
            self._apply_filters()

            self.models_refreshed.emit(len(self.all_models))

        except Exception as e:
            logger.error(f"Failed to load models: {e}", exc_info=True)

    def _infer_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """モデル情報から機能を推測"""
        name = model_data.get("name", "").lower()
        provider = model_data.get("provider", "").lower()

        capabilities = []

        # マルチモーダルLLM（Caption + Tags生成）
        if any(keyword in name for keyword in ["gpt-4", "claude", "gemini"]):
            capabilities = ["caption", "tags"]
        # Caption特化
        elif any(keyword in name for keyword in ["gpt-4o", "dall-e"]):
            capabilities = ["caption"]
        # タグ生成特化
        elif any(keyword in name for keyword in ["tagger", "danbooru", "wd-", "deepdanbooru"]):
            capabilities = ["tags"]
        # 品質評価特化
        elif any(keyword in name for keyword in ["aesthetic", "clip", "musiq", "quality", "score"]):
            capabilities = ["scores"]
        # プロバイダーベース推測
        elif provider in ["openai", "anthropic", "google"]:
            capabilities = ["caption", "tags"]
        else:
            capabilities = ["caption"]  # デフォルト

        return capabilities

    @Slot()
    def _on_function_type_changed(self) -> None:
        """機能タイプ変更時の処理"""
        self._update_current_settings()
        self._apply_filters()
        logger.debug("Function type selection changed")

    @Slot()
    def _on_provider_changed(self) -> None:
        """プロバイダー変更時の処理"""
        self._update_current_settings()
        self._apply_filters()
        logger.debug("Provider selection changed")

    @Slot()
    def _on_option_changed(self) -> None:
        """オプション変更時の処理"""
        self._update_current_settings()
        logger.debug("Options changed")

    @Slot()
    def _on_execute_clicked(self) -> None:
        """実行ボタンクリック時の処理"""
        try:
            self._update_current_settings()

            # 選択モデル確認
            if not self.current_settings.selected_models:
                logger.warning("No models selected for annotation")
                return

            # 機能タイプ確認
            if not self.current_settings.selected_function_types:
                logger.warning("No function types selected for annotation")
                return

            # アノテーション開始シグナル送信
            self.annotation_started.emit(self.current_settings)
            logger.info(f"Annotation started with {len(self.current_settings.selected_models)} models")

        except Exception as e:
            logger.error(f"Error starting annotation: {e}", exc_info=True)

    def _update_current_settings(self) -> None:
        """現在の設定を更新"""
        try:
            # 機能タイプ取得
            function_types = []
            if self.checkBoxCaption.isChecked():
                function_types.append("caption")
            if self.checkBoxTagger.isChecked():
                function_types.append("tags")
            if self.checkBoxScorer.isChecked():
                function_types.append("scores")

            # プロバイダー取得
            providers = []
            if self.checkBoxWebAPI.isChecked():
                providers.append("web_api")
            if self.checkBoxLocal.isChecked():
                providers.append("local")

            # 選択モデル取得
            selected_models = self._get_selected_models()

            # オプション取得
            use_low_resolution = self.checkBoxLowResolution.isChecked()
            batch_mode = self.checkBoxBatchMode.isChecked()

            # 設定更新
            self.current_settings = AnnotationSettings(
                selected_function_types=function_types,
                selected_providers=providers,
                selected_models=selected_models,
                use_low_resolution=use_low_resolution,
                batch_mode=batch_mode,
            )

            # 設定変更シグナル送信
            self.settings_changed.emit(self.current_settings)

        except Exception as e:
            logger.error(f"Error updating settings: {e}")

    def _apply_filters(self) -> None:
        """フィルターを適用してテーブル更新"""
        try:
            # 現在の設定取得
            self._update_current_settings()

            # フィルタリング実行
            self.filtered_models = []
            for model in self.all_models:
                # プロバイダーフィルター
                if not self._model_matches_provider_filter(model):
                    continue

                # 機能フィルター
                if not self._model_matches_function_filter(model):
                    continue

                self.filtered_models.append(model)

            # テーブル更新
            self._update_model_table()

            logger.debug(f"Applied filters: {len(self.filtered_models)} models displayed")

        except Exception as e:
            logger.error(f"Error applying filters: {e}", exc_info=True)

    def _model_matches_provider_filter(self, model: dict[str, Any]) -> bool:
        """モデルがプロバイダーフィルターに一致するかチェック"""
        if not self.current_settings.selected_providers:
            return False

        if "web_api" in self.current_settings.selected_providers:
            if not model["is_local"]:
                return True

        if "local" in self.current_settings.selected_providers:
            if model["is_local"]:
                return True

        return False

    def _model_matches_function_filter(self, model: dict[str, Any]) -> bool:
        """モデルが機能フィルターに一致するかチェック"""
        if not self.current_settings.selected_function_types:
            return False

        model_capabilities = model.get("capabilities", [])
        return any(func in model_capabilities for func in self.current_settings.selected_function_types)

    def _update_model_table(self) -> None:
        """モデルテーブルを更新"""
        try:
            # テーブルクリア
            self.tableWidgetModels.setRowCount(0)

            # フィルタされたモデルを追加
            for row, model in enumerate(self.filtered_models):
                self.tableWidgetModels.insertRow(row)

                # チェックボックス列（選択）
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)  # デフォルト未選択
                self.tableWidgetModels.setItem(row, 0, checkbox_item)

                # モデル名列
                name_item = QTableWidgetItem(model["name"])
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 1, name_item)

                # プロバイダー列
                provider_display = "ローカル" if model["is_local"] else model["provider"].title()
                provider_item = QTableWidgetItem(provider_display)
                provider_item.setFlags(provider_item.flags() & ~QTableWidgetItem.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 2, provider_item)

                # 機能列
                capabilities_text = ", ".join(model.get("capabilities", []))
                capability_item = QTableWidgetItem(capabilities_text)
                capability_item.setFlags(capability_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tableWidgetModels.setItem(row, 3, capability_item)

            logger.debug(f"Model table updated with {len(self.filtered_models)} models")

        except Exception as e:
            logger.error(f"Error updating model table: {e}")

    def _get_selected_models(self) -> list[str]:
        """選択されたモデル名のリストを取得"""
        selected_models = []

        try:
            for row in range(self.tableWidgetModels.rowCount()):
                checkbox_item = self.tableWidgetModels.item(row, 0)
                if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:  # Checked
                    model_name_item = self.tableWidgetModels.item(row, 1)
                    if model_name_item:
                        selected_models.append(model_name_item.text())

        except Exception as e:
            logger.error(f"Error getting selected models: {e}")

        return selected_models

    def get_current_settings(self) -> AnnotationSettings:
        """現在の設定を取得"""
        self._update_current_settings()
        return self.current_settings

    def set_enabled_state(self, enabled: bool) -> None:
        """ウィジェット全体の有効/無効状態を設定"""
        # チェックボックス群
        checkboxes = [
            self.checkBoxCaption,
            self.checkBoxTagger,
            self.checkBoxScorer,
            self.checkBoxWebAPI,
            self.checkBoxLocal,
            self.checkBoxLowResolution,
            self.checkBoxBatchMode,
        ]
        for checkbox in checkboxes:
            checkbox.setEnabled(enabled)

        # テーブルと実行ボタン
        self.tableWidgetModels.setEnabled(enabled)
        self.pushButtonStart.setEnabled(enabled)

        if not enabled:
            logger.debug("AnnotationControlWidget disabled")
        else:
            logger.debug("AnnotationControlWidget enabled")
