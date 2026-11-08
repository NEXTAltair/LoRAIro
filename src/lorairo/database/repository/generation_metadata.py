"""生成メタデータ (`generation_metadata` / `generation_metadata_sources`) の Repository (ADR 0105, #1481)。

原データは画像ごと・取得元ごとに 1 行で、一度保存したら書き換えない。解析結果は 1 画像 1 行で、
保存のたびに最新の解析結果で置き換える。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select

from ...domain.generation_metadata import GenerationMetadataResult
from ...utils.log import logger
from ..schema import GenerationMetadata, GenerationMetadataSource, Image
from .base import BaseRepository


class GenerationMetadataRepository(BaseRepository):
    """生成メタデータの原データと解析結果を保存・取得する Repository。"""

    def save_result(self, image_id: int, result: GenerationMetadataResult) -> int:
        """解析結果を保存し、`generation_metadata.id` を返す。

        原データは (取得元の種類, キー) ごとに、まだ無いものだけを追加する (既存の原データは
        書き換えない)。解析結果の行は置き換える。

        Args:
            image_id: 画像 ID (images.id)。
            result: parser の解析結果。

        Returns:
            保存した解析結果の行 ID。

        Raises:
            IntegrityError: 画像が存在しない場合 (FK 違反) など。
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                existing_keys = {
                    (kind, key)
                    for kind, key in session.execute(
                        select(
                            GenerationMetadataSource.source_kind, GenerationMetadataSource.source_key
                        ).where(GenerationMetadataSource.image_id == image_id)
                    ).all()
                }
                for source in result.sources:
                    if (source.kind, source.key) in existing_keys:
                        continue
                    session.add(
                        GenerationMetadataSource(
                            image_id=image_id,
                            source_kind=source.kind,
                            source_key=source.key,
                            raw_text=source.raw_text,
                            raw_bytes=source.raw_bytes,
                            sha256=source.sha256,
                        )
                    )

                row = session.execute(
                    select(GenerationMetadata).where(GenerationMetadata.image_id == image_id)
                ).scalar_one_or_none()
                if row is None:
                    row = GenerationMetadata(image_id=image_id)
                    session.add(row)
                self._apply_result(row, result)
                session.commit()
                row_id: int = row.id
                logger.debug(
                    f"生成メタデータを保存: image_id={image_id}, status={result.status.value}, "
                    f"tool={result.tool}"
                )
                return row_id
            except SQLAlchemyError:
                session.rollback()
                logger.opt(exception=True).error(f"生成メタデータの保存に失敗: image_id={image_id}")
                raise

    @staticmethod
    def _apply_result(row: GenerationMetadata, result: GenerationMetadataResult) -> None:
        """解析結果の値で行を上書きする (取得できなかった項目は NULL に戻す)。"""
        params = result.parameters
        row.status = result.status.value
        row.tool = result.tool
        row.parser_name = result.parser_name
        row.parser_version = result.parser_version
        row.input_sha256 = result.input_sha256
        row.error_message = result.error_message
        # server_default は INSERT 時だけ効くため、置き換えのたびに解析日時を更新する
        row.analyzed_at = datetime.datetime.now(datetime.UTC)
        row.positive_prompt = params.positive_prompt if params else None
        row.negative_prompt = params.negative_prompt if params else None
        row.model_name = params.model_name if params else None
        row.model_hash = params.model_hash if params else None
        row.seed = params.seed if params else None
        row.steps = params.steps if params else None
        row.sampler = params.sampler if params else None
        row.cfg_scale = params.cfg_scale if params else None
        row.loras_json = (
            json.dumps([asdict(lora) for lora in params.loras], ensure_ascii=False)
            if params and params.loras
            else None
        )
        row.extra_json = json.dumps(params.extra, ensure_ascii=False) if params and params.extra else None

    def get_by_image_id(self, image_id: int) -> GenerationMetadata | None:
        """画像の解析結果を返す。未解析なら None。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(GenerationMetadata).where(GenerationMetadata.image_id == image_id)
                return session.execute(stmt).scalar_one_or_none()
            except SQLAlchemyError:
                logger.opt(exception=True).error(f"生成メタデータの取得に失敗: image_id={image_id}")
                raise

    def get_sources(self, image_id: int) -> list[GenerationMetadataSource]:
        """画像の原データを保存順に返す。無ければ空リスト。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(GenerationMetadataSource)
                    .where(GenerationMetadataSource.image_id == image_id)
                    .order_by(GenerationMetadataSource.id)
                )
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError:
                logger.opt(exception=True).error(f"生成メタデータの原データ取得に失敗: image_id={image_id}")
                raise

    def get_analyzed_image_ids(self, image_ids: list[int]) -> set[int]:
        """指定した画像のうち、解析結果がある画像 ID の集合を返す。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        if not image_ids:
            return set()
        analyzed: set[int] = set()
        with self.session_factory() as session:
            try:
                for start in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[start : start + self.BATCH_CHUNK_SIZE]
                    stmt = select(GenerationMetadata.image_id).where(GenerationMetadata.image_id.in_(chunk))
                    analyzed.update(session.execute(stmt).scalars().all())
                return analyzed
            except SQLAlchemyError:
                logger.opt(exception=True).error("解析済み画像 ID の取得に失敗")
                raise

    def get_unanalyzed_image_ids(self, limit: int, after_id: int = 0) -> list[int]:
        """解析結果が無い画像 ID を、``after_id`` より大きいものから ID 順に最大 ``limit`` 件返す。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(Image.id)
                    .outerjoin(GenerationMetadata, GenerationMetadata.image_id == Image.id)
                    .where(GenerationMetadata.id.is_(None), Image.id > after_id)
                    .order_by(Image.id)
                    .limit(limit)
                )
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError:
                logger.opt(exception=True).error("未解析の画像 ID の取得に失敗")
                raise

    def count_unanalyzed_images(self) -> int:
        """解析結果が無い画像の件数を返す。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(func.count(Image.id))
                    .outerjoin(GenerationMetadata, GenerationMetadata.image_id == Image.id)
                    .where(GenerationMetadata.id.is_(None))
                )
                return int(session.execute(stmt).scalar_one())
            except SQLAlchemyError:
                logger.opt(exception=True).error("未解析の画像件数の取得に失敗")
                raise
