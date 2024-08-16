from PySide6.QtWidgets import QWidget, QFileDialog
from DirectoryPickerWidget_ui import Ui_DirectoryPickerWidget

class DirectoryPickerWidget(QWidget, Ui_DirectoryPickerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.set_label_text("フォルダを選択")

        self.DirectoryPicker.pushButtonPicker.clicked.connect(self.select_folder)
        self.DirectoryPicker.pushButtonHistory.clicked.connect(self.DirectoryPicker.toggle_history_visibility)
        self.DirectoryPicker.pushButtonHistory.clicked.disconnect()  # 既存の接続を切断
        self.DirectoryPicker.pushButtonHistory.clicked.connect(self.DirectoryPicker.toggle_history_visibility)

    def select_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if dir_path:
            self.DirectoryPicker.lineEditPicker.setText(dir_path)
            self.DirectoryPicker.add_to_history(dir_path)

    def on_history_item_clicked(self, item):
        self.DirectoryPicker.lineEditPicker.setText(item.text())
        self.DirectoryPicker.listWidgetHistory.hide()

    def set_label_text(self, text):
        self.DirectoryPicker.set_label_text(text)

    def get_selected_path(self):
        return self.DirectoryPicker.lineEditPicker.text()

    def set_path(self, path):
        self.DirectoryPicker.lineEditPicker.setText(path)

    def on_path_changed(self, new_path):
        print(f"Selected directory changed: {new_path}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = DirectoryPickerWidget()
    widget.set_label_text("Select Folder")
    widget.show()
    sys.exit(app.exec())