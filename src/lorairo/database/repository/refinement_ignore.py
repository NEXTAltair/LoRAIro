"""RefinementIgnore (タグ refinement リコメンドのローカル無視) 永続化 Repository (#931 / #1053)。

tag + reason_code (+ 画像スコープ image_id) 単位で「このリコメンドは今後出さない」を
永続化する。``image_id=None`` = 全画像スコープ / 非 None = その画像限定。
`BaseRepository` (`session_factory`) を継承する。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.future import select

from ...utils.log import logger
from ..schema import RefinementIgnore
from .base import BaseRepository


def _scope_clause(image_id: int | None) -> Any:
    """スコープ (image_id) の一致条件を返す (None は IS NULL)。"""
    if image_id is None:
        return RefinementIgnore.image_id.is_(None)
    return RefinementIgnore.image_id == image_id


class RefinementIgnoreRepository(BaseRepository):
    """refinement リコメンドの無視設定 (tag + reason_code + スコープ) を永続化する Repository。"""

    def add_ignore(self, tag: str, reason_code: str, image_id: int | None = None) -> None:
        """(tag, reason_code, スコープ) を無視対象に登録する (冪等)。

        既に登録済みの場合は何もしない (部分 UNIQUE インデックス違反は握って正常終了)。

        Args:
            tag: 対象タグ文字列。
            reason_code: 無視する RefinementReason.code。
            image_id: None なら全画像スコープ、指定時はその画像限定 (#1053)。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                session.add(RefinementIgnore(tag=tag, reason_code=reason_code, image_id=image_id))
                session.commit()
                logger.debug(
                    f"refinement ignore 登録: tag='{tag}', reason_code='{reason_code}', image_id={image_id}"
                )
            except IntegrityError as e:
                session.rollback()
                # 部分 UNIQUE インデックス違反 = 既に登録済み (正常系) のみ握る。
                # FK 違反 (削除済み画像の image_id 等) まで重複扱いすると、行が無いのに
                # UI が「保存成功」として進んでしまうため伝播させる (PR #1082 Codex P2)。
                if "UNIQUE constraint failed" not in str(e.orig):
                    logger.opt(exception=True).error(
                        f"add_ignore 整合性エラー (tag={tag}, reason_code={reason_code}, "
                        f"image_id={image_id}): {e}"
                    )
                    raise
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(
                    f"add_ignore エラー (tag={tag}, reason_code={reason_code}): {e}"
                )
                raise

    def is_ignored(self, tag: str, reason_code: str, image_id: int | None = None) -> bool:
        """(tag, reason_code) が指定スコープで無視対象か返す。

        Args:
            tag: 対象タグ文字列。
            reason_code: RefinementReason.code。
            image_id: None なら全画像スコープの行を、指定時はその画像限定の行を見る。

        Returns:
            無視対象なら True。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(RefinementIgnore.id).where(
                    RefinementIgnore.tag == tag,
                    RefinementIgnore.reason_code == reason_code,
                    _scope_clause(image_id),
                )
                return session.execute(stmt).scalar_one_or_none() is not None
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(f"is_ignored エラー (tag={tag}): {e}")
                raise

    def list_ignored(self, image_id: int | None = None) -> set[tuple[str, str]]:
        """指定画像の評価で効く (tag, reason_code) 集合を返す。

        全画像スコープ (image_id IS NULL) の行は常に含まれ、``image_id`` 指定時は
        その画像限定の行も合算する (#1053)。

        Args:
            image_id: 評価対象の画像 ID。None なら全画像スコープのみ。

        Returns:
            (tag, reason_code) のタプル集合。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(RefinementIgnore.tag, RefinementIgnore.reason_code).where(
                    RefinementIgnore.image_id.is_(None)
                    if image_id is None
                    else (RefinementIgnore.image_id.is_(None) | (RefinementIgnore.image_id == image_id))
                )
                return {(row[0], row[1]) for row in session.execute(stmt).all()}
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(f"list_ignored エラー: {e}")
                raise

    def list_ignored_entries(self) -> list[dict[str, Any]]:
        """無視設定の全行 (スコープ含む) を管理 UI 向けに返す (#1053)。

        Returns:
            ``[{"tag", "reason_code", "image_id", "created_at"}, ...]`` (登録順)。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                rows = session.execute(select(RefinementIgnore).order_by(RefinementIgnore.id)).scalars()
                return [
                    {
                        "tag": row.tag,
                        "reason_code": row.reason_code,
                        "image_id": row.image_id,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ]
            except SQLAlchemyError as e:
                logger.opt(exception=True).error(f"list_ignored_entries エラー: {e}")
                raise

    def remove_ignore(self, tag: str, reason_code: str, image_id: int | None = None) -> None:
        """(tag, reason_code, スコープ) の無視設定を解除する (冪等)。

        Args:
            tag: 対象タグ文字列。
            reason_code: RefinementReason.code。
            image_id: None なら全画像スコープの行を、指定時はその画像限定の行を消す。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                obj = session.execute(
                    select(RefinementIgnore).where(
                        RefinementIgnore.tag == tag,
                        RefinementIgnore.reason_code == reason_code,
                        _scope_clause(image_id),
                    )
                ).scalar_one_or_none()
                if obj is not None:
                    session.delete(obj)
                    session.commit()
                    logger.debug(
                        f"refinement ignore 解除: tag='{tag}', reason_code='{reason_code}', "
                        f"image_id={image_id}"
                    )
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"remove_ignore エラー (tag={tag}): {e}")
                raise
