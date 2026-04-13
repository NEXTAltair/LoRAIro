from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QPainter, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QWidget

from ...gui.designer.ImagePreviewWidget_ui import Ui_ImagePreviewWidget
from ...utils.log import logger

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

        # Phase 3.3: Enhanced Event-Driven Pattern (状態管理なし)

        logger.debug("ImagePreviewWidget initialized with Enhanced Event-Driven Pattern support")

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
        # pixmap_item が None の場合はスキップ（sceneRect が (0,0,0,0) の状態での縮小を防ぐ）
        if self.pixmap_item is not None:
            self.previewGraphicsView.fitInView(
                self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
            )

    # resizeEvent をオーバーライドしてウィンドウサイズ変更時にサイズ調整
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_view_size()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._adjust_view_size()

    # === Phase 3.3: Enhanced Event-Driven Pattern ===

    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（状態管理なし）

        接続経路の詳細をログに記録し、問題診断を可能にする。
        connect()の戻り値を検証し、接続失敗を検出する。

        Args:
            state_manager: DatasetStateManagerインスタンス
        """
        logger.info(
            f"🔌 connect_to_data_signals() 呼び出し開始 - "
            f"widget instance: {id(self)}, state_manager: {id(state_manager)}"
        )

        if not state_manager:
            logger.error("❌ DatasetStateManager is None - 接続中止")
            return

        # シグナル接続（戻り値を確認）
        connection = state_manager.current_image_data_changed.connect(self._on_image_data_received)
        connection_valid = bool(connection)

        logger.info(f"📊 connect()戻り値: valid={connection_valid}, type={type(connection)}")

        if not connection_valid:
            logger.error("❌ Qt接続失敗 - connect()が無効なConnectionを返しました")
            return

        logger.info(
            f"✅ current_image_data_changed シグナル接続完了 - from {id(state_manager)} to {id(self)}"
        )

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict) -> None:
        """
        画像データ受信時のプレビュー更新（純粋表示専用）

        DatasetStateManagerから直接送信される完全な画像メタデータを受信し、
        プレビュー表示を更新します。検索機能への依存を完全に排除。
        """
        try:
            logger.info(
                f"📨 ImagePreviewWidget: current_image_data_changed シグナル受信 - データサイズ: {len(image_data) if image_data else 0}"
            )

            # 空データの場合はプレビューをクリア
            if not image_data:
                logger.debug("Empty image data received, clearing preview")
                self._clear_preview()
                return

            # 画像IDを取得（ログ用）
            image_id = image_data.get("id", "Unknown")
            logger.debug(f"🔍 画像データ受信: ID={image_id}")

            # ファイルパスを取得
            image_path_str = image_data.get("stored_image_path")
            if not image_path_str:
                logger.warning(f"画像パス未設定 ID:{image_id} | メタデータ: {list(image_data.keys())}")
                self._clear_preview()
                return

            # プレビュー更新（LoRAIro標準パス解決使用）
            from ...database.db_core import resolve_stored_path

            image_path = resolve_stored_path(image_path_str)
            if not image_path.exists():
                logger.warning(f"画像ファイル不存在 ID:{image_id} | パス: {image_path}")
                self._clear_preview()
                return

            self.load_image(image_path)

            logger.info(
                f"✅ プレビュー表示成功: ID={image_id}, path={image_path.name} - Enhanced Event-Driven Pattern 完全動作"
            )

        except Exception as e:
            logger.error(
                f"プレビュー更新エラー データ:{image_data.get('id', 'Unknown')} | エラー: {e}",
                exc_info=True,
            )
            self._clear_preview()

    def _clear_preview(self) -> None:
        """プレビューをクリア（メモリ最適化）"""
        try:
            # GraphicsSceneをクリアしてメモリを解放
            self.graphics_scene.clear()

            # PixmapItemの参照もクリア
            self.pixmap_item = None

            logger.debug("Preview cleared and memory optimized")

        except Exception as e:
            logger.error(f"Error clearing preview: {e}", exc_info=True)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget = ImagePreviewWidget()
    widget.resize(800, 600)
    widget.show()
    widget.load_image(Path("tests/resources/img/1_img/file01.webp"))
    app.exec()
