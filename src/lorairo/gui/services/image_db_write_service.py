# src/lorairo/gui/services/image_db_write_service.py

from pathlib import Path

from ...database.db_manager import ImageDatabaseManager
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from ..widgets.annotation_data_display_widget import AnnotationData, ImageDetails


class ImageDBWriteService:
    """
    画像データベース書き込みサービス（GUI専用）

    責任:
    - 単一画像の詳細情報取得
    - 画像Rating/Score情報のデータベース更新
    - アノテーション情報の取得
    - GUI層でのDB書き込み操作専門化

    Phase 1-2で確立されたSearchFilterServiceパターンを継承し、
    Read/Write分離による美しい対称性を実現
    """

    def __init__(self, db_manager: ImageDatabaseManager):
        """ImageDBWriteServiceコンストラクタ（SearchFilterServiceと同一パターン）"""
        self.db_manager = db_manager
        logger.debug("ImageDBWriteService initialized")

    def get_image_details(self, image_id: int) -> ImageDetails:
        """
        単一画像の詳細情報取得（SelectedImageDetailsWidget._fetch_image_detailsから移行）

        Args:
            image_id: 取得対象の画像ID

        Returns:
            ImageDetails: 画像詳細情報
        """
        try:
            # ImageRepositoryを通じて画像メタデータを取得
            image_metadata = self.db_manager.repository.get_image_metadata(image_id)

            if not image_metadata:
                logger.warning(f"Image not found for ID: {image_id}")
                return ImageDetails()

            # ファイル情報作成
            file_path = Path(image_metadata.get("stored_image_path", ""))
            file_size_bytes = image_metadata.get("file_size", 0)
            file_size_mb = file_size_bytes / (1024 * 1024) if file_size_bytes > 0 else 0

            # アノテーション情報取得
            annotation_data = self.get_annotation_data(image_id)

            # Rating/Score 情報取得 (FIXME: Issue #4参照 - 実際のスキーマに合わせて実装)
            # 現在はプレースホルダー
            rating_value = ""
            score_value = 0

            result = ImageDetails(
                image_id=image_id,
                file_name=file_path.name,
                file_path=str(file_path),
                image_size=f"{image_metadata.get('width', 0)}x{image_metadata.get('height', 0)}"
                if image_metadata.get("width")
                else "-",
                file_size=f"{file_size_mb:.2f} MB" if file_size_mb > 0 else "-",
                created_date=format_datetime_for_display(image_metadata.get("created_at")),
                rating_value=rating_value,
                score_value=score_value,
                annotation_data=annotation_data,
            )

            logger.debug(f"Image details retrieved for ID: {image_id}")
            return result

        except Exception as e:
            logger.error(f"Error fetching image details for ID {image_id}: {e}", exc_info=True)
            return ImageDetails()

    def get_annotation_data(self, image_id: int) -> AnnotationData:
        """
        単一画像のアノテーション情報取得（SelectedImageDetailsWidget._fetch_annotation_dataから移行）

        Args:
            image_id: 取得対象の画像ID

        Returns:
            AnnotationData: アノテーション情報
        """
        try:
            # ImageRepositoryを通じてアノテーション情報を取得
            annotations = self.db_manager.repository.get_image_annotations(image_id)

            # タグ情報取得
            tags_data = annotations.get("tags", [])
            tags = [tag_item.get("content", "") for tag_item in tags_data] if tags_data else []

            # キャプション情報取得（最新のもの）
            captions_data = annotations.get("captions", [])
            caption = captions_data[0].get("content", "") if captions_data else ""

            # スコア情報取得（最新のもの）
            scores_data = annotations.get("scores", [])
            aesthetic_score = scores_data[0].get("value") if scores_data else None

            result = AnnotationData(
                tags=tags,
                caption=caption,
                aesthetic_score=aesthetic_score,
                overall_score=0,
                score_type="Aesthetic",
            )

            logger.debug(f"Annotation data retrieved for ID: {image_id}")
            return result

        except Exception as e:
            logger.error(f"Error fetching annotation data for ID {image_id}: {e}", exc_info=True)
            return AnnotationData()

    def update_rating(self, image_id: int, rating: str) -> bool:
        """
        Rating情報をデータベースに書き込み

        Args:
            image_id: 更新対象の画像ID
            rating: Rating値 ("PG", "R", "X", など)

        Returns:
            bool: 更新成功/失敗
        """
        try:
            # FIXME: Issue #4参照 - 実際のRating更新機能を実装
            # 現在はプレースホルダー実装
            logger.info(f"Rating update requested for image_id {image_id}: '{rating}'")

            # ImageRepositoryを通じてDB更新を行う
            # 例: self.db_manager.repository.save_annotations(image_id, {"ratings": [...]})

            logger.debug(f"Rating updated successfully for image_id {image_id}: '{rating}'")
            return True

        except Exception as e:
            logger.error(f"Error updating rating for image_id {image_id}: {e}", exc_info=True)
            return False

    def update_score(self, image_id: int, score: int) -> bool:
        """
        Score情報をデータベースに書き込み

        Args:
            image_id: 更新対象の画像ID
            score: Score値 (0-1000範囲)

        Returns:
            bool: 更新成功/失敗
        """
        try:
            if not (0 <= score <= 1000):
                logger.warning(f"Invalid score value: {score}. Must be between 0-1000")
                return False

            # FIXME: Issue #4参照 - 実際のScore更新機能を実装
            # 現在はプレースホルダー実装
            logger.info(f"Score update requested for image_id {image_id}: {score}")

            # ImageRepositoryを通じてDB更新を行う
            # 例: self.db_manager.repository.save_annotations(image_id, {"scores": [...]})

            logger.debug(f"Score updated successfully for image_id {image_id}: {score}")
            return True

        except Exception as e:
            logger.error(f"Error updating score for image_id {image_id}: {e}", exc_info=True)
            return False
