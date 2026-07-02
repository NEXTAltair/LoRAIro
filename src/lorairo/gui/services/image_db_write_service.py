# src/lorairo/gui/services/image_db_write_service.py

from sqlalchemy.exc import SQLAlchemyError

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import (
    CaptionAnnotationData,
    RatingAnnotationData,
    ScoreAnnotationData,
    TagAnnotationData,
)
from ...utils.log import logger


class ImageDBWriteService:
    """
    画像データベース書き込みサービス（GUI専用）

    責任:
    - 画像Rating/Score/Tags/Caption情報のデータベース更新
    - GUI層でのDB書き込み操作専門化

    読み取り (詳細パネル表示) は DatasetStateManager 経由のメタデータ投影
    (ImageRepository._format_annotations_for_metadata) が担う。
    旧 get_image_details / get_annotation_data は呼び出し元ゼロの dead code
    だったため削除した (Issue #1061)。

    エラーハンドリング方針 (Issue #1062, coding-style.md Manager 層準拠):
    - ValueError (image_id 不存在) / SQLAlchemyError → False を返し呼び出し元が処理
    - それ以外の予期しない例外 (プログラミングエラー) は握りつぶさず伝播させる

    提供メソッド:
    - update_rating: Rating更新
    - update_score: Score更新
    - update_tags: Tags更新（カンマ区切り文字列）
    - update_caption: Caption更新
    """

    def __init__(self, db_manager: ImageDatabaseManager):
        """ImageDBWriteServiceコンストラクタ（SearchFilterServiceと同一パターン）"""
        self.db_manager = db_manager
        logger.debug("ImageDBWriteService initialized")

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
            self.db_manager.annotation_repo.save_annotations(
                image_id=image_id,
                annotations={"ratings": [rating_data]},
            )

            logger.info(f"Rating updated successfully for image_id {image_id}: '{rating}'")
            return True

        except ValueError:
            # save_annotations は image_id 不存在で ValueError を送出する (期待されるケース)
            logger.warning(f"Rating update skipped: image_id {image_id} not found")
            return False
        except SQLAlchemyError:
            logger.error(f"DB error updating rating for image_id {image_id}", exc_info=True)
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
                "display_score": db_score,  # 手動編集値は既に 0-10 スケール
                "is_edited_manually": True,  # 手動編集フラグ
            }

            # Repositoryの save_annotations を呼び出し
            self.db_manager.annotation_repo.save_annotations(
                image_id=image_id,
                annotations={"scores": [score_data]},
            )

            logger.info(f"Score updated successfully for image_id {image_id}: UI={score} -> DB={db_score}")
            return True

        except ValueError:
            logger.warning(f"Score update skipped: image_id {image_id} not found")
            return False
        except SQLAlchemyError:
            logger.error(f"DB error updating score for image_id {image_id}", exc_info=True)
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
                    "confidence_score": None,  # 手動編集時は信頼度スコアなし
                    "existing": False,
                    "is_edited_manually": True,
                }
                tags_data.append(tag_data)

            # Repositoryの save_annotations を呼び出し
            self.db_manager.annotation_repo.save_annotations(
                image_id=image_id,
                annotations={"tags": tags_data},
            )

            logger.info(f"Tags updated successfully for image_id {image_id}: {len(tag_list)} tags")
            return True

        except ValueError:
            logger.warning(f"Tags update skipped: image_id {image_id} not found")
            return False
        except SQLAlchemyError:
            logger.error(f"DB error updating tags for image_id {image_id}", exc_info=True)
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
                "is_edited_manually": True,
            }

            # Repositoryの save_annotations を呼び出し
            self.db_manager.annotation_repo.save_annotations(
                image_id=image_id,
                annotations={"captions": [caption_data]},
            )

            logger.info(f"Caption updated successfully for image_id {image_id}")
            return True

        except ValueError:
            logger.warning(f"Caption update skipped: image_id {image_id} not found")
            return False
        except SQLAlchemyError:
            logger.error(f"DB error updating caption for image_id {image_id}", exc_info=True)
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
            success, added_count = self.db_manager.annotation_repo.add_tag_to_images_batch(
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

        except SQLAlchemyError:
            logger.error("DB error in batch tag add", exc_info=True)
            return False

    def update_rating_batch(self, image_ids: list[int], rating: str) -> bool:
        """複数画像のRatingを一括更新

        Args:
            image_ids: 更新対象の画像IDリスト
            rating: Rating値 ("PG", "PG-13", "R", "X", "XXX")

        Returns:
            bool: 更新成功/失敗
        """
        if not image_ids:
            logger.warning("Empty image_ids for batch rating update")
            return False

        # バリデーション
        valid_ratings = ["PG", "PG-13", "R", "X", "XXX"]
        if rating not in valid_ratings:
            logger.warning(f"Invalid rating value for batch update: '{rating}'")
            return False

        try:
            model_id = self.db_manager.get_manual_edit_model_id()
            success, updated_count = self.db_manager.annotation_repo.update_rating_batch(
                image_ids=image_ids,
                rating=rating,
                model_id=model_id,
            )

            if success:
                logger.info(
                    f"Batch rating update succeeded: rating='{rating}', "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
            else:
                logger.warning(f"Batch rating update returned failure for rating='{rating}'")

            return success

        except SQLAlchemyError:
            logger.error("DB error in batch rating update", exc_info=True)
            return False

    def update_score_batch(self, image_ids: list[int], score: int) -> bool:
        """複数画像のScoreを一括更新

        Args:
            image_ids: 更新対象の画像IDリスト
            score: Score値 (0-1000範囲のUI値)

        Returns:
            bool: 更新成功/失敗
        """
        if not image_ids:
            logger.warning("Empty image_ids for batch score update")
            return False

        # バリデーション: Score値範囲チェック（UI値）
        if not (0 <= score <= 1000):
            logger.warning(f"Invalid score value for batch update: {score}")
            return False

        try:
            # UI値（0-1000）→ DB値（0.0-10.0）に変換
            db_score = score / 100.0

            model_id = self.db_manager.get_manual_edit_model_id()
            success, updated_count = self.db_manager.annotation_repo.update_score_batch(
                image_ids=image_ids,
                score=db_score,
                model_id=model_id,
            )

            if success:
                logger.info(
                    f"Batch score update succeeded: UI={score} -> DB={db_score:.2f}, "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
            else:
                logger.warning(f"Batch score update returned failure for score={score}")

            return success

        except SQLAlchemyError:
            logger.error("DB error in batch score update", exc_info=True)
            return False
