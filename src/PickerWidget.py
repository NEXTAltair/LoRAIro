from pathlib import Path

from PySide6.QtWidgets import QWidget, QFileDialog
from PySide6.QtCore import Qt

from gui_file.PickerWidget_ui import Ui_PickerWidget

from module.log import get_logger


class PickerWidget(QWidget, Ui_PickerWidget):
    def __init__(self, parent=None):
        self.logger = get_logger("PickerWidget")
        super().__init__(parent)
        self.setupUi(self)
        self.history = []  # 履歴を保存するリスト

        self.comboBoxHistory.currentIndexChanged.connect(self.on_history_item_selected)

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

    def update_history(self, path):
        if path and path not in self.history:
            self.history.append(path)
            self.lineEditPicker.setText(path)
            # コンボボックスにdir名だけを追加
            dir_name = Path(path).name
            self.comboBoxHistory.blockSignals(True) # シグナルを無効にしないとon_history_item_selectedが呼び出されてバグる
            self.comboBoxHistory.addItem(dir_name)
            # マウスオーバーでフルパスを表示
            self.comboBoxHistory.setItemData(self.comboBoxHistory.count() - 1, path, Qt.ToolTipRole)
            self.comboBoxHistory.blockSignals(False) # シグナルを有効に戻す
            if len(self.history) > 10:
                self.history.pop(0)
                self.comboBoxHistory.removeItem(0)

    def on_history_item_selected(self, index):
        """履歴項目が選択されたときの処理"""
        selected_path = self.comboBoxHistory.itemData(index, Qt.ToolTipRole) # フルパスを取得
        self.lineEditPicker.setText(selected_path)
        self.logger.debug(f"on_history_item_selected \n 履歴からファイルを選択: {selected_path}")



if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    widget = PickerWidget()
    widget.show()
    sys.exit(app.exec())