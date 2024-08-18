import sys
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from PySide6.QtCore import Slot

from SettingspageWidget_ui import Ui_SettingspageWidget

import toml

class SettingspageWidget(QWidget, Ui_SettingspageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.config = None

    def initialize(self, config):
        self.config = config
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
            picker.set_path(self.config['directories'][key])

    def initialize_api_settings(self):
        api_settings = {
            'openai_key': self.lineEditOpenAiKey,
            'google_key': self.lineEditGoogleVisionKey,
            'claude_key': self.lineEditAnthropicKey
        }
        for key, widget in api_settings.items():
            widget.setText(self.config['api'][key])

    def initialize_huggingface_settings(self):
        hf_settings = {
            'hf_username': self.lineEditHfUsername,
            'repo_name': self.lineEditHfRepoName,
            'token': self.lineEditHfToken
        }
        for key, widget in hf_settings.items():
            widget.setText(self.config['huggingface'][key])

    # 自動接続のためのon_プレフィックスを持つメソッド
    @Slot()
    def on_buttonSave_clicked(self):
        try:
            self.cm.save()
            QMessageBox.information(self, "保存成功", "設定を保存しました。")
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"設定の保存中にエラーが発生しました: {str(e)}")

    @Slot()
    def on_buttonSaveAs_clicked(self):
        filename, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "", "TOML Files (*.toml)")
        if filename:
            try:
                with open(filename, 'w') as f:
                    toml.dump(self.config, f)
                QMessageBox.information(self, "保存成功", f"設定を {filename} に保存しました。")
            except Exception as e:
                QMessageBox.critical(self, "保存エラー", f"設定の保存中にエラーが発生しました: {str(e)}")


    def initialize_log_settings(self):
        self.comboBoxLogLevel.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.comboBoxLogLevel.setCurrentText(self.config['log']['level'])
        self.filePickerLogFile.set_label_text("Log File")
        self.filePickerLogFile.set_path(self.config['log']['file'])

    def on_lineEditOpenAiKey_editingFinished(self):
        self.config['api']['openai_key'] = self.lineEditOpenAiKey.text()

    def on_lineEditGoogleVisionKey_editingFinished(self):
        self.config['api']['google_key'] = self.lineEditGoogleVisionKey.text()

    def on_lineEditAnthropicKey_editingFinished(self):
        self.config['api']['claude_key'] = self.lineEditAnthropicKey.text()

    def on_lineEditHfUsername_editingFinished(self):
        self.config['huggingface']['hf_username'] = self.lineEditHfUsername.text()

    def on_lineEditHfRepoName_editingFinished(self):
        self.config['huggingface']['repo_name'] = self.lineEditHfRepoName.text()

    def on_lineEditHfToken_editingFinished(self):
        self.config['huggingface']['token'] = self.lineEditHfToken.text()

    def on_comboBoxLogLevel_currentIndexChanged(self, index):
        self.config['log']['level'] = self.comboBoxLogLevel.itemText(index)

    def connect_custom_widgets(self):
        # DirectoryPickerWidgetの接続
        self.dirPickerOutput.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerOutput_changed)
        self.dirPickerResponse.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerResponse_changed)
        self.dirPickerEditedOutput.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dirPickerEditedOutput_changed)

        # FilePickerWidgetの接続
        self.filePickerLogFile.FilePicker.lineEditPicker.textChanged.connect(self.on_filePickerLogFile_changed)

    def on_dirPickerOutput_changed(self, new_path):
        self.config['directories']['output'] = new_path
        #print(f"Output directory changed to: {new_path}")  # デバッグ用

    def on_dirPickerResponse_changed(self, new_path):
        self.config['directories']['response_file'] = new_path
        #print(f"Response file directory changed to: {new_path}")  # デバッグ用

    def on_dirPickerEditedOutput_changed(self, new_path):
        self.config['directories']['edited_output'] = new_path
        #print(f"Edited output directory changed to: {new_path}")  # デバッグ用

    def on_filePickerLogFile_changed(self, new_path):
        self.config['log']['file'] = new_path
        #print(f"Log file path changed to: {new_path}")  # デバッグ用



if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    settings_page = SettingspageWidget(cm)
    settings_page.show()
    sys.exit(app.exec())
