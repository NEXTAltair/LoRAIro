from PySide6.QtWidgets import QWidget, QFileDialog, QLabel, QPushButton
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QSize
from pathlib import Path

from dataset_overview_ui import Ui_DatasetOverviewWidget
from module.file_sys import FileSystemManager
from module.config import get_config

class DatasetOverviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_DatasetOverviewWidget()
        self.ui.setupUi(self)

        # ファイルシステムの初期化UIには直接関係ない
        self.file_system_manager = FileSystemManager()
        config = get_config()
        output_dir = Path(config['directories']['output'])
        target_resolution = config['image_processing']['target_resolution']
        image_extensions = config['image_extensions']
        # TODO: 優先度: 中 処理でディレクトリを作成するのでデータセットディレクトリを指定するに不要なディレクトリを作成してしまう
        self.file_system_manager.initialize(output_dir, target_resolution, image_extensions)

        self.current_dataset_dir = None
        self.ui.selectDatasetButton.clicked.connect(self.on_select_dataset_button_clicked)

        # サムネイルの最低サイズ (例: 150x150)
        self.minimum_thumbnail_size = QSize(150, 150)

        # scrollAreaのwidgetResizableプロパティをTrueに設定
        self.ui.previewScrollArea.setWidgetResizable(True)
        self.ui.thumbnailScrollArea.setWidgetResizable(True)

        # QSplitterのストレッチファクターを設定
        self.ui.mainSplitter.setSizes([500, 500])

        # thumbnailButtonTemplate は load_dataset_info メソッドで取得する
        self.thumbnail_button_template = None

    def on_select_dataset_button_clicked(self):
        dataset_dir = QFileDialog.getExistingDirectory(self, "データセットディレクトリを選択")
        if dataset_dir:
            self.current_dataset_dir = Path(dataset_dir)
            self.ui.datasetDirLineEdit.setText(str(dataset_dir))
            self.load_dataset_info()

    def load_dataset_info(self):
        if self.current_dataset_dir:
            # thumbnailButtonTemplate を取得
            self.thumbnail_button_template = self.findChild(QPushButton, "thumbnailButtonTemplate")
            if self.thumbnail_button_template is None:
                print("エラー: thumbnailButtonTemplateが見つかりません")
                return

            try:
                image_files = self.file_system_manager.get_image_files(self.current_dataset_dir)
                self.display_dataset_info(image_files)
            except Exception as e:
                print(f"データセット読み込み中にエラーが発生しました: {e}")

    def display_dataset_info(self, image_files):
        self.clear_layout(self.ui.thumbnailLayout)  # サムネイルをクリア
        for image_path in image_files:
            self.add_thumbnail_item(image_path)
        self.update_metadata(image_files[0] if image_files else None)

    def clear_layout(self, layout):
        """レイアウト内のウィジェットを削除"""
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_thumbnail_item(self, image_path: Path):
        """サムネイルをQHBoxLayoutに追加"""
        try:
            # テンプレートボタンを複製
            button = QPushButton(self.ui.thumbnailContainer)
            button.setIconSize(self.thumbnail_button_template.iconSize())
            button.setToolTip(str(image_path))
            button.setFlat(True)  # 枠線を消す

            # ボタンクリックのシグナルをスロットに接続
            button.clicked.connect(self.onThumbnailClicked)  # 修正箇所

            pixmap = QPixmap(str(image_path))
            # 最低サイズ (例: 150x150) を維持しながら、ウィンドウサイズに合わせて拡大縮小
            scaled_pixmap = pixmap.scaledToWidth(
                max(self.ui.thumbnailContainer.width() // 4, self.minimum_thumbnail_size.width()),
                Qt.TransformationMode.SmoothTransformation
            )
            icon = QIcon(scaled_pixmap)  # アイコンを作成
            button.setIcon(icon)  # アイコンを設定

            self.ui.thumbnailLayout.addWidget(button)

        except Exception as e:
            print(f"サムネイル追加中にエラーが発生しました: {e}")

    def onThumbnailClicked(self):
        """サムネイルボタンがクリックされたときの処理"""
        clicked_button = self.sender()
        if isinstance(clicked_button, QPushButton):
            image_path = clicked_button.toolTip()
            self.update_metadata(Path(image_path))

    def calculation_aspect_ratio(self, width, height):
        # アスペクト比を計算
        # ユークリッドの互除法 で 最大公約数を求める
        def gcb(a, b):
            while b:
                a, b = b, a % b
            return a
        aspect_ratio = f"{width // gcb(width, height)} : {height // gcb(width, height)}"
        return aspect_ratio

    def update_metadata(self, image_path: Path = None):
        """メタデータを更新"""
        if image_path:
            metadata = self.file_system_manager.get_image_info(image_path)
            self.ui.fileNameValueLabel.setText(metadata['filename'])
            self.ui.imagePathValueLabel.setText(str(image_path))
            self.ui.formatValueLabel.setText(metadata['format'])
            self.ui.modeValueLabel.setText(metadata['mode'])
            self.ui.alphaChannelValueLabel.setText("あり" if metadata['has_alpha'] else "なし")
            width = metadata['width']
            height = metadata['height']
            self.ui.resolutionValueLabel.setText(f"{width} x {height}")
            aspect_ratio = self.calculation_aspect_ratio(width, height)
            self.ui.aspectRatioValueLabel.setText(aspect_ratio)
            self.ui.extensionValueLabel.setText(metadata['extension'])
            self.update_preview(image_path)  # プレビューを更新
        else:
            self.clear_metadata()

    def clear_metadata(self):
        """メタデータをクリア"""
        for label in [
            self.ui.fileNameValueLabel,
            self.ui.imagePathValueLabel,
            self.ui.formatValueLabel,
            self.ui.modeValueLabel,
            self.ui.alphaChannelValueLabel,
            self.ui.resolutionValueLabel,
            self.ui.extensionValueLabel,
            self.ui.aspectRatioValueLabel,
        ]:
            label.clear()
        self.clear_preview()  # プレビューをクリア

    def update_preview(self, image_path: Path):
        """プレビューを更新"""
        pixmap = QPixmap(str(image_path))
        scaled_pixmap = pixmap.scaled(
            self.ui.previewLabel.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.ui.previewLabel.setPixmap(scaled_pixmap)

    def clear_preview(self):
        """プレビューをクリア"""
        self.ui.previewLabel.clear()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = DatasetOverviewWidget()
    widget.show()
    sys.exit(app.exec())