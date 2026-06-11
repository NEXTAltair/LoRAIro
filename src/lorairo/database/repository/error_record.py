"""ErrorRecord 永続化担当 Repository (ADR 0035 §1)。

`ImageRepository` god class 分割の段階 3 として、`ErrorRecord` エンティティの
CRUD・状態遷移 (resolved_at 更新) を本 Repository に集約する。

管轄 entity:
  - `ErrorRecord` (`operation_type`, `error_type`, `error_message`, `resolved_at` 他)

段階 1 で確立した `BaseRepository` (`session_factory` + `BATCH_CHUNK_SIZE`) を継承する。

Note:
    Manager 層 (`ImageDatabaseManager.save_error_record`) では「二次エラー防止」のため
    本 Repository が送出する例外を sentinel `-1` に畳む。本 Repository 側では
    SQLAlchemyError を rollback 後に呼び出し元へ伝播させる責務に留める
    (PR #476 で確立した方針)。
"""

from __future__ import annotations

import datetime
from datetime import UTC

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select

from ...utils.log import logger
from ..schema import ErrorRecord
from .base import BaseRepository


class ErrorRecordRepository(BaseRepository):
    """`ErrorRecord` の永続化を担当する Repository (ADR 0035)。

    管轄 entity:
      - `ErrorRecord` (CRUD + 解決マーク + 集計クエリ)
    """

    def save_error_record(
        self,
        operation_type: str,
        error_type: str,
        error_message: str,
        image_id: int | None = None,
        stack_trace: str | None = None,
        file_path: str | None = None,
        model_name: str | None = None,
    ) -> int:
        """エラーレコードを保存する。

        Args:
            operation_type: 操作種別 ("registration" | "annotation" | "processing")。
            error_type: エラー種別 ("pHash calculation" | "API error" | "DB constraint")。
            error_message: エラーメッセージ。
            image_id: 画像ID (Optional)。
            stack_trace: スタックトレース (Optional)。
            file_path: ファイルパス (Optional)。
            model_name: モデル名 (Optional)。

        Returns:
            int: 作成された error_record_id。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                record = ErrorRecord(
                    image_id=image_id,
                    operation_type=operation_type,
                    error_type=error_type,
                    error_message=error_message,
                    stack_trace=stack_trace,
                    file_path=file_path,
                    model_name=model_name,
                )
                session.add(record)
                session.flush()
                error_id = record.id
                session.commit()
                logger.debug(
                    f"エラーレコードを保存しました: ID={error_id}, "
                    f"operation={operation_type}, type={error_type}",
                )
                return error_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エラーレコードの保存中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_count_unresolved(self, operation_type: str | None = None) -> int:
        """未解決エラー件数を取得する (resolved_at IS NULL)。

        Args:
            operation_type: 操作種別フィルタ (None = 全操作)。

        Returns:
            int: 未解決エラー件数。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                query = select(func.count(ErrorRecord.id)).where(ErrorRecord.resolved_at.is_(None))
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                count = session.execute(query).scalar() or 0
                logger.debug(
                    f"未解決エラー件数を取得: {count}件 (operation_type={operation_type or 'all'})",
                )
                return count
            except SQLAlchemyError as e:
                logger.error(f"未解決エラー件数の取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_image_ids(
        self,
        operation_type: str | None = None,
        resolved: bool = False,
        error_types: list[str] | None = None,
    ) -> list[int]:
        """エラー画像のID一覧を取得する。

        Args:
            operation_type: 操作種別フィルタ (None = 全操作)。
            resolved: True = 解決済み (resolved_at IS NOT NULL)、
                False = 未解決 (resolved_at IS NULL)。
            error_types: 特定 error_type のみに絞る (例:
                ["SAFETY_REFUSAL", "CONTENT_POLICY_REFUSAL"])。
                None = 全 type。ADR 0023 Phase 1.5 の送信前 filter で使用。

        Returns:
            list[int]: 画像IDリスト (重複除去済み、None を除外)。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                query = select(ErrorRecord.image_id).distinct().where(ErrorRecord.image_id.is_not(None))
                if resolved:
                    query = query.where(ErrorRecord.resolved_at.is_not(None))
                else:
                    query = query.where(ErrorRecord.resolved_at.is_(None))
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                if error_types:
                    query = query.where(ErrorRecord.error_type.in_(error_types))

                results = session.execute(query).scalars().all()
                image_ids = [id for id in results if id is not None]
                logger.debug(
                    f"エラー画像ID一覧を取得: {len(image_ids)}件 "
                    f"(operation_type={operation_type or 'all'}, resolved={resolved}, "
                    f"error_types={error_types or 'all'})",
                )
                return image_ids
            except SQLAlchemyError as e:
                logger.error(f"エラー画像ID一覧の取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_records(
        self,
        operation_type: str | None = None,
        error_type: str | None = None,
        message_contains: str | None = None,
        resolved: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ErrorRecord]:
        """エラーレコードを取得する (ページネーション対応)。

        Args:
            operation_type: 操作種別フィルタ (None = 全操作)。
            error_type: エラー種別フィルタ (None = 全種別)。
            message_contains: error_message 部分一致フィルタ (None = 全メッセージ)。
            resolved: None = 全て、True = 解決済み、False = 未解決。
            limit: 取得件数上限。
            offset: オフセット。

        Returns:
            list[ErrorRecord]: エラーレコードリスト。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                query = select(ErrorRecord).order_by(ErrorRecord.created_at.desc())
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                if error_type:
                    query = query.where(ErrorRecord.error_type == error_type)
                if message_contains:
                    query = query.where(ErrorRecord.error_message.contains(message_contains))
                if resolved is not None:
                    if resolved:
                        query = query.where(ErrorRecord.resolved_at.is_not(None))
                    else:
                        query = query.where(ErrorRecord.resolved_at.is_(None))
                query = query.limit(limit).offset(offset)
                records = list(session.execute(query).scalars().all())
                logger.debug(
                    f"エラーレコードを取得: {len(records)}件 "
                    f"(operation_type={operation_type or 'all'}, "
                    f"error_type={error_type or 'all'}, "
                    f"message_contains={message_contains!r}, "
                    f"resolved={resolved}, limit={limit}, offset={offset})",
                )
                return records
            except SQLAlchemyError as e:
                logger.error(f"エラーレコードの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def mark_error_resolved(self, error_id: int) -> None:
        """エラーを解決済みにマークする (resolved_at = 現在時刻)。

        Args:
            error_id: エラーレコードID。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                record = session.get(ErrorRecord, error_id)
                if record:
                    record.resolved_at = datetime.datetime.now(UTC)
                    session.commit()
                    logger.info(f"エラーレコードを解決済みにマーク: ID={error_id}")
                else:
                    logger.warning(f"エラーレコードが見つかりません: ID={error_id}")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エラーレコードの解決マーク中にエラーが発生しました: {e}", exc_info=True)
                raise

    def mark_errors_resolved_batch(self, error_ids: list[int]) -> tuple[bool, int]:
        """複数のエラーレコードを原子的に解決済みにマークする。

        単一トランザクションで全エラーを処理する。全件成功 or 全件ロールバック。
        ADR-0012 (Batch Tag Atomic Transaction) パターン準拠。

        Args:
            error_ids: 対象エラーレコードのIDリスト。

        Returns:
            tuple[bool, int]: (成功フラグ, 解決済みマーク件数)。

        Raises:
            SQLAlchemyError: データベースエラー時 (ロールバック後に再送出)。
        """
        if not error_ids:
            logger.warning("mark_errors_resolved_batch: 空のerror_idsリストが渡されました")
            return (False, 0)

        with self.session_factory() as session:
            try:
                existing = (
                    session.execute(select(ErrorRecord).where(ErrorRecord.id.in_(error_ids)))
                    .scalars()
                    .all()
                )

                now = datetime.datetime.now(UTC)
                updated_count = 0
                for record in existing:
                    record.resolved_at = now
                    updated_count += 1

                session.commit()
                logger.info(f"エラーレコード一括解決完了: 要求={len(error_ids)}件, 更新={updated_count}件")
                return (True, updated_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エラーレコード一括解決失敗: {e}", exc_info=True)
                raise

    def count_error_records(
        self,
        operation_type: str | None = None,
        error_type: str | None = None,
        message_contains: str | None = None,
        resolved: bool | None = None,
    ) -> int:
        """条件に一致するエラーレコード件数を返す (dry-run 用)。

        Args:
            operation_type: 操作種別フィルタ。
            error_type: エラー種別フィルタ。
            message_contains: error_message 部分一致フィルタ。
            resolved: None = 全て、True = 解決済み、False = 未解決。

        Returns:
            int: 一致件数。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                query = select(func.count(ErrorRecord.id))
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                if error_type:
                    query = query.where(ErrorRecord.error_type == error_type)
                if message_contains:
                    query = query.where(ErrorRecord.error_message.contains(message_contains))
                if resolved is not None:
                    if resolved:
                        query = query.where(ErrorRecord.resolved_at.is_not(None))
                    else:
                        query = query.where(ErrorRecord.resolved_at.is_(None))
                count = session.execute(query).scalar() or 0
                logger.debug(f"エラーレコード件数を集計: {count}件")
                return count
            except SQLAlchemyError as e:
                logger.error(f"エラーレコード件数集計中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_ids_by_filter(
        self,
        operation_type: str | None = None,
        error_type: str | None = None,
        message_contains: str | None = None,
    ) -> list[int]:
        """未解決エラーレコードの ID リストをフィルター条件で取得する (一括 resolve 用)。

        Args:
            operation_type: 操作種別フィルタ。
            error_type: エラー種別フィルタ。
            message_contains: error_message 部分一致フィルタ。

        Returns:
            list[int]: 未解決エラーレコード ID リスト。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                query = (
                    select(ErrorRecord.id).where(ErrorRecord.resolved_at.is_(None)).order_by(ErrorRecord.id)
                )
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                if error_type:
                    query = query.where(ErrorRecord.error_type == error_type)
                if message_contains:
                    query = query.where(ErrorRecord.error_message.contains(message_contains))
                ids = list(session.execute(query).scalars().all())
                logger.debug(f"一括 resolve 対象 ID: {len(ids)}件")
                return ids
            except SQLAlchemyError as e:
                logger.error(f"エラーレコード ID 取得中にエラーが発生しました: {e}", exc_info=True)
                raise
