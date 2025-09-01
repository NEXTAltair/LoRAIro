from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QSizePolicy, QWidget

from ...utils.log import logger
from ...gui.ui.ImagePreview_ui import Ui_ImagePreviewWidget

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


class ImagePreviewWidget(QWidget, Ui_ImagePreviewWidget):
    """DatasetStateManager統合対応プレビューウィジェット"""

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
        self.pixmap_item: QGraphicsPixmapItem | None = None

        # Phase 3.3: DatasetStateManager統合
        self.state_manager: DatasetStateManager | None = None
        self._current_image_id: int | None = None

        logger.debug("ImagePreviewWidget initialized with DatasetStateManager support")

    @Slot(Path)
    def load_image(self, image_path: Path) -> None:
        """パスベースで画像を読み込む（動的パス解決対応・メモリ最適化）"""
        # Phase 3.3: メモリ最適化 - 既存の表示をクリアしてリソース解放
        self._clear_preview()

        try:
            # 画像を読み込み
            pixmap = QPixmap(str(image_path))

            # 画像をシーンに追加
            self.pixmap_item = self.graphics_scene.addPixmap(pixmap)

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_path.name} を プレビュー領域に表示")
        except Exception as e:
            logger.error(f"画像の読み込みに失敗しました: {image_path}, エラー: {e}")
            self._clear_preview()

    def load_image_from_pil(self, pil_image: Image.Image, image_name: str = "Unknown") -> None:
        """PILイメージオブジェクトから直接画像を読み込む（メモリ最適化）"""
        # Phase 3.3: メモリ最適化 - 既存の表示をクリアしてリソース解放
        self._clear_preview()

        try:
            # PILイメージをQPixmapに変換
            pixmap = self._pil_to_qpixmap(pil_image)

            # PixmapがNull（変換失敗）でないことを確認
            if pixmap.isNull():
                logger.warning(f"Failed to convert PIL image to pixmap: {image_name}")
                return

            # 画像をシーンに追加
            self.pixmap_item = self.graphics_scene.addPixmap(pixmap)

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_name} を プレビュー領域に表示（PILイメージから）")
        except Exception as e:
            logger.error(f"PILイメージの読み込みに失敗しました: {image_name}, エラー: {e}")
            self._clear_preview()

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

    # === Phase 3.3: DatasetStateManager統合メソッド ===

    def set_dataset_state_manager(self, state_manager: "DatasetStateManager") -> None:
        """状態管理統合"""
        # 既存の接続があれば切断
        if self.state_manager:
            self.state_manager.current_image_changed.disconnect(self._on_current_image_changed)

        self.state_manager = state_manager

        # シグナル接続
        self.state_manager.current_image_changed.connect(self._on_current_image_changed)

        logger.debug("DatasetStateManager connected to ImagePreviewWidget")

        # 現在の画像があれば即座に表示
        if self.state_manager.current_image_id:
            self._on_current_image_changed(self.state_manager.current_image_id)

    @Slot(int)
    def _on_current_image_changed(self, image_id: int) -> None:
        """状態変更時の自動プレビュー更新"""
        try:
            if not self.state_manager:
                logger.warning("DatasetStateManager not available for preview update")
                return

            # 同じ画像の場合はスキップ（無駄な再描画を防ぐ）
            if self._current_image_id == image_id:
                logger.debug(f"Same image ID {image_id}, skipping reload")
                return

            # 画像データを取得
            image_data = self.state_manager.get_image_by_id(image_id)
            if not image_data:
                logger.warning(f"Image data not found for ID: {image_id}")
                self._clear_preview()
                return

            # ファイルパスを取得
            image_path_str = image_data.get("stored_image_path")
            if not image_path_str:
                logger.warning(f"Image path not found for ID: {image_id}")
                self._clear_preview()
                return

            # プレビュー更新
            image_path = Path(image_path_str)
            self.load_image(image_path)

            # 現在のIDを更新
            self._current_image_id = image_id

            logger.debug(f"Preview updated for image ID: {image_id}")

        except Exception as e:
            logger.error(f"Error updating preview for image ID {image_id}: {e}", exc_info=True)
            self._clear_preview()

    def _clear_preview(self) -> None:
        """プレビューをクリア（メモリ最適化）"""
        try:
            # GraphicsSceneをクリアしてメモリを解放
            self.graphics_scene.clear()

            # PixmapItemの参照もクリア
            self.pixmap_item = None

            # 現在のIDもクリア
            self._current_image_id = None

            logger.debug("Preview cleared and memory optimized")

        except Exception as e:
            logger.error(f"Error clearing preview: {e}", exc_info=True)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget = ImagePreviewWidget()
    widget.load_image(Path("tests/resources/img/1_img/file01.webp"))  # 画像パスを指定
    widget.show()
    app.exec()
