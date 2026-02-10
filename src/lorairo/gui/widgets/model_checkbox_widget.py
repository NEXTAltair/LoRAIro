"""
Model Checkbox Widget

個別のモデル選択チェックボックス専用ウィジェット
ModelSelectionWidgetから分離された機能を提供

機能:
- モデル情報表示（チェックボックス/名前/プロバイダー/機能）
- チェック状態変更の通知
- プロバイダー別の視覚的識別
- 機能タグの表示
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QWidget

from ...gui.designer.ModelCheckboxWidget_ui import Ui_ModelCheckboxWidget
from ...utils.log import logger


@dataclass
class ModelInfo:
    """モデル情報データクラス"""

    name: str
    provider: str
    capabilities: list[str]
    is_local: bool = False
    requires_api_key: bool = True


# プロバイダー別スタイル定義（PySide6パレット機能でダークモード自動対応）
# palette()関数で背景色・文字色はシステム自動調整、ボーダーで視覚的区別
PROVIDER_STYLES = {
    "local": """QLabel {
        background-color: palette(button);
        color: palette(button-text);
        border: 2px solid #4CAF50;
        border-radius: 9px;
        padding: 1px 4px;
        font-weight: 500;
    }""",
    "openai": """QLabel {
        background-color: palette(button);
        color: palette(button-text);
        border: 2px solid #2196F3;
        border-radius: 9px;
        padding: 1px 4px;
        font-weight: 500;
    }""",
    "anthropic": """QLabel {
        background-color: palette(button);
        color: palette(button-text);
        border: 2px solid #FF9800;
        border-radius: 9px;
        padding: 1px 4px;
        font-weight: 500;
    }""",
    "google": """QLabel {
        background-color: palette(button);
        color: palette(button-text);
        border: 2px solid #9C27B0;
        border-radius: 9px;
        padding: 1px 4px;
        font-weight: 500;
    }""",
    "default": """QLabel {
        background-color: palette(button);
        color: palette(button-text);
        border: 2px solid palette(mid);
        border-radius: 9px;
        padding: 1px 4px;
        font-weight: 500;
    }""",
}


class ModelCheckboxWidget(QWidget, Ui_ModelCheckboxWidget):
    """
    モデル選択チェックボックスウィジェット

    機能:
    - 個別モデルのチェックボックス表示
    - モデル情報の視覚的表示（名前、プロバイダー、機能）
    - チェック状態変更の通知
    - プロバイダー別スタイリング
    """

    # シグナル定義
    selection_changed = Signal(str, bool)  # model_name, is_selected

    def __init__(self, model_info: ModelInfo, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)  # Multi-inheritance pattern

        # モデル情報保存
        self.model_info = model_info

        # UI初期化
        self._setup_model_display()
        self._setup_connections()

        logger.debug(f"ModelCheckboxWidget initialized for model: {model_info.name}")

    def _setup_model_display(self) -> None:
        """モデル情報をUIに表示"""
        try:
            # モデル名設定
            self.labelModelName.setText(self.model_info.name)

            # プロバイダー表示設定
            provider_display = "ローカル" if self.model_info.is_local else self.model_info.provider.title()
            self.labelProvider.setText(provider_display)

            # プロバイダー別スタイル適用
            self._apply_provider_styling(provider_display)

            # 機能タグ表示
            capabilities_text = ", ".join(self.model_info.capabilities[:2])  # 最大2つまで表示
            if len(self.model_info.capabilities) > 2:
                capabilities_text += "..."
            self.labelCapabilities.setText(capabilities_text)

            logger.debug(f"Model display setup completed for {self.model_info.name}")

        except Exception as e:
            logger.error(f"Error setting up model display for {self.model_info.name}: {e}", exc_info=True)

    def _apply_provider_styling(self, provider_display: str) -> None:
        """プロバイダー別スタイリング適用（辞書ベース）"""
        try:
            # プロバイダー表示名をキーに変換
            provider_key = "local" if provider_display == "ローカル" else provider_display.lower()

            # スタイル辞書から取得（存在しない場合はデフォルト）
            style = PROVIDER_STYLES.get(provider_key, PROVIDER_STYLES["default"])

            # Dynamic Property設定（将来的なQSS対応のため）
            self.labelProvider.setProperty("provider", provider_key)

            # スタイルシート適用
            self.labelProvider.setStyleSheet(style)

            logger.debug(f"Applied style for provider: {provider_key}")

        except Exception as e:
            logger.error(f"Error applying provider styling: {e}", exc_info=True)

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # チェックボックス状態変更時の処理
        self.checkboxModel.stateChanged.connect(self._on_checkbox_changed)
        logger.debug("Signal connections established")

    @Slot(int)
    def _on_checkbox_changed(self, state: int) -> None:
        """チェックボックス状態変更時の処理"""
        try:
            # stateはint値なので、.valueで比較
            is_selected = state == Qt.CheckState.Checked.value
            self.selection_changed.emit(self.model_info.name, is_selected)

            logger.debug(f"Model selection changed: {self.model_info.name} = {is_selected}")

        except Exception as e:
            logger.error(f"Error handling checkbox change for {self.model_info.name}: {e}")

    def set_selected(self, selected: bool) -> None:
        """チェックボックスの選択状態を設定"""
        try:
            # シグナルを一時的にブロックして無限ループを防ぐ
            self.checkboxModel.blockSignals(True)
            self.checkboxModel.setChecked(selected)
            self.checkboxModel.blockSignals(False)

            logger.debug(f"Set {self.model_info.name} selection to: {selected}")

        except Exception as e:
            logger.error(f"Error setting selection for {self.model_info.name}: {e}")

    def is_selected(self) -> bool:
        """チェックボックスの選択状態を取得"""
        return self.checkboxModel.isChecked()

    def get_model_name(self) -> str:
        """モデル名を取得"""
        return self.model_info.name

    def get_model_info(self) -> ModelInfo:
        """モデル情報を取得"""
        return self.model_info


if __name__ == "__main__":
    # 単体実行とテスト表示
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

    # パッケージのトップレベルから相対インポート解決
    try:
        from ...utils.log import initialize_logging
    except ImportError:
        # スタンドアローン実行用の代替パス
        from pathlib import Path

        src_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(src_root))
        from lorairo.utils.log import initialize_logging

    # ログ設定（コンソール出力）
    initialize_logging({"level": "DEBUG", "file": None})

    app = QApplication(sys.argv)

    # メインウィンドウ作成
    main_window = QMainWindow()
    main_window.setWindowTitle("ModelCheckboxWidget 単体テスト")
    main_window.resize(400, 300)

    # 中央ウィジェットとレイアウト
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)

    # テスト用モデル情報
    test_models = [
        ModelInfo(
            name="gpt-4-vision-preview",
            provider="openai",
            capabilities=["caption", "tags"],
            requires_api_key=True,
            is_local=False,
        ),
        ModelInfo(
            name="claude-3-sonnet",
            provider="anthropic",
            capabilities=["caption", "tags"],
            requires_api_key=True,
            is_local=False,
        ),
        ModelInfo(
            name="wd-v1-4-swin-v2-tagger-v3",
            provider="local",
            capabilities=["tags"],
            requires_api_key=False,
            is_local=True,
        ),
        ModelInfo(
            name="gemini-pro-vision",
            provider="google",
            capabilities=["caption", "tags", "scores"],
            requires_api_key=True,
            is_local=False,
        ),
    ]

    # ModelCheckboxWidget作成
    checkbox_widgets: list[ModelCheckboxWidget] = []
    for model_info in test_models:
        checkbox_widget = ModelCheckboxWidget(model_info)
        layout.addWidget(checkbox_widget)
        checkbox_widgets.append(checkbox_widget)

        # シグナル接続（テスト用コンソール出力）
        def on_selection_changed(model_name: str, is_selected: bool) -> None:
            print(f"🔄 Selection changed: {model_name} = {is_selected}")

        checkbox_widget.selection_changed.connect(on_selection_changed)

    # 全選択ボタン（テスト用）
    def toggle_all_selection() -> None:
        current_state: bool = checkbox_widgets[0].is_selected() if checkbox_widgets else False
        new_state = not current_state
        print(f"📋 Toggle all to: {new_state}")
        for widget in checkbox_widgets:
            widget.set_selected(new_state)

    btn_toggle = QPushButton("全選択/全解除 切り替え")
    btn_toggle.clicked.connect(toggle_all_selection)
    layout.addWidget(btn_toggle)

    # ウィンドウ設定
    main_window.setCentralWidget(central_widget)
    main_window.show()

    print("🚀 ModelCheckboxWidget 単体テスト起動")
    print("📋 テスト項目:")
    print("   - 4種類のプロバイダー表示（OpenAI/Anthropic/Google/ローカル）")
    print("   - プロバイダー別カラーリング")
    print("   - チェックボックス選択変更")
    print("   - シグナル動作確認（コンソール出力）")
    print("   - 全選択/全解除機能")
    print("💡 操作: チェックボックスや全選択ボタンをクリックしてください")

    # アプリケーション実行
    sys.exit(app.exec())
