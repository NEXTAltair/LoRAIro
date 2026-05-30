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


def test_create_db_engine_keeps_memory_sqlite_usable() -> None:
    engine = create_db_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    assert result == 1
