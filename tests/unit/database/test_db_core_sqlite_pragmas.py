"""SQLite engine PRAGMA 設定のテスト。"""

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
