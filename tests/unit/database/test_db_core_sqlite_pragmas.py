"""SQLite engine PRAGMA 設定のテスト。"""

import sqlite3

from sqlalchemy import text

from lorairo.database.db_core import create_db_engine


def test_create_db_engine_sets_file_sqlite_wal_and_normal(tmp_path) -> None:
    db_path = tmp_path / "pragma-test.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    with engine.connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        synchronous = connection.execute(text("PRAGMA synchronous")).scalar_one()
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert journal_mode == "wal"
    assert synchronous == 1
    assert foreign_keys == 1


def test_create_db_engine_sets_busy_timeout(tmp_path) -> None:
    """GUI/CLI 併用時のロック待機のため busy_timeout が設定される (Issue #767)。"""
    from lorairo.database.db_core import BUSY_TIMEOUT_MS

    db_path = tmp_path / "busy-timeout.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    with engine.connect() as connection:
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert busy_timeout == BUSY_TIMEOUT_MS
    assert BUSY_TIMEOUT_MS > 0


def test_create_db_engine_keeps_memory_sqlite_usable() -> None:
    engine = create_db_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    assert result == 1


class _FlakyCursor:
    """journal_mode=WAL の実行だけ最初の 1 回に限り失敗させる sqlite3.Cursor プロキシ。

    ``sqlite3.Cursor`` / ``sqlite3.Connection`` は C 実装の immutable 型のため、インスタンス
    属性の直接上書き (monkeypatch.setattr) では書き換えられない。そのため薄いプロキシで
    包み、``sqlite3.connect`` 自体を差し替えて実コネクションの代わりに返す。
    """

    def __init__(self, cursor: sqlite3.Cursor, state: dict[str, bool]) -> None:
        self._cursor = cursor
        self._state = state

    def execute(self, sql: str, *args: object, **kwargs: object) -> sqlite3.Cursor:
        if sql == "PRAGMA journal_mode=WAL" and not self._state["triggered"]:
            self._state["triggered"] = True
            raise sqlite3.OperationalError("database is locked")
        return self._cursor.execute(sql, *args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._cursor, name)


class _FlakyConnection:
    """connect() の戻り値を差し替えるための sqlite3.Connection プロキシ。"""

    def __init__(self, connection: sqlite3.Connection, state: dict[str, bool]) -> None:
        self._connection = connection
        self._state = state

    def cursor(self, *args: object, **kwargs: object) -> _FlakyCursor:
        return _FlakyCursor(self._connection.cursor(*args, **kwargs), self._state)

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


def test_busy_timeout_survives_journal_mode_failure(tmp_path, monkeypatch) -> None:
    """journal_mode=WAL の PRAGMA が例外を起こしても busy_timeout は設定される。

    QueuePool 化 (Issue #1002) で複数スレッドが同時に新規コネクションを開けるようになった
    ため、接続直後に PRAGMA journal_mode=WAL がロック中の DB に当たって失敗する余地がある。
    以前は全 PRAGMA を単一の try/except でまとめていたため、journal_mode の失敗で後続の
    busy_timeout 設定までスキップされ、そのコネクションは busy_timeout=0 のまま
    "database is locked" を即時に返す可能性があった (Codex レビュー指摘、Issue #1002)。
    busy_timeout を journal_mode より先に、かつ独立した try/except で設定することで、
    journal_mode が失敗してもこのコネクションの busy_timeout は有効なままであることを検証する。
    """
    from lorairo.database.db_core import BUSY_TIMEOUT_MS

    # SQLAlchemy の pysqlite dialect は ``sqlite3.dbapi2`` 経由で connect() を解決するため
    # (SQLiteDialect_pysqlite.import_dbapi)、``sqlite3.connect`` ではなく
    # ``sqlite3.dbapi2.connect`` を差し替える必要がある。
    original_connect = sqlite3.dbapi2.connect
    state = {"triggered": False}

    def patched_connect(*args: object, **kwargs: object) -> _FlakyConnection:
        return _FlakyConnection(original_connect(*args, **kwargs), state)

    monkeypatch.setattr(sqlite3.dbapi2, "connect", patched_connect)

    db_path = tmp_path / "flaky-wal.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    with engine.connect() as connection:
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert state["triggered"] is True
    assert busy_timeout == BUSY_TIMEOUT_MS
