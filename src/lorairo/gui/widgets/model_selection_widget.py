"""
Model Selection Widget

動的モデル選択ウィジェット - Qt Designer多重継承パターン完全対応

機能:
- Qt Designer多重継承パターン実装
- ModelCheckboxWidget分離による適切なコンポーネント化
- ModelSelectionService統合による現代的データ取得
- プロバイダー・機能タイプによるフィルタリング
- 推奨モデル自動選択
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QLabel, QWidget

# Database imports moved to conditional section for standalone compatibility
if __name__ == "__main__":
    # テスト実行時は絶対インポート使用（後でインポート）
    pass
else:
    # 通常実行時は相対インポート使用
    from ...gui.designer.ModelSelectionWidget_ui import Ui_ModelSelectionWidget
    from ...services import get_service_container
    from ...services.model_selection_service import ModelSelectionCriteria, ModelSelectionService
    from ...utils.log import logger
    from .model_checkbox_widget import ModelCheckboxWidget, ModelInfo

if TYPE_CHECKING:
    from PySide6.QtWidgets import QVBoxLayout

    from ...database.schema import Model


if not __name__ == "__main__":

    class ModelSelectionWidget(QWidget, Ui_ModelSelectionWidget):
        """
        動的モデル選択ウィジェット - Qt Designer多重継承パターン完全実装

        機能:
        - Qt Designer多重継承パターン (`class Widget(QWidget, Ui_Widget)`)
        - レイアウト定義完全排除（.ui文件で定義済み）
        - ModelCheckboxWidget分離による適切な責任分離
        - ModelSelectionService統合による現代的データ取得
        - プロバイダー・機能別フィルタリング
        """

        # シグナル定義
        model_selection_changed = Signal(list)  # selected_model_names
        selection_count_changed = Signal(int, int)  # selected_count, total_count

        # UI elements type hints (from Ui_ModelSelectionWidget via multi-inheritance)
        if TYPE_CHECKING:
            from PySide6.QtWidgets import QPushButton

            dynamicContentLayout: QVBoxLayout
            placeholderLabel: QLabel
            statusLabel: QLabel
            btnSelectAll: QPushButton
            btnDeselectAll: QPushButton
            btnSelectRecommended: QPushButton

        def __init__(
            self,
            parent: QWidget | None = None,
            model_selection_service: ModelSelectionService | None = None,
            mode: str = "simple",  # "simple" or "advanced"
        ) -> None:
            super().__init__(parent)
            self.setupUi(self)  # type: ignore  # Multi-inheritance pattern - direct setupUi call

            self.mode = mode

            # ModelSelectionService統合
            if model_selection_service:
                self.model_selection_service = model_selection_service
            else:
                self.model_selection_service = self._create_model_selection_service()

            # データ管理
            self.all_models: list[Model] = []
            self.filtered_models: list[Model] = []
            self.model_checkbox_widgets: dict[str, ModelCheckboxWidget] = {}

            # フィルタ状態
            self.current_provider_filter: str | None = None
            self.current_capability_filters: list[str] = []
            self.current_exclude_local: bool = False

            # UI初期化
            self.load_models()

            logger.debug(
                f"ModelSelectionWidget initialized in {mode} mode with Qt Designer multi-inheritance"
            )

        def _create_model_selection_service(self) -> ModelSelectionService:
            """ModelSelectionService 作成"""
            service_container = get_service_container()
            return ModelSelectionService.create(db_repository=service_container.image_repository)

        def load_models(self) -> None:
            """モデル情報をModelSelectionServiceから取得"""
            try:
                self.all_models = self.model_selection_service.load_models()
                logger.info(f"Loaded {len(self.all_models)} models via ModelSelectionService")
                self.update_model_display()

            except Exception as e:
                logger.error(f"Failed to load models: {e}")
                self.all_models = []
                self.update_model_display()

        def apply_filters(
            self,
            provider: str | None = None,
            capabilities: list[str] | None = None,
            exclude_local: bool = False,
        ) -> None:
            """フィルタリング適用

            Args:
                provider: プロバイダーフィルタ（"local", "openai" など）
                capabilities: 機能フィルタ（["caption", "tags", "scores"]）
                exclude_local: True の場合、ローカルモデルを除外（API モデルのみ表示）
            """
            self.current_provider_filter = provider
            self.current_capability_filters = capabilities or []
            self.current_exclude_local = exclude_local
            self.update_model_display()

        def update_model_display(self) -> None:
            """モデル表示更新"""
            # 現在の表示をクリア
            self._clear_model_display()

            # フィルタリング実行
            if self.mode == "simple":
                try:
                    recommended_models = self.model_selection_service.get_recommended_models()
                    self.filtered_models = recommended_models
                except Exception as e:
                    logger.error(f"Failed to get recommended models: {e}")
                    self.filtered_models = [m for m in self.all_models if m.is_recommended]
            else:
                self.filtered_models = self._apply_advanced_filters()

            # フィルタされたモデルがない場合
            if not self.filtered_models:
                self.placeholderLabel.setVisible(True)
                self._update_selection_count()
                return

            # プレースホルダーを非表示
            self.placeholderLabel.setVisible(False)

            # プロバイダー別にグループ化して表示
            provider_groups = self._group_models_by_provider()

            for provider, models in provider_groups.items():
                if models:
                    self._add_provider_group(provider, models)

            self._update_selection_count()

        def _apply_advanced_filters(self) -> list[Model]:
            """詳細モード用フィルタリング"""
            try:
                criteria = ModelSelectionCriteria(
                    provider=self.current_provider_filter
                    if self.current_provider_filter != "すべて"
                    else None,
                    capabilities=self.current_capability_filters
                    if self.current_capability_filters
                    else None,
                    only_available=True,
                    exclude_local=self.current_exclude_local,
                )

                filtered = self.model_selection_service.filter_models(criteria)
                logger.debug(f"Applied advanced filters: {len(self.all_models)} -> {len(filtered)} models")
                return filtered

            except Exception as e:
                logger.error(f"Advanced filtering error: {e}")
                return self._apply_basic_filters()

        def _apply_basic_filters(self) -> list[Model]:
            """基本フィルタリング（フォールバック用）"""
            filtered = self.all_models

            if self.current_provider_filter and self.current_provider_filter != "すべて":
                filtered = [
                    m
                    for m in filtered
                    if m.provider and m.provider.lower() == self.current_provider_filter.lower()
                ]

            if self.current_capability_filters:
                filtered = [
                    m
                    for m in filtered
                    if any(cap in m.capabilities for cap in self.current_capability_filters)
                ]

            return filtered

        def _group_models_by_provider(self) -> dict[str, list[Model]]:
            """プロバイダー別にモデルをグループ化"""
            groups: dict[str, list[Model]] = {}
            for model in self.filtered_models:
                provider = model.provider or "local"
                if provider not in groups:
                    groups[provider] = []
                groups[provider].append(model)
            return groups

        def _add_provider_group(self, provider: str, models: list[Model]) -> None:
            """プロバイダーグループをUIに追加"""
            # プロバイダーラベル
            provider_icons = {"openai": "🤖", "anthropic": "🧠", "google": "🌟", "local": "💻"}
            icon = provider_icons.get(provider.lower(), "🔧")

            provider_label = QLabel(f"{icon} {provider.title()} Models")
            provider_label.setProperty("class", "provider-group-label")

            # Qt Designer多重継承パターンでは直接アクセス
            self.dynamicContentLayout.addWidget(provider_label)

            # ModelCheckboxWidget作成と追加
            for model in models:
                model_info = self._convert_model_to_info(model)
                checkbox_widget = ModelCheckboxWidget(model_info)

                # シグナル接続
                checkbox_widget.selection_changed.connect(self._on_model_selection_changed)

                self.model_checkbox_widgets[model.name] = checkbox_widget
                self.dynamicContentLayout.addWidget(checkbox_widget)

        def _convert_model_to_info(self, model: Model) -> ModelInfo:
            """Database Model を ModelInfo に変換"""
            return ModelInfo(
                name=model.name,
                provider=model.provider or "local",
                capabilities=model.capabilities,
                is_local=not model.requires_api_key,
                requires_api_key=model.requires_api_key,
            )

        def _clear_model_display(self) -> None:
            """モデル表示をクリア"""
            # 既存のウィジェットを削除
            for widget in self.model_checkbox_widgets.values():
                widget.setParent(None)
                widget.deleteLater()

            self.model_checkbox_widgets.clear()

            # レイアウトから削除（プレースホルダーとverticalSpacer以外）
            for i in reversed(range(self.dynamicContentLayout.count())):
                item = self.dynamicContentLayout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if widget != self.placeholderLabel and widget.objectName() != "verticalSpacer":
                        self.dynamicContentLayout.removeWidget(widget)
                        widget.setParent(None)
                        widget.deleteLater()

        @Slot(str, bool)
        def _on_model_selection_changed(self, model_name: str, is_selected: bool) -> None:
            """モデル選択変更時の処理"""
            selected_models = self.get_selected_models()
            self._update_selection_count()
            self.model_selection_changed.emit(selected_models)

            logger.debug(f"Model selection changed: {model_name} = {is_selected}")

        def get_selected_models(self) -> list[str]:
            """選択されたモデル名のリストを取得"""
            selected: list[str] = []
            for model_name, widget in self.model_checkbox_widgets.items():
                if widget.is_selected():
                    selected.append(model_name)
            return selected

        def _update_selection_count(self) -> None:
            """選択数表示を更新"""
            selected_count = len(self.get_selected_models())
            total_count = len(self.filtered_models)

            if self.mode == "simple":
                self.statusLabel.setText(f"選択数: {selected_count} (推奨)")
            else:
                self.statusLabel.setText(f"選択数: {selected_count} (フィルタ後)")

            self.selection_count_changed.emit(selected_count, total_count)

        @Slot()
        def select_all_models(self) -> None:
            """全モデル選択"""
            for widget in self.model_checkbox_widgets.values():
                widget.set_selected(True)

        @Slot()
        def deselect_all_models(self) -> None:
            """全モデル選択解除"""
            for widget in self.model_checkbox_widgets.values():
                widget.set_selected(False)

        @Slot()
        def select_recommended_models(self) -> None:
            """推奨モデル選択"""
            try:
                recommended_models = self.model_selection_service.get_recommended_models()
                recommended_names = {model.name for model in recommended_models}

                for model_name, widget in self.model_checkbox_widgets.items():
                    if model_name in recommended_names:
                        widget.set_selected(True)

                logger.debug(f"Selected {len(recommended_names)} recommended models")

            except Exception as e:
                logger.error(f"Failed to select recommended models: {e}")
                # Fallback: check based on is_recommended property
                for model_name, widget in self.model_checkbox_widgets.items():
                    model = next((m for m in self.all_models if m.name == model_name), None)
                    if model and model.is_recommended:
                        widget.set_selected(True)

        def set_selected_models(self, model_names: list[str]) -> None:
            """指定されたモデルを選択状態に設定"""
            for model_name, widget in self.model_checkbox_widgets.items():
                widget.set_selected(model_name in model_names)

        def get_selection_info(self) -> dict[str, int]:
            """選択情報を取得"""
            return {
                "selected_count": len(self.get_selected_models()),
                "total_available": len(self.all_models),
                "filtered_count": len(self.filtered_models),
            }


if __name__ == "__main__":
    # 単体実行とテスト表示 - 完全な依存関係をインポート
    import os
    import sys

    # 完全な依存関係を強制インポート（テスト用）
    from pathlib import Path
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

    src_root = str(Path(__file__).parent.parent.parent)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)

    # 必要な依存関係を直接インポート（軽量版）
    try:
        # 最小限の依存関係のみ
        from lorairo.gui.designer.ModelSelectionWidget_ui import Ui_ModelSelectionWidget

        light_dependencies = True
        print("✅ 軽量依存関係読み込み成功")
    except ImportError as e:
        print(f"⚠️ 軽量依存関係不足: {e}")
        light_dependencies = False

    # より詳細な依存関係（失敗可能）
    try:
        from lorairo.gui.widgets.model_checkbox_widget import ModelCheckboxWidget, ModelInfo
        from lorairo.services import get_service_container
        from lorairo.services.model_selection_service import ModelSelectionCriteria, ModelSelectionService

        full_dependencies = True
        print("✅ 完全依存関係読み込み成功")
    except ImportError as e:
        print(f"⚠️ 完全依存関係不足: {e}")
        full_dependencies = False

    if light_dependencies:
        # Qt Designer UI クラスを直接定義（テスト用）
        class ModelSelectionWidgetTest(QWidget, Ui_ModelSelectionWidget):
            def __init__(
                self, parent: QWidget | None = None, model_selection_service=None, mode: str = "simple"
            ) -> None:
                super().__init__(parent)
                print("🔧 setupUi開始...")

                try:
                    self.setupUi(self)
                    print("✅ setupUi完了")
                except Exception as e:
                    print(f"⚠️ setupUi失敗: {e}")
                    return

                # 最小限の初期化
                self.all_models: list = []
                self.filtered_models: list = []

                # UI表示テスト
                try:
                    if hasattr(self, "statusLabel"):
                        self.statusLabel.setText("Qt Designer テストウィジェット")
                    if hasattr(self, "placeholderLabel"):
                        self.placeholderLabel.setText("UI初期化成功")
                        self.placeholderLabel.setVisible(True)
                    print("✅ UI要素初期化完了")
                except Exception as e:
                    print(f"⚠️ UI要素初期化失敗: {e}")

                print("✅ TestWidgetの初期化完了")

            def get_selected_models(self) -> list[str]:
                """選択モデル取得（テスト用）"""
                return []

            def get_selection_info(self) -> dict[str, int]:
                """選択情報取得（テスト用）"""
                return {
                    "selected_count": 0,
                    "total_available": len(self.all_models),
                    "filtered_count": len(self.filtered_models),
                }

        # Qt Designer signal-slot connection compatibility methods (test stubs)
        def select_all_models(self) -> None:
            """Test stub for select_all_models signal-slot connection"""
            print("🧪 Test stub: select_all_models called")
            pass

        def deselect_all_models(self) -> None:
            """Test stub for deselect_all_models signal-slot connection"""
            print("🧪 Test stub: deselect_all_models called")
            pass

        def select_recommended_models(self) -> None:
            """Test stub for select_recommended_models signal-slot connection"""
            print("🧪 Test stub: select_recommended_models called")
            pass

        dependencies_available = True

    else:
        print("❌ 軽量依存関係不足のためテスト不可")
        dependencies_available = False

    if dependencies_available:
        app = QApplication(sys.argv)

        # メインウィンドウ作成
        main_window = QMainWindow()
        main_window.setWindowTitle("ModelSelectionWidget Qt Designer軽量テスト")
        main_window.resize(600, 400)

        # 中央ウィジェットとレイアウト
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        # 軽量テストウィジェット作成
        print("🔧 軽量テストウィジェット作成開始...")
        selection_widget = ModelSelectionWidgetTest()
        print("✅ 軽量テストウィジェット作成完了")

        layout.addWidget(selection_widget)

        # 簡単なテストボタン
        def show_info() -> None:
            info = selection_widget.get_selection_info()
            print(f"📊 テスト情報: {info}")

        btn_test = QPushButton("テスト情報表示")
        btn_test.clicked.connect(show_info)
        layout.addWidget(btn_test)

        # ウィンドウ設定
        main_window.setCentralWidget(central_widget)
        main_window.show()

        print("🚀 ModelSelectionWidget 軽量テスト起動")
        print("📋 テスト項目:")
        print("   - Qt Designer UIファイル読み込み")
        print("   - 基本ウィジェット表示")
        print("   - レイアウト正常動作")

        # アプリケーション実行
        sys.exit(app.exec())
    else:
        print("❌ UI依存関係が不足しています。")
