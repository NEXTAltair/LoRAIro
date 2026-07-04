"""Provider Batch 永続化担当 Repository (ADR 0035 §1)。

`db_repository.py` god class 分割の段階 6 として、Provider Batch API
(`ProviderBatchJob` / `ProviderBatchItem` / `ProviderBatchArtifact`) の CRUD を
本 Repository に集約する。

管轄 entity:
  - `ProviderBatchJob` (provider 別バッチジョブのライフサイクル + 統計)
  - `ProviderBatchItem` (job 配下の per-image item 状態)
  - `ProviderBatchArtifact` (job 入出力のファイル成果物 metadata)

カバー領域:
  - Job CRUD: 作成 / 取得 / 一覧 / 更新 / 削除 (cascade items + artifacts)
  - Item CRUD: 作成 / 一覧 / custom_id ベースの更新 (単体 / 一括)
  - Artifact CRUD: 作成 / 一覧 (artifact_type フィルタ対応)
  - 許可フィールド whitelist による安全な更新
    (`PROVIDER_BATCH_JOB_UPDATE_FIELDS`, `PROVIDER_BATCH_ITEM_UPDATE_FIELDS`)

段階 1 で確立した `BaseRepository` (`session_factory` + `BATCH_CHUNK_SIZE`) を継承する。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, cast

from sqlalchemy import delete, func, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ...utils.log import logger
from ..schema import (
    ProviderBatchArtifact,
    ProviderBatchArtifactData,
    ProviderBatchItem,
    ProviderBatchItemData,
    ProviderBatchJob,
    ProviderBatchJobData,
)
from .base import BaseRepository


class ProviderBatchRepository(BaseRepository):
    """Provider Batch API 関連 entity の永続化を担当する Repository (ADR 0035)。

    管轄 entity:
      - `ProviderBatchJob`
      - `ProviderBatchItem`
      - `ProviderBatchArtifact`
    """

    PROVIDER_BATCH_JOB_UPDATE_FIELDS: ClassVar[set[str]] = {
        "provider_job_id",
        "status",
        "provider_status",
        "endpoint",
        "model_id",
        "request_count",
        "succeeded_count",
        "failed_count",
        "canceled_count",
        "expired_count",
        "submitted_at",
        "completed_at",
        "canceled_at",
        "imported_at",
        "expires_at",
        "input_artifact_path",
        "output_artifact_path",
        "error_artifact_path",
        "raw_provider_payload",
    }
    PROVIDER_BATCH_ITEM_UPDATE_FIELDS: ClassVar[set[str]] = {
        "image_id",
        "model_id",
        "task_type",
        "status",
        "error_type",
        "error_message",
        "raw_request",
        "raw_response",
    }

    # --- Provider Batch Job CRUD ---

    def create_provider_batch_job(self, data: ProviderBatchJobData) -> int:
        """Provider Batch API job を作成する。"""
        with self.session_factory() as session:
            try:
                job = ProviderBatchJob(**data)
                session.add(job)
                session.flush()
                job_id = job.id
                session.commit()
                logger.debug(
                    f"Provider batch job を作成しました: ID={job_id}, "
                    f"provider={job.provider}, status={job.status}",
                )
                return job_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Provider batch job 作成中にエラーが発生しました: {e}")
                raise

    def create_provider_batch_job_with_items(
        self,
        job_data: ProviderBatchJobData,
        items_data: list[ProviderBatchItemData],
    ) -> int:
        """Provider Batch API job と item 群を単一 transaction で作成する。"""
        with self.session_factory() as session:
            try:
                job = ProviderBatchJob(**job_data)
                session.add(job)
                session.flush()
                job_id = job.id
                for item_data in items_data:
                    item_values = dict(item_data)
                    item_values["job_id"] = job_id
                    session.add(ProviderBatchItem(**item_values))
                session.commit()
                logger.debug(
                    f"Provider batch job/items を作成しました: ID={job_id}, "
                    f"provider={job.provider}, status={job.status}, items={len(items_data)}",
                )
                return job_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(
                    f"Provider batch job/items 作成中にエラーが発生しました: {e}"
                )
                raise

    def get_provider_batch_job(self, job_id: int) -> ProviderBatchJob | None:
        """Provider Batch API job を ID で取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchJob)
                    .options(
                        selectinload(ProviderBatchJob.model),
                        selectinload(ProviderBatchJob.items),
                        selectinload(ProviderBatchJob.artifacts),
                    )
                    .where(ProviderBatchJob.id == job_id)
                )
                return session.execute(stmt).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(f"Provider batch job 取得中にエラーが発生しました: {e}")
                raise

    def get_provider_batch_job_by_provider_id(
        self,
        provider: str,
        provider_job_id: str,
    ) -> ProviderBatchJob | None:
        """provider と provider_job_id で Provider Batch API job を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = select(ProviderBatchJob).where(
                    ProviderBatchJob.provider == provider,
                    ProviderBatchJob.provider_job_id == provider_job_id,
                )
                return session.execute(stmt).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(
                    f"Provider batch job provider ID 取得中にエラーが発生しました: {e}"
                )
                raise

    def list_provider_batch_jobs(
        self,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProviderBatchJob]:
        """Provider Batch API job 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = select(ProviderBatchJob).order_by(ProviderBatchJob.created_at.desc())
                if provider is not None:
                    stmt = stmt.where(ProviderBatchJob.provider == provider)
                if status is not None:
                    stmt = stmt.where(ProviderBatchJob.status == status)
                stmt = stmt.limit(limit).offset(offset)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(
                    f"Provider batch job 一覧取得中にエラーが発生しました: {e}"
                )
                raise

    def update_provider_batch_job(self, job_id: int, updates: dict[str, Any]) -> bool:
        """Provider Batch API job を更新する。許可フィールドのみ更新対象。"""
        invalid_fields = set(updates) - self.PROVIDER_BATCH_JOB_UPDATE_FIELDS
        if invalid_fields:
            raise ValueError(f"更新できない provider batch job フィールド: {sorted(invalid_fields)}")
        if not updates:
            return False

        with self.session_factory() as session:
            try:
                stmt = (
                    update(ProviderBatchJob)
                    .where(ProviderBatchJob.id == job_id)
                    .values(**updates, updated_at=func.now())
                )
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Provider batch job 更新中にエラーが発生しました: {e}")
                raise

    def delete_provider_batch_job(self, job_id: int) -> bool:
        """Provider Batch API job を削除する。items / artifacts は cascade される。"""
        with self.session_factory() as session:
            try:
                session.execute(delete(ProviderBatchArtifact).where(ProviderBatchArtifact.job_id == job_id))
                session.execute(delete(ProviderBatchItem).where(ProviderBatchItem.job_id == job_id))
                stmt = delete(ProviderBatchJob).where(ProviderBatchJob.id == job_id)
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Provider batch job 削除中にエラーが発生しました: {e}")
                raise

    # --- Provider Batch Item CRUD ---

    def create_provider_batch_item(self, data: ProviderBatchItemData) -> int:
        """Provider Batch API job item を作成する。"""
        with self.session_factory() as session:
            try:
                item = ProviderBatchItem(**data)
                session.add(item)
                session.flush()
                item_id = item.id
                session.commit()
                return item_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Provider batch item 作成中にエラーが発生しました: {e}")
                raise

    def list_provider_batch_items(
        self,
        job_id: int,
        status: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[ProviderBatchItem]:
        """Provider Batch API job item 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchItem)
                    .where(ProviderBatchItem.job_id == job_id)
                    .order_by(ProviderBatchItem.id)
                )
                if status is not None:
                    stmt = stmt.where(ProviderBatchItem.status == status)
                stmt = stmt.limit(limit).offset(offset)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(
                    f"Provider batch item 一覧取得中にエラーが発生しました: {e}"
                )
                raise

    def update_provider_batch_item_by_custom_id(
        self,
        job_id: int,
        custom_id: str,
        updates: dict[str, Any],
    ) -> bool:
        """job_id + custom_id で Provider Batch API job item を更新する。"""
        invalid_fields = set(updates) - self.PROVIDER_BATCH_ITEM_UPDATE_FIELDS
        if invalid_fields:
            raise ValueError(f"更新できない provider batch item フィールド: {sorted(invalid_fields)}")
        if not updates:
            return False

        with self.session_factory() as session:
            try:
                stmt = (
                    update(ProviderBatchItem)
                    .where(
                        ProviderBatchItem.job_id == job_id,
                        ProviderBatchItem.custom_id == custom_id,
                    )
                    .values(**updates, updated_at=func.now())
                )
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Provider batch item 更新中にエラーが発生しました: {e}")
                raise

    def update_provider_batch_items_by_custom_id(
        self,
        job_id: int,
        updates_by_custom_id: Mapping[str, Mapping[str, Any]],
    ) -> set[str]:
        """job_id + custom_id ごとの Provider Batch API job item 更新を 1 transaction で反映する。"""
        for updates in updates_by_custom_id.values():
            invalid_fields = set(updates) - self.PROVIDER_BATCH_ITEM_UPDATE_FIELDS
            if invalid_fields:
                raise ValueError(f"更新できない provider batch item フィールド: {sorted(invalid_fields)}")
        if not updates_by_custom_id:
            return set()

        with self.session_factory() as session:
            try:
                updated_custom_ids: set[str] = set()
                for custom_id, updates in updates_by_custom_id.items():
                    if not updates:
                        continue
                    stmt = (
                        update(ProviderBatchItem)
                        .where(
                            ProviderBatchItem.job_id == job_id,
                            ProviderBatchItem.custom_id == custom_id,
                        )
                        .values(**dict(updates), updated_at=func.now())
                    )
                    result = cast(CursorResult[Any], session.execute(stmt))
                    if result.rowcount:
                        updated_custom_ids.add(custom_id)
                session.commit()
                return updated_custom_ids
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(
                    f"Provider batch item 一括更新中にエラーが発生しました: {e}"
                )
                raise

    # --- Provider Batch Artifact CRUD ---

    def create_provider_batch_artifact(self, data: ProviderBatchArtifactData) -> int:
        """Provider Batch API job artifact を作成する。"""
        with self.session_factory() as session:
            try:
                artifact = ProviderBatchArtifact(**data)
                session.add(artifact)
                session.flush()
                artifact_id = artifact.id
                session.commit()
                return artifact_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(
                    f"Provider batch artifact 作成中にエラーが発生しました: {e}"
                )
                raise

    def list_provider_batch_artifacts(
        self,
        job_id: int,
        artifact_type: str | None = None,
    ) -> list[ProviderBatchArtifact]:
        """Provider Batch API job artifact 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchArtifact)
                    .where(ProviderBatchArtifact.job_id == job_id)
                    .order_by(ProviderBatchArtifact.id)
                )
                if artifact_type is not None:
                    stmt = stmt.where(ProviderBatchArtifact.artifact_type == artifact_type)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(
                    f"Provider batch artifact 一覧取得中にエラーが発生しました: {e}"
                )
                raise
