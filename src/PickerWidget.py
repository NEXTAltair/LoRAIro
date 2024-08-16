from PySide6.QtWidgets import QWidget, QFileDialog, QListWidgetItem
from PickerWidget_ui import Ui_PickerWidget  # ここでUIファイルをインポートします

class PickerWidget(QWidget, Ui_PickerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.listWidgetHistory.hide()  # 履歴ウィジェットを非表示にする
        self.history = []  # 履歴を保存するリスト

    def configure(self, label_text="Select File"):
        self.set_label_text(label_text)

    def set_label_text(self, text):
        self.labelPicker.setText(text)

    def set_button_text(self, text):
        self.pushButtonPicker.setText(text)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*);;Text Files (*.txt)")
        if file_path:
            self.lineEditPicker.setText(file_path)
            self.history.append(file_path)

    def select_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.lineEditPicker.setText(dir_path)
            self.history.append(dir_path)

    def toggle_history_visibility(self):
        if self.listWidgetHistory.isVisible():
            self.listWidgetHistory.hide()
        else:
            self.update_history_list()
            self.listWidgetHistory.show()

    def update_history_list(self):
        self.listWidgetHistory.clear()
        for item in reversed(self.history):
            self.listWidgetHistory.addItem(item)

    def add_to_history(self, path):
        if path and path not in self.history:
            self.history.append(path)
            if len(self.history) > 10:  # 履歴の最大数を制限
                self.history.pop(0)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    widget = PickerWidget()
    widget.show()
    sys.exit(app.exec())