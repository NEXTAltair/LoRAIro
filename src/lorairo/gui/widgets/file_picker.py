from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget

from ...utils.log import logger
from ..designer.FilePickerWidget_ui import Ui_FilePickerWidget


class FilePickerWidget(QWidget, Ui_FilePickerWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)  # type: ignore
        self.set_label_text("フォルダを選択")  # type: ignore

        self.FilePicker.pushButtonPicker.clicked.connect(self.select_file)
        self.FilePicker.comboBoxHistory.currentIndexChanged.connect(self.on_history_item_selected)

    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "ファイルを選択", "", "すべてのファイル (*)")
        if file_path:
            self.FilePicker.lineEditPicker.setText(file_path)
            self.FilePicker.update_history(file_path)  # type: ignore
            logger.debug(f"ファイル選択: {file_path}")

    def on_history_item_selected(self, index: int) -> None:
        """履歴項目が選択されたときの処理"""
        selected_path = self.FilePicker.comboBoxHistory.itemData(
            index, Qt.ItemDataRole.ToolTipRole
        )  # ツールチップデータ (フルパス) を取得
        self.FilePicker.lineEditPicker.setText(selected_path)
        logger.debug(f"履歴からファイルを選択: {selected_path}")

    def set_label_text(self, text: str) -> None:
        self.FilePicker.set_label_text(text)

    def get_selected_path(self) -> str:
        return self.FilePicker.lineEditPicker.text()

    def set_path(self, path: str | Path) -> None:
        self.FilePicker.lineEditPicker.setText(str(path))

    def on_path_changed(self, new_path: str) -> None:
        print(f"Selected file changed: {new_path}")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = FilePickerWidget()  # type: ignore
    widget.set_label_text("Select Folder")  # type: ignore
    widget.show()
    sys.exit(app.exec())
