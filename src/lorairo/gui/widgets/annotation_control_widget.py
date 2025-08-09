"""
Annotation Control Widget (Phase 2: UI専用・責任分離版)

複数モデル選択・実行制御機能を提供
機能タイプ・実行環境によるフィルタリングと実行制御

Phase 2変更:
- SearchFilterService依存注入パターン継承（Phase 1）
- ビジネスロジックをSearchFilterServiceに移行
- UI専用処理に軽量化

# TODO: レイアウトの調整はまた今度やる｡ 2025-08-03
"""

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ...gui.designer.AnnotationControlWidget_ui import Ui_AnnotationControlWidget
from ...utils.log import logger
from ..services.search_filter_service import SearchFilterService


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
    ):
        super().__init__(parent)
        self.setupUi(self)  # type: ignore

        # 依存関係（Phase 1パターン継承）
        self.search_filter_service: SearchFilterService | None = None

        # モデル情報（UI表示用）
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

        logger.debug("AnnotationControlWidget initialized (UI-only)")

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
        # TODO: レイアウトの定義はQtデザイナーで 2025-08-03
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
        # TODO: 別ウィジェットにしてQtデザイナーで作成する 2025-08-03
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

    def set_search_filter_service(self, service: SearchFilterService) -> None:
        """Phase 1パターン継承：SearchFilterService設定"""
        self.search_filter_service = service
        # サービス設定後、モデル情報を再ロード
        self.load_models()
        logger.debug("SearchFilterService set for AnnotationControlWidget")


    def load_models(self) -> None:
        """モデル情報を取得（SearchFilterService経由）"""
        if self.search_filter_service:
            # Phase 1パターン：SearchFilterService経由でモデル取得
            try:
                self.all_models = self.search_filter_service.get_annotation_models_list()
                logger.info(f"Loaded {len(self.all_models)} models via SearchFilterService")

                # フィルタリングしてテーブル更新
                self._apply_filters()
                self.models_refreshed.emit(len(self.all_models))

            except Exception as e:
                logger.error(f"Failed to load models via SearchFilterService: {e}")
                self.all_models = []

        elif self.annotator_adapter:
            # 後方互換性：直接AnnotatorLibAdapter使用（非推奨）
            logger.warning("Using AnnotatorLibAdapter directly (deprecated, use SearchFilterService)")
            try:
                models_metadata = self.annotator_adapter.get_available_models_with_metadata()

                # 簡易変換（機能推定なし）
                self.all_models = []
                for model_data in models_metadata:
                    model_info = {
                        "name": model_data.get("name", ""),
                        "provider": model_data.get("provider", "unknown"),
                        "capabilities": ["caption"],  # デフォルト
                        "requires_api_key": model_data.get("requires_api_key", False),
                        "is_local": model_data.get("provider", "").lower() == "local",
                        "estimated_size_gb": model_data.get("estimated_size_gb"),
                    }
                    self.all_models.append(model_info)

                logger.info(f"Loaded {len(self.all_models)} models from AnnotatorLibAdapter (direct)")
                self._apply_filters()
                self.models_refreshed.emit(len(self.all_models))

            except Exception as e:
                logger.error(f"Failed to load models: {e}", exc_info=True)
                self.all_models = []
        else:
            logger.warning("Neither SearchFilterService nor AnnotatorLibAdapter available")
            self.all_models = []

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
        """実行ボタンクリック時の処理（SearchFilterService経由検証）"""
        try:
            self._update_current_settings()

            if self.search_filter_service:
                # Phase 1パターン：SearchFilterService経由で設定検証
                settings_dict = {
                    "selected_models": self.current_settings.selected_models,
                    "selected_function_types": self.current_settings.selected_function_types,
                    "selected_providers": self.current_settings.selected_providers,
                    "use_low_resolution": self.current_settings.use_low_resolution,
                    "batch_mode": self.current_settings.batch_mode,
                }

                validation_result = self.search_filter_service.validate_annotation_settings(settings_dict)

                if not validation_result.is_valid:
                    logger.warning(f"Settings validation failed: {validation_result.error_message}")
                    return

                logger.info("Settings validated via SearchFilterService")
            else:
                # フォールバック：直接検証（非推奨）
                if not self.current_settings.selected_models:
                    logger.warning("No models selected for annotation")
                    return

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
        """フィルターを適用してテーブル更新（SearchFilterService経由）"""
        try:
            # 現在の設定取得
            self._update_current_settings()

            if self.search_filter_service:
                # Phase 1パターン：SearchFilterService経由でフィルタリング
                self.filtered_models = self.search_filter_service.filter_models_by_criteria(
                    models=self.all_models,
                    function_types=self.current_settings.selected_function_types,
                    providers=self.current_settings.selected_providers,
                )
            else:
                # フォールバック：直接フィルタリング（非推奨）
                self.filtered_models = []
                for model in self.all_models:
                    # プロバイダーフィルター
                    if not self._model_matches_provider_filter(model):
                        continue

                    # 機能フィルター
                    if not self._model_matches_function_filter(model):
                        continue

                    self.filtered_models.append(model)

            # テーブル更新（UI専用処理）
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
                provider_item.setFlags(provider_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
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


if __name__ == "__main__":
    import sys
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    # ログ設定の初期化
    logconf = {"level": "DEBUG", "file": "AnnotationControlWidget.log"}
    initialize_logging(logconf)

    # テスト用のアプリケーション
    app = QApplication(sys.argv)

    # メインウィンドウ作成
    main_window = QMainWindow()
    main_window.setWindowTitle("AnnotationControlWidget テスト - Windows表示確認")
    main_window.resize(800, 600)

    # AnnotationControlWidgetウィジェット作成
    annotation_widget = AnnotationControlWidget()

    # モックSearchFilterService設定
    mock_service = Mock()

    # ダミーモデルデータ
    dummy_models: list[dict[str, Any]] = [
        {
            "name": "gpt-4-vision-preview",
            "provider": "openai",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
            "estimated_size_gb": None,
        },
        {
            "name": "wd-v1-4-swinv2-tagger-v3",
            "provider": "local",
            "capabilities": ["tags"],
            "requires_api_key": False,
            "is_local": True,
            "estimated_size_gb": 1.2,
        },
        {
            "name": "clip-aesthetic-score",
            "provider": "local",
            "capabilities": ["scores"],
            "requires_api_key": False,
            "is_local": True,
            "estimated_size_gb": 0.5,
        },
        {
            "name": "claude-3-sonnet",
            "provider": "anthropic",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
            "estimated_size_gb": None,
        },
        {
            "name": "blip2-opt-2.7b",
            "provider": "local",
            "capabilities": ["caption"],
            "requires_api_key": False,
            "is_local": True,
            "estimated_size_gb": 5.4,
        },
    ]

    # モックサービスの動作設定
    mock_service.get_annotation_models_list.return_value = dummy_models

    def mock_filter_models(
        models: list[dict[str, Any]], function_types: list[str], providers: list[str]
    ) -> list[dict[str, Any]]:
        return [
            model
            for model in models
            if any(func in model["capabilities"] for func in function_types)
            and any(
                (provider == "web_api" and not model["is_local"])
                or (provider == "local" and model["is_local"])
                for provider in providers
            )
        ]

    mock_service.filter_models_by_criteria.side_effect = mock_filter_models
    mock_service.validate_annotation_settings.return_value = Mock(
        is_valid=True, settings={}, error_message=None
    )

    # SearchFilterService設定
    annotation_widget.set_search_filter_service(mock_service)

    # シグナル接続（テスト用）
    def on_annotation_started(settings: AnnotationSettings) -> None:
        print(f"アノテーション開始: {settings}")

    def on_settings_changed(settings: AnnotationSettings) -> None:
        print(f"設定変更: {settings}")

    def on_models_refreshed(count: int) -> None:
        print(f"モデル一覧更新完了: {count}件")

    annotation_widget.annotation_started.connect(on_annotation_started)
    annotation_widget.settings_changed.connect(on_settings_changed)
    annotation_widget.models_refreshed.connect(on_models_refreshed)

    # ウィジェットをメインウィンドウに設定
    main_window.setCentralWidget(annotation_widget)

    # ウィンドウ表示
    main_window.show()

    print("AnnotationControlWidget Windows表示テスト起動")
    print("テスト項目:")
    print("- チェックボックス操作（Caption/Tags/Scores、Web API/Local）")
    print("- モデル選択テーブルの表示・フィルタリング")
    print("- 実行ボタンの動作確認")
    print("- UI全体のレスポンシブ動作")

    # アプリケーション実行
    sys.exit(app.exec())
