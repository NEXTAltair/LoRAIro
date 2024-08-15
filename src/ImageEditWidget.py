from PySide6.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from pathlib import Path

from ImageEditWidget_ui import Ui_ImageEditWidget
from module.file_sys import FileSystemManager

class ImageEditWidget(QWidget, Ui_ImageEditWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        header = self.tableWidgetImageList.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

        # シグナル/スロット接続
        self.tableWidgetImageList.itemSelectionChanged.connect(self.update_preview)
        self.pushButtonStartProcess.clicked.connect(self.start_processing)

    @Slot(list)
    def load_images(self, image_extensions: list, image_paths: list):
        self.image_extensions = image_extensions
        self.tableWidgetImageList.setRowCount(0)
        for file_path in image_paths:
            if file_path.suffix.lower() not in self.image_extensions:
                continue
            self._add_image_to_table(file_path)

    @Slot()
    def update_preview(self):
        selected_items = self.tableWidgetImageList.selectedItems()
        if selected_items:
            row = self.tableWidgetImageList.currentRow()  # 選択されている行のインデックスを取得
            file_path = self.tableWidgetImageList.item(row, 2).text()  # 3列目からファイルパスを取得
            self.ImagePreview.load_image(Path(file_path))  # ImagePreview の load_image を呼び出す

    def _add_image_to_table(self, file_path: Path):
        str_filename = str(file_path.name)
        str_file_path = str(file_path)
        row_position = self.tableWidgetImageList.rowCount()
        self.tableWidgetImageList.insertRow(row_position)

        # サムネイル
        thumbnail = QPixmap(str_file_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
        thumbnail_item = QTableWidgetItem()
        thumbnail_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        self.tableWidgetImageList.setItem(row_position, 0, thumbnail_item)

        # ファイル名
        self.tableWidgetImageList.setItem(row_position, 1, QTableWidgetItem(str_filename))

        # パス
        self.tableWidgetImageList.setItem(row_position, 2, QTableWidgetItem(str_file_path))

        # サイズ
        file_size = file_path.stat().st_size
        self.tableWidgetImageList.setItem(row_position, 3, QTableWidgetItem(f"{file_size / 1024:.2f} KB"))

    def start_processing(self):
        # TODO: 優先度: 高 ここで実際の処理を実装
        pass

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    fsm = FileSystemManager()
    image_paths = fsm.get_image_files(Path(r"testimg\1_img")) # 画像ファイルのディレクトリを指定
    widget = ImageEditWidget()
    widget.load_images(fsm.image_extensions, image_paths)
    widget.show()
    sys.exit(app.exec())