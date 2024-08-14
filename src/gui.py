import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar
from PySide6.QtCore import Signal, Slot

from gui_ui import Ui_mainWindow
from module.config import get_config
from module.file_sys import FileSystemManager


class MainWindow(QMainWindow, Ui_mainWindow):
    _instance = None
    dataset_dir_changed = Signal(str)  # データセットディレクトリ変更シグナル

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # データセット選択用の DirectoryPickerWidget の設定
        self.datasetSelector.set_label_text("データセット:")

        # 各機能の初期化
        self.config = get_config()

        # シグナル/スロットの接続
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)
        self.datasetSelector.DirectoryPicker.lineEditPicker.textChanged.connect(self.on_dataset_dir_changed)
        self.dataset_dir_changed.connect(self.DatasetOverview.load_images)
        self.actionExit.triggered.connect(self.close)

        # スプリッターの初期サイズを設定
        self.maineindowspliter.setSizes([self.width() // 5, self.width() *4 // 5])

        # ステータスバーの初期化
        if not hasattr(self, 'statusbar') or self.statusbar is None:
            self.statusbar = QStatusBar(self)
            self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def load_images(self, directory: str):
        file_system_manager = FileSystemManager() #Initializeメソッドを実行すると無駄
        image_files = file_system_manager.get_image_files(Path(directory))
        self.DatasetOverview.load_images(file_system_manager, image_files)

    @Slot(str)
    def on_dataset_dir_changed(self, new_path):
        """データセットディレクトリが変更されたときに呼び出されるスロット"""
        print(f"データセットディレクトリが変更されました: {new_path}")
        self.load_images(new_path)  # ここで直接呼び出す

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())