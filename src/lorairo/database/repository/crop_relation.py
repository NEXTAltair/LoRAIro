"""クロップ親子関係 (`crop_relations`) の永続化 Repository (ADR 0092, Issue #1343)。

クロップ画像は親画像と同じ `images` テーブルへ独立した ID で登録され、本 Repository は
「直接の親 ID・子 ID・親画像基準の切り出し矩形・切り出し由来」だけを扱う。
`BaseRepository` (`session_factory`) を継承する。
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select

from ...domain.crop_request import DEFAULT_CROP_ORIGIN
from ...utils.log import logger
from ..schema import CropRelation
from .base import BaseRepository


class CropRelationRepository(BaseRepository):
    """クロップ画像の直接の親子関係を登録・取得する Repository。"""

    def add_relation(
        self,
        parent_image_id: int,
        child_image_id: int,
        x: int,
        y: int,
        width: int,
        height: int,
        origin: str = DEFAULT_CROP_ORIGIN,
    ) -> int:
        """親子関係を 1 件登録し、作成された関係行の ID を返す。

        Args:
            parent_image_id: 直接の親画像 ID (images.id)。
            child_image_id: 子 (クロップ画像) の ID (images.id)。
            x: 親画像基準の左上 x 座標 (px)。
            y: 親画像基準の左上 y 座標 (px)。
            width: 切り出し幅 (px)。
            height: 切り出し高さ (px)。
            origin: 切り出し由来。手動選択は `manual`、物体検出は検出器名等 (#1340)。

        Returns:
            作成された `crop_relations.id`。

        Raises:
            IntegrityError: 子が既に別の親を持つ場合や、参照先画像が存在しない場合。
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                relation = CropRelation(
                    parent_image_id=parent_image_id,
                    child_image_id=child_image_id,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    origin=origin,
                )
                session.add(relation)
                session.commit()
                relation_id: int = relation.id
                logger.debug(
                    f"クロップ親子関係を登録: id={relation_id}, parent={parent_image_id}, "
                    f"child={child_image_id}, rect=({x}, {y}, {width}, {height}), origin='{origin}'"
                )
                return relation_id
            except SQLAlchemyError:
                # IntegrityError (子の二重登録 / FK 違反) は握らず呼び出し元へ伝播させる。
                session.rollback()
                logger.opt(exception=True).error(
                    f"クロップ親子関係の登録に失敗: parent={parent_image_id}, child={child_image_id}"
                )
                raise

    def get_children(self, parent_image_id: int) -> list[CropRelation]:
        """指定した親画像から切り出された子の関係行を作成順に返す。

        Args:
            parent_image_id: 親画像 ID (images.id)。

        Returns:
            `CropRelation` のリスト (登録順)。子が無ければ空リスト。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(CropRelation)
                    .where(CropRelation.parent_image_id == parent_image_id)
                    .order_by(CropRelation.id)
                )
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError:
                logger.opt(exception=True).error(f"クロップ子一覧の取得に失敗: parent={parent_image_id}")
                raise

    def get_parent(self, child_image_id: int) -> CropRelation | None:
        """指定した子画像の直接の親の関係行を返す。

        Args:
            child_image_id: 子 (クロップ画像) の ID (images.id)。

        Returns:
            `CropRelation`。クロップ画像でなければ None。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(CropRelation).where(CropRelation.child_image_id == child_image_id)
                return session.execute(stmt).scalars().one_or_none()
            except SQLAlchemyError:
                logger.opt(exception=True).error(f"クロップ親の取得に失敗: child={child_image_id}")
                raise
