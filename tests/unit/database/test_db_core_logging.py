"""db_core のログが loguru sink に捕捉されることを検証する (Issue #572)。

db_core.py が標準 ``logging`` を使っていると、これらのログは loguru の
file/stderr sink に乗らず ``logs/lorairo.log`` に記録されない。本テストは
db_core が loguru logger を使い、DB 層のログ (engine 生成・PRAGMA 適用・
トランザクション失敗 ERROR) が loguru sink に捕捉されることを保証する。
"""

import io
from collections.abc import Iterator

import pytest
from loguru import logger

from lorairo.database.db_core import (
    create_db_engine,
    create_session_factory,
    get_db_session,
)


@pytest.fixture
def loguru_sink() -> Iterator[io.StringIO]:
    """loguru に一時 StringIO sink を追加し、テスト後に除去する。

    enqueue 済みログを確実に取り込むため、読み出し前に ``logger.complete()``
    を呼ぶこと。
    """
    sink = io.StringIO()
    sink_id = logger.add(sink, level=0, format="{message}", colorize=False)
    try:
        yield sink
    finally:
        logger.remove(sink_id)


def test_create_db_engine_logs_engine_creation_to_loguru(loguru_sink: io.StringIO) -> None:
    """create_db_engine の engine 生成 INFO ログが loguru sink に捕捉される。"""
    create_db_engine("sqlite:///:memory:")
    logger.complete()

    assert "Creating SQLAlchemy engine" in loguru_sink.getvalue()


def test_sqlite_pragma_logged_to_loguru(loguru_sink: io.StringIO) -> None:
    """SQLite connect 時の PRAGMA 設定 DEBUG ログが loguru sink に捕捉される。

    #569 で追加した ``PRAGMA journal_mode=WAL`` 適用の確認手段が loguru 経由で
    機能することを保証する。``:memory:`` でも connect listener は発火し、
    ``foreign_keys=ON`` の PRAGMA ログが出力される。
    """
    engine = create_db_engine("sqlite:///:memory:")
    with engine.connect():
        pass
    logger.complete()

    assert "PRAGMA" in loguru_sink.getvalue()


def test_get_db_session_logs_transaction_failure_to_loguru(loguru_sink: io.StringIO) -> None:
    """トランザクション失敗時の ERROR + traceback が loguru sink に捕捉される。

    #572 の主目的: DB 書き込み失敗のスタックトレースが ``logs/lorairo.log``
    に残ることを保証する。
    """
    engine = create_db_engine("sqlite:///:memory:")
    factory = create_session_factory(engine)

    with pytest.raises(ValueError, match="boom"), get_db_session(factory):
        raise ValueError("boom")
    logger.complete()

    output = loguru_sink.getvalue()
    assert "Transaction failed" in output
    assert "ValueError" in output


def test_default_session_factory_logs_init_to_loguru(
    loguru_sink: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """default session factory の初回準備で DB core 初期化 INFO が loguru sink に出る。

    module-level ではなく遅延 (関数内) でログを出すことで initialize_logging 後に
    実行され、file sink に確実に乗る (#572)。
    """
    import lorairo.database.db_core as db_core

    monkeypatch.setattr(db_core, "_default_session_factory", None)
    monkeypatch.setattr(db_core, "ensure_default_db_dir", lambda: db_core.DB_DIR)
    monkeypatch.setattr(
        db_core,
        "_prepare_project_database",
        lambda path: create_db_engine("sqlite:///:memory:"),
    )

    db_core._get_default_session_factory()
    logger.complete()

    assert "データベースコアが初期化されました" in loguru_sink.getvalue()
