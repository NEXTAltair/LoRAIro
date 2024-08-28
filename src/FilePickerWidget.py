from PySide6.QtWidgets import QWidget, QFileDialog
from PySide6.QtCore import Qt

from FilePickerWidget_ui import Ui_FilePickerWidget
from module.log import get_logger

class FilePickerWidget(QWidget, Ui_FilePickerWidget):
    def __init__(self, parent=None):
        self.logger = get_logger("FilePickerWidget")
        super().__init__(parent)
        self.setupUi(self)
        self.set_label_text("フォルダを選択")

        self.FilePicker.pushButtonPicker.clicked.connect(self.select_file)
        self.FilePicker.comboBoxHistory.currentIndexChanged.connect(self.on_history_item_selected)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "ファイルを選択", "", "すべてのファイル (*)")
        if file_path:
            self.FilePicker.lineEditPicker.setText(file_path)
            self.FilePicker.update_history(file_path)
            self.logger.debug(f"ファイル選択: {file_path}")

    def on_history_item_selected(self, index):
        """履歴項目が選択されたときの処理"""
        selected_path = self.FilePicker.comboBoxHistory.itemData(index, Qt.ToolTipRole)  # ツールチップデータ (フルパス) を取得
        self.FilePicker.lineEditPicker.setText(selected_path)
        self.logger.debug(f"履歴からファイルを選択: {selected_path}")

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