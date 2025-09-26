"""
Selected Image Details Widget

選択画像の詳細情報表示とインライン編集機能を提供
画像基本情報、アノテーション概要、Rating/Score の編集機能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...gui.designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from .annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    ImageDetails,
)

if TYPE_CHECKING:
    from ..services.image_db_write_service import ImageDBWriteService
    from ..state.dataset_state import DatasetStateManager


class SelectedImageDetailsWidget(QWidget, Ui_SelectedImageDetailsWidget):
    """
    選択画像詳細情報ウィジェット

    機能:
    - 画像基本情報表示
    - アノテーション概要表示
    - Rating/Score のインライン編集
    - データベース保存機能
    """

    # シグナル
    image_details_loaded = Signal(ImageDetails)  # 画像詳細読み込み完了
    rating_updated = Signal(int, str)  # Rating 更新 (image_id, rating_value)
    score_updated = Signal(int, int)  # Score 更新 (image_id, score_value)
    save_requested = Signal(dict)  # 保存要求 {image_id, rating, score}

    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)

        # Phase 3.2: DB操作分離 - ImageDBWriteService依存注入パターン
        self.image_db_write_service: ImageDBWriteService | None = None

        # 現在の画像情報
        self.current_details: ImageDetails = ImageDetails()
        self.current_image_id: int | None = None

        # UIファイルの既存AnnotationDataDisplayWidgetを参照
        self.annotation_display: AnnotationDataDisplayWidget = self.annotationDataDisplay

        # UI初期化
        self._setup_connections()

        # Phase 3.3: Enhanced Event-Driven Pattern (状態管理なし)
        logger.debug("SelectedImageDetailsWidget initialized with Enhanced Event-Driven Pattern support")


    def _setup_connections(self) -> None:
        """Enhanced Event-Driven Pattern シグナル接続設定（基本接続はUIファイルで定義済み）"""
        # アノテーション表示コンポーネントのシグナル接続
        self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

    @Slot(str)
    def _on_rating_changed(self, rating_value: str) -> None:
        """Rating 変更時の処理"""
        if self.current_image_id and rating_value != self.current_details.rating_value:
            self.current_details.rating_value = rating_value
            self.rating_updated.emit(self.current_image_id, rating_value)
            logger.debug(f"Rating changed to: {rating_value}")

    @Slot(int)
    def _on_score_changed(self, score_value: int) -> None:
        """Score 変更時の処理"""
        # スコア値ラベル更新
        self.labelScoreValue.setText(str(score_value))

        if self.current_image_id and score_value != self.current_details.score_value:
            self.current_details.score_value = score_value
            self.score_updated.emit(self.current_image_id, score_value)
            logger.debug(f"Score changed to: {score_value}")

    @Slot()
    def _on_save_clicked(self) -> None:
        """保存ボタンクリック時の処理"""
        if not self.current_image_id:
            logger.warning("No image selected for save operation")
            return

        save_data: dict[str, Any] = {
            "image_id": self.current_image_id,
            "rating": self.current_details.rating_value,
            "score": self.current_details.score_value,
        }

        self.save_requested.emit(save_data)
        logger.debug(f"Save requested for image {self.current_image_id}")

    @Slot(AnnotationData)
    def _on_annotation_data_loaded(self, data: AnnotationData) -> None:
        """アノテーション表示データ読み込み完了時の処理"""
        self.current_details.annotation_data = data
        logger.debug("Annotation data loaded in details widget")

    def set_image_db_write_service(self, service: "ImageDBWriteService") -> None:
        """Phase 1-2依存注入パターン継承"""
        self.image_db_write_service = service
        logger.debug("ImageDBWriteService set for SelectedImageDetailsWidget")

    # === Phase 3.3: Enhanced Event-Driven Pattern ===

    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（状態管理なし）"""
        # 新しいデータシグナルに接続
        state_manager.current_image_data_changed.connect(self._on_image_data_received)

        logger.debug("SelectedImageDetailsWidget connected to current_image_data_changed signal")

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict[str, Any]) -> None:
        """
        画像データ受信時のメタデータ更新（純粋表示専用）

        DatasetStateManagerから直接送信される完全な画像メタデータを受信し、
        詳細情報表示を更新します。検索機能への依存を完全に排除。
        """
        try:
            logger.info(
                f"📨 SelectedImageDetailsWidget: current_image_data_changed シグナル受信 - データサイズ: {len(image_data) if image_data else 0}"
            )

            # 空データの場合は表示をクリア
            if not image_data:
                logger.debug("Empty image data received, clearing details display")
                self._clear_display()
                return

            # 画像IDを取得
            image_id = image_data.get("id")
            if not image_id:
                logger.warning(f"画像ID未設定 | メタデータ: {list(image_data.keys())}")
                self._clear_display()
                return

            logger.debug(f"🔍 画像データ受信: ID={image_id}")

            # メタデータから詳細情報を構築
            details = self._build_image_details_from_metadata(image_data)

            # UI更新
            self._update_details_display(details)

            # 現在の詳細情報保存
            self.current_details = details
            self.current_image_id = image_id

            # シグナル発行
            self.image_details_loaded.emit(details)

            logger.info(f"✅ メタデータ表示成功: ID={image_id} - Enhanced Event-Driven Pattern 完全動作")

        except Exception as e:
            logger.error(
                f"メタデータ更新エラー データ:{image_data.get('id', 'Unknown')} | エラー: {e}",
                exc_info=True,
            )
            self._clear_display()

    def _build_image_details_from_metadata(self, image_data: dict[str, Any]) -> ImageDetails:
        """メタデータから ImageDetails を構築"""
        try:
            # ファイル名の取得
            image_path_str = image_data.get("stored_image_path", "")
            file_name = Path(image_path_str).name if image_path_str else "Unknown"

            # 画像サイズの構築 (width x height)
            width = image_data.get("width", 0)
            height = image_data.get("height", 0)
            image_size = f"{width} x {height}" if width and height else "Unknown"

            # ファイルサイズの取得
            file_size_bytes = image_data.get("file_size_bytes")
            if file_size_bytes:
                # バイトを適切な単位に変換
                if file_size_bytes >= 1024 * 1024:
                    file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"
                elif file_size_bytes >= 1024:
                    file_size = f"{file_size_bytes / 1024:.1f} KB"
                else:
                    file_size = f"{file_size_bytes} bytes"
            else:
                file_size = "Unknown"

            # 作成日時の取得と文字列変換
            created_date = format_datetime_for_display(image_data.get("created_at"))

            # Rating/Score の取得
            rating_value = image_data.get("rating", "") or ""
            score_value = image_data.get("score", 0) or 0

            # ImageDetails を構築
            details = ImageDetails(
                file_name=file_name,
                image_size=image_size,
                file_size=file_size,
                created_date=created_date,
                rating_value=rating_value,
                score_value=score_value,
                annotation_data=None,  # アノテーションデータは別途取得
            )

            logger.debug(f"ImageDetails constructed from metadata: {file_name}")
            return details

        except Exception as e:
            logger.error(f"Error building ImageDetails from metadata: {e}", exc_info=True)
            return ImageDetails()

    # === Legacy Methods (移行期のサポート) ===

    def load_image_details(self, image_id: int) -> None:
        """指定画像IDの詳細情報をロード（Phase 3.2: ImageDBWriteService使用）"""
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not available for loading image details")
            return

        try:
            self.current_image_id = image_id

            # ImageDBWriteServiceから画像情報取得
            details = self.image_db_write_service.get_image_details(image_id)

            # UI更新
            self._update_details_display(details)

            # 現在の詳細情報保存
            self.current_details = details

            self.image_details_loaded.emit(details)
            logger.debug(f"Image details loaded for ID: {image_id} (via ImageDBWriteService)")

        except Exception as e:
            logger.error(f"Error loading image details for ID {image_id}: {e}", exc_info=True)
            self._clear_display()

    # Phase 3.2: DB操作分離 - 以下のメソッドはImageDBWriteServiceに移行済み
    # def _fetch_image_details(self, image_id: int) -> ImageDetails:
    #     """廃止予定: ImageDBWriteService.get_image_details()を使用"""

    # Phase 3.2: DB操作分離 - 以下のメソッドはImageDBWriteServiceに移行済み
    # def _fetch_annotation_data(self, session: Any, image_id: int) -> AnnotationData:
    #     """廃止予定: ImageDBWriteService.get_annotation_data()を使用"""

    def _update_details_display(self, details: ImageDetails) -> None:
        """詳細情報表示を更新"""
        try:
            # 画像基本情報更新
            self.labelFileNameValue.setText(details.file_name)
            self.labelImageSizeValue.setText(details.image_size)
            self.labelFileSizeValue.setText(details.file_size)
            self.labelCreatedDateValue.setText(details.created_date)

            # Rating/Score 更新
            self._update_rating_score_display(details.rating_value, details.score_value)

            # アノテーション表示更新
            if details.annotation_data:
                self.annotation_display.update_data(details.annotation_data)

        except Exception as e:
            logger.error(f"Error updating details display: {e}")

    def _update_rating_score_display(self, rating_value: str, score_value: int) -> None:
        """Rating/Score 表示を更新"""
        try:
            # シグナルブロック
            self.comboBoxRating.blockSignals(True)
            self.sliderScore.blockSignals(True)

            # Rating コンボボックス設定
            if rating_value:
                index = self.comboBoxRating.findText(rating_value)
                if index >= 0:
                    self.comboBoxRating.setCurrentIndex(index)
            else:
                self.comboBoxRating.setCurrentIndex(0)

            # Score スライダー設定
            self.sliderScore.setValue(score_value)
            self.labelScoreValue.setText(str(score_value))

        finally:
            # シグナルブロック解除
            self.comboBoxRating.blockSignals(False)
            self.sliderScore.blockSignals(False)

    def _clear_display(self) -> None:
        """表示をクリア"""
        try:
            # 基本情報クリア
            self.labelFileNameValue.setText("-")
            self.labelImageSizeValue.setText("-")
            self.labelFileSizeValue.setText("-")
            self.labelCreatedDateValue.setText("-")

            # Rating/Score クリア
            self._update_rating_score_display("", 0)

            # アノテーション表示クリア
            self.annotation_display.clear_data()

            # 現在のデータリセット
            self.current_details = ImageDetails()
            self.current_image_id = None

            logger.debug("Image details display cleared")

        except Exception as e:
            logger.error(f"Error clearing display: {e}")

    def get_current_details(self) -> ImageDetails:
        """現在表示中の詳細情報を取得"""
        return self.current_details

    def set_enabled_state(self, enabled: bool) -> None:
        """ウィジェット全体の有効/無効状態を設定"""
        self.comboBoxRating.setEnabled(enabled)
        self.sliderScore.setEnabled(enabled)
        self.pushButtonSaveRating.setEnabled(enabled)
        self.pushButtonSaveScore.setEnabled(enabled)

        self.annotation_display.setEnabled(enabled)

        if not enabled:
            logger.debug("SelectedImageDetailsWidget disabled")
        else:
            logger.debug("SelectedImageDetailsWidget enabled")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # アプリケーションのエントリポイント
    def main():
        """アプリケーションのメイン実行関数"""
        app = QApplication(sys.argv)

        # ウィジェットのインスタンスを作成
        widget = SelectedImageDetailsWidget()

        # --- テスト用のダミーデータ ---
        dummy_annotation = AnnotationData(
            tags=["tag1", "tag2", "1girl", "solo"],
            caption="A beautiful illustration of a girl.",
            aesthetic_score=6.5,
            overall_score=850,
            score_type="Aesthetic",
        )

        dummy_details = ImageDetails(
            image_id=1,
            file_name="example_image_01.png",
            image_size="512x768",
            file_size="850 KB",
            created_date="2024-05-20 14:30:00",
            rating_value="PG",
            score_value=850,
            annotation_data=dummy_annotation,
        )
        # --- ここまでダミーデータ ---

        # データをウィジェットにロード
        # 本来は image_db_write_service 経由でロードされるが、
        # 単体テストのため、内部メソッドを直接呼び出してUIを更新する
        widget.current_image_id = dummy_details.image_id
        widget.current_details = dummy_details
        widget._update_details_display(dummy_details)  # type: ignore
        widget.set_enabled_state(True)  # 最初から操作可能にする

        # ウィジェットを表示
        widget.setWindowTitle("Selected Image Details - Test")
        widget.show()

        sys.exit(app.exec())

    main()
