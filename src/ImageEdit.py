from PySide6.QtWidgets import (QWidget, QFileDialog, QTableWidgetItem, QGraphicsScene, 
                               QGraphicsView, QComboBox, QPushButton, QLineEdit, QTableWidget)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt
from PySide6.QtUiTools import QUiLoader
from pathlib import Path

from ImageEdit_ui import Ui_ImageEditWidget
from module.config import get_config

class ImageEditWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_ImageEditWidget()
        self.ui.setupUi(self)

        # uiには直接関係ない設定の読み込み
        self.config = get_config()

        # シグナル/スロットを接続
        self.ui.tableWidget_ImageList.itemSelectionChanged.connect(self.update_preview)
        # ボタンクリックイベントを接続
        self.ui.pushButton_SelectDataset.clicked.connect(self.select_dataset_directory)
        self.ui.pushButton_StartProcess.clicked.connect(self.start_processing)

        self.setup_upscaler_options()

    def select_dataset_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Dataset Directory")
        if directory:
            self.ui.lineEdit_DatasetPath.setText(str(directory))
            self.load_images(directory)

    def load_images(self, directory):
        directory = Path(directory)
        self.ui.tableWidget_ImageList.setRowCount(0)
        file_list = directory.rglob('*')
        for filename in file_list:
            if filename.suffix.lower() not in self.config['image_extensions']:
                continue
            file_path = directory / filename
            str_filename = str(filename)
            str_file_path = str(file_path)
            row_position = self.ui.tableWidget_ImageList.rowCount()
            self.ui.tableWidget_ImageList.insertRow(row_position)

            # サムネイル
            # TODO: 枠に合わせて伸縮するようにする 優先度:低
            thumbnail = QPixmap(str_file_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
            thumbnail_item = QTableWidgetItem()
            thumbnail_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
            self.ui.tableWidget_ImageList.setItem(row_position, 0, thumbnail_item)

            # ファイル名
            self.ui.tableWidget_ImageList.setItem(row_position, 1, QTableWidgetItem(str_filename))

            # パス
            self.ui.tableWidget_ImageList.setItem(row_position, 2, QTableWidgetItem(str_file_path))

            # サイズ
            file_size = file_path.stat().st_size
            self.ui.tableWidget_ImageList.setItem(row_position, 3, QTableWidgetItem(f"{file_size / 1024:.2f} KB"))

            # TODO: 既存タグとキャプションの取得と表示 優先度:低
            # src.caption_tags.ImageAnalyzer.get_existing_annotations を使って取得
            # ImageAnalyzer の初期化にはAPIクライアントが必要なので処理がおもすぎるかも

    def update_preview(self):
        selected_items = self.ui.tableWidget_ImageList.selectedItems()
        if selected_items:
            file_path = selected_items[2].text()
            scene = QGraphicsScene()
            pixmap = QPixmap(file_path)
            scene.addPixmap(pixmap)
            self.ui.graphicsView_Preview.setScene(scene)
            self.ui.graphicsView_Preview.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def setup_upscaler_options(self):
        # TODO: 優先度: 低 アップスケーラーオプションを追加
        # src.ImageEditor.ImageProcessor でもまだ実装してないよ
        self.ui.comboBox_Upscaler.addItems(["RealESRGAN", "Waifu2x", "ESRGAN"])

    def start_processing(self):
        # 処理開始の実装
        selected_items = self.ui.tableWidget_ImageList.selectedItems()
        if selected_items:
            file_path = selected_items[2].text()
            resize_option = self.ui.comboBox_ResizeOption.currentText()
            upscaler = self.ui.comboBox_Upscaler.currentText()

            # ここで実際の処理を実装
            print(f"Processing {file_path} with resize option {resize_option} and upscaler {upscaler}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = ImageEditWidget()
    widget.show()
    sys.exit(app.exec())