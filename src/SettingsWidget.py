from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from PySide6.QtCore import Slot

from gui_file.SettingsWidget_ui import Ui_SettingsWidget

from module.file_sys import FileSystemManager

class SettingsWidget(QWidget, Ui_SettingsWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def initialize(self, cm: 'ConfigManager'):
        self.cm = cm
        self.initialize_ui()
        self.connect_custom_widgets()

    def initialize_ui(self):
        self.initialize_directory_pickers()
        self.initialize_api_settings()
        self.initialize_huggingface_settings()
        self.initialize_log_settings()

    def initialize_directory_pickers(self):
        directories = {
            'output': self.dirPickerOutput,
            'response_file': self.dirPickerResponse,
            'edited_output': self.dirPickerEditedOutput
        }
        for key, picker in directories.items():
            picker.set_label_text(f"{key.capitalize()} Directory")
            picker.set_path(self.cm.config['directories'][key])

    def initialize_api_settings(self):
        api_settings = {
            'openai_key': self.lineEditOpenAiKey,
            'google_key': self.lineEditGoogleVisionKey,
            'claude_key': self.lineEditAnthropicKey
        }
        for key, widget in api_settings.items():
            widget.setText(self.cm.config['api'][key])

    def initialize_huggingface_settings(self):
        hf_settings = {
            'hf_username': self.lineEditHfUsername,
            'repo_name': self.lineEditHfRepoName,
            'token': self.lineEditHfToken
        }
        for key, widget in hf_settings.items():
            widget.setText(self.cm.config['huggingface'][key])

    def initialize_log_settings(self):
        self.comboBoxLogLevel.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.comboBoxLogLevel.setCurrentText(self.cm.config['log']['level'])
        self.filePickerLogFile.set_label_text("Log File")
        self.filePickerLogFile.set_path(self.cm.config['log']['file'])

    def _save_config(self, filename: str) -> bool:
        try:
            FileSystemManager.save_toml_config(self.cm.config, filename)
            return True
        except IOError as e:
            QMessageBox.critical(self, "保存エラー", str(e))
            return False

    @Slot()
    def on_buttonSave_clicked(self):
        if self._save_config("processing.toml"):
            QMessageBox.information(self, "保存成功", "設定を保存しました。")

    @Slot()
    def on_buttonSaveAs_clicked(self):
        filename, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "", "TOML Files (*.toml)")
        if filename and self._save_config(filename):
            QMessageBox.information(self, "保存成功", f"設定を {filename} に保存しました。")

    def on_lineEditOpenAiKey_editingFinished(self):
        self.cm.config['api']['openai_key'] = self.lineEditOpenAiKey.text()

    def on_lineEditGoogleVisionKey_editingFinished(self):
        self.cm.config['api']['google_key'] = self.lineEditGoogleVisionKey.text()

    def on_lineEditAnthropicKey_editingFinished(self):
        self.cm.config['api']['claude_key'] = self.lineEditAnthropicKey.text()

    def on_lineEditHfUsername_editingFinished(self):
        self.cm.config['huggingface']['hf_username'] = self.lineEditHfUsername.text()

    def on_lineEditHfRepoName_editingFinished(self):
        self.cm.config['huggingface']['repo_name'] = self.lineEditHfRepoName.text()

    def on_lineEditHfToken_editingFinished(self):
        self.cm.config['huggingface']['token'] = self.lineEditHfToken.text()

    def on_comboBoxLogLevel_currentIndexChanged(self, index):
        self.cm.config['log']['level'] = self.comboBoxLogLevel.itemText(index)

    def connect_custom_widgets(self):
        self.dirPickerOutput.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerOutput_changed)
        self.dirPickerResponse.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerResponse_changed)
        self.dirPickerEditedOutput.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerEditedOutput_changed)
        self.filePickerLogFile.FilePicker.lineEditPicker.textChanged.connect(self.on_filePickerLogFile_changed)

    def on_dirPickerOutput_changed(self, new_path):
        self.cm.config['directories']['output'] = new_path

    def on_dirPickerResponse_changed(self, new_path):
        self.cm.config['directories']['response_file'] = new_path

    def on_dirPickerEditedOutput_changed(self, new_path):
        self.cm.config['directories']['edited_output'] = new_path

    def on_filePickerLogFile_changed(self, new_path):
        self.cm.config['log']['file'] = new_path

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    app = QApplication(sys.argv)
    cm = ConfigManager()
    settings_page = SettingsWidget()
    settings_page.initialize(cm)
    settings_page.show()
    sys.exit(app.exec())