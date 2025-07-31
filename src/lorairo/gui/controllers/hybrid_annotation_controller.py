"""HybridAnnotationController - アノテーション機能の統合コントローラー

MainWorkspaceWindow内でのアノテーション機能を管理:
- ModelInfoManagerと連携したモデル選択UI動的生成
- アノテーション実行制御
- 結果表示制御
- UI状態管理
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...database.db_repository import ImageRepository
from ...services.configuration_service import ConfigurationService
from ...services.model_info_manager import ModelFilterCriteria, ModelInfo, ModelInfoManager
from ...utils.log import logger
from ..widgets.annotation_results_widget import AnnotationResult, AnnotationResultsWidget


@dataclass
class AnnotationUIState:
    """アノテーション画面UI状態"""

    selected_models: list[str]
    annotation_in_progress: bool = False
    results_visible: bool = False
    filter_criteria: ModelFilterCriteria | None = None


class HybridAnnotationController(QObject):
    """HybridAnnotationController - アノテーション機能の中央制御

    機能:
    - MainWorkspaceWindow_HybridAnnotation.uiの動的ロード
    - ModelInfoManagerと連携したモデル選択UI生成
    - 選択画像DB情報表示
    - アノテーション実行・結果表示制御
    """

    # シグナル
    annotation_started = Signal(list)  # selected_models
    annotation_completed = Signal(dict)  # results
    model_selection_changed = Signal(list)  # selected_model_names
    ui_state_changed = Signal(object)  # AnnotationUIState

    def __init__(
        self, db_repository: ImageRepository, config_service: ConfigurationService, parent: QObject | None = None
    ):
        """HybridAnnotationController初期化

        Args:
            db_repository: 画像データベースリポジトリ
            config_service: 設定サービス
            parent: 親QObject
        """
        super().__init__(parent)

        self.db_repository = db_repository
        self.config_service = config_service

        # ModelInfoManager初期化
        self.model_info_manager = ModelInfoManager(
            db_repository=db_repository, config_service=config_service
        )

        # UI状態
        self.ui_state = AnnotationUIState(selected_models=[])

        # UI要素の参照
        self.hybrid_annotation_widget: QWidget | None = None
        self.model_selection_container: QScrollArea | None = None
        self.selected_image_table: QTableView | None = None
        self.annotation_results_container: QWidget | None = None

        # 結果表示ウィジェット
        self.annotation_results_widget: AnnotationResultsWidget | None = None

        # モデル選択UI要素
        self.model_checkboxes: dict[str, QCheckBox] = {}
        self.model_selection_controls: dict[str, QPushButton] = {}

        logger.info("HybridAnnotationController初期化完了")

    def load_hybrid_annotation_ui(self, ui_file_path: Path) -> QWidget:
        """HybridAnnotation UI をロードして初期化

        Args:
            ui_file_path: UIファイルのパス

        Returns:
            QWidget: ロードされたUIウィジェット
        """
        logger.debug(f"HybridAnnotation UIロード開始: {ui_file_path}")

        try:
            # UIファイルをロード
            loader = QUiLoader()
            ui_file_content = ui_file_path.read_text(encoding="utf-8")
            self.hybrid_annotation_widget = loader.load(ui_file_content)

            if not self.hybrid_annotation_widget:
                raise RuntimeError("UIファイルのロードに失敗しました")

            # UI要素の参照を取得
            self._setup_ui_references()

            # 動的UI初期化
            self._initialize_dynamic_ui()

            # アノテーション結果表示を初期化
            self._initialize_annotation_results()

            # シグナル接続
            self._connect_signals()

            logger.info("HybridAnnotation UIロード・初期化完了")
            return self.hybrid_annotation_widget

        except Exception as e:
            logger.error(f"HybridAnnotation UIロードエラー: {e}", exc_info=True)
            raise

    def _setup_ui_references(self) -> None:
        """UI要素の参照を設定"""
        if not self.hybrid_annotation_widget:
            return

        # モデル選択エリア
        self.model_selection_container = self.hybrid_annotation_widget.findChild(
            QScrollArea, "scrollAreaModelSelection"
        )

        # 選択画像DB情報テーブル
        self.selected_image_table = self.hybrid_annotation_widget.findChild(
            QTableView, "tableViewSelectedImageInfo"
        )

        # アノテーション結果表示エリア
        self.annotation_results_container = self.hybrid_annotation_widget.findChild(
            QWidget, "widgetAnnotationResults"
        )

        # 制御ボタン
        self.model_selection_controls = {
            "select_all": cast(QPushButton, self.hybrid_annotation_widget.findChild(QPushButton, "pushButtonSelectAll")),
            "deselect_all": cast(QPushButton, self.hybrid_annotation_widget.findChild(QPushButton, "pushButtonDeselectAll")),
            "recommended": cast(QPushButton, self.hybrid_annotation_widget.findChild(QPushButton, "pushButtonRecommended")),
            "execute": cast(QPushButton, self.hybrid_annotation_widget.findChild(QPushButton, "pushButtonExecuteAnnotation")),
        }

        logger.debug("UI要素参照設定完了")

    def _initialize_dynamic_ui(self) -> None:
        """動的UI要素を初期化"""
        # 選択画像DB情報テーブル設定
        self._setup_selected_image_table()

        # モデル選択UI生成
        self._generate_model_selection_ui()

        # 初期状態設定
        self._update_ui_state()

        logger.debug("動的UI初期化完了")

    def _initialize_annotation_results(self) -> None:
        """アノテーション結果表示を初期化"""
        if not self.annotation_results_container:
            logger.warning("アノテーション結果コンテナが見つかりません")
            return

        try:
            # AnnotationResultsWidget作成
            self.annotation_results_widget = AnnotationResultsWidget()

            # コンテナのレイアウトに追加
            container_layout = self.annotation_results_container.layout()
            if not container_layout:
                container_layout = QVBoxLayout(self.annotation_results_container)
                container_layout.setContentsMargins(0, 0, 0, 0)

            container_layout.addWidget(self.annotation_results_widget)

            # シグナル接続
            self.annotation_results_widget.export_requested.connect(self._on_export_results_requested)

            logger.debug("アノテーション結果表示初期化完了")

        except Exception as e:
            logger.error(f"アノテーション結果表示初期化エラー: {e}", exc_info=True)

    def _setup_selected_image_table(self) -> None:
        """選択画像DB情報テーブルを設定"""
        if not self.selected_image_table:
            return

        # テーブル設定
        self.selected_image_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.selected_image_table.setAlternatingRowColors(True)
        self.selected_image_table.setSortingEnabled(True)
        self.selected_image_table.setShowGrid(False)

        # TODO: Phase 4で実装 - 選択画像情報のモデル設定
        # self.selected_image_table.setModel(selected_image_model)

        logger.debug("選択画像DB情報テーブル設定完了")

    def _generate_model_selection_ui(self) -> None:
        """モデル選択UIを動的生成"""
        if not self.model_selection_container:
            logger.warning("モデル選択コンテナが見つかりません")
            return

        try:
            # 利用可能モデル取得
            filter_criteria = ModelFilterCriteria(only_available=True)
            available_models = self.model_info_manager.get_available_models(filter_criteria)

            if not available_models:
                self._show_no_models_message()
                return

            # モデル選択UI生成
            self._create_model_selection_widgets(available_models)

            logger.info(f"モデル選択UI生成完了: {len(available_models)}件")

        except Exception as e:
            logger.error(f"モデル選択UI生成エラー: {e}", exc_info=True)
            self._show_model_loading_error()

    def _show_no_models_message(self) -> None:
        """利用可能モデルなしメッセージ表示"""
        if not self.model_selection_container:
            return

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)

        message_label = QLabel(
            "🔧 利用可能なアノテーションモデルがありません\n\n"
            "以下を確認してください:\n"
            "• APIキーが設定されているか（OpenAI/Anthropic/Google）\n"
            "• ローカルモデルがインストールされているか\n"
            "• image-annotator-lib が正常に動作しているか\n\n"
            "設定画面でAPIキーを設定後、画面を更新してください。"
        )
        message_label.setStyleSheet("""
            color: #666; 
            font-style: italic; 
            padding: 20px; 
            font-size: 11px;
            line-height: 1.4;
            background-color: #fff8dc;
            border: 1px dashed #ffa500;
            border-radius: 4px;
        """)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setWordWrap(True)

        layout.addWidget(message_label)
        self.model_selection_container.setWidget(content_widget)

    def _show_model_loading_error(self) -> None:
        """モデル読み込みエラーメッセージ表示"""
        if not self.model_selection_container:
            return

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)

        error_label = QLabel(
            "⚠️ モデル情報の読み込みに失敗しました\n\n"
            "以下をお試しください:\n"
            "• アプリケーションの再起動\n"
            "• ログファイルの確認\n"
            "• image-annotator-lib の動作確認\n\n"
            "問題が続く場合は、サポートにお問い合わせください。"
        )
        error_label.setStyleSheet("""
            color: #d32f2f; 
            font-weight: bold;
            padding: 20px; 
            font-size: 11px;
            line-height: 1.4;
            background-color: #ffebee;
            border: 1px solid #f44336;
            border-radius: 4px;
        """)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)

        layout.addWidget(error_label)
        self.model_selection_container.setWidget(content_widget)

    def _create_model_selection_widgets(self, models: list[ModelInfo]) -> None:
        """モデル選択ウィジェット作成"""
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)

        # プロバイダー別にグループ化
        provider_groups = self._group_models_by_provider(models)

        for provider, provider_models in provider_groups.items():
            if provider_models:
                group_widget = self._create_provider_group_widget(provider, provider_models)
                main_layout.addWidget(group_widget)

        # スペーサー追加
        main_layout.addStretch()

        self.model_selection_container.setWidget(content_widget)

    def _group_models_by_provider(self, models: list[ModelInfo]) -> dict[str, list[ModelInfo]]:
        """プロバイダー別にモデルをグループ化"""
        groups: dict[str, list[ModelInfo]] = {}

        for model in models:
            provider = model["provider"] or "local"
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(model)

        return groups

    def _create_provider_group_widget(self, provider: str, models: list[ModelInfo]) -> QGroupBox:
        """プロバイダーグループウィジェット作成"""
        # プロバイダーアイコン
        provider_icons = {"openai": "🤖", "anthropic": "🧠", "google": "🌟", "local": "💻"}
        icon = provider_icons.get(provider.lower(), "🔧")

        group_box = QGroupBox(f"{icon} {provider.title()}")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold; 
                font-size: 11px;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
            }
        """)

        layout = QVBoxLayout(group_box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        # モデルチェックボックス作成
        for model in models:
            checkbox = self._create_model_checkbox(model)
            self.model_checkboxes[model["name"]] = checkbox
            layout.addWidget(checkbox)

        return group_box

    def _create_model_checkbox(self, model: ModelInfo) -> QCheckBox:
        """モデル用チェックボックス作成"""
        # 表示名作成
        display_name = model["name"]

        # 追加情報
        info_parts = []
        if model["requires_api_key"]:
            info_parts.append("API")
        if model["estimated_size_gb"]:
            info_parts.append(f"{model['estimated_size_gb']:.1f}GB")

        if info_parts:
            display_name += f" ({', '.join(info_parts)})"

        checkbox = QCheckBox(display_name)
        checkbox.setObjectName(f"checkBox_{model['name']}")

        # ツールチップ
        tooltip_parts = [
            f"プロバイダー: {model['provider']}",
            f"モデルタイプ: {model['model_type']}",
            f"APIキー必要: {'Yes' if model['requires_api_key'] else 'No'}",
        ]

        if model["api_model_id"]:
            tooltip_parts.append(f"API ID: {model['api_model_id']}")

        checkbox.setToolTip("\n".join(tooltip_parts))

        # シグナル接続
        checkbox.stateChanged.connect(self._on_model_selection_changed)

        # スタイル
        checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 10px;
                font-weight: normal;
                margin: 1px 0px;
                padding: 2px;
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
        """)

        return checkbox

    def _connect_signals(self) -> None:
        """シグナル接続"""
        # 制御ボタンのシグナル接続
        if self.model_selection_controls.get("select_all"):
            self.model_selection_controls["select_all"].clicked.connect(self._select_all_models)

        if self.model_selection_controls.get("deselect_all"):
            self.model_selection_controls["deselect_all"].clicked.connect(self._deselect_all_models)

        if self.model_selection_controls.get("recommended"):
            self.model_selection_controls["recommended"].clicked.connect(self._select_recommended_models)

        if self.model_selection_controls.get("execute"):
            self.model_selection_controls["execute"].clicked.connect(self._execute_annotation)

        logger.debug("シグナル接続完了")

    def _update_ui_state(self) -> None:
        """UI状態を更新"""
        # 選択モデル数を更新
        selected_count = len(self.ui_state.selected_models)

        # 実行ボタンの有効/無効
        if self.model_selection_controls.get("execute"):
            self.model_selection_controls["execute"].setEnabled(
                selected_count > 0 and not self.ui_state.annotation_in_progress
            )

        # 状態変更シグナル送信
        self.ui_state_changed.emit(self.ui_state)

        logger.debug(f"UI状態更新: 選択モデル数={selected_count}")

    @Slot()
    def _on_model_selection_changed(self) -> None:
        """モデル選択変更時の処理"""
        # 選択されたモデル名を更新
        selected_models = []
        for model_name, checkbox in self.model_checkboxes.items():
            if checkbox.isChecked():
                selected_models.append(model_name)

        self.ui_state.selected_models = selected_models
        self._update_ui_state()

        # シグナル送信
        self.model_selection_changed.emit(selected_models)

    @Slot()
    def _select_all_models(self) -> None:
        """全モデル選択"""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(True)
        logger.debug("全モデル選択実行")

    @Slot()
    def _deselect_all_models(self) -> None:
        """全モデル選択解除"""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(False)
        logger.debug("全モデル選択解除実行")

    @Slot()
    def _select_recommended_models(self) -> None:
        """推奨モデル選択"""
        # ModelInfoManagerから推奨モデル判定情報を取得
        filter_criteria = ModelFilterCriteria(only_available=True)
        available_models = self.model_info_manager.get_available_models(filter_criteria)

        # 推奨モデル名のセット作成
        recommended_names = {
            model["name"] for model in available_models if self._is_recommended_model(model["name"])
        }

        # チェックボックス更新
        for model_name, checkbox in self.model_checkboxes.items():
            checkbox.setChecked(model_name in recommended_names)

        logger.debug(f"推奨モデル選択実行: {len(recommended_names)}件")

    def _is_recommended_model(self, model_name: str) -> bool:
        """推奨モデル判定"""
        name_lower = model_name.lower()

        # 高品質推奨モデルのパターン
        recommended_patterns = [
            "gpt-4o",
            "claude-3-5-sonnet",
            "claude-3-sonnet",
            "gemini-pro",
            "wd-v1-4",
            "wd-tagger",
            "deepdanbooru",
            "wd-swinv2",
            "clip-aesthetic",
            "musiq",
            "aesthetic-scorer",
        ]

        return any(pattern in name_lower for pattern in recommended_patterns)

    @Slot()
    def _execute_annotation(self) -> None:
        """アノテーション実行"""
        if not self.ui_state.selected_models:
            logger.warning("アノテーション実行: モデルが選択されていません")
            return

        if self.ui_state.annotation_in_progress:
            logger.warning("アノテーション実行: 既に実行中です")
            return

        try:
            # 実行状態に変更
            self.ui_state.annotation_in_progress = True
            self._update_ui_state()

            # シグナル送信
            self.annotation_started.emit(self.ui_state.selected_models.copy())

            logger.info(f"アノテーション実行開始: {len(self.ui_state.selected_models)}モデル")

            # TODO: Phase 4で実装 - 実際のアノテーション処理
            # await self.annotation_service.execute_annotation(self.ui_state.selected_models)

        except Exception as e:
            logger.error(f"アノテーション実行エラー: {e}", exc_info=True)
            self.ui_state.annotation_in_progress = False
            self._update_ui_state()

    def refresh_model_selection(self) -> None:
        """モデル選択UIの再構築"""
        logger.debug("モデル選択UI再構築開始")

        try:
            # チェックボックスクリア
            for checkbox in self.model_checkboxes.values():
                checkbox.setParent(None)
                checkbox.deleteLater()
            self.model_checkboxes.clear()

            # UI再生成
            self._generate_model_selection_ui()

            logger.info("モデル選択UI再構築完了")

        except Exception as e:
            logger.error(f"モデル選択UI再構築エラー: {e}", exc_info=True)

    def get_model_info_manager(self) -> ModelInfoManager:
        """ModelInfoManagerの参照を取得"""
        return self.model_info_manager

    def get_ui_state(self) -> AnnotationUIState:
        """現在のUI状態を取得"""
        return self.ui_state

    # アノテーション結果表示関連メソッド

    def add_annotation_result(self, result: AnnotationResult) -> None:
        """アノテーション結果を追加表示"""
        if self.annotation_results_widget:
            self.annotation_results_widget.add_result(result)

            # UI状態更新
            self.ui_state.results_visible = True
            self._update_ui_state()

            logger.debug(f"アノテーション結果追加表示: {result.model_name}")

    def clear_annotation_results(self) -> None:
        """アノテーション結果をクリア"""
        if self.annotation_results_widget:
            self.annotation_results_widget.clear_results()

            # UI状態更新
            self.ui_state.results_visible = False
            self._update_ui_state()

            logger.debug("アノテーション結果クリア")

    def get_annotation_results_summary(self) -> dict[str, Any]:
        """アノテーション結果サマリーを取得"""
        if self.annotation_results_widget:
            return self.annotation_results_widget.get_results_summary()
        return {}

    @Slot(list)
    def _on_export_results_requested(self, results: list[AnnotationResult]) -> None:
        """結果エクスポート要求の処理"""
        try:
            logger.info(f"アノテーション結果エクスポート要求: {len(results)}件")

            # TODO: Phase 4で実装 - 実際のエクスポート処理
            # export_service.export_annotation_results(results)

        except Exception as e:
            logger.error(f"結果エクスポート処理エラー: {e}", exc_info=True)

    # デモ用メソッド（Phase 4で削除）

    def _simulate_annotation_result(self, model_name: str, success: bool = True) -> None:
        """アノテーション結果のシミュレーション（デモ用）"""
        import random
        from datetime import datetime

        if success:
            result = AnnotationResult(
                model_name=model_name,
                success=True,
                processing_time=random.uniform(1.0, 5.0),
                content="Simulated content for " + model_name, # Add content field
                timestamp=datetime.now(),
            )
        else:
            result = AnnotationResult(
                model_name=model_name,
                success=False,
                processing_time=random.uniform(0.5, 2.0),
                error_message=f"API connection failed for {model_name}",
                function_type="unknown", # Add function_type
                content="", # Add content
                timestamp=datetime.now(),
            )

        self.add_annotation_result(result)

    def demo_show_annotation_results(self) -> None:
        """アノテーション結果表示デモ（開発用）"""
        logger.info("アノテーション結果表示デモ開始")

        # 複数モデルの結果をシミュレート
        demo_models = ["gpt-4o", "claude-3-5-sonnet", "wd-v1-4-tagger", "aesthetic-predictor"]

        for i, model_name in enumerate(demo_models):
            # 最後のモデルはエラーにする
            success = i < len(demo_models) - 1
            self._simulate_annotation_result(model_name, success)

        logger.info("アノテーション結果表示デモ完了")
