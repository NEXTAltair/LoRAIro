# src/lorairo/gui/window/configuration_window.py
"""設定ウィンドウ - アプリケーション設定の表示・編集・保存を行うダイアログ。

ConfigurationService と連携して、API KEY、ディレクトリ、ログ設定等を管理する。
UIは Qt Designer の ConfigurationWindow.ui から自動生成された Ui_ConfigurationWindow を使用。
"""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...services.configuration_service import ConfigurationService
from ...utils.log import logger
from ..designer.ConfigurationWindow_ui import Ui_ConfigurationWindow

# ログレベル選択肢
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


class ConfigurationWindow(QDialog):
    """アプリケーション設定ダイアログ。

    ConfigurationService 経由で設定の読み込み・更新・保存を行う。
    UIは QWidget ベースの Ui_ConfigurationWindow を QDialog 内に埋め込む構成。
    """

    def __init__(
        self,
        config_service: ConfigurationService,
        parent: QWidget | None = None,
    ) -> None:
        """ConfigurationWindow を初期化する。

        Args:
            config_service: 設定の読み書きを行うサービス
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self._config_service = config_service

        # UI セットアップ（QWidget ベースの UI を QDialog 内に埋め込み）
        self._ui_widget = QWidget()
        self._ui = Ui_ConfigurationWindow()
        self._ui.setupUi(self._ui_widget)  # type: ignore[no-untyped-call]  # Justification: Qt Designer generated method

        # ダイアログレイアウト構成
        layout = QVBoxLayout(self)
        layout.addWidget(self._ui_widget)

        # ダイアログボタン（OK/Cancel）
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_save_and_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self.setWindowTitle("設定")
        self.setMinimumSize(600, 500)

        # UI内ボタンのシグナル接続
        self._ui.buttonSave.clicked.connect(self._on_save_clicked)
        self._ui.buttonSaveAs.clicked.connect(self._on_save_as_clicked)

        # ログレベルコンボボックスの初期化
        self._ui.comboBoxLogLevel.addItems(_LOG_LEVELS)

        # 設定値をUIに反映
        self._populate_from_config()

        logger.debug("ConfigurationWindow initialized")

    def _populate_from_config(self) -> None:
        """ConfigurationService から現在の設定値を読み込み、UIに反映する。"""
        config = self._config_service.get_all_settings()

        # API KEY
        api = config.get("api", {})
        self._ui.lineEditOpenAiKey.setText(api.get("openai_key", ""))
        self._ui.lineEditGoogleVisionKey.setText(api.get("google_key", ""))
        self._ui.lineEditAnthropicKey.setText(api.get("claude_key", ""))

        # HuggingFace
        hf = config.get("huggingface", {})
        self._ui.lineEditHfUsername.setText(hf.get("username", ""))
        self._ui.lineEditHfRepoName.setText(hf.get("repo_name", ""))
        self._ui.lineEditHfToken.setText(hf.get("token", ""))

        # ディレクトリ
        dirs = config.get("directories", {})
        export_dir = dirs.get("export_dir", "")
        batch_results_dir = dirs.get("batch_results_dir", "")
        database_base_dir = dirs.get("database_base_dir", "")

        self._ui.dirPickerExportDir.set_label_text("エクスポート先:")
        if export_dir:
            self._ui.dirPickerExportDir.set_path(export_dir)

        self._ui.dirPickerBatchResults.set_label_text("バッチ結果:")
        if batch_results_dir:
            self._ui.dirPickerBatchResults.set_path(batch_results_dir)

        self._ui.dirPickerDatabaseDir.set_label_text("データベース:")
        if database_base_dir:
            self._ui.dirPickerDatabaseDir.set_path(database_base_dir)

        # ログ設定
        log = config.get("log", {})
        log_level = log.get("level", "INFO")
        idx = self._ui.comboBoxLogLevel.findText(log_level)
        if idx >= 0:
            self._ui.comboBoxLogLevel.setCurrentIndex(idx)

        log_file = log.get("file", "")
        self._ui.filePickerLogFile.set_label_text("ログファイル:")
        if log_file:
            self._ui.filePickerLogFile.set_path(log_file)

    def _collect_settings_from_ui(self) -> dict[str, dict[str, Any]]:
        """UIの入力値を設定辞書として収集する。

        Returns:
            セクション名をキーとした設定辞書
        """
        return {
            "api": {
                "openai_key": self._ui.lineEditOpenAiKey.text().strip(),
                "google_key": self._ui.lineEditGoogleVisionKey.text().strip(),
                "claude_key": self._ui.lineEditAnthropicKey.text().strip(),
            },
            "huggingface": {
                "username": self._ui.lineEditHfUsername.text().strip(),
                "repo_name": self._ui.lineEditHfRepoName.text().strip(),
                "token": self._ui.lineEditHfToken.text().strip(),
            },
            "directories": {
                "export_dir": self._ui.dirPickerExportDir.get_selected_path() or "",
                "batch_results_dir": self._ui.dirPickerBatchResults.get_selected_path() or "",
                "database_base_dir": self._ui.dirPickerDatabaseDir.get_selected_path() or "",
            },
            "log": {
                "level": self._ui.comboBoxLogLevel.currentText(),
                "file": self._ui.filePickerLogFile.get_selected_path() or "",
            },
        }

    def _apply_settings(self) -> bool:
        """UIの入力値を ConfigurationService に反映して保存する。

        Returns:
            保存に成功した場合 True
        """
        settings = self._collect_settings_from_ui()
        for section, values in settings.items():
            for key, value in values.items():
                self._config_service.update_setting(section, key, value)

        return self._config_service.save_settings()

    def _on_save_and_accept(self) -> None:
        """OKボタン: 設定を保存してダイアログを閉じる。"""
        if self._apply_settings():
            logger.info("設定を保存しました")
            self.accept()
        else:
            QMessageBox.critical(self, "保存失敗", "設定ファイルの保存に失敗しました。")

    def _on_save_clicked(self) -> None:
        """保存ボタン: 設定を保存（ダイアログは閉じない）。"""
        if self._apply_settings():
            QMessageBox.information(self, "保存完了", "設定を保存しました。")
        else:
            QMessageBox.critical(self, "保存失敗", "設定ファイルの保存に失敗しました。")

    def _on_save_as_clicked(self) -> None:
        """名前を付けて保存ボタン: 別のファイルパスに設定を保存する。"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "設定ファイルの保存先", "", "TOML Files (*.toml);;All Files (*)"
        )
        if not file_path:
            return

        settings = self._collect_settings_from_ui()
        for section, values in settings.items():
            for key, value in values.items():
                self._config_service.update_setting(section, key, value)

        if self._config_service.save_settings(target_path=Path(file_path)):
            QMessageBox.information(self, "保存完了", f"設定を保存しました:\n{file_path}")
        else:
            QMessageBox.critical(self, "保存失敗", f"保存に失敗しました:\n{file_path}")
