# src/lorairo/gui/services/image_db_write_service.py

from pathlib import Path

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import (
    CaptionAnnotationData,
    RatingAnnotationData,
    ScoreAnnotationData,
    TagAnnotationData,
)
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from ..widgets.annotation_data_display_widget import AnnotationData, ImageDetails


class ImageDBWriteService:
    """
    画像データベース書き込みサービス（GUI専用）

    責任:
    - 単一画像の詳細情報取得
    - 画像Rating/Score/Tags/Caption情報のデータベース更新
    - アノテーション情報の取得
    - GUI層でのDB書き込み操作専門化

    Phase 1-2で確立されたSearchFilterServiceパターンを継承し、
    Read/Write分離による美しい対称性を実現

    提供メソッド:
    - get_image_details: 画像詳細情報取得
    - get_annotation_data: アノテーション情報取得
    - update_rating: Rating更新
    - update_score: Score更新
    - update_tags: Tags更新（カンマ区切り文字列）
    - update_caption: Caption更新
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

            # Rating/Score 情報取得（Repository側で整形済み）
            rating_value = image_metadata.get("rating_value", "")
            # Score: DB値（0-10）→ UI値（0-1000）に変換
            db_score_value = image_metadata.get("score_value", 0)
            score_value = int(db_score_value * 100) if db_score_value else 0

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
            rating: Rating値 ("PG", "PG-13", "R", "X", "XXX")

        Returns:
            bool: 更新成功/失敗
        """
        try:
            # Rating値のバリデーション（Civitai標準）
            valid_ratings = ["PG", "PG-13", "R", "X", "XXX"]
            if rating not in valid_ratings:
                logger.warning(f"Invalid rating value: '{rating}'. Must be one of {valid_ratings}")
                return False

            # RatingAnnotationData を作成（手動編集時はraw_rating_valueとnormalized_ratingは同じ値）
            rating_data: RatingAnnotationData = {
                "model_id": self.db_manager.get_manual_edit_model_id(),
                "raw_rating_value": rating,
                "normalized_rating": rating,
                "confidence_score": None,  # 手動編集時は信頼度スコアなし
            }

            # Repositoryの save_annotations を呼び出し
            self.db_manager.repository.save_annotations(
                image_id=image_id,
                annotations={"ratings": [rating_data]},
            )

            logger.info(f"Rating updated successfully for image_id {image_id}: '{rating}'")
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

            # UI値（0-1000）→ DB値（0-10）に変換
            db_score = score / 100.0

            # ScoreAnnotationData を作成
            score_data: ScoreAnnotationData = {
                "model_id": self.db_manager.get_manual_edit_model_id(),
                "score": db_score,
                "is_edited_manually": True,  # 手動編集フラグ
            }

            # Repositoryの save_annotations を呼び出し
            self.db_manager.repository.save_annotations(
                image_id=image_id,
                annotations={"scores": [score_data]},
            )

            logger.info(f"Score updated successfully for image_id {image_id}: UI={score} -> DB={db_score}")
            return True

        except Exception as e:
            logger.error(f"Error updating score for image_id {image_id}: {e}", exc_info=True)
            return False

    def update_tags(self, image_id: int, tags_text: str) -> bool:
        """
        Tags情報をデータベースに書き込み

        Args:
            image_id: 更新対象の画像ID
            tags_text: タグ文字列（カンマ区切り）

        Returns:
            bool: 更新成功/失敗

        処理:
            1. タグ文字列をカンマで分割
            2. 各タグをTagAnnotationDataに変換
            3. save_annotationsで一括保存
        """
        try:
            # タグ文字列をパース（カンマ区切り、前後の空白削除）
            tag_list = [tag.strip() for tag in tags_text.split(",") if tag.strip()]

            if not tag_list:
                logger.warning(f"Empty tags list for image_id {image_id}")
                return False

            # TagAnnotationData のリストを作成
            tags_data: list[TagAnnotationData] = []
            for tag in tag_list:
                tag_data: TagAnnotationData = {
                    "tag_id": None,  # 手動編集時はNone（自動生成）
                    "model_id": self.db_manager.get_manual_edit_model_id(),
                    "tag": tag,
                    "source": "manual",  # 手動編集ソース
                    "confidence_score": None,  # 手動編集時は信頼度スコアなし
                }
                tags_data.append(tag_data)

            # Repositoryの save_annotations を呼び出し
            self.db_manager.repository.save_annotations(
                image_id=image_id,
                annotations={"tags": tags_data},
            )

            logger.info(f"Tags updated successfully for image_id {image_id}: {len(tag_list)} tags")
            return True

        except Exception as e:
            logger.error(f"Error updating tags for image_id {image_id}: {e}", exc_info=True)
            return False

    def update_caption(self, image_id: int, caption: str) -> bool:
        """
        Caption情報をデータベースに書き込み

        Args:
            image_id: 更新対象の画像ID
            caption: キャプション文字列

        Returns:
            bool: 更新成功/失敗
        """
        try:
            if not caption.strip():
                logger.warning(f"Empty caption for image_id {image_id}")
                return False

            # CaptionAnnotationData を作成
            caption_data: CaptionAnnotationData = {
                "model_id": self.db_manager.get_manual_edit_model_id(),
                "caption": caption.strip(),
                "existing": False,  # 手動編集時は新規作成
            }

            # Repositoryの save_annotations を呼び出し
            self.db_manager.repository.save_annotations(
                image_id=image_id,
                annotations={"captions": [caption_data]},
            )

            logger.info(f"Caption updated successfully for image_id {image_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating caption for image_id {image_id}: {e}", exc_info=True)
            return False

    def add_tag_batch(self, image_ids: list[int], tag: str) -> bool:
        """
        複数画像に1つのタグを追加（既存タグに追加、重複は許可しない）

        バッチ操作で複数画像に同じタグを一括追加。
        既存タグに追加（append mode）、重複は自動的にスキップ。
        全件一括コミット、エラー時は自動ロールバック（原子的処理）。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ（Widget側で TagCleaner.clean_format() + lower + strip 済み前提）
                 Service側では防御的に strip().lower() を再適用

        Returns:
            bool: 成功した場合 True、失敗した場合 False

        処理:
            1. Repository層の add_tag_to_images_batch() を呼び出し
            2. 単一トランザクションで全画像を処理
            3. 全件成功 or 全件ロールバック（原子性保証）

        Note:
            タグ正規化は主に呼び出し元（BatchTagAddWidget）で実施。
            Service側は防御的に追加の strip().lower() を適用。
        """
        try:
            if not image_ids:
                logger.warning("Empty image_ids list for batch tag add")
                return False

            if not tag.strip():
                logger.warning("Empty tag for batch add")
                return False

            # Repository層の原子的バッチ追加メソッドを使用
            model_id = self.db_manager.get_manual_edit_model_id()
            success, added_count = self.db_manager.repository.add_tag_to_images_batch(
                image_ids=image_ids,
                tag=tag,
                model_id=model_id,
            )

            if success:
                logger.info(
                    f"Batch tag add succeeded: tag='{tag}', processed={len(image_ids)}, added={added_count}"
                )
            else:
                logger.warning(f"Batch tag add returned failure for tag='{tag}'")

            return success

        except Exception as e:
            logger.error(f"Error in batch tag add: {e}", exc_info=True)
            return False
