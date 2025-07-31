"""
Selected Image Details Widget

選択画像の詳細情報表示とインライン編集機能を提供
画像基本情報、アノテーション概要、Rating/Score の編集機能
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import Image
from ...utils.log import logger
from ..designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from .annotation_data_display_widget import AnnotationData, AnnotationDataDisplayWidget


@dataclass
class ImageDetails:
    """選択画像の詳細情報"""

    image_id: int | None = None
    file_name: str = ""
    file_path: str = ""
    image_size: str = ""  # "1920x1080" format
    file_size: str = ""  # "2.5 MB" format
    created_date: str = ""  # "2025-07-29 15:30:00" format
    rating_value: str = ""  # "PG", "R", etc.
    score_value: int = 0  # 0-1000 range
    annotation_data: AnnotationData = None

    def __post_init__(self):
        if self.annotation_data is None:
            self.annotation_data = AnnotationData()


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
        db_manager: ImageDatabaseManager | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)

        # 依存関係
        self.db_manager = db_manager

        # 現在の画像情報
        self.current_details: ImageDetails = ImageDetails()
        self.current_image_id: int | None = None

        # 共通コンポーネント取得 - AnnotationDataDisplayWidget
        self.annotation_display: AnnotationDataDisplayWidget | None = None
        self._setup_annotation_display()

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()

        logger.debug("SelectedImageDetailsWidget initialized")

    def _setup_annotation_display(self) -> None:
        """AnnotationDataDisplayWidget を最下部に配置"""
        try:
            # 共通コンポーネントとして AnnotationDataDisplayWidget を作成
            self.annotation_display = AnnotationDataDisplayWidget(self)

            # メインレイアウトに追加
            self.verticalLayoutMain.addWidget(self.annotation_display)

            logger.debug("AnnotationDataDisplayWidget added to SelectedImageDetailsWidget")

        except Exception as e:
            logger.error(f"Error setting up annotation display: {e}", exc_info=True)

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # Rating コンボボックス変更
        self.comboBoxRating.currentTextChanged.connect(self._on_rating_changed)

        # Score スライダー変更
        self.horizontalSliderScore.valueChanged.connect(self._on_score_changed)

        # 保存ボタン
        self.pushButtonSave.clicked.connect(self._on_save_clicked)

        # アノテーション表示コンポーネントのシグナル
        if self.annotation_display:
            self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # Rating コンボボックス設定
        rating_options = ["", "PG", "PG-13", "R", "X", "XXX"]
        self.comboBoxRating.addItems(rating_options)
        self.comboBoxRating.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
        """)

        # Score スライダー設定 (0-1000 範囲)
        self.horizontalSliderScore.setMinimum(0)
        self.horizontalSliderScore.setMaximum(1000)
        self.horizontalSliderScore.setValue(0)
        self.horizontalSliderScore.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
        """)

        # スコア値ラベル
        self.labelScoreValue.setStyleSheet("font-size: 10px; font-weight: bold; color: #333;")

        # 保存ボタン
        self.pushButtonSave.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 4px 8px;
                border: 1px solid #4CAF50;
                border-radius: 3px;
                background-color: #f0f8f0;
                color: #2E7D32;
            }
            QPushButton:hover {
                background-color: #e8f5e8;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaa;
                border-color: #ddd;
            }
        """)

        # 情報ラベルスタイル
        info_label_style = "font-size: 9px; font-weight: bold; color: #333;"
        value_label_style = "font-size: 9px; color: #666;"

        # 各ラベルにスタイル適用
        for label_name in [
            "labelFileName",
            "labelImageSize",
            "labelFileSize",
            "labelCreatedDate",
        ]:
            label = getattr(self, label_name, None)
            if label:
                label.setStyleSheet(info_label_style)

        for label_name in [
            "labelFileNameValue",
            "labelImageSizeValue",
            "labelFileSizeValue",
            "labelCreatedDateValue",
        ]:
            label = getattr(self, label_name, None)
            if label:
                label.setStyleSheet(value_label_style)

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

        save_data = {
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

    def set_database_manager(self, db_manager: ImageDatabaseManager) -> None:
        """データベースマネージャー設定"""
        self.db_manager = db_manager
        logger.debug("Database manager set for SelectedImageDetailsWidget")

    def load_image_details(self, image_id: int) -> None:
        """指定画像IDの詳細情報をロード"""
        if not self.db_manager:
            logger.warning("Database manager not available for loading image details")
            return

        try:
            self.current_image_id = image_id

            # データベースから画像情報取得
            details = self._fetch_image_details(image_id)

            # UI更新
            self._update_details_display(details)

            # 現在の詳細情報保存
            self.current_details = details

            self.image_details_loaded.emit(details)
            logger.debug(f"Image details loaded for ID: {image_id}")

        except Exception as e:
            logger.error(f"Error loading image details for ID {image_id}: {e}", exc_info=True)
            self._clear_display()

    def _fetch_image_details(self, image_id: int) -> ImageDetails:
        """データベースから画像詳細情報を取得"""
        try:
            session = self.db_manager.get_session()

            with session:
                # 画像基本情報取得
                image_query = session.query(Image).filter(Image.id == image_id).first()

                if not image_query:
                    logger.warning(f"Image not found for ID: {image_id}")
                    return ImageDetails()

                # ファイル情報作成
                file_path = Path(image_query.file_path)
                file_size_bytes = image_query.file_size or 0
                file_size_mb = file_size_bytes / (1024 * 1024) if file_size_bytes > 0 else 0

                # アノテーション情報取得
                annotation_data = self._fetch_annotation_data(session, image_id)

                # Rating/Score 情報取得 (TODO: 実際のスキーマに合わせて実装)
                # 現在はプレースホルダー
                rating_value = ""
                score_value = 0

                return ImageDetails(
                    image_id=image_id,
                    file_name=file_path.name,
                    file_path=str(file_path),
                    image_size=f"{image_query.width}x{image_query.height}" if image_query.width else "-",
                    file_size=f"{file_size_mb:.2f} MB" if file_size_mb > 0 else "-",
                    created_date=image_query.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if image_query.created_at
                    else "-",
                    rating_value=rating_value,
                    score_value=score_value,
                    annotation_data=annotation_data,
                )

        except Exception as e:
            logger.error(f"Error fetching image details: {e}")
            return ImageDetails()

    def _fetch_annotation_data(self, session: Any, image_id: int) -> AnnotationData:
        """指定画像のアノテーション情報を取得"""
        try:
            # タグ取得
            tags_query = "SELECT content FROM tags WHERE image_id = ? ORDER BY created_at DESC"
            tags_result = session.execute(tags_query, (image_id,)).fetchall()
            tags = [row[0] for row in tags_result] if tags_result else []

            # キャプション取得
            caption_query = (
                "SELECT content FROM captions WHERE image_id = ? ORDER BY created_at DESC LIMIT 1"
            )
            caption_result = session.execute(caption_query, (image_id,)).fetchone()
            caption = caption_result[0] if caption_result else ""

            # スコア取得
            score_query = "SELECT value FROM scores WHERE image_id = ? ORDER BY created_at DESC LIMIT 1"
            score_result = session.execute(score_query, (image_id,)).fetchone()
            aesthetic_score = score_result[0] if score_result else None

            return AnnotationData(
                tags=tags,
                caption=caption,
                aesthetic_score=aesthetic_score,
                overall_score=0,
                score_type="Aesthetic",
            )

        except Exception as e:
            logger.error(f"Error fetching annotation data: {e}")
            return AnnotationData()

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
            if self.annotation_display and details.annotation_data:
                self.annotation_display.update_data(details.annotation_data)

        except Exception as e:
            logger.error(f"Error updating details display: {e}")

    def _update_rating_score_display(self, rating_value: str, score_value: int) -> None:
        """Rating/Score 表示を更新"""
        try:
            # シグナルブロック
            self.comboBoxRating.blockSignals(True)
            self.horizontalSliderScore.blockSignals(True)

            # Rating コンボボックス設定
            if rating_value:
                index = self.comboBoxRating.findText(rating_value)
                if index >= 0:
                    self.comboBoxRating.setCurrentIndex(index)
            else:
                self.comboBoxRating.setCurrentIndex(0)

            # Score スライダー設定
            self.horizontalSliderScore.setValue(score_value)
            self.labelScoreValue.setText(str(score_value))

        finally:
            # シグナルブロック解除
            self.comboBoxRating.blockSignals(False)
            self.horizontalSliderScore.blockSignals(False)

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
            if self.annotation_display:
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
        self.horizontalSliderScore.setEnabled(enabled)
        self.pushButtonSave.setEnabled(enabled)

        if self.annotation_display:
            self.annotation_display.setEnabled(enabled)

        if not enabled:
            logger.debug("SelectedImageDetailsWidget disabled")
        else:
            logger.debug("SelectedImageDetailsWidget enabled")
