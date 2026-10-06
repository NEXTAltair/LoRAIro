"""画像ごとの最新アノテーション確認結果の永続化。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from ...utils.log import logger
from ..schema import AnnotationReviewRecord
from .base import BaseRepository


@dataclass(frozen=True)
class StoredAnnotationReview:
    """セッション終了後も利用できる確認結果。checked_at は UTC。"""

    image_id: int
    fingerprint: str
    model_name: str
    warning_threshold: float
    status: str
    items_json: str
    error: str | None
    checked_at: datetime


class AnnotationReviewRepository(BaseRepository):
    """確認結果を画像ごとに 1 件保持する。項目の解釈はサービスが担当する。"""

    def save_result(
        self,
        *,
        image_id: int,
        fingerprint: str,
        model_name: str,
        warning_threshold: float,
        status: str,
        items_json: str,
        error: str | None,
    ) -> None:
        """最新結果を原子的に upsert する。元の画像やアノテーション行は変更しない。"""
        statement = insert(AnnotationReviewRecord).values(
            image_id=image_id,
            fingerprint=fingerprint,
            model_name=model_name,
            warning_threshold=warning_threshold,
            status=status,
            items_json=items_json,
            error=error,
            checked_at=datetime.now(UTC),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AnnotationReviewRecord.image_id],
            set_={
                "fingerprint": statement.excluded.fingerprint,
                "model_name": statement.excluded.model_name,
                "warning_threshold": statement.excluded.warning_threshold,
                "status": statement.excluded.status,
                "items_json": statement.excluded.items_json,
                "error": statement.excluded.error,
                "checked_at": statement.excluded.checked_at,
            },
        )
        with self.session_factory() as session:
            try:
                session.execute(statement)
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                logger.opt(exception=True).error(f"アノテーション確認結果の保存エラー: image_id={image_id}")
                raise

    def get_results(
        self, image_ids: Sequence[int] | None = None, *, limit: int | None = None
    ) -> dict[int, StoredAnnotationReview]:
        """新しい順に結果を返す。None は全画像、空リストは結果なし。limit は取得上限。"""
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if image_ids is not None and not image_ids:
            return {}

        statement = select(AnnotationReviewRecord).order_by(
            AnnotationReviewRecord.checked_at.desc(), AnnotationReviewRecord.image_id.desc()
        )
        if limit is not None:
            statement = statement.limit(limit)
        with self.session_factory() as session:
            try:
                if image_ids is None:
                    records = session.scalars(statement).all()
                    return {record.image_id: self._to_stored(record) for record in records}

                results: dict[int, StoredAnnotationReview] = {}
                ids = list(dict.fromkeys(image_ids))
                for offset in range(0, len(ids), self.BATCH_CHUNK_SIZE):
                    chunk_statement = statement.where(
                        AnnotationReviewRecord.image_id.in_(ids[offset : offset + self.BATCH_CHUNK_SIZE])
                    )
                    for record in session.scalars(chunk_statement):
                        results[record.image_id] = self._to_stored(record)
                ordered = sorted(
                    results.values(), key=lambda result: (result.checked_at, result.image_id), reverse=True
                )
                return {result.image_id: result for result in ordered[:limit]}
            except SQLAlchemyError:
                logger.opt(exception=True).error("アノテーション確認結果の取得エラー")
                raise

    @staticmethod
    def _to_stored(record: AnnotationReviewRecord) -> StoredAnnotationReview:
        # SQLite の TIMESTAMP は timezone=True でも naive datetime を返す。
        checked_at = record.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        return StoredAnnotationReview(
            image_id=record.image_id,
            fingerprint=record.fingerprint,
            model_name=record.model_name,
            warning_threshold=record.warning_threshold,
            status=record.status,
            items_json=record.items_json,
            error=record.error,
            checked_at=checked_at.astimezone(UTC),
        )
