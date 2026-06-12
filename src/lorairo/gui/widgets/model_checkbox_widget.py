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

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QLabel, QWidget

from ...gui.designer.ModelCheckboxWidget_ui import Ui_ModelCheckboxWidget
from ...utils.log import logger


@dataclass
class ModelInfo:
    """モデル情報データクラス

    Issue #245 / ADR 0023 Phase 1.11: `name` は表示用 (`Model.name`、非 UNIQUE)、
    `litellm_model_id` は registry/route 判別キー (`Model.litellm_model_id`、UNIQUE)。
    同 `name` で `provider` が異なる行 (migration 経由 OpenRouter vs 新規 sync 直接版)
    が共存しうるため、内部キーは `litellm_model_id` を使うこと。

    Issue #241/#343: 同一モデルが direct / openrouter 経路で別エントリ登録される
    仕様に対し、UI 表示は preferred route の 1 行に畳む。``route`` は preferred
    の経路 ("direct" / "openrouter")、``alternatives`` は同一 canonical key の
    代替 route の litellm_model_id 群。OpenRouter は実行経路なので primary label
    には出さず、tooltip に raw ID と route 情報を載せる。

    Issue #755: ``available`` は API キー設定状況による実行可否
    (``DisplayModelOption.available`` 由来)。False の WebAPI モデルは
    ``○ needs key`` ステータスで可視化する (非表示にしない)。
    """

    name: str
    provider: str
    capabilities: list[str]
    litellm_model_id: str
    is_local: bool = False
    requires_api_key: bool = True
    route: str = "direct"
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    available: bool = True


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

# Issue #755: Wireframes v11 のモデルステータス表現 (● installed / ● API ready / ○ needs key)
STATUS_INSTALLED = "● installed"
STATUS_API_READY = "● API ready"
STATUS_NEEDS_KEY = "○ needs key"
_STATUS_READY_STYLE = "QLabel { color: #2E7D32; }"
_STATUS_NEEDS_KEY_STYLE = "QLabel { color: #E65100; }"
_NEEDS_KEY_TOOLTIP = "API キー未設定のため実行できません。⚙ 設定の該当プロバイダ欄でキーを保存すると ● API ready になります。"


class ModelCheckboxWidget(QWidget, Ui_ModelCheckboxWidget):
    """
    モデル選択チェックボックスウィジェット

    機能:
    - 個別モデルのチェックボックス表示
    - モデル情報の視覚的表示（名前、プロバイダー、機能）
    - チェック状態変更の通知
    - プロバイダー別スタイリング
    """

    # シグナル定義 (Issue #245: 引数は litellm_model_id、is_selected)
    selection_changed = Signal(str, bool)  # litellm_model_id, is_selected

    def __init__(self, model_info: ModelInfo, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)  # Multi-inheritance pattern

        # モデル情報保存
        self.model_info = model_info

        # Issue #755: ステータスラベル (.ui には無いためプログラム的に追加)
        self.labelStatus = QLabel(self)
        self.labelStatus.setObjectName("labelStatus")
        self.mainLayout.addWidget(self.labelStatus)

        # UI初期化
        self._setup_model_display()
        self._setup_connections()

    def _setup_model_display(self) -> None:
        """モデル情報をUIに表示

        Issue #245: 同じ表示名 `Model.name` を持つ行が異なる `provider`/family で
        共存しうるため、ラベル末尾に `(provider)` を併記する。

        Issue #343: direct/openrouter は execution route metadata であり annotation
        capability ではないため、primary label には ``[openrouter]`` を出さない。
        raw ``litellm_model_id`` と route/via 情報は tooltip に載せる。
        """
        try:
            # モデル名設定 (provider/family 併記)
            base_label = f"{self.model_info.name} ({self.model_info.provider})"
            self.labelModelName.setText(base_label)

            # tooltip: raw litellm_model_id + route/via + alternatives
            tooltip_lines = [
                f"Model ID: {self.model_info.litellm_model_id}",
                f"Route: {self._format_route_tooltip(self.model_info.route)}",
            ]
            for alt_id in self.model_info.alternatives:
                tooltip_lines.append(f"Alternative: {alt_id}")
            self.labelModelName.setToolTip("\n".join(tooltip_lines))

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

            # Issue #755: ステータス表示 (● installed / ● API ready / ○ needs key)
            self._update_status_display()

        except Exception as e:
            logger.error(f"Error setting up model display for {self.model_info.name}: {e}", exc_info=True)

    def _update_status_display(self) -> None:
        """API キー設定状況に応じたモデルステータスを表示する (Issue #755)。

        Wireframes v11: キー未設定の WebAPI モデルは非表示にせず ``○ needs key``
        で可視化し、⚙ 設定での解消を tooltip で案内する。
        """
        if self.model_info.is_local:
            self.labelStatus.setText(STATUS_INSTALLED)
            self.labelStatus.setStyleSheet(_STATUS_READY_STYLE)
            self.labelStatus.setToolTip("")
        elif self.model_info.available:
            self.labelStatus.setText(STATUS_API_READY)
            self.labelStatus.setStyleSheet(_STATUS_READY_STYLE)
            self.labelStatus.setToolTip("")
        else:
            self.labelStatus.setText(STATUS_NEEDS_KEY)
            self.labelStatus.setStyleSheet(_STATUS_NEEDS_KEY_STYLE)
            self.labelStatus.setToolTip(_NEEDS_KEY_TOOLTIP)

    @staticmethod
    def _format_route_tooltip(route: str) -> str:
        """tooltip 用の route/via 表記を返す。"""
        if route == "openrouter":
            return "openrouter via OpenRouter"
        return route

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

        except Exception as e:
            logger.error(f"Error applying provider styling: {e}", exc_info=True)

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # チェックボックス状態変更時の処理
        self.checkboxModel.stateChanged.connect(self._on_checkbox_changed)

    @Slot(int)
    def _on_checkbox_changed(self, state: int) -> None:
        """チェックボックス状態変更時の処理 (Issue #245: emit する文字列は litellm_model_id)"""
        try:
            # stateはint値なので、.valueで比較
            is_selected = state == Qt.CheckState.Checked.value
            self.selection_changed.emit(self.model_info.litellm_model_id, is_selected)

            logger.trace(f"Model selection changed: {self.model_info.litellm_model_id} = {is_selected}")

        except Exception as e:
            logger.error(f"Error handling checkbox change for {self.model_info.litellm_model_id}: {e}")

    def set_selected(self, selected: bool) -> None:
        """チェックボックスの選択状態を設定"""
        try:
            # シグナルを一時的にブロックして無限ループを防ぐ
            self.checkboxModel.blockSignals(True)
            self.checkboxModel.setChecked(selected)
            self.checkboxModel.blockSignals(False)

            logger.trace(f"Set {self.model_info.name} selection to: {selected}")

        except Exception as e:
            logger.error(f"Error setting selection for {self.model_info.name}: {e}")

    def is_selected(self) -> bool:
        """チェックボックスの選択状態を取得"""
        return self.checkboxModel.isChecked()

    def get_model_name(self) -> str:
        """モデルの表示名を取得 (Issue #245: 内部キーは get_model_litellm_id() を使用)"""
        return self.model_info.name

    def get_model_litellm_id(self) -> str:
        """モデルの内部キー (litellm_model_id) を取得"""
        return self.model_info.litellm_model_id

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
            litellm_model_id="openai/gpt-4-vision-preview",
            requires_api_key=True,
            is_local=False,
        ),
        ModelInfo(
            name="claude-3-sonnet",
            provider="anthropic",
            capabilities=["caption", "tags"],
            litellm_model_id="anthropic/claude-3-sonnet",
            requires_api_key=True,
            is_local=False,
        ),
        ModelInfo(
            name="wd-v1-4-swin-v2-tagger-v3",
            provider="local",
            capabilities=["tags"],
            litellm_model_id="wd-v1-4-swin-v2-tagger-v3",
            requires_api_key=False,
            is_local=True,
        ),
        ModelInfo(
            name="gemini-pro-vision",
            provider="google",
            capabilities=["caption", "tags", "scores"],
            litellm_model_id="gemini/gemini-pro-vision",
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
