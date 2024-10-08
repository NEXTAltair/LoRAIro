from pathlib import Path

from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from PySide6.QtCore import Slot

from gui_file.ImageTaggerWidget_ui import Ui_ImageTaggerWidget

from module.file_sys import FileSystemManager
from caption_tags import ImageAnalyzer
from module.api_utils import APIClientFactory
from module.log import get_logger
from module.db import ImageDatabaseManager


class ImageTaggerWidget(QWidget, Ui_ImageTaggerWidget):
    def __init__(self, parent=None):
        self.logger = get_logger("ImageTaggerWidget")
        super().__init__(parent)
        self.setupUi(self)

        self.splitterMain.setSizes([self.splitterMain.width() // 3, self.splitterMain.width() * 2 // 3])

    def initialize(self, cm: 'ConfigManager', idm: ImageDatabaseManager):
        self.cm = cm
        self.idm = idm
        self.vision_providers = list(set(model['provider'] for model in self.cm.vision_models.values()))
        self.format_name = ["danbooru", "e621", "derpibooru"] # TODO:そのうちDatabase参照に変更する
        self.all_webp_files = []
        self.selected_webp = []
        self.prompt = ""
        self.model_name = ""
        self.model = ""
        self.check_low_res = False

        self.init_ui()

    def init_ui(self):
        self.comboBoxAPI.addItems(self.vision_providers)
        self.comboBoxTagFormat.addItems(self.format_name)
        self.main_prompt = self.cm.config['prompts']['main']
        self.add_prompt = self.cm.config['prompts']['additional']
        self.textEditMainPrompt.setPlainText(self.main_prompt)
        self.textEditAddPrompt.setPlainText(self.add_prompt)
        self.DirectoryPickerSave.set_label_text("保存先:")
        self.DirectoryPickerSave.set_path(self.cm.config['directories']['edited_output'])

        self.dbSearchWidget.filterGroupBox.setTitle("Search Tag")
        self.dbSearchWidget.filterTypeWidget.hide()
        self.dbSearchWidget.countRangeWidget.hide()
        self.dbSearchWidget.resolutionWidget.hide()

        self.ThumbnailSelector.imageSelected.connect(self.single_image_selection)
        self.ThumbnailSelector.multipleImagesSelected.connect(self.multiple_image_selection)

    @Slot(int)
    def on_comboBoxAPI_currentIndexChanged(self, index: int):
        """
        comboBoxAPIのインデックスが変更されたときに呼び出されるスロット。
        """
        api = self.comboBoxAPI.itemText(index)
        self.comboBoxModel.clear()
        model_list = [model['name'] for model in self.cm.vision_models.values() if model['provider'] == api]
        self.comboBoxModel.addItems(model_list)
        self.model_name = self.comboBoxModel.currentText()

    @Slot()
    def on_comboBoxModel_currentTextChanged(self):
        model_name = self.comboBoxModel.currentText()
        for model_id, model_info in self.cm.vision_models.items():
            if model_info['name'] == model_name:
                self.model_id = model_id
                break

    @Slot()
    def on_comboBoxTagFormat_currentTextChanged(self):
        self.format_name = self.comboBoxTagFormat.currentText()

    @Slot()
    def on_lowRescheckBox_clicked(self):
        self.check_low_res = True

    def showEvent(self, event):
        """ウィジェットが表示される際に呼び出されるイベントハンドラ"""
        super().showEvent(event)
        if self.cm.dataset_image_paths:
            self.load_images(self.cm.dataset_image_paths)

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

    @Slot(dict)
    def on_dbSearchWidget_filterApplied(self, filter_conditions: dict):
        self.logger.debug(f"on_dbSearchWidget_filterApplied: {filter_conditions}")
        filter_text = filter_conditions['filter_text']
        include_untagged = filter_conditions['include_untagged']
        include_nsfw = filter_conditions['include_nsfw']

        tags = []
        tags = [tag.strip() for tag in filter_text.split(',')]

        filtered_images, list_count = self.idm.get_images_by_filter(tags=tags, include_untagged=include_untagged, include_nsfw=include_nsfw)

        if not filtered_images:
            self.logger.info(f"Tag に {filter_text} を含む検索結果がありません")
            QMessageBox.critical(self,  "info", f"Tag に {filter_text} を含む検索結果がありません")

        # 重複を除いた画像のリストを作成
        unique_images = {}
        for metadata in filtered_images:
            image_id = metadata['image_id']
            if image_id not in unique_images:
                unique_images[image_id] = Path(metadata['stored_image_path'])
        image_list = list(unique_images.values())

        self.ThumbnailSelector.load_images(image_list)
        if image_list:
            self.ThumbnailSelector.select_first_image()

    @Slot(Path)
    def single_image_selection(self, image_path: Path):
        self.logger.debug(f"single_image_selection: {image_path}")
        self.selected_webp = [image_path]
        self.ImagePreview.load_image(image_path)

    @Slot(list)
    def multiple_image_selection(self, image_list: list[Path]):
        self.logger.debug(f"multiple_image_selection: {image_list}")
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
    def on_pushButtonGenerate_clicked(self):
        self.logger.info("タグとキャプションの生成を開始")
        self.ia = ImageAnalyzer()
        self.acf = APIClientFactory(self.cm.config['api'])
        self.acf.initialize(self.cm.config['prompts']['main'], self.cm.config['prompts']['additional'])
        self.ia.initialize(self.acf, (self.cm.vision_models, self.cm.score_models))

        self.all_tags = []
        self.all_captions = []
        self.all_scores = []
        self.all_results = []
        try:
            for image_path in self.selected_webp:
                self.logger.info(f"{image_path.stem}の処理中")

                if self.check_low_res:
                    image_id = self.idm.detect_duplicate_image(image_path)
                    if image_id is None:
                        self.logger.info(f"DBに登録されていない画像です。{image_path.name}")
                    else:
                        image_path = Path(self.idm.get_low_res_image(image_id))

                result = self.ia.analyze_image(image_path, self.model_id, self.format_name)
                self.all_results.append(result)

                tags_data = result.get("tags", [])
                captions_data = result.get("captions", [])
                score = result.get('score', {}).get('score', 0)
                self.scoreSlider.setValue(int(score * 100))
                self.scoreSlider.setToolTip(f"{score:.2f}")

                tags_list = [tag_info['tag'] for tag_info in tags_data if 'tag' in tag_info]
                self.all_tags.append(", ".join(tags_list))
                self.textEditTags.setPlainText(self.all_tags[-1])  # 最後に生成されたタグを表示

                if captions_data:
                    for caption_info in captions_data:
                        if 'caption' in caption_info:
                            self.all_captions.append(caption_info['caption'])
                            self.textEditCaption.setPlainText(self.all_captions[-1])  # 最後に生成されたキャプションを表示
                            break
                else:
                    self.all_captions.append("No caption available")
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
            if not self.all_tags and not self.all_captions:
                QMessageBox.warning(self, "エラー", "タグまたはキャプションが生成されていません。")
                return

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
        fsm = FileSystemManager() # TODO: 暫定後で設計から見直す
        fsm.initialize(Path(self.cm.config['directories']['output']), self.cm.config['image_processing']['target_resolution'])
        for result in self.all_results:
            image_path = Path(result['image_path'])
            image_id = self.idm.detect_duplicate_image(image_path)
            if image_id is None:
                image_id, original_metadata = self.idm.register_original_image(image_path, fsm)
                self.logger.info(f"ImageTaggerWidget.save_to_db {image_path.name}")

            self.idm.save_annotations(image_id, result)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from gui import ConfigManager
    from module.log import setup_logger
    cm = ConfigManager()
    import sys
    setup_logger(cm.config["log"])
    logger = get_logger(__name__)
    app = QApplication(sys.argv)
    fsm = FileSystemManager()
    idm = ImageDatabaseManager()
    image_files = fsm.get_image_files(Path(r"testimg\1_img")) # 画像ファイルのディレクトリを指定
    widget = ImageTaggerWidget()
    widget.initialize(cm, idm)
    widget.load_images(image_files)
    widget.show()
    sys.exit(app.exec())
