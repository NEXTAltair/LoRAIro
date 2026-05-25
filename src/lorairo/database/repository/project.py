"""Project 永続化担当 Repository (ADR 0035 §1)。

`ImageRepository` god class 分割の段階 2 として、Project エンティティおよび
`Image.project_id` (FK) 関連の CRUD・割り当てを本 Repository に集約する。

管轄 entity:
  - `Project` (`name` UNIQUE, `path`, `description`)
  - `Image.project_id` FK 経由のプロジェクトアサイン

段階 1 で確立した `BaseRepository` (`session_factory` + `BATCH_CHUNK_SIZE`) を継承する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.future import select

from ...utils.log import logger
from ..schema import Image, Project
from .base import BaseRepository


class ProjectRepository(BaseRepository):
    """Project / Image.project_id (FK) の永続化を担当する Repository (ADR 0035)。

    管轄 entity:
      - `Project`
      - `Image.project_id` (FK) を介したプロジェクトアサイン
    """

    def ensure_project(self, name: str, path: Path, description: str = "") -> int:
        """プロジェクトを upsert して ID を返す（name UNIQUE）。

        Args:
            name: プロジェクト名（UNIQUE制約あり）。
            path: プロジェクトの絶対パス。
            description: プロジェクト説明（省略可）。

        Returns:
            int: プロジェクトID。

        Raises:
            SQLAlchemyError: DB操作エラー。
        """
        with self.session_factory() as session:
            try:
                existing = session.execute(select(Project).where(Project.name == name)).scalar_one_or_none()

                if existing is not None:
                    if str(existing.path) != str(path):
                        existing.path = str(path)
                        session.commit()
                    return existing.id

                project = Project(name=name, path=str(path), description=description or None)
                session.add(project)
                session.flush()
                project_id = project.id
                session.commit()
                logger.info(f"Project created: name='{name}', id={project_id}")
                return project_id
            except IntegrityError:
                session.rollback()
                return session.execute(select(Project.id).where(Project.name == name)).scalar_one()
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"ensure_project エラー (name={name}): {e}", exc_info=True)
                raise

    def get_image_ids_by_project(self, project_name: str) -> list[int]:
        """プロジェクト名で画像ID一覧を取得する。

        Args:
            project_name: フィルタ対象プロジェクト名。

        Returns:
            list[int]: 画像IDのリスト。プロジェクトが存在しない場合は空リスト。

        Raises:
            SQLAlchemyError: DB操作エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(Image.id)
                    .join(Project, Image.project_id == Project.id)
                    .where(Project.name == project_name)
                )
                result = list(session.execute(stmt).scalars().all())
                logger.debug(f"get_image_ids_by_project: name='{project_name}', count={len(result)}")
                return result
            except SQLAlchemyError as e:
                logger.error(f"get_image_ids_by_project エラー: {e}", exc_info=True)
                raise

    def get_image_ids_by_project_id(self, project_id: int) -> list[int]:
        """プロジェクトIDで画像ID一覧を取得する。

        Args:
            project_id: フィルタ対象プロジェクトID。

        Returns:
            list[int]: 画像IDのリスト。

        Raises:
            SQLAlchemyError: DB操作エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Image.id).where(Image.project_id == project_id)
                result = list(session.execute(stmt).scalars().all())
                logger.debug(f"get_image_ids_by_project_id: id={project_id}, count={len(result)}")
                return result
            except SQLAlchemyError as e:
                logger.error(f"get_image_ids_by_project_id エラー: {e}", exc_info=True)
                raise

    def assign_images_to_project(self, image_ids: list[int], project_id: int) -> int:
        """画像IDリストをプロジェクトに割り当てる。

        Args:
            image_ids: 割り当てる画像IDリスト。
            project_id: 割り当て先プロジェクトID。

        Returns:
            int: 実際に更新された件数。

        Raises:
            SQLAlchemyError: DB操作エラー。
        """
        if not image_ids:
            return 0

        with self.session_factory() as session:
            try:
                total_updated = 0
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    stmt = update(Image).where(Image.id.in_(chunk)).values(project_id=project_id)
                    total_updated += cast("CursorResult[Any]", session.execute(stmt)).rowcount
                session.commit()
                logger.info(
                    f"assign_images_to_project: {total_updated}/{len(image_ids)} images"
                    f" → project_id={project_id}"
                )
                return total_updated
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"assign_images_to_project エラー: {e}", exc_info=True)
                raise
