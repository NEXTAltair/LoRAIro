"""
Annotation Control Widget (Phase 3: ModelSelectionTableWidget統合版)

複数モデル選択・実行制御機能を提供
機能タイプ・実行環境によるフィルタリングと実行制御

Phase 3変更:
- ModelSelectionTableWidgetを統合
- テーブル管理ロジックを専用ウィジェットに分離
"""

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

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

        # 現在の設定
        self.current_settings: AnnotationSettings = AnnotationSettings(
            selected_function_types=["caption", "tags", "scores"],
            selected_providers=["web_api", "local"],
            selected_models=[],
        )

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()
        self._setup_model_table_widget()

        logger.debug("AnnotationControlWidget initialized (ModelSelectionTableWidget integrated)")

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

        # ModelSelectionTableWidgetのシグナル接続（UI統合後に設定）

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定（スタイルはQt Designerで定義済み）"""
        # スタイルシートはQt Designer UIファイルで定義済み
        # 追加のプロパティ設定が必要な場合はここに記述
        pass

    def _setup_model_table_widget(self) -> None:
        """ModelSelectionTableWidgetの設定と接続"""
        try:
            # ModelSelectionTableWidgetのシグナル接続
            self.modelSelectionTable.model_selection_changed.connect(self._on_model_selection_changed)
            self.modelSelectionTable.selection_count_changed.connect(self._on_selection_count_changed)
            self.modelSelectionTable.models_loaded.connect(self._on_models_loaded)

            logger.debug("ModelSelectionTableWidget setup completed")

        except Exception as e:
            logger.error(f"Error setting up ModelSelectionTableWidget: {e}", exc_info=True)

    def set_search_filter_service(self, service: SearchFilterService) -> None:
        """SearchFilterService設定（ModelSelectionTableWidgetに委譲）"""
        self.search_filter_service = service
        # ModelSelectionTableWidgetにもサービス設定
        self.modelSelectionTable.set_search_filter_service(service)
        # モデル情報をロード
        self.modelSelectionTable.load_models()
        logger.debug("SearchFilterService set for AnnotationControlWidget and ModelSelectionTableWidget")

    @Slot(list)
    def _on_model_selection_changed(self, selected_models: list[str]) -> None:
        """ModelSelectionTableWidgetからのモデル選択変更通知"""
        self.current_settings.selected_models = selected_models
        self.settings_changed.emit(self.current_settings)
        logger.debug(f"Model selection updated: {len(selected_models)} models selected")

    @Slot(int, int)
    def _on_selection_count_changed(self, selected_count: int, total_count: int) -> None:
        """ModelSelectionTableWidgetからの選択数変更通知"""
        logger.debug(f"Selection count changed: {selected_count}/{total_count}")

    @Slot(int)
    def _on_models_loaded(self, model_count: int) -> None:
        """ModelSelectionTableWidgetからのモデル読み込み完了通知"""
        self.models_refreshed.emit(model_count)
        logger.debug(f"Models loaded notification: {model_count} models")

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

            # 選択モデル取得（ModelSelectionTableWidgetから）
            selected_models = self.modelSelectionTable.get_selected_models()

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

            # 設定変更シグナル送信（モデル選択変更以外の場合のみ）
            # モデル選択変更は_on_model_selection_changedで処理済み

        except Exception as e:
            logger.error(f"Error updating settings: {e}")

    def _apply_filters(self) -> None:
        """フィルターを適用（ModelSelectionTableWidgetに委譲）"""
        try:
            # 現在の設定取得
            self._update_current_settings()

            # ModelSelectionTableWidgetにフィルターを適用
            self.modelSelectionTable.apply_filters(
                function_types=self.current_settings.selected_function_types,
                providers=self.current_settings.selected_providers,
            )

            logger.debug("Applied filters to ModelSelectionTableWidget")

        except Exception as e:
            logger.error(f"Error applying filters: {e}", exc_info=True)

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

        # ModelSelectionTableWidgetと実行ボタン
        self.modelSelectionTable.setEnabled(enabled)
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
