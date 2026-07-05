"""SQLite engine PRAGMA 設定のテスト。"""

import sqlite3

from sqlalchemy import text

from lorairo.database.db_core import (
    BUSY_TIMEOUT_MS,
    _ensure_wal_journal_mode,
    _prepare_project_database,
    create_db_engine,
)


def test_create_db_engine_does_not_force_wal_on_connect(tmp_path) -> None:
    """接続リスナーは journal_mode を書き換えない (Issue #1165)。

    journal_mode=WAL を毎接続で実行すると 9p bind mount + GUI/CLI 併用時に
    busy_timeout の効かないロック取得となり disk I/O error / database is locked で
    接続セットアップがクラッシュしていた。WAL は DB 準備時に 1 回だけ設定する方針に
    変更したため、接続リスナーは journal_mode を触らないことを検証する。
    DELETE モードで用意した DB に接続しても DELETE のままであることを確認する。
    """
    db_path = tmp_path / "no-force-wal.sqlite"
    raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA journal_mode=DELETE")
    raw.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    raw.commit()
    raw.close()

    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")
    with engine.connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert journal_mode == "delete"


def test_create_db_engine_sets_per_connection_pragmas(tmp_path) -> None:
    """接続ごとの PRAGMA (foreign_keys / synchronous / busy_timeout) は設定される。

    busy_timeout は他の PRAGMA より先に設定され、単独で失敗しても他に影響しない
    (Issue #767 / #1002)。journal_mode は per-connection では設定しない (Issue #1165)。
    """
    db_path = tmp_path / "per-conn.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    with engine.connect() as connection:
        synchronous = connection.execute(text("PRAGMA synchronous")).scalar_one()
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert synchronous == 1
    assert foreign_keys == 1
    assert busy_timeout == BUSY_TIMEOUT_MS
    assert BUSY_TIMEOUT_MS > 0


def test_prepare_project_database_persists_wal(tmp_path) -> None:
    """_prepare_project_database は WAL を DB ヘッダに永続化する (Issue #1165)。

    毎接続ではなく DB 準備時に 1 回だけ WAL を設定する。準備後に生の接続で開いても
    WAL になっていること (= 永続化されていること) を確認する。
    """
    db_path = tmp_path / "prepared.sqlite"
    _prepare_project_database(db_path)

    raw = sqlite3.connect(db_path)
    try:
        journal_mode = raw.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        raw.close()

    assert journal_mode.lower() == "wal"


def test_ensure_wal_journal_mode_converts_delete_db(tmp_path) -> None:
    """DELETE モードの DB に対しては WAL へ変換して永続化する (Issue #1165)。"""
    db_path = tmp_path / "convert.sqlite"
    raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA journal_mode=DELETE")
    raw.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    raw.commit()
    raw.close()

    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")
    _ensure_wal_journal_mode(engine)

    raw = sqlite3.connect(db_path)
    try:
        journal_mode = raw.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        raw.close()

    assert journal_mode.lower() == "wal"


def test_ensure_wal_journal_mode_idempotent_on_wal_db(tmp_path) -> None:
    """既に WAL の DB では例外なく WAL を維持する (再実行しても安全, Issue #1165)。"""
    db_path = tmp_path / "already-wal.sqlite"
    raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.close()

    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")
    _ensure_wal_journal_mode(engine)
    _ensure_wal_journal_mode(engine)

    raw = sqlite3.connect(db_path)
    try:
        journal_mode = raw.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        raw.close()

    assert journal_mode.lower() == "wal"


def test_ensure_wal_journal_mode_noop_for_memory() -> None:
    """:memory: DB では WAL 設定を試みない (適用不能, 例外も出さない)。"""
    engine = create_db_engine("sqlite:///:memory:")
    _ensure_wal_journal_mode(engine)

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    assert result == 1


def test_create_db_engine_keeps_memory_sqlite_usable() -> None:
    engine = create_db_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    assert result == 1
