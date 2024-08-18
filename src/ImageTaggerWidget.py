from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Slot

from ImageTaggerWidget_ui import Ui_ImageTaggerWidget
from module.file_sys import FileSystemManager
from caption_tags import ImageAnalyzer
from module.db import ImageDatabaseManager
from module.api_utils import APIClientFactory
from pathlib import Path
from module.log import get_logger

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Slot
from pathlib import Path
from ImageTaggerWidget_ui import Ui_ImageTaggerWidget
from module.db import ImageDatabaseManager

class ImageTaggerWidget(QWidget, Ui_ImageTaggerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)
        self.setupUi(self)

    def initialize(self, config: dict, idm: ImageDatabaseManager):
        self.config = config
        self.idm = idm
        self.models = self.idm.get_models()
        self.idm = idm
        self.webp_file = None
        self.prompt = ""
        self.model_name = ""
        self.model = ""

        self.init_ui()

    def init_ui(self):
        self.vision_providers = list(set([model['provider'] for model in self.models if model['type'] == 'vision']))
        self.main_prompt = self.config['prompts']['main']
        self.add_prompt = self.config['prompts']['additional']
        self.prompt = self.main_prompt + "\n" + self.add_prompt
        self.textEditPrompt.setPlainText(self.prompt)
        self.comboBoxAPI.addItems(self.vision_providers)
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
        print(f"スロット呼び出し: {image_path}") # デバッグ用
        self.webp_file = image_path
        self.ImagePreview.load_image(image_path)

    def send_vision_prompt(self):
        self.prompt = self.textEditPrompt.toPlainText()

    def send_vision_model(self):
        self.model = self.comboBoxModel.currentText()

    @Slot()
    def on_pushButtonGenerate_clicked(self):
        self.logger.info("タグとキャプションの生成を開始")
        # print("Generate tags and caption:")
        # print(f"Model: {self.model}")
        # print(f"Prompt: {self.prompt}")
        # print(f"Image: {self.webp_file}")
        self.ia = ImageAnalyzer()
        self.acf = APIClientFactory(self.config['api'], self.models, self.main_prompt, self.add_prompt)
        self.ia.initialize(self.acf, self.models)
        try:
            # ImageAnalyzerを使用して画像を分析
            result = self.ia.analyze_image(self.webp_file, self.model)

            # 結果をテキストエディットに表示
            tags_data = result.get("tags", [])
            captions_data = result.get("captions", [])

            # タグの抽出
            tags = [tag_info['tag'] for tag_info in tags_data if 'tag' in tag_info]
            self.textEditTags.setPlainText(", ".join(tags))

            # キャプションの抽出
            if captions_data:
                caption = captions_data[0].get('caption', '')  # 例として最初のキャプションを使用
                self.textEditCaption.setPlainText(caption)
            else:
                self.textEditCaption.setPlainText("No caption available")

            self.logger.info("タグとキャプションの生成が完了しました")
        except Exception as e:
            self.logger.error(f"タグとキャプションの生成中にエラーが発生しました: {e}")
            self.textEditTags.setPlainText("Error generating tags")
            self.textEditCaption.setPlainText("Error generating caption")

    @Slot()
    def save_tags_and_caption(self):
        # タグとキャプションを保存する処理
        pass

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from module.config import get_config
    config = get_config()
    import sys

    app = QApplication(sys.argv)
    fsm = FileSystemManager()
    idm = ImageDatabaseManager()
    image_files = fsm.get_image_files(Path(r"testimg\1_img")) # 画像ファイルのディレクトリを指定
    widget = ImageTaggerWidget()
    widget.initialize(config, idm)
    widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())
