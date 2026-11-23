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


# --- SQL 中断判定 (Issue #1621) ---


@pytest.mark.unit
def test_detects_interrupted_query() -> None:
    from lorairo.database.db_errors import is_sqlite_interrupt_error

    assert is_sqlite_interrupt_error(_operational_error("interrupted")) is True


@pytest.mark.unit
def test_detects_interrupt_wrapped_in_value_error() -> None:
    """tag-db が ValueError に包んで送出しても cause chain から中断を検出する。"""
    from lorairo.database.db_errors import is_sqlite_interrupt_error

    try:
        try:
            raise _operational_error("(sqlite3.OperationalError) interrupted", module="sqlalchemy.exc")
        except Exception as inner:
            raise ValueError("DB operation failed: interrupted") from inner
    except ValueError as outer:
        assert is_sqlite_interrupt_error(outer) is True


@pytest.mark.unit
def test_lock_and_plain_errors_are_not_interrupt() -> None:
    from lorairo.database.db_errors import is_sqlite_interrupt_error

    assert is_sqlite_interrupt_error(_operational_error("database is locked")) is False
    assert is_sqlite_interrupt_error(ValueError("interrupted")) is False


@pytest.mark.unit
def test_interrupt_propagates_only_inside_registration_context() -> None:
    """中断の伝播は propagate_sqlite_interrupts の文脈内だけ (#1621)。"""
    from lorairo.database.db_errors import propagate_sqlite_interrupts, should_propagate_sqlite_interrupt

    interrupted = _operational_error("interrupted")
    assert should_propagate_sqlite_interrupt(interrupted) is False
    with propagate_sqlite_interrupts():
        assert should_propagate_sqlite_interrupt(interrupted) is True
        assert should_propagate_sqlite_interrupt(_operational_error("database is locked")) is False
    assert should_propagate_sqlite_interrupt(interrupted) is False
