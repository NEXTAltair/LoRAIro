"""Repository 層の共通基盤 (ADR 0035 §2)。

`ImageRepository` を Aggregate 単位で分割した後、全 Repository クラスが本基盤を継承する。
共通プロパティ (`session_factory`) と全体定数 (`BATCH_CHUNK_SIZE`) を保持する。
"""

from collections.abc import Callable
from typing import ClassVar

from sqlalchemy.orm import Session

from ..db_core import DefaultSessionLocal


class BaseRepository:
    """Repository の共通基盤。

    各 Aggregate Repository (`ModelRepository` / `ImageRepository` / `AnnotationRepository` /
    `ProjectRepository` / `ErrorRecordRepository`) が本クラスを継承する。

    Attributes:
        session_factory: SQLAlchemy セッションを生成する callable。
        BATCH_CHUNK_SIZE: SQLite バインド変数上限の安全マージン (32,766 の約半分)。
            IN 句以外にもクエリ内で変数を使うため余裕を持たせる。

    """

    # SQLite バインド変数上限の安全マージン（32,766の約半分）
    # IN句以外にもクエリ内で変数を使うため余裕を持たせる
    BATCH_CHUNK_SIZE: ClassVar[int] = 15000

    def __init__(self, session_factory: Callable[[], Session] = DefaultSessionLocal) -> None:
        """BaseRepository のコンストラクタ。

        Args:
            session_factory: SQLAlchemy セッションを生成するファクトリ関数。
                デフォルトは `db_core.DefaultSessionLocal` を使用。
                テスト時にモック化可能。

        """
        self.session_factory = session_factory
