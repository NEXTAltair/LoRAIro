"""SQLite ロック競合判定 (lorairo.database.db_errors) のテスト (Issue #767)。"""

import pytest

from lorairo.database.db_errors import is_sqlite_lock_error


def _operational_error(message: str, module: str = "sqlite3") -> Exception:
    """型名 OperationalError を持つ軽量例外を生成する (sqlite3/SQLAlchemy 模擬)。"""
    return type("OperationalError", (Exception,), {"__module__": module})(message)


@pytest.mark.unit
def test_detects_database_is_locked() -> None:
    assert is_sqlite_lock_error(_operational_error("database is locked")) is True


@pytest.mark.unit
def test_detects_database_is_busy() -> None:
    assert is_sqlite_lock_error(_operational_error("database is busy")) is True


@pytest.mark.unit
def test_detects_sqlalchemy_wrapped_message() -> None:
    wrapped = _operational_error("(sqlite3.OperationalError) database is locked", module="sqlalchemy.exc")
    assert is_sqlite_lock_error(wrapped) is True


@pytest.mark.unit
def test_detects_lock_in_cause_chain() -> None:
    orig = _operational_error("database is locked")
    try:
        raise RuntimeError("save failed") from orig
    except RuntimeError as exc:
        assert is_sqlite_lock_error(exc) is True


@pytest.mark.unit
def test_other_operational_error_is_not_lock() -> None:
    assert is_sqlite_lock_error(_operational_error("no such table: images")) is False


@pytest.mark.unit
def test_non_operational_error_is_not_lock() -> None:
    assert is_sqlite_lock_error(ValueError("database is locked")) is False
