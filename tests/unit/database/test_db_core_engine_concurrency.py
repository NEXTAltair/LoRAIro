"""エンジンプール方式とマルチスレッド同時アクセスの回帰テスト (Issue #1002)。

StaticPool は 1 本の生 SQLite コネクションを全セッションで共有するため、GUI メインスレッドと
RefinementWorker (QThread) が同一エンジンを共有すると sqlite3 の真の同時アクセスで
``bad parameter or other API misuse`` を招く。実ファイル DB では QueuePool を使い、
:memory: のときだけ StaticPool を使うことを検証する。
"""

import threading

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool, StaticPool

from lorairo.database.db_core import create_db_engine


def test_create_db_engine_uses_queue_pool_for_file_db(tmp_path) -> None:
    """実ファイル DB では既定の QueuePool を使う (StaticPool ではない)。"""
    db_path = tmp_path / "pool-file.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    assert isinstance(engine.pool, QueuePool)
    assert not isinstance(engine.pool, StaticPool)


def test_create_db_engine_uses_static_pool_for_memory_db() -> None:
    """:memory: は接続ごとに別 DB になるため単一コネクション保持の StaticPool が必須。"""
    engine = create_db_engine("sqlite:///:memory:")

    assert isinstance(engine.pool, StaticPool)


def test_concurrent_sessions_do_not_raise_interface_error(tmp_path) -> None:
    """実ファイル DB に対し複数スレッドが同時にセッションを使っても例外なく完了する。

    修正前 (poolclass=StaticPool) では同一の生コネクションを複数スレッドが同時に叩き、
    sqlite3.InterfaceError: bad parameter or other API misuse を散発的に起こしていた。
    """
    db_path = tmp_path / "concurrency.sqlite"
    engine = create_db_engine(f"sqlite:///{db_path}?check_same_thread=False")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)"))
        connection.execute(text("INSERT INTO items (value) VALUES ('a'), ('b'), ('c')"))

    errors: list[SQLAlchemyError] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        try:
            barrier.wait()  # 全スレッドの SQL 発行を同時刻に揃えて競合を誘発
            for _ in range(20):
                with engine.connect() as connection:
                    connection.execute(text("SELECT id, value FROM items")).fetchall()
        except SQLAlchemyError as exc:
            # 修正前は bad parameter or other API misuse (InterfaceError) がここで捕捉される
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
