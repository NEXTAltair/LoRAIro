from PySide6.QtWidgets import QWidget, QGraphicsScene, QSizePolicy
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import Qt, QTimer, Slot
from pathlib import Path

from ImagePreviewWidget_ui import Ui_ImagePreviewWidget
class ImagePreviewWidget(QWidget, Ui_ImagePreviewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # QGraphicsScene を作成
        self.graphics_scene = QGraphicsScene()
        self.previewGraphicsView.setScene(self.graphics_scene)

        # スムーススケーリングを有効にする
        self.previewGraphicsView.setRenderHints(QPainter.RenderHint.Antialiasing 
                                               | QPainter.RenderHint.SmoothPixmapTransform)
        self.pixmap_item = None

    @Slot(Path)
    def load_image(self, image_path: Path):
        # 既存の表示をクリア
        self.graphics_scene.clear()

        # 画像を読み込み
        pixmap = QPixmap(str(image_path))

        # 画像をシーンに追加
        self.graphics_scene.addPixmap(pixmap)

        # シーンの矩形を画像のサイズに設定
        self.graphics_scene.setSceneRect(pixmap.rect())

        # サイズ調整処理を遅延
        QTimer.singleShot(0, self._adjust_view_size)

    def _adjust_view_size(self):
        # graphicsView のサイズポリシーを一時的に Ignored に設定
        self.previewGraphicsView.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        # graphicsView のサイズを表示領域のサイズに設定
        view_size = self.previewGraphicsView.viewport().size()
        self.previewGraphicsView.resize(view_size)

        # fitInView を呼び出して画像をフィット
        self.previewGraphicsView.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # resizeEvent をオーバーライドしてウィンドウサイズ変更時にサイズ調整
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_view_size()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    widget = ImagePreviewWidget()
    widget.load_image(Path(r"testimg\1_img\file01.png"))  # 画像パスを指定
    widget.show()
    app.exec()