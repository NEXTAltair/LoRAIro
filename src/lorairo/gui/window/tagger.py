from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ...annotations.caption_tags import ImageAnalyzer
from ...database.db_manager import ImageDatabaseManager
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.ImageTaggerWidget_ui import Ui_ImageTaggerWidget


class ImageTaggerWidget(QWidget, Ui_ImageTaggerWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.splitterMain.setSizes([self.splitterMain.width() // 3, self.splitterMain.width() * 2 // 3])

        self.all_webp_files = []
        self.selected_webp = []
        self.main_prompt = ""
        self.add_prompt = ""
        self.imggen_prompt = ""
        self.model_name = ""
        self.model = ""
        self.check_low_res = False
        self.image_path_id_map = {}

        # タグとキャプションの生成結果を保持するリスト {path: risult_dict}
        self.all_results = {}

    def initialize(self, cm: "ConfigManager", idm: ImageDatabaseManager):
        self.cm = cm
        self.idm = idm
        self.llm_providers = {model["provider"] for model in self.cm.llm_models}
        self.tagger_providers = {
            model["provider"] for model in self.cm.tagger_models
        }  # TODO: 変数名は後で考える プロバイダーではないよな?
        self.captioner_providers = {model["provider"] for model in self.cm.captioner_models}
        self.format_name = ["danbooru", "e621", "derpibooru"]  # TODO:そのうちDatabase参照に変更する

        self.init_ui()

    def init_ui(self):
        self.comboBoxAPI.addItems(self.llm_providers)
        self.comboBoxTagFormat.addItems(self.format_name)
        self.main_prompt = self.cm.config["prompts"]["main"]
        self.add_prompt = self.cm.config["prompts"]["additional"]
        self.textEditMainPrompt.setPlainText(self.main_prompt)
        self.textEditAddPrompt.setPlainText(self.add_prompt)
        self.DirectoryPickerSave.set_label_text("保存先:")
        self.DirectoryPickerSave.set_path(self.cm.config["directories"]["edited_output"])

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
        model_list = [model["name"] for model in self.cm.llm_models if model["provider"] == api]
        self.comboBoxModel.addItems(model_list)
        self.model_name = self.comboBoxModel.currentText()

    @Slot()
    def on_comboBoxModel_currentTextChanged(self):
        model_name = self.comboBoxModel.currentText()
        for model_id, model_info in self.cm.llm_models.items():
            if model_info["name"] == model_name:
                self.model_id = model_id
                break

    @Slot()
    def on_comboBoxTagFormat_currentTextChanged(self):
        self.format_name = self.comboBoxTagFormat.currentText()

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
        self.all_webp_files = [file for file in image_files if file.suffix == ".webp"]
        self.ThumbnailSelector.load_images(self.all_webp_files)
        if self.all_webp_files:
            self.ThumbnailSelector.select_first_image()

    @Slot(dict)
    def on_dbSearchWidget_filterApplied(self, filter_conditions: dict):
        logger.debug(f"on_dbSearchWidget_filterApplied: {filter_conditions}")
        filter_text = filter_conditions["filter_text"]
        include_untagged = filter_conditions["include_untagged"]
        include_nsfw = filter_conditions["include_nsfw"]

        tags = []
        tags = [tag.strip() for tag in filter_text.split(",")]

        filtered_images, list_count = self.idm.get_images_by_filter(
            tags=tags, include_untagged=include_untagged, include_nsfw=include_nsfw
        )

        if not filtered_images:
            logger.info(f"Tag に {filter_text} を含む検索結果がありません")
            QMessageBox.critical(self, "info", f"Tag に {filter_text} を含む検索結果がありません")

        # 重複を除いた画像のリストを作成
        unique_images = {}
        for metadata in filtered_images:
            image_id = metadata["image_id"]
            if image_id not in unique_images:
                unique_images[image_id] = Path(metadata["stored_image_path"])
        image_list = list(unique_images.values())

        self.ThumbnailSelector.load_images(image_list)
        if image_list:
            self.ThumbnailSelector.select_first_image()

    @Slot(Path)
    def single_image_selection(self, image_path: Path):
        logger.debug(f"single_image_selection: {image_path}")
        self.selected_webp = [image_path]
        self.ImagePreview.load_image(image_path)

    @Slot(list)
    def multiple_image_selection(self, image_list: list[Path]):
        logger.debug(f"multiple_image_selection: {image_list}")
        self.selected_webp = image_list
        self.ImagePreview.load_image(image_list[0])

    @Slot()
    def on_textEditMainPrompt_textChanged(self):
        self.main_prompt = self.textEditMainPrompt.toPlainText()
        self.cm.config["prompts"]["main_prompt"] = self.main_prompt

    @Slot()
    def on_textEditAddPrompt_textChanged(self):
        self.add_prompt = self.textEditAddPrompt.toPlainText()
        self.cm.config["prompts"]["additional"] = self.add_prompt

    @Slot()
    def on_textEditGenaiPrompt_textChanged(self):
        self.imggen_prompt = self.textEditAddPrompt.toPlainText()
        self.cm.config["prompts"]["imggen_prompt"] = self.imggen_prompt.strip()

    @Slot()
    def on_pushButtonGenerate_clicked(self):
        logger.info("タグとキャプションの生成を開始")
        self.ia = ImageAnalyzer()
        self.acf.initialize(self.cm.config["prompts"]["main"], self.cm.config["prompts"]["additional"])
        self.ia.initialize(self.acf, (self.cm.llm_models, self.cm.score_models))

        try:
            for i, image_path in enumerate(self.selected_webp):
                logger.info(f"{image_path.stem}の処理中")

                api_image_path = image_path
                if self.lowRescheckBox.isChecked():
                    image_id = self.idm.detect_duplicate_image(image_path)
                    if image_id is not None:  # NOTE: image_pathを上書きするとselected_webp不整合が起こる
                        api_image_path = Path(self.idm.get_low_res_image(image_id))

                result = self.ia.analyze_image(api_image_path, self.model_id, self.format_name)
                self.all_results[image_path] = result
                logger.info(f"画像 {image_path.name} のタグとキャプションの生成が完了しました")
                i += 1
                if i == len(self.selected_webp):
                    # HACK: kここから表示処理メソッド分ける？
                    tags_data = result.get("tags", [])
                    caps_data = result.get("captions", [])
                    score = result.get("score", {}).get("score", 0)
                    self.scoreSlider.setValue(int(score * 100))
                    self.scoreSlider.setToolTip(f"{score:.2f}")

                    tags_list = [tag_dict["tag"] for tag_dict in tags_data if "tag" in tag_dict]
                    combined_tags = ", ".join(tags_list)
                    self.textEditTags.setPlainText(combined_tags)

                    if caps_data:
                        for cap_dict in caps_data:
                            if "caption" in cap_dict:
                                caption_list = [
                                    cap_dict["caption"] for cap_dict in caps_data if "caption" in cap_dict
                                ]
                                combined_captions = ", ".join(caption_list)
                                self.textEditCaption.setPlainText(combined_captions)
                    else:
                        self.textEditCaption.setPlainText("No caption available")
        except Exception as e:
            logger.error(f"タグとキャプションの生成中にエラーが発生しました: {e}")
            self.textEditTags.setPlainText("Error generating tags")
            self.textEditCaption.setPlainText("Error generating caption")

    @Slot()
    def on_pushButtonSave_clicked(self):
        save_txt_on = self.checkBoxText.isChecked()
        save_json_on = self.checkBoxJson.isChecked()
        register_db_on = self.checkBoxDB.isChecked()

        if not save_txt_on and not save_json_on and not register_db_on:
            QMessageBox.warning(self, "info", "保存方法が選択されていません。")
            return

        if not self.selected_webp:
            QMessageBox.warning(self, "info", "画像が選択されていません。")
            return

        if save_txt_on or save_json_on:
            export_dir = Path(QFileDialog.getExistingDirectory(self, "保存先フォルダを選択"))
            self.DirectoryPickerSave.set_path(str(export_dir))
            if not export_dir:
                return  # キャンセルされた場合

        try:
            for image_path, result in self.all_results.items():
                if not result["tags"] and not result["captions"]:
                    QMessageBox.warning(self, "info", "タグまたはキャプションが生成されていません。")
                    return

                if image_path in self.selected_webp:
                    image_data = {
                        "path": image_path,
                        "tags": result.get("tags", []),
                        "captions": result.get("captions", []),
                    }
                    if save_txt_on:
                        FileSystemManager.export_dataset_to_txt(image_data, export_dir)
                    if save_json_on:
                        FileSystemManager.export_dataset_to_json(image_data, export_dir)
                    if register_db_on:
                        self.save_to_db()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"アノテーション保存中にエラーが発生しました: {e}")

    def save_to_db(self):
        fsm = FileSystemManager()  # TODO: 暫定後で設計から見直す
        fsm.initialize(
            Path(self.cm.config["directories"]["output"]),
            self.cm.config["image_processing"]["target_resolution"],
        )
        for image_path, result in self.all_results.items():
            image_id = self.idm.detect_duplicate_image(image_path)
            if image_id is None:
                image_id, original_metadata = self.idm.register_original_image(image_path, fsm)
                logger.info(f"ImageTaggerWidget.save_to_db {image_path.name}")

            if self.imggen_prompt:
                tag_list = [tag.strip() for tag in self.imggen_prompt.split(",") if tag.strip()]
                self.idm.register_prompt_tags(
                    image_id, tag_list
                )  # NOTE: 手入力 imggen_prompt とモデルIDが違うので別に登録
            self.idm.save_annotations(image_id, result)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from ..window.main_window import ConfigManager, MainWindow

    app = QApplication(sys.argv)
    cm = ConfigManager()
    m_window = MainWindow()
    fsm = FileSystemManager()
    idm = ImageDatabaseManager(cm.config["directories"]["database"])
    image_dir = fsm.get_image_files(Path(r"TEST\testimg\1_img"))  # 画像ファイルのディレクトリを指定
    widget = ImageTaggerWidget()
    widget.initialize(cm, idm)
    widget.load_images(image_dir)
    widget.show()
    sys.exit(app.exec())
