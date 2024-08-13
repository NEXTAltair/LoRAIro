import sys
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import QFile
from module.config import get_config
from SettingspageWidget_ui import Ui_SettingspageWidget  # UIファイルから生成されたPythonクラス
import toml

class SettingspageWidget(QWidget, Ui_SettingspageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.config = get_config()
        self.initialize_ui()
        self.connect_signals()

    def initialize_ui(self):
        self.initialize_directory_pickers()
        self.initialize_api_settings()
        self.initialize_huggingface_settings()
        self.initialize_log_settings()

    def initialize_directory_pickers(self):
        directories = {
            'dataset': self.dataset_DirPickerWidget,
            'output': self.output_DirPickerWidget,
            'response_file': self.response_DirPickerWidget,
            'edited_output': self.new_output_DirPickerWidget
        }

        for key, picker in directories.items():
            path = self.config['directories'].get(key, '')
            picker.set_label_text(f"{key.capitalize()} Directory")
            picker.set_path(path)

    def initialize_api_settings(self):
        api_settings = {
            'openai_key': self.lineEditOpenAIApiKey,
            'openai_model': self.lineEditOpenAIModel,
            'google_key': self.lineEditGoogleApiKey,
            'google_model': self.lineEditGoogleApiModel,
            'claude_key': self.lineEditAnthropicApiKey,
            'claude_model': self.lineEditAnthropicApiModel
        }

        for key, widget in api_settings.items():
            widget.setText(self.config['api'].get(key, ''))

    def initialize_huggingface_settings(self):
        hf_settings = {
            'hf_username': self.lineEditHuggingFaceUsername,
            'repo_name': self.lineEditHuggingFaceRepoName,
            'token': self.lineEditHuggingFaceToken
        }

        for key, widget in hf_settings.items():
            widget.setText(self.config.get('huggingface', {}).get(key, ''))

    def initialize_log_settings(self):
        self.comboBoxLogLevel.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.comboBoxLogLevel.setCurrentText(self.config['log']['level'])
        self.log_PilePickerWidget.set_label_text("Log File")
        self.log_PilePickerWidget.set_path(self.config['log']['file'])

    def connect_signals(self):
        directory_pickers = [
            ('dataset', self.dataset_DirPickerWidget),
            ('output', self.output_DirPickerWidget),
            ('response_file', self.response_DirPickerWidget),
            ('edited_output', self.new_output_DirPickerWidget)
        ]

        for key, picker in directory_pickers:
            picker.DirectoryPicker.lineEditPicker.textChanged.connect(
                lambda path, k=key: self.on_path_changed(k, path))

        self.log_PilePickerWidget.FilePicker.lineEditPicker.textChanged.connect(
            lambda path: self.on_log_file_changed(path))

        self.buttonSave.clicked.connect(self.save_settings)
        self.buttonSaveAs.clicked.connect(self.save_settings_as)
        self.buttonSave.clicked.connect(self.save_settings)

    def on_path_changed(self, setting_key, new_path):
        print(f"{setting_key.capitalize()} path changed to: {new_path}")
        self.config['directories'][setting_key] = new_path

    def on_log_file_changed(self, new_path):
        print(f"Log file path changed to: {new_path}")
        self.config['log']['file'] = new_path

    def get_current_settings(self):
        return {
            'directories': {
                'dataset': self.dataset_DirPickerWidget.DirectoryPicker.lineEditPicker.text(),
                'output': self.output_DirPickerWidget.DirectoryPicker.lineEditPicker.text(),
                'response_file': self.response_DirPickerWidget.DirectoryPicker.lineEditPicker.text(),
                'edited_output': self.new_output_DirPickerWidget.DirectoryPicker.lineEditPicker.text()
            },
            'api': {
                'openai_api_key': self.lineEditOpenAIApiKey.text(),
                'openai_model': self.lineEditOpenAIModel.text(),
                'google_api_key': self.lineEditGoogleApiKey.text(),
                'google_api_model': self.lineEditGoogleApiModel.text(),
                'anthropic_api_key': self.lineEditAnthropicApiKey.text(),
                'anthropic_api_model': self.lineEditAnthropicApiModel.text()
            },
            'huggingface': {
                'username': self.lineEditHuggingFaceUsername.text(),
                'repo_name': self.lineEditHuggingFaceRepoName.text(),
                'token': self.lineEditHuggingFaceToken.text()
            },
            'log': {
                'level': self.comboBoxLogLevel.currentText(),
                'file': self.log_PilePickerWidget.FilePicker.lineEditPicker.text()
            }
        }

    def write_config_file(self, settings, filename=None):
        if filename:
            with open(filename, 'w') as f:
                toml.dump(settings, f)
        else:
            with open('config.toml', 'w') as f:
                toml.dump(settings, f)

    def save_settings(self):
        settings = self.get_current_settings()
        try:
            self.write_config_file(settings)
            QMessageBox.information(self, "保存成功", "設定を保存しました。")
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"設定の保存中にエラーが発生しました: {str(e)}")

    def save_settings_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "", "TOML Files (*.toml)")
        if filename:
            settings = self.get_current_settings()
            try:
                self.write_config_file(settings, filename)
                QMessageBox.information(self, "保存成功", f"設定を {filename} に保存しました。")
            except Exception as e:
                QMessageBox.critical(self, "保存エラー", f"設定の保存中にエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    settings_page = SettingspageWidget()
    settings_page.show()
    sys.exit(app.exec())