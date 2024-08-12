import sys
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import QFile
from module.config import get_config
from settingspage_ui import Ui_SettingsPageWidget  # UIファイルから生成されたPythonクラス
import toml

class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_SettingsPageWidget()
        self.ui.setupUi(self)
        self.config = get_config()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        # フォルダ設定
        self.ui.lineEditDatasetFolder.setText(self.config['directories'].get('dataset', ''))
        self.ui.lineEditOutputFolder.setText(self.config['directories'].get('output', ''))
        self.ui.lineEditResponseFolder.setText(self.config['directories'].get('response_file', ''))
        self.ui.lineEditEditedOutputFolder.setText(self.config['directories'].get('edited_output', ''))

        # API設定
        self.ui.lineEditOpenAIApiKey.setText(self.config['api'].get('openai_key', ''))
        self.ui.lineEditOpenAIModel.setText(self.config['api'].get('openai_model', ''))
        self.ui.lineEditGoogleApiKey.setText(self.config['api'].get('google_key', ''))
        self.ui.lineEditGoogleApiModel.setText(self.config['api'].get('google_model', ''))
        self.ui.lineEditAnthropicApiKey.setText(self.config['api'].get('claude_key', ''))
        self.ui.lineEditAnthropicApiModel.setText(self.config['api'].get('claude_model', ''))

        # Hugging Face設定
        self.ui.lineEditHuggingFaceUsername.setText(self.config.get('huggingface', {}).get('hf_username', ''))
        self.ui.lineEditHuggingFaceRepoName.setText(self.config.get('huggingface', {}).get('repo_name', ''))
        self.ui.lineEditHuggingFaceToken.setText(self.config.get('huggingface', {}).get('token', ''))

        # ログ設定
        self.ui.comboBoxLogLevel.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.ui.comboBoxLogLevel.setCurrentText(self.config['log']['level'])
        self.ui.lineEditLogFile.setText(self.config['log']['file'])

    def connect_signals(self):
        # フォルダ選択ボタン
        self.ui.buttonBrowseDataset.clicked.connect(lambda: self.browse_folder(self.ui.lineEditDatasetFolder))
        self.ui.buttonBrowseOutput.clicked.connect(lambda: self.browse_folder(self.ui.lineEditOutputFolder))
        self.ui.buttonBrowseResponse.clicked.connect(lambda: self.browse_folder(self.ui.lineEditResponseFolder))
        self.ui.buttonBrowseEditedOutput.clicked.connect(lambda: self.browse_folder(self.ui.lineEditEditedOutputFolder))
        self.ui.buttonBrowseLogFile.clicked.connect(lambda: self.browse_file(self.ui.lineEditLogFile))

        # 保存ボタン
        self.ui.buttonSave.clicked.connect(self.save_settings)
        self.ui.buttonSaveAs.clicked.connect(self.save_settings_as)

    def browse_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            line_edit.setText(folder)

    def browse_file(self, line_edit):
        file, _ = QFileDialog.getOpenFileName(self, "ファイルを選択")
        if file:
            line_edit.setText(file)

    def get_current_settings(self):
        return {
            'directories': {
                'dataset': self.ui.lineEditDatasetFolder.text(),
                'output': self.ui.lineEditOutputFolder.text(),
                'response_file': self.ui.lineEditResponseFolder.text(),
                'edited_output': self.ui.lineEditEditedOutputFolder.text()
            },
            'api': {
                'openai_api_key': self.ui.lineEditOpenAIApiKey.text(),
                'openai_model': self.ui.lineEditOpenAIModel.text(),
                'google_api_key': self.ui.lineEditGoogleApiKey.text(),
                'google_api_model': self.ui.lineEditGoogleApiModel.text(),
                'anthropic_api_key': self.ui.lineEditAnthropicApiKey.text(),
                'anthropic_api_model': self.ui.lineEditAnthropicApiModel.text()
            },
            'huggingface': {
                'username': self.ui.lineEditHuggingFaceUsername.text(),
                'repo_name': self.ui.lineEditHuggingFaceRepoName.text(),
                'token': self.ui.lineEditHuggingFaceToken.text()
            },
            'log': {
                'level': self.ui.comboBoxLogLevel.currentText(),
                'file': self.ui.lineEditLogFile.text()
            }
        }

    def save_settings(self, filename=None):
        if not filename:
            filename = 'processing.toml'

        settings = self.get_current_settings()

        try:
            with open(filename, 'w') as f:
                toml.dump(settings, f)
            QMessageBox.information(self, "保存成功", f"設定を {filename} に保存しました。")
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"設定の保存中にエラーが発生しました: {str(e)}")

    def save_settings_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "", "TOML Files (*.toml)")
        if filename:
            self.save_settings(filename)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    settings_page = SettingsPage()
    settings_page.show()
    sys.exit(app.exec())