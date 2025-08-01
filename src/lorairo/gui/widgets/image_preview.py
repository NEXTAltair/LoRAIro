from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QGraphicsScene, QSizePolicy, QWidget

from ...utils.log import logger
from ..designer.ImagePreviewWidget_ui import Ui_ImagePreviewWidget


class ImagePreviewWidget(QWidget, Ui_ImagePreviewWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)

        # QGraphicsScene を作成
        self.graphics_scene = QGraphicsScene()
        self.previewGraphicsView.setScene(self.graphics_scene)

        # スムーススケーリングを有効にする
        self.previewGraphicsView.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.pixmap_item = None

    @Slot(Path)
    def load_image(self, image_path: Path) -> None:
        """パスベースで画像を読み込む（動的パス解決対応）"""
        # 既存の表示をクリア
        self.graphics_scene.clear()

        try:
            # パスを動的に解決
            from ...database.db_core import resolve_stored_path

            resolved_path = resolve_stored_path(str(image_path))

            # 画像を読み込み
            pixmap = QPixmap(str(resolved_path))

            # 画像をシーンに追加
            self.graphics_scene.addPixmap(pixmap)

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_path.name} を プレビュー領域に表示")
        except Exception as e:
            logger.error(f"画像の読み込みに失敗しました: {image_path}, エラー: {e}")

    def load_image_from_pil(self, pil_image: Image.Image, image_name: str = "Unknown") -> None:
        """PILイメージオブジェクトから直接画像を読み込む"""
        # 既存の表示をクリア
        self.graphics_scene.clear()

        try:
            # PILイメージをQPixmapに変換
            pixmap = self._pil_to_qpixmap(pil_image)

            # 画像をシーンに追加
            self.graphics_scene.addPixmap(pixmap)

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_name} を プレビュー領域に表示（PILイメージから）")
        except Exception as e:
            logger.error(f"PILイメージの読み込みに失敗しました: {image_name}, エラー: {e}")

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """PILイメージをQPixmapに変換"""
        # RGBまたはRGBAモードに変換
        if pil_image.mode not in ["RGB", "RGBA"]:
            pil_image = pil_image.convert("RGB")

        # PILイメージをバイト配列に変換
        import io

        byte_array = io.BytesIO()
        pil_image.save(byte_array, format="PNG")
        byte_array.seek(0)

        # QPixmapとして読み込み
        pixmap = QPixmap()
        pixmap.loadFromData(byte_array.getvalue())
        return pixmap

    def _adjust_view_size(self) -> None:
        # graphicsView のサイズポリシーを一時的に Ignored に設定
        self.previewGraphicsView.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        # graphicsView のサイズを表示領域のサイズに設定
        view_size = self.previewGraphicsView.viewport().size()
        self.previewGraphicsView.resize(view_size)

        # fitInView を呼び出して画像をフィット
        self.previewGraphicsView.fitInView(
            self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

    # resizeEvent をオーバーライドしてウィンドウサイズ変更時にサイズ調整
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_view_size()


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget = ImagePreviewWidget()
    widget.load_image(Path(r"testimg\1_img\file01.png"))  # 画像パスを指定
    widget.show()
    app.exec()
