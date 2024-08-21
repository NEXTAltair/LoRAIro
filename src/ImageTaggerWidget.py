from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from PySide6.QtCore import Slot

from ImageTaggerWidget_ui import Ui_ImageTaggerWidget
from module.file_sys import FileSystemManager
from caption_tags import ImageAnalyzer
from module.api_utils import APIClientFactory
from pathlib import Path
from module.log import get_logger

from module.db import ImageDatabaseManager

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui import ConfigManager
class ImageTaggerWidget(QWidget, Ui_ImageTaggerWidget):
    def __init__(self, parent=None):
        self.logger = get_logger(__name__)
        super().__init__(parent)
        self.setupUi(self)

        self.splitterMain.setSizes([self.splitterMain.width() // 3, self.splitterMain.width() * 2 // 3])

    def initialize(self, cm: 'ConfigManager', idm: ImageDatabaseManager):
        self.cm = cm
        self.idm = idm
        self.models = self.idm.get_models()
        self.format_name = ["danbooru", "e621", "derpibooru"] # TODO:そのうちDatabase参照に変更する
        self.all_webp_files = []
        self.selected_webp = []
        self.prompt = ""
        self.model_name = ""
        self.model = ""

        self.init_ui()

    def init_ui(self):
        self.vision_providers = list(set([model['provider'] for model in self.models if model['type'] == 'vision']))
        self.comboBoxAPI.addItems(self.vision_providers)
        self.on_comboBoxAPI_currentIndexChanged(self.comboBoxAPI.currentIndex())
        self.comboBoxTagFormat.addItems(self.format_name)
        self.main_prompt = self.cm.config['prompts']['main']
        self.add_prompt = self.cm.config['prompts']['additional']
        self.textEditMainPrompt.setPlainText(self.main_prompt)
        self.textEditAddPrompt.setPlainText(self.add_prompt)
        self.DirectoryPickerSave.set_label_text("保存先:")
        self.DirectoryPickerSave.set_path(self.cm.config['directories']['edited_output'])

        self.ThumbnailSelector.imageSelected.connect(self.single_image_selection)
        self.ThumbnailSelector.multipleImagesSelected.connect(self.multiple_image_selection)

    @Slot()
    def on_comboBoxAPI_currentIndexChanged(self, index):
        """
        comboBoxAPIのインデックスが変更されたときに呼び出されるスロット。
        """
        api = self.comboBoxAPI.itemText(index)
        self.comboBoxModel.clear()
        model_list = [model['name'] for model in self.models if model['provider'] == api]
        self.comboBoxModel.addItems(model_list)
        self.model_name = self.comboBoxModel.currentText()

    def load_images(self, image_files: list):
        """
        画像のリストをウィジェットにロードし、サムネイルとして表示します。
        トークン数節約のため.webpファイルに限定されます。
        # IDEA: トークン数節約ならあえて低解像度に落とした画像を送り込んでもいいかも
        Args:
            image_files (list[Path]): 画像のパスのリスト
        """
        self.all_webp_files = [file for file in image_files if file.suffix == '.webp']
        self.ThumbnailSelector.load_images(self.all_webp_files)
        if self.all_webp_files:
            self.ThumbnailSelector.select_first_image()

    @Slot(Path)
    def single_image_selection(self, image_path: Path):
        # print(f"スロット呼び出し: {image_path}") # デバッグ用
        self.selected_webp = [image_path]
        self.ImagePreview.load_image(image_path)

    @Slot(list)
    def multiple_image_selection(self, image_list: list[Path]):
        # print(f"スロット呼び出し: {image_path}") # デバッグ用
        self.selected_webp = image_list
        self.ImagePreview.load_image(image_list[0])

    @Slot()
    def on_textEditMainPrompt_textChanged(self):
        self.main_prompt = self.textEditMainPrompt.toPlainText()
        self.cm.config['prompts']['main'] = self.main_prompt

    @Slot()
    def on_textEditAddPrompt_textChanged(self):
        self.add_prompt = self.textEditAddPrompt.toPlainText()
        self.cm.config['prompts']['additional'] = self.add_prompt

    @Slot()
    def on_comboBoxModel_currentTextChanged(self):
        self.model = self.comboBoxModel.currentText()

    @Slot()
    def on_comboBoxTagFormat_currentTextChanged(self):
        self.format_name = self.comboBoxTagFormat.currentText()

    @Slot()
    def on_pushButtonGenerate_clicked(self):
        self.logger.info("タグとキャプションの生成を開始")
        self.ia = ImageAnalyzer()
        self.acf = APIClientFactory(self.cm.config['api'], self.models, self.main_prompt, self.add_prompt)
        self.ia.initialize(self.acf, self.models)

        self.all_tags = []  # すべての画像のタグを格納するリスト
        self.all_captions = []  # すべての画像のキャプションを格納するリスト

        try:
            for image_path in self.selected_webp:
                self.logger.info(f"{image_path.stem}の処理中")
                result = self.ia.analyze_image(image_path, self.model, self.format_name)

                tags_data = result.get("tags", [])
                captions_data = result.get("captions", [])

                tags_dict = [tag_info['tag'] for tag_info in tags_data if 'tag' in tag_info]
                self.all_tags.append(", ".join(tags_dict))  # タグをリストに追加
                self.textEditTags.setPlainText(self.all_tags[-1])  # 最後に生成されたタグを表示

                if captions_data:
                    for caption_info in captions_data:
                        if 'caption' in caption_info:
                            self.all_captions.append(caption_info['caption'])  # キャプションをリストに追加
                            self.textEditCaption.setPlainText(self.all_captions[-1])  # 最後に生成されたキャプションを表示
                            break
                else:
                    self.all_captions.append("No caption available")  # キャプションがない場合は空文字列を追加
                    self.textEditCaption.setPlainText("No caption available")

                self.logger.info(f"画像 {image_path.name} のタグとキャプションの生成が完了しました")
        except Exception as e:
            self.logger.error(f"タグとキャプションの生成中にエラーが発生しました: {e}")
            self.textEditTags.setPlainText("Error generating tags")
            self.textEditCaption.setPlainText("Error generating caption")

    @Slot()
    def on_pushButtonSave_clicked(self):
        if not self.selected_webp:
            QMessageBox.warning(self, "エラー", "画像が選択されていません。")
            return

        save_to_txt = self.checkBoxText.isChecked()
        save_to_json = self.checkBoxJson.isChecked()
        save_to_db = self.checkBoxDB.isChecked()

        # 保存先を取得 (テキストファイルとJSONファイルの場合のみ)
        if save_to_txt or save_to_json:
            save_dir = Path(QFileDialog.getExistingDirectory(self, "保存先フォルダを選択"))
            self.DirectoryPickerSave.set_path(str(save_dir))
            if not save_dir:
                return  # キャンセルされた場合

        try:
            # TODO: タグやキャプションがない場合のエラー処理を考える
            if save_to_txt:
                FileSystemManager.export_dataset_to_txt(
                    self.selected_webp, self.all_tags, self.all_captions, save_dir
                )
            if save_to_json:
                FileSystemManager.export_dataset_to_json(
                    self.selected_webp, self.all_tags, self.all_captions, save_dir
                )
            if save_to_db:
                self.save_to_db()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存中にエラーが発生しました: {e}")

    def save_to_db(self):
        # ... (データベース保存処理を実装) ...
        # TODO: タグとキャプションだけを保存するときimege_idをどうするか
        # 元画像のみDBへ保存して､idを発行させる？
        # 同一ファイルがDBへ登録済みのときの挙動は？ ハッシュを使って画像を照合すると時間がかかりすぎる
        pass


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    cm = ConfigManager()
    import sys

    app = QApplication(sys.argv)
    fsm = FileSystemManager()
    idm = ImageDatabaseManager()
    image_files = fsm.get_image_files(Path(r"testimg\1_img")) # 画像ファイルのディレクトリを指定
    widget = ImageTaggerWidget()
    widget.initialize(cm, idm)
    widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())
