# tests/unit/gui/widgets/test_model_checkbox_widget.py

import pytest
from PySide6.QtCore import Qt

from lorairo.gui.widgets.model_checkbox_widget import PROVIDER_STYLES, ModelCheckboxWidget, ModelInfo


class TestModelCheckboxWidget:
    """ModelCheckboxWidget単体テスト"""

    @pytest.fixture
    def openai_model_info(self):
        """OpenAIモデル情報フィクスチャ"""
        return ModelInfo(
            name="gpt-4-vision-preview",
            provider="openai",
            capabilities=["caption", "tags"],
            is_local=False,
            requires_api_key=True,
        )

    @pytest.fixture
    def local_model_info(self):
        """ローカルモデル情報フィクスチャ"""
        return ModelInfo(
            name="wd-v1-4-swin-v2-tagger-v3",
            provider="local",
            capabilities=["tags"],
            is_local=True,
            requires_api_key=False,
        )

    @pytest.fixture
    def anthropic_model_info(self):
        """Anthropicモデル情報フィクスチャ"""
        return ModelInfo(
            name="claude-3-sonnet",
            provider="anthropic",
            capabilities=["caption", "tags", "analysis"],
            is_local=False,
            requires_api_key=True,
        )

    @pytest.fixture
    def google_model_info(self):
        """Googleモデル情報フィクスチャ"""
        return ModelInfo(
            name="gemini-pro-vision",
            provider="google",
            capabilities=["caption", "tags", "scores"],
            is_local=False,
            requires_api_key=True,
        )

    @pytest.fixture
    def widget_openai(self, qtbot, openai_model_info):
        """OpenAI用ウィジェット"""
        widget = ModelCheckboxWidget(openai_model_info)
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def widget_local(self, qtbot, local_model_info):
        """ローカルモデル用ウィジェット"""
        widget = ModelCheckboxWidget(local_model_info)
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget_openai, openai_model_info):
        """初期化テスト"""
        assert widget_openai.model_info == openai_model_info
        assert hasattr(widget_openai, "checkboxModel")
        assert hasattr(widget_openai, "labelModelName")
        assert hasattr(widget_openai, "labelProvider")
        assert hasattr(widget_openai, "labelCapabilities")

    def test_model_name_display(self, widget_openai):
        """モデル名表示テスト"""
        assert widget_openai.labelModelName.text() == "gpt-4-vision-preview"

    def test_provider_display_openai(self, widget_openai):
        """OpenAIプロバイダー表示テスト"""
        assert widget_openai.labelProvider.text() == "Openai"

    def test_provider_display_local(self, widget_local):
        """ローカルプロバイダー表示テスト"""
        assert widget_local.labelProvider.text() == "ローカル"

    def test_capabilities_display_truncation(self, qtbot, google_model_info):
        """機能表示の切り詰めテスト（3つ以上の場合）"""
        widget = ModelCheckboxWidget(google_model_info)
        qtbot.addWidget(widget)

        # 3つ以上の機能がある場合、最大2つ+...で表示
        capabilities_text = widget.labelCapabilities.text()
        assert "..." in capabilities_text
        # 最初の2つの機能が含まれている
        assert "caption" in capabilities_text or "tags" in capabilities_text

    def test_capabilities_display_no_truncation(self, widget_openai):
        """機能表示の切り詰めなしテスト（2つ以下）"""
        capabilities_text = widget_openai.labelCapabilities.text()
        assert "..." not in capabilities_text
        assert "caption" in capabilities_text
        assert "tags" in capabilities_text

    def test_provider_styling_openai(self, widget_openai):
        """OpenAI用スタイリング適用テスト"""
        style = widget_openai.labelProvider.styleSheet()
        # OpenAI用のボーダーカラーとパレット参照が適用されている
        assert "#2196F3" in style  # OpenAI border
        assert "palette(button)" in style  # System-adaptive background
        assert "palette(button-text)" in style  # System-adaptive text

    def test_provider_styling_local(self, widget_local):
        """ローカルモデル用スタイリング適用テスト"""
        style = widget_local.labelProvider.styleSheet()
        # ローカル用のボーダーカラーとパレット参照が適用されている
        assert "#4CAF50" in style  # Local border
        assert "palette(button)" in style  # System-adaptive background
        assert "palette(button-text)" in style  # System-adaptive text

    def test_provider_styling_anthropic(self, qtbot, anthropic_model_info):
        """Anthropic用スタイリング適用テスト"""
        widget = ModelCheckboxWidget(anthropic_model_info)
        qtbot.addWidget(widget)

        style = widget.labelProvider.styleSheet()
        assert "#FF9800" in style  # Anthropic border
        assert "palette(button)" in style  # System-adaptive background
        assert "palette(button-text)" in style  # System-adaptive text

    def test_provider_styling_google(self, qtbot, google_model_info):
        """Google用スタイリング適用テスト"""
        widget = ModelCheckboxWidget(google_model_info)
        qtbot.addWidget(widget)

        style = widget.labelProvider.styleSheet()
        assert "#9C27B0" in style  # Google border
        assert "palette(button)" in style  # System-adaptive background
        assert "palette(button-text)" in style  # System-adaptive text

    def test_provider_styling_unknown_provider(self, qtbot):
        """未知のプロバイダー用デフォルトスタイリングテスト"""
        unknown_model = ModelInfo(
            name="unknown-model",
            provider="unknown",
            capabilities=["test"],
            is_local=False,
            requires_api_key=True,
        )
        widget = ModelCheckboxWidget(unknown_model)
        qtbot.addWidget(widget)

        style = widget.labelProvider.styleSheet()
        # デフォルトスタイルが適用されている
        assert "palette(mid)" in style  # Default border with system palette
        assert "palette(button)" in style  # System-adaptive background
        assert "palette(button-text)" in style  # System-adaptive text

    def test_dynamic_property_set(self, widget_openai):
        """Dynamic Property設定テスト（将来的なQSS対応）"""
        provider_property = widget_openai.labelProvider.property("provider")
        assert provider_property == "openai"

    def test_checkbox_initial_state(self, widget_openai):
        """チェックボックス初期状態テスト"""
        assert widget_openai.is_selected() is False
        assert widget_openai.checkboxModel.isChecked() is False

    def test_set_selected_true(self, widget_openai):
        """選択状態設定テスト（True）"""
        widget_openai.set_selected(True)
        assert widget_openai.is_selected() is True
        assert widget_openai.checkboxModel.isChecked() is True

    def test_set_selected_false(self, widget_openai):
        """選択状態設定テスト（False）"""
        widget_openai.set_selected(True)
        widget_openai.set_selected(False)
        assert widget_openai.is_selected() is False
        assert widget_openai.checkboxModel.isChecked() is False

    def test_selection_changed_signal_on_check(self, widget_openai, qtbot):
        """チェック時のシグナル発火テスト"""
        # 初期状態を確認
        assert widget_openai.checkboxModel.isChecked() is False

        with qtbot.waitSignal(widget_openai.selection_changed, timeout=1000) as blocker:
            # Qt.CheckState.Checked (2) を明示的に設定
            widget_openai.checkboxModel.setCheckState(Qt.CheckState.Checked)

        # シグナルの引数確認
        assert blocker.args == ["gpt-4-vision-preview", True]

    def test_selection_changed_signal_on_uncheck(self, widget_openai, qtbot):
        """チェック解除時のシグナル発火テスト"""
        widget_openai.checkboxModel.setChecked(True)

        with qtbot.waitSignal(widget_openai.selection_changed, timeout=1000) as blocker:
            widget_openai.checkboxModel.setChecked(False)

        # シグナルの引数確認
        assert blocker.args == ["gpt-4-vision-preview", False]

    def test_set_selected_blocks_signal(self, widget_openai, qtbot):
        """set_selected()はシグナルをブロックすることを確認"""
        signal_emitted = False

        def on_signal(*args):
            nonlocal signal_emitted
            signal_emitted = True

        widget_openai.selection_changed.connect(on_signal)

        # set_selected()ではシグナルが発火しない
        widget_openai.set_selected(True)
        qtbot.wait(100)  # 少し待機
        assert signal_emitted is False

        # 直接チェックボックスを操作するとシグナルが発火
        widget_openai.checkboxModel.setChecked(False)
        qtbot.wait(100)
        assert signal_emitted is True

    def test_get_model_name(self, widget_openai):
        """モデル名取得テスト"""
        assert widget_openai.get_model_name() == "gpt-4-vision-preview"

    def test_get_model_info(self, widget_openai, openai_model_info):
        """モデル情報取得テスト"""
        assert widget_openai.get_model_info() == openai_model_info


class TestProviderStylesConstant:
    """PROVIDER_STYLES定数のテスト"""

    def test_all_providers_defined(self):
        """全プロバイダーのスタイルが定義されていることを確認"""
        required_providers = ["local", "openai", "anthropic", "google", "default"]
        for provider in required_providers:
            assert provider in PROVIDER_STYLES

    def test_styles_are_valid_qss(self):
        """スタイル文字列が有効なQSS形式であることを確認"""
        for provider, style in PROVIDER_STYLES.items():
            # 基本的なQSS構文チェック
            assert "QLabel" in style
            assert "{" in style
            assert "}" in style
            assert "background-color" in style
            assert "color" in style

    def test_styles_contain_required_properties(self):
        """各スタイルに必須プロパティが含まれることを確認"""
        required_properties = [
            "background-color",
            "color",
            "border",
            "border-radius",
            "padding",
            "font-weight",
        ]

        for provider, style in PROVIDER_STYLES.items():
            for prop in required_properties:
                assert prop in style, f"{provider} style missing {prop}"
