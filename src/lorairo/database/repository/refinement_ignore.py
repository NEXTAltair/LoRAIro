"""RefinementIgnore (タグ refinement リコメンドのローカル無視) 永続化 Repository (#931)。

tag + reason_code 単位で「このタグのこの理由のリコメンドは今後出さない」を永続化する。
`BaseRepository` (`session_factory`) を継承する。
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.future import select

from ...utils.log import logger
from ..schema import RefinementIgnore
from .base import BaseRepository


class RefinementIgnoreRepository(BaseRepository):
    """refinement リコメンドの無視設定 (tag + reason_code) を永続化する Repository。"""

    def add_ignore(self, tag: str, reason_code: str) -> None:
        """(tag, reason_code) を無視対象に登録する (冪等)。

        既に登録済みの場合は何もしない (UNIQUE 制約違反は握って正常終了)。

        Args:
            tag: 対象タグ文字列。
            reason_code: 無視する RefinementReason.code。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                session.add(RefinementIgnore(tag=tag, reason_code=reason_code))
                session.commit()
                logger.debug(f"refinement ignore 登録: tag='{tag}', reason_code='{reason_code}'")
            except IntegrityError:
                # UNIQUE(tag, reason_code) 違反 = 既に登録済み (正常系)
                session.rollback()
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"add_ignore エラー (tag={tag}, reason_code={reason_code}): {e}", exc_info=True
                )
                raise

    def is_ignored(self, tag: str, reason_code: str) -> bool:
        """(tag, reason_code) が無視対象か返す。

        Args:
            tag: 対象タグ文字列。
            reason_code: RefinementReason.code。

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
                )
                return session.execute(stmt).scalar_one_or_none() is not None
            except SQLAlchemyError as e:
                logger.error(f"is_ignored エラー (tag={tag}): {e}", exc_info=True)
                raise

    def list_ignored(self) -> set[tuple[str, str]]:
        """無視対象の (tag, reason_code) 集合を返す。

        Returns:
            (tag, reason_code) のタプル集合。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(RefinementIgnore.tag, RefinementIgnore.reason_code)
                return {(row[0], row[1]) for row in session.execute(stmt).all()}
            except SQLAlchemyError as e:
                logger.error(f"list_ignored エラー: {e}", exc_info=True)
                raise

    def remove_ignore(self, tag: str, reason_code: str) -> None:
        """(tag, reason_code) の無視設定を解除する (冪等)。

        Args:
            tag: 対象タグ文字列。
            reason_code: RefinementReason.code。

        Raises:
            SQLAlchemyError: 予期しない DB エラー。
        """
        with self.session_factory() as session:
            try:
                obj = session.execute(
                    select(RefinementIgnore).where(
                        RefinementIgnore.tag == tag,
                        RefinementIgnore.reason_code == reason_code,
                    )
                ).scalar_one_or_none()
                if obj is not None:
                    session.delete(obj)
                    session.commit()
                    logger.debug(f"refinement ignore 解除: tag='{tag}', reason_code='{reason_code}'")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"remove_ignore エラー (tag={tag}): {e}", exc_info=True)
                raise
