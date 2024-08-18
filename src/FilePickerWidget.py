from PySide6.QtWidgets import QWidget, QFileDialog
from FilePickerWidget_ui import Ui_FilePickerWidget

class FilePickerWidget(QWidget, Ui_FilePickerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.set_label_text("フォルダを選択")

        self.FilePicker.pushButtonPicker.clicked.connect(self.select_file)
        self.FilePicker.pushButtonHistory.clicked.connect(self.FilePicker.toggle_history_visibility)
        self.FilePicker.pushButtonHistory.clicked.disconnect()  # 既存の接続を切断
        self.FilePicker.pushButtonHistory.clicked.connect(self.FilePicker.toggle_history_visibility)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "ファイルを選択", "", "すべてのファイル (*)")
        if file_path:
            self.FilePicker.lineEditPicker.setText(file_path)
            self.FilePicker.add_to_history(file_path)

    def on_history_item_clicked(self, item):
        self.FilePicker.lineEditPicker.setText(item.text())
        self.FilePicker.listWidgetHistory.hide()

    def set_label_text(self, text):
        self.FilePicker.set_label_text(text)

    def get_selected_path(self):
            return self.FilePicker.lineEditPicker.text()

    def set_path(self, path):
        self.FilePicker.lineEditPicker.setText(path)

    def on_path_changed(self, new_path):
        print(f"Selected file changed: {new_path}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = FilePickerWidget()
    widget.set_label_text("Select Folder")
    widget.show()
    sys.exit(app.exec())