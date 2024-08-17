from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Slot
from PySide6.QtGui import QIcon

from ImageTaggerWidget_ui import Ui_ImageTaggerWidget
from module.file_sys import FileSystemManager
# from module.image_analyzer import ImageAnalyzer
from module.db import ImageDatabaseManager
from pathlib import Path


from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Slot
from pathlib import Path
from ImageTaggerWidget_ui import Ui_ImageTaggerWidget
from module.db import ImageDatabaseManager

class ImageTaggerWidget(QWidget, Ui_ImageTaggerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.idm = ImageDatabaseManager()
        self.models = self.idm.get_models()
        self.webp_file = None
        self.prompt = ""
        self.model_name = ""
        self.model = ""

        self.init_ui()

    def init_ui(self):
        vision_providers = list(set([model['provider'] for model in self.models if model['type'] == 'vision']))
        self.comboBoxAPI.addItems(vision_providers)
        self.update_model_options(self.comboBoxAPI.currentIndex())

        # シグナル/スロット接続
        self.comboBoxAPI.currentIndexChanged.connect(self.update_model_options)
        self.ThumbnailSelector.imageSelected.connect(self.image_selected)
        self.pushButtonSave.clicked.connect(self.save_tags_and_caption)

    def update_model_options(self, index):
        api = self.comboBoxAPI.itemText(index)
        self.comboBoxModel.clear()
        model_list = [model['name'] for model in self.models if model['provider'] == api]
        self.comboBoxModel.addItems(model_list)
        self.model_name = self.comboBoxModel.currentText()

    def load_images(self, image_files: list):
        self.webp_files = [file for file in image_files if file.suffix == '.webp']
        self.ThumbnailSelector.load_images(self.webp_files)
        if self.webp_files:
            self.ThumbnailSelector.select_first_image()

    @Slot(Path)
    def image_selected(self, image_path: Path):
        self.webp_file = image_path
        self.ImagePreview.load_image(image_path)

    def send_vision_prompt(self):
        self.prompt = self.textEditPrompt.toPlainText()

    def send_vision_model(self):
        self.model = self.comboBoxModel.currentText()

    def generate_tags_and_caption(self):
        print("Generate tags and caption:")
        print(f"Model: {self.model}")
        print(f"Prompt: {self.prompt}")
        print(f"Image: {self.webp_file}")
        # タグとキャプションを生成する処理
        # APIリクエストを送信
        # 結果をテキストエディットに表示

    def save_tags_and_caption(self):
        # タグとキャプションを保存する処理
        pass

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    fsm = FileSystemManager()
    image_files = fsm.get_image_files(Path(r"testimg\1_img")) # 画像ファイルのディレクトリを指定
    widget = ImageTaggerWidget()

    widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())
