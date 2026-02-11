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
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...services.configuration_service import ConfigurationService
from ...utils.log import initialize_logging, logger
from ..widgets.directory_picker import DirectoryPickerWidget

# ログレベル選択肢
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


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

        # API設定
        api_group = QGroupBox("API設定")
        api_layout = QFormLayout(api_group)

        self._line_edit_openai_key = QLineEdit()
        self._line_edit_openai_key.setObjectName("lineEditOpenAiKey")
        self._line_edit_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("OpenAI API Key:", self._line_edit_openai_key)

        self._line_edit_google_key = QLineEdit()
        self._line_edit_google_key.setObjectName("lineEditGoogleKey")
        self._line_edit_google_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("Google API Key:", self._line_edit_google_key)

        self._line_edit_claude_key = QLineEdit()
        self._line_edit_claude_key.setObjectName("lineEditClaudeKey")
        self._line_edit_claude_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("Claude API Key:", self._line_edit_claude_key)

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

        # プロンプト設定
        prompt_group = QGroupBox("プロンプト")
        prompt_layout = QVBoxLayout(prompt_group)

        self._text_edit_prompt = QPlainTextEdit()
        self._text_edit_prompt.setObjectName("textEditPrompt")
        self._text_edit_prompt.setMaximumHeight(120)
        prompt_layout.addWidget(self._text_edit_prompt)

        tab_layout.addWidget(prompt_group)
        tab_layout.addStretch()

        return tab

    def _populate_from_config(self) -> None:
        """ConfigurationService から現在の設定値を読み込み、UIに反映する。"""
        config = self._config_service.get_all_settings()

        # API設定
        api = config.get("api", {})
        self._line_edit_openai_key.setText(api.get("openai_key", ""))
        self._line_edit_google_key.setText(api.get("google_key", ""))
        self._line_edit_claude_key.setText(api.get("claude_key", ""))

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

        # プロンプト設定
        prompts = config.get("prompts", {})
        self._text_edit_prompt.setPlainText(prompts.get("additional", ""))

    def _collect_settings(self) -> dict[str, dict[str, Any]]:
        """全ウィジェットから設定値を収集する。

        Returns:
            セクション名をキーとした設定辞書。
        """
        return {
            "api": {
                "openai_key": self._line_edit_openai_key.text().strip(),
                "google_key": self._line_edit_google_key.text().strip(),
                "claude_key": self._line_edit_claude_key.text().strip(),
            },
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
            log_config = self._config_service.get_all_settings().get("log", {})
            initialize_logging(log_config)
            logger.info("設定を保存しました")
            self.accept()
        else:
            QMessageBox.critical(self, "保存失敗", "設定ファイルの保存に失敗しました。")
