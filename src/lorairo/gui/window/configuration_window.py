"""設定ウィンドウ - アプリケーション設定の表示・編集・保存を行うダイアログ。

ConfigurationService と連携して、API KEY、ディレクトリ、ログ設定等を管理する。
全UIをPythonコードで構築（Qt Designer不使用）。
"""

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...services.configuration_service import ConfigurationService
from ...services.model_route_service import parse_route_preference
from ...utils.log import build_gui_log_config, initialize_logging, logger
from .. import theme
from ..message_box import show_critical
from ..widgets.directory_picker import DirectoryPickerWidget

# ログレベル選択肢
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]
# Issue #249: モデル経路の優先設定値域 (GUI 公開分)。
# "all" は CLI 専用 (--route all): 同一モデルの全 candidate を 1 行ずつ展開する用途で、
# GUI checkbox UI では preferred のみ描画する設計と整合しないため、GUI dropdown からは除外。
# CLI 経路 (--route all) と config 手動編集 ("all") の値は parse_route_preference で
# 受理し続けるが、GUI から保存できる値は auto / direct / openrouter のみ。
_ROUTE_PREFERENCES = ["auto", "direct", "openrouter"]

# Issue #755: API キー欄の定義。provider 名 (model_route_service の
# required_provider_for が返す canonical key) → (表示ラベル, config キー, objectName)。
_API_KEY_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("openai", "OpenAI API Key:", "openai_key", "lineEditOpenAiKey"),
    ("google", "Google API Key:", "google_key", "lineEditGoogleKey"),
    ("anthropic", "Claude API Key:", "claude_key", "lineEditClaudeKey"),
    ("openrouter", "OpenRouter API Key:", "openrouter_key", "lineEditOpenRouterKey"),
)
_API_KEY_SAVED_TEXT = "保存済"
_API_KEY_UNSET_TEXT = "未設定"
_API_KEY_SAVED_PLACEHOLDER = "保存済（変更する場合のみ入力）"
_API_KEY_HIGHLIGHT_STYLE = f"QLineEdit {{ border: {theme.BORDER_WIDTH_ACCENT}px solid {theme.WARN}; }}"
_API_KEY_SAVED_STATUS_STYLE = f"QLabel {{ color: {theme.OK}; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
_API_KEY_UNSET_STATUS_STYLE = f"QLabel {{ color: {theme.INK_FAINT}; }}"


class ConfigurationWindow(QDialog):
    """アプリケーション設定ダイアログ。

    ConfigurationService 経由で設定の読み込み・更新・保存を行う。
    2タブ構成: 基本設定（API、ディレクトリ、ログ）と詳細設定（画像処理、プロンプト）。
    """

    def __init__(
        self,
        config_service: ConfigurationService,
        parent: QWidget | None = None,
    ) -> None:
        """ConfigurationWindow を初期化する。

        Args:
            config_service: 設定の読み書きを行うサービス。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._config_service = config_service
        self._build_ui()
        self._populate_from_config()
        logger.debug("ConfigurationWindow initialized")

    def _build_ui(self) -> None:
        """UIを構築する。"""
        self.setWindowTitle("設定")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)

        # タブウィジェット
        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(self._build_basic_tab(), "基本設定")
        self._tab_widget.addTab(self._build_advanced_tab(), "詳細設定")
        layout.addWidget(self._tab_widget)

        # OK/Cancel ボタン
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accepted)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_basic_tab(self) -> QWidget:
        """基本設定タブを構築する。

        Returns:
            基本設定タブのウィジェット。
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        # API設定 (Issue #755: マスク入力 + 保存済/未設定ステータスのみ表示。
        # 保存済キーは UI に echo back しない。クリアは config/lorairo.toml 直接編集で行う)
        api_group = QGroupBox("API設定")
        api_layout = QFormLayout(api_group)

        self._api_key_edits: dict[str, QLineEdit] = {}
        self._api_key_status_labels: dict[str, QLabel] = {}
        self._saved_api_keys: dict[str, str] = {}

        for provider, label_text, _config_key, object_name in _API_KEY_ROWS:
            key_edit = QLineEdit()
            key_edit.setObjectName(object_name)
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)

            status_label = QLabel(_API_KEY_UNSET_TEXT)
            status_label.setObjectName(f"{object_name}Status")
            status_label.setStyleSheet(_API_KEY_UNSET_STATUS_STYLE)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(key_edit, stretch=1)
            row_layout.addWidget(status_label)
            api_layout.addRow(label_text, row_widget)

            self._api_key_edits[provider] = key_edit
            self._api_key_status_labels[provider] = status_label

        tab_layout.addWidget(api_group)

        # ディレクトリ設定
        dir_group = QGroupBox("ディレクトリ設定")
        dir_layout = QFormLayout(dir_group)

        self._dir_picker_database_dir = DirectoryPickerWidget()
        self._dir_picker_database_dir.setObjectName("dirPickerDatabaseDir")
        dir_layout.addRow("データベース:", self._dir_picker_database_dir)

        self._line_edit_project_name = QLineEdit()
        self._line_edit_project_name.setObjectName("lineEditProjectName")
        dir_layout.addRow("プロジェクト名:", self._line_edit_project_name)

        self._dir_picker_export_dir = DirectoryPickerWidget()
        self._dir_picker_export_dir.setObjectName("dirPickerExportDir")
        dir_layout.addRow("エクスポート先:", self._dir_picker_export_dir)

        self._dir_picker_batch_results = DirectoryPickerWidget()
        self._dir_picker_batch_results.setObjectName("dirPickerBatchResults")
        dir_layout.addRow("バッチ結果:", self._dir_picker_batch_results)

        tab_layout.addWidget(dir_group)

        # ログ設定
        log_group = QGroupBox("ログ")
        log_layout = QFormLayout(log_group)

        self._combo_box_log_level = QComboBox()
        self._combo_box_log_level.setObjectName("comboBoxLogLevel")
        self._combo_box_log_level.addItems(_LOG_LEVELS)
        log_layout.addRow("ログレベル:", self._combo_box_log_level)

        tab_layout.addWidget(log_group)
        tab_layout.addStretch()

        return tab

    def _build_advanced_tab(self) -> QWidget:
        """詳細設定タブを構築する。

        Returns:
            詳細設定タブのウィジェット。
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        # 画像処理設定
        image_group = QGroupBox("画像処理")
        image_layout = QFormLayout(image_group)

        self._combo_box_upscaler = QComboBox()
        self._combo_box_upscaler.setObjectName("comboBoxUpscaler")
        upscalers = self._config_service.get_available_upscaler_names()
        self._combo_box_upscaler.addItems(upscalers)
        image_layout.addRow("登録時のアップスケーラー:", self._combo_box_upscaler)

        tab_layout.addWidget(image_group)

        # モデル選択設定 (Issue #249)
        model_group = QGroupBox("モデル選択")
        model_layout = QFormLayout(model_group)

        self._combo_box_route_preference = QComboBox()
        self._combo_box_route_preference.setObjectName("comboBoxRoutePreference")
        self._combo_box_route_preference.addItems(_ROUTE_PREFERENCES)
        self._combo_box_route_preference.setToolTip(
            "モデル経路の優先設定。auto: API key 状況に応じて direct を優先 / "
            "direct: 直接プロバイダー経路のみ / openrouter: OpenRouter 経由のみ。"
            "全 route 一覧表示は CLI 専用 (lorairo-cli models list --route all)。"
        )
        model_layout.addRow("経路の優先設定:", self._combo_box_route_preference)

        tab_layout.addWidget(model_group)

        # プロンプト設定
        prompt_group = QGroupBox("WebAPI 追加プロンプト")
        prompt_layout = QVBoxLayout(prompt_group)

        prompt_label = QLabel(
            "WebAPI アノテーション時にベースプロンプトの末尾に追記するテキスト。\n"
            "ポーズ・照明・構図・スタイル以外に注目させたい指示を入力してください。\n"
            "空欄の場合はデフォルトのベースプロンプトのみ使用されます。"
        )
        prompt_label.setWordWrap(True)
        prompt_layout.addWidget(prompt_label)

        self._text_edit_prompt = QPlainTextEdit()
        self._text_edit_prompt.setObjectName("textEditPrompt")
        self._text_edit_prompt.setMaximumHeight(120)
        self._text_edit_prompt.setPlaceholderText(
            "例: Focus on any text or logos visible in the image. Note the language and font style."
        )
        prompt_layout.addWidget(self._text_edit_prompt)

        tab_layout.addWidget(prompt_group)
        tab_layout.addStretch()

        return tab

    def _populate_from_config(self) -> None:
        """ConfigurationService から現在の設定値を読み込み、UIに反映する。"""
        config = self._config_service.get_all_settings()

        # API設定 (Issue #755: 保存済キーは欄に echo back せず「保存済かだけ分かる」表示)
        api = config.get("api", {})
        for provider, _label_text, config_key, _object_name in _API_KEY_ROWS:
            saved_key = str(api.get(config_key, "") or "")
            self._saved_api_keys[provider] = saved_key
            key_edit = self._api_key_edits[provider]
            status_label = self._api_key_status_labels[provider]
            key_edit.clear()
            if saved_key.strip():
                key_edit.setPlaceholderText(_API_KEY_SAVED_PLACEHOLDER)
                status_label.setText(_API_KEY_SAVED_TEXT)
                status_label.setStyleSheet(_API_KEY_SAVED_STATUS_STYLE)
            else:
                key_edit.setPlaceholderText(_API_KEY_UNSET_TEXT)
                status_label.setText(_API_KEY_UNSET_TEXT)
                status_label.setStyleSheet(_API_KEY_UNSET_STATUS_STYLE)

        # ディレクトリ設定
        dirs = config.get("directories", {})
        database_base_dir = dirs.get("database_base_dir", "")
        if database_base_dir:
            self._dir_picker_database_dir.set_path(database_base_dir)
        self._line_edit_project_name.setText(dirs.get("database_project_name", ""))
        export_dir = dirs.get("export_dir", "")
        if export_dir:
            self._dir_picker_export_dir.set_path(export_dir)
        batch_results_dir = dirs.get("batch_results_dir", "")
        if batch_results_dir:
            self._dir_picker_batch_results.set_path(batch_results_dir)

        # ログ設定
        log = config.get("log", {})
        log_level = log.get("level", "INFO")
        idx = self._combo_box_log_level.findText(log_level)
        if idx >= 0:
            self._combo_box_log_level.setCurrentIndex(idx)

        # 画像処理設定
        default_upscaler = self._config_service.get_default_upscaler_name()
        idx = self._combo_box_upscaler.findText(default_upscaler)
        if idx >= 0:
            self._combo_box_upscaler.setCurrentIndex(idx)

        # モデル選択設定 (Issue #249): 不正値・None・空文字は parse_route_preference で auto fallback。
        # "all" は CLI 専用のため GUI ComboBox には項目が無い → findText が -1 を返す。
        # その場合 auto にフォールバックして警告ログを残す (silently overwrite を避けるための明示通知)。
        model_selection = config.get("model_selection", {})
        normalized_preference = parse_route_preference(model_selection.get("route_preference"))
        idx = self._combo_box_route_preference.findText(normalized_preference)
        if idx >= 0:
            self._combo_box_route_preference.setCurrentIndex(idx)
        else:
            logger.warning(
                "route_preference={!r} は GUI 設定では選択できないため auto にフォールバック表示します "
                "(OK 押下時に auto で上書き保存)。CLI でのみ利用する場合は GUI で変更しないでください。",
                normalized_preference,
            )
            auto_idx = self._combo_box_route_preference.findText("auto")
            if auto_idx >= 0:
                self._combo_box_route_preference.setCurrentIndex(auto_idx)

        # プロンプト設定
        prompts = config.get("prompts", {})
        self._text_edit_prompt.setPlainText(prompts.get("additional", ""))

    def focus_api_key_field(self, provider: str) -> bool:
        """指定 provider の API キー欄をハイライトしてフォーカスする (Issue #755)。

        モデルピッカーの ``○ needs key`` チップからの往復導線で使う。
        基本設定タブへ切り替え、該当欄に強調枠を付けて入力を促す。

        Args:
            provider: provider 名 (``"openai"`` / ``"anthropic"`` / ``"google"`` /
                ``"openrouter"``)。大文字小文字は区別しない。

        Returns:
            該当プロバイダ欄が存在しハイライトした場合 True、未知の provider は False。
        """
        key_edit = self._api_key_edits.get(provider.strip().lower())
        if key_edit is None:
            logger.warning(f"API キー欄が見つからない provider 指定: {provider}")
            return False
        self._tab_widget.setCurrentIndex(0)
        key_edit.setStyleSheet(_API_KEY_HIGHLIGHT_STYLE)
        key_edit.setFocus()
        return True

    def _collect_settings(self) -> dict[str, dict[str, Any]]:
        """全ウィジェットから設定値を収集する。

        Returns:
            セクション名をキーとした設定辞書。
        """
        # Issue #755: API キー欄が空のままなら保存済の値を維持する
        # (欄に echo back しない UI のため、空欄 = 「変更なし」と解釈する)。
        api_settings = {
            config_key: (self._api_key_edits[provider].text().strip() or self._saved_api_keys[provider])
            for provider, _label_text, config_key, _object_name in _API_KEY_ROWS
        }
        return {
            "api": api_settings,
            "directories": {
                "database_base_dir": self._dir_picker_database_dir.get_selected_path() or "",
                "database_project_name": self._line_edit_project_name.text().strip(),
                "export_dir": self._dir_picker_export_dir.get_selected_path() or "",
                "batch_results_dir": self._dir_picker_batch_results.get_selected_path() or "",
            },
            "log": {
                "level": self._combo_box_log_level.currentText(),
            },
            "image_processing": {
                "upscaler": self._combo_box_upscaler.currentText(),
            },
            "model_selection": {
                # Issue #249: ComboBox の値域は _ROUTE_PREFERENCES なので
                # parse_route_preference を通さなくても常に valid だが、防御的に正規化。
                "route_preference": parse_route_preference(self._combo_box_route_preference.currentText()),
            },
            "prompts": {
                "additional": self._text_edit_prompt.toPlainText(),
            },
        }

    def _on_accepted(self) -> None:
        """OKボタン: 設定を収集・反映・保存してダイアログを閉じる。"""
        settings = self._collect_settings()
        for section, values in settings.items():
            for key, value in values.items():
                self._config_service.update_setting(section, key, value)

        if self._config_service.save_settings():
            # ログレベル変更を即座に反映するためLoguruハンドラを再初期化
            initialize_logging(build_gui_log_config(self._config_service.get_all_settings()))
            logger.info("設定を保存しました")
            self.accept()
        else:
            show_critical(self, "保存失敗", "設定ファイルの保存に失敗しました。")
