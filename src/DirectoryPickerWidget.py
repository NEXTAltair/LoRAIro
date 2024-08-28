from PySide6.QtWidgets import QWidget, QFileDialog
from PySide6.QtCore import Qt
from DirectoryPickerWidget_ui import Ui_DirectoryPickerWidget
from module.log import get_logger

class DirectoryPickerWidget(QWidget, Ui_DirectoryPickerWidget):
    def __init__(self, parent=None):
        self.logger = get_logger("DirectoryPickerWidget")
        super().__init__(parent)
        self.setupUi(self)
        self.set_label_text("フォルダを選択")

        self.DirectoryPicker.pushButtonPicker.clicked.connect(self.select_folder)
        self.DirectoryPicker.comboBoxHistory.currentIndexChanged.connect(self.on_history_item_selected)

    def select_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if dir_path:
            self.DirectoryPicker.lineEditPicker.setText(dir_path)
            self.DirectoryPicker.update_history(dir_path)  # 呼び出すメソッド名を修正
            self.logger.debug(f"フォルダが選択: {dir_path}")

    def on_history_item_selected(self, index):
        """履歴項目が選択されたときの処理"""
        selected_path = self.DirectoryPicker.comboBoxHistory.itemData(index, Qt.ToolTipRole)  # ツールチップデータ (フルパス) を取得
        self.DirectoryPicker.lineEditPicker.setText(selected_path)
        self.logger.debug(f"履歴からフォルダが選択: {selected_path}")

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
    from module.log import setup_logger
    logconf = {'level': 'DEBUG', 'file': 'DirectoryPickerWidget.log'}
    setup_logger(logconf)
    import sys

    app = QApplication(sys.argv)
    widget = DirectoryPickerWidget()
    widget.set_label_text("Select Folder")
    widget.show()
    sys.exit(app.exec())