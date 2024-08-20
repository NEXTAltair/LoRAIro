from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Slot, Signal, QThread
from DatasetExportWidget_ui import Ui_DatasetExportWidget
from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from caption_tags import ImageAnalyzer
from module.log import get_logger
from pathlib import Path

class ExportWorker(QThread):
    """
    データセットのエクスポート処理を行うワーカースレッド。

    Signals:
        progress (int): エクスポートの進捗状況を0-100のパーセンテージで通知します。
        finished: エクスポート処理が完了したことを通知します。
        error (str): エクスポート処理中にエラーが発生したことを通知します。
    """
    progress = Signal(int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, export_function, *args):
        """
        ExportWorkerの初期化。

        Args:
            export_function: エクスポート処理を行う関数。
            *args: export_functionに渡す引数。
        """
        super().__init__()
        self.export_function = export_function
        self.args = args

    def run(self):
        """
        エクスポート処理を実行します。
        処理の進捗、完了、エラーを適切なシグナルで通知します。
        """
        try:
            self.export_function(*self.args, progress_callback=self.progress.emit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class DatasetExportWidget(QWidget, Ui_DatasetExportWidget):
    """
    データセットのエクスポート機能を提供するウィジェット。

    このウィジェットは、画像データセットのフィルタリング、選択、エクスポートの
    機能を提供します。ユーザーはフィルタ条件を設定し、エクスポート形式を選択して
    データセットをエクスポートすることができます。
    """

    def __init__(self, parent=None):
        """
        DatasetExportWidgetの初期化。

        Args:
            parent (QWidget, optional): 親ウィジェット。デフォルトはNone。
        """
        super().__init__(parent)
        self.setupUi(self)
        self.logger = get_logger(__name__)
        self.fsm = FileSystemManager()
        self.idm = ImageDatabaseManager()
        self.ia = ImageAnalyzer()

        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        """UIの初期設定を行います。"""
        self.exportDirectoryPicker.set_label_text("Export Directory:")
        self.exportProgressBar.setVisible(False)

    def connect_signals(self):
        """シグナルとスロットの接続を行います。"""
        self.exportButton.clicked.connect(self.on_exportButton_clicked)
        self.applyFilterButton.clicked.connect(self.apply_filters)
        self.thumbnailSelector.imageSelected.connect(self.on_thumbnail_selected)

    @Slot()
    def on_exportButton_clicked(self):
        """
        エクスポートボタンがクリックされたときの処理を行います。
        エクスポートディレクトリの選択とエクスポート形式の確認を行い、
        エクスポート処理を開始します。
        """
        export_directory = self.exportDirectoryPicker.get_selected_path()
        if not export_directory:
            QMessageBox.warning(self, "Warning", "Please select an export directory.")
            return

        export_formats = []
        if self.checkBoxTxtCap.isChecked():
            export_formats.append("txt_cap")
        if self.checkBoxJson.isChecked():
            export_formats.append("json")

        if not export_formats:
            QMessageBox.warning(self, "Warning", "Please select at least one export format.")
            return

        self.start_export(export_directory, export_formats)

    def start_export(self, export_dir: str, export_formats: list):
        """
        エクスポート処理を開始します。

        Args:
            export_dir (str): エクスポート先ディレクトリのパス。
            export_formats (list): エクスポート形式のリスト。
        """
        self.exportButton.setEnabled(False)
        self.exportProgressBar.setVisible(True)
        self.statusLabel.setText("Status: Exporting...")

        selected_images = self.thumbnailSelector.get_selected_images()
        self.export_worker = ExportWorker(
            self.export_dataset, export_dir, selected_images, export_formats
        )
        self.export_worker.progress.connect(self.update_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

    def export_dataset(self, export_dir: str, images: list, formats: list, progress_callback):
        """
        データセットのエクスポート処理を行います。

        Args:
            export_dir (str): エクスポート先ディレクトリのパス。
            images (list): エクスポートする画像のリスト。
            formats (list): エクスポート形式のリスト。
            progress_callback (function): 進捗状況を通知するためのコールバック関数。
        """
        total_images = len(images)
        for i, image in enumerate(images):
            if "txt_cap" in formats:
                self.export_txt_cap(export_dir, image)
            if "json" in formats:
                self.export_json(export_dir, image)
            progress_callback(int((i + 1) / total_images * 100))

    def export_txt_cap(self, export_dir: str, image: Path):
        """
        画像をtxtとcaptionファイル形式でエクスポートします。

        Args:
            export_dir (str): エクスポート先ディレクトリのパス。
            image (Path): エクスポートする画像のパス。
        """
        # TODO: 実装する

    def export_json(self, export_dir: str, image: Path):
        """
        画像をJSON形式でエクスポートします。

        Args:
            export_dir (str): エクスポート先ディレクトリのパス。
            image (Path): エクスポートする画像のパス。
        """
        # TODO: 実装する

    @Slot(int)
    def update_progress(self, value: int):
        """
        エクスポートの進捗状況を更新します。

        Args:
            value (int): 進捗状況を表す0-100のパーセンテージ値。
        """
        self.exportProgressBar.setValue(value)

    @Slot()
    def on_export_finished(self):
        """エクスポート処理が完了したときの処理を行います。"""
        self.exportButton.setEnabled(True)
        self.exportProgressBar.setVisible(False)
        self.statusLabel.setText("Status: Export completed")
        QMessageBox.information(self, "Success", "Dataset export completed successfully.")

    @Slot(str)
    def on_export_error(self, error_message: str):
        """
        エクスポート処理中にエラーが発生したときの処理を行います。

        Args:
            error_message (str): エラーメッセージ。
        """
        self.exportButton.setEnabled(True)
        self.exportProgressBar.setVisible(False)
        self.statusLabel.setText("Status: Export failed")
        QMessageBox.critical(self, "Error", f"An error occurred during export: {error_message}")

    @Slot()
    def apply_filters(self):
        """
        ユーザーが設定したフィルタ条件を適用し、画像一覧を更新します。

        このメソッドは以下の処理を行います：
        1. filterTypeComboBoxから現在選択されているフィルタタイプを取得します（例：'Tags'または'Caption'）。
        2. filterLineEditからユーザーが入力したフィルタテキストを取得します。
        3. resolutionComboBoxから選択された解像度を取得します（例：'512x512'）。
        4. ImageDatabaseManagerのget_images_by_filterメソッドを呼び出し、
           指定されたフィルタ条件に基づいて画像をフィルタリングします。
        5. フィルタリングされた画像リストでupdate_thumbnail_selectorを呼び出し、
           ThumbnailSelectorWidgetの表示を更新します。

        注意：このメソッドは、フィルタ適用ボタンがクリックされたときに呼び出されます。
        """
        filter_type = self.filterTypeComboBox.currentText()
        filter_text = self.filterLineEdit.text()
        resolution = self.resolutionComboBox.currentText()

        filtered_images = self.idm.get_images_by_filter(
            filter_type, filter_text, resolution
        )
        self.update_thumbnail_selector(filtered_images)

    def update_thumbnail_selector(self, images):
        """
        ThumbnailSelectorWidgetの表示を更新し、フィルタリングされた画像を表示します。

        このメソッドは以下の処理を行います：
        1. ThumbnailSelectorWidgetの内容をリセットします。これは scene.clear() と
           thumbnail_items リストのクリアによって行われます。
        2. 提供された画像リストの各要素に対して：
           - 画像の'path'キーを使用してパスを取得します。
           - ThumbnailSelectorWidgetのadd_thumbnail_itemメソッドを呼び出し、
             新しいサムネイルを追加します。
        3. サムネイルのレイアウトを更新します。
        4. update_image_count_labelメソッドを呼び出し、画像数の表示を更新します。

        Args:
            images: フィルタリングされた画像のリスト。各要素は辞書形式で、
                    少なくとも'path'キーを含む必要があります。
                    例：[{'path': Path('/path/to/image1.jpg')}, {'path': Path('/path/to/image2.jpg')}]

        注意：
        - このメソッドは、フィルタが適用されたとき、または画像リストが
          更新されたときに呼び出されます。
        - ThumbnailSelectorWidgetの実装に依存するため、その内部構造が
          変更された場合、このメソッドも適宜更新する必要があります。
        """
        self.thumbnailSelector.scene.clear()
        self.thumbnailSelector.thumbnail_items.clear()

        button_width = self.thumbnailSelector.thumbnail_size.width()
        grid_width = self.thumbnailSelector.scrollAreaThumbnails.viewport().width()
        column_count = max(grid_width // button_width, 1)

        for i, image in enumerate(images):
            self.thumbnailSelector.add_thumbnail_item(image['path'], i, column_count)

        self.thumbnailSelector.update_thumbnail_layout()
        self.update_image_count_label(len(images))

    def update_image_count_label(self, count):
        """
        画面上の画像数表示ラベル（imageCountLabel）を更新します。

        このメソッドは以下の処理を行います：
        1. ImageDatabaseManagerのget_total_image_countメソッドを呼び出し、
           データベース内の総画像数を取得します。
        2. 引数で渡された現在の選択（フィルタリング）された画像数と、
           総画像数を組み合わせて新しいラベルテキストを生成します。
        3. imageCountLabelのテキストを更新します。

        Args:
            count (int): 現在選択されている（フィルタリングされた）画像の数。

        表示例：
            "Selected Images: 50 / Total Images: 1000"

        注意：このメソッドは、画像リストが更新されるたびに呼び出されます。
              これにより、ユーザーは常に現在の選択状態と全体の画像数を把握できます。
        """
        total = self.idm.get_total_image_count()
        self.imageCountLabel.setText(f"Selected Images: {count} / Total Images: {total}")

    @Slot(Path)
    def on_thumbnail_selected(self, image_path: Path):
        """
        サムネイルが選択されたときの処理を行います。

        Args:
            image_path (Path): 選択された画像のパス。
        """
        self.imagePreview.load_image(image_path)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = DatasetExportWidget()
    widget.show()
    sys.exit(app.exec())