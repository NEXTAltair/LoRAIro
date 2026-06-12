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
            litellm_model_id="openai/gpt-4-vision-preview",
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
            litellm_model_id="wd-v1-4-swin-v2-tagger-v3",
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
            litellm_model_id="anthropic/claude-3-sonnet",
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
            litellm_model_id="gemini/gemini-pro-vision",
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
        assert hasattr(widget_openai, "labelStatus")

    def test_api_model_available_shows_api_ready_status(self, widget_openai):
        """Issue #755: available な API モデルは ● API ready を表示する。"""
        assert widget_openai.labelStatus.text() == "● API ready"

    def test_local_model_shows_installed_status(self, widget_local):
        """Issue #755: ローカルモデルは ● installed を表示する。"""
        assert widget_local.labelStatus.text() == "● installed"

    def test_api_model_unavailable_shows_needs_key_status(self, qtbot):
        """Issue #755: API key 未設定の API モデルは ○ needs key を表示する。"""
        info = ModelInfo(
            name="claude-3-sonnet",
            provider="anthropic",
            capabilities=["caption"],
            litellm_model_id="anthropic/claude-3-sonnet",
            is_local=False,
            requires_api_key=True,
            available=False,
        )
        widget = ModelCheckboxWidget(info)
        qtbot.addWidget(widget)
        assert widget.labelStatus.text() == "○ needs key"
        assert "API キー未設定" in widget.labelStatus.toolTip()

    def test_model_name_display(self, widget_openai):
        """モデル名表示テスト (Issue #245: ラベルは "{name} ({provider})" 形式)"""
        assert widget_openai.labelModelName.text() == "gpt-4-vision-preview (openai)"

    def test_model_name_tooltip_is_litellm_id(self, widget_openai):
        """tooltip には正規ルーティングキー (litellm_model_id) が出る (Issue #245)"""
        assert "Model ID: openai/gpt-4-vision-preview" in widget_openai.labelModelName.toolTip()
        assert "Route: direct" in widget_openai.labelModelName.toolTip()

    def test_label_distinguishes_same_name_different_provider(self, qtbot):
        """同 name 異 provider の行が UI 上で視覚的に区別できる (Issue #245)"""
        openrouter_route = ModelInfo(
            name="openai/gpt-4o",
            provider="openrouter",
            capabilities=["caption", "tags"],
            litellm_model_id="openrouter/openai/gpt-4o",
            is_local=False,
            requires_api_key=True,
        )
        direct_route = ModelInfo(
            name="openai/gpt-4o",
            provider="openai",
            capabilities=["caption", "tags"],
            litellm_model_id="openai/gpt-4o",
            is_local=False,
            requires_api_key=True,
        )
        w_router = ModelCheckboxWidget(openrouter_route)
        w_direct = ModelCheckboxWidget(direct_route)
        qtbot.addWidget(w_router)
        qtbot.addWidget(w_direct)

        # ラベルが異なる (provider 併記)
        assert w_router.labelModelName.text() != w_direct.labelModelName.text()
        # tooltip も異なる (litellm_model_id)
        assert w_router.labelModelName.toolTip() != w_direct.labelModelName.toolTip()

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
            litellm_model_id="unknown/unknown-model",
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
        """チェック時のシグナル発火テスト (Issue #245: 第1引数は litellm_model_id)"""
        # 初期状態を確認
        assert widget_openai.checkboxModel.isChecked() is False

        with qtbot.waitSignal(widget_openai.selection_changed, timeout=1000) as blocker:
            # Qt.CheckState.Checked (2) を明示的に設定
            widget_openai.checkboxModel.setCheckState(Qt.CheckState.Checked)

        # シグナルの引数確認
        assert blocker.args == ["openai/gpt-4-vision-preview", True]

    def test_selection_changed_signal_on_uncheck(self, widget_openai, qtbot):
        """チェック解除時のシグナル発火テスト (Issue #245: 第1引数は litellm_model_id)"""
        widget_openai.checkboxModel.setChecked(True)

        with qtbot.waitSignal(widget_openai.selection_changed, timeout=1000) as blocker:
            widget_openai.checkboxModel.setChecked(False)

        # シグナルの引数確認
        assert blocker.args == ["openai/gpt-4-vision-preview", False]

    def test_set_selected_blocks_signal(self, widget_openai, qtbot):
        """set_selected()はシグナルをブロックすることを確認"""
        signal_emitted = False

        def on_signal(*args):
            nonlocal signal_emitted
            signal_emitted = True

        widget_openai.selection_changed.connect(on_signal)

        # set_selected()ではシグナルが発火しない
        widget_openai.set_selected(True)
        qtbot.waitUntil(lambda: True, timeout=100)  # 非ブロッキング待機
        assert signal_emitted is False

        # 直接チェックボックスを操作するとシグナルが発火
        widget_openai.checkboxModel.setChecked(False)
        qtbot.waitUntil(lambda: signal_emitted, timeout=1000)
        assert signal_emitted is True

    def test_get_model_name(self, widget_openai):
        """表示用モデル名取得テスト (Issue #245: get_model_name は表示名)"""
        assert widget_openai.get_model_name() == "gpt-4-vision-preview"

    def test_get_model_litellm_id(self, widget_openai):
        """内部キー取得テスト (Issue #245: 新規 API)"""
        assert widget_openai.get_model_litellm_id() == "openai/gpt-4-vision-preview"

    def test_get_model_info(self, widget_openai, openai_model_info):
        """モデル情報取得テスト"""
        assert widget_openai.get_model_info() == openai_model_info

    # --- Issue #241: route badge / alternative tooltip ---

    def test_route_badge_not_shown_for_openrouter_route(self, qtbot):
        """preferred route が openrouter の場合も primary label に route badge を出さない"""
        info = ModelInfo(
            name="claude-3-5-sonnet",
            provider="Anthropic",
            capabilities=["caption"],
            litellm_model_id="openrouter/anthropic/claude-3-5-sonnet",
            is_local=False,
            requires_api_key=True,
            route="openrouter",
        )
        widget = ModelCheckboxWidget(info)
        qtbot.addWidget(widget)
        assert widget.labelModelName.text() == "claude-3-5-sonnet (Anthropic)"
        assert "[openrouter]" not in widget.labelModelName.text()
        assert "Route: openrouter via OpenRouter" in widget.labelModelName.toolTip()

    def test_route_badge_absent_for_direct_route(self, widget_openai):
        """direct route はラベルに badge が付かない (Issue #245 の表記を維持)"""
        assert "[openrouter]" not in widget_openai.labelModelName.text()
        assert "[direct]" not in widget_openai.labelModelName.text()

    def test_alternative_tooltip_lists_alternatives(self, qtbot):
        """alternatives がある場合、tooltip に Alternative 行が追加される"""
        info = ModelInfo(
            name="claude-3-5-sonnet",
            provider="anthropic",
            capabilities=["caption"],
            litellm_model_id="anthropic/claude-3-5-sonnet-20241022",
            is_local=False,
            requires_api_key=True,
            route="direct",
            alternatives=("openrouter/anthropic/claude-3-5-sonnet-20241022",),
        )
        widget = ModelCheckboxWidget(info)
        qtbot.addWidget(widget)
        tooltip = widget.labelModelName.toolTip()
        assert "Model ID: anthropic/claude-3-5-sonnet-20241022" in tooltip
        assert "Alternative: openrouter/anthropic/claude-3-5-sonnet-20241022" in tooltip

    def test_tooltip_without_alternatives_has_model_id_and_route(self, widget_openai):
        """alternatives が空の場合も tooltip は raw ID と route を含む"""
        assert widget_openai.labelModelName.toolTip() == (
            "Model ID: openai/gpt-4-vision-preview\nRoute: direct"
        )

    def test_openrouter_raw_id_not_primary_visible_name(self, qtbot):
        """長い OpenRouter raw ID は primary visible name に使わない (Issue #343)"""
        info = ModelInfo(
            name="qwen3.7-max",
            provider="Qwen",
            capabilities=["caption"],
            litellm_model_id="openrouter/qwen/qwen3.7-max",
            is_local=False,
            requires_api_key=True,
            route="openrouter",
        )
        widget = ModelCheckboxWidget(info)
        qtbot.addWidget(widget)

        assert widget.labelModelName.text() == "qwen3.7-max (Qwen)"
        assert "openrouter/qwen/qwen3.7-max" not in widget.labelModelName.text()
        assert "Model ID: openrouter/qwen/qwen3.7-max" in widget.labelModelName.toolTip()


class TestProviderStylesConstant:
    """PROVIDER_STYLES定数のテスト"""

    def test_all_providers_defined(self):
        """全プロバイダーのスタイルが定義されていることを確認"""
        required_providers = ["local", "openai", "anthropic", "google", "default"]
        for provider in required_providers:
            assert provider in PROVIDER_STYLES

    def test_styles_are_valid_qss(self):
        """スタイル文字列が有効なQSS形式であることを確認"""
        for _provider, style in PROVIDER_STYLES.items():
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
