"""CLI 構造化エラー契約 (``lorairo.cli._errors``) の test (ADR 0057 §4/§5/§6)。"""

from __future__ import annotations

import pytest

from lorairo.cli._errors import ErrorCode, classify_exception, hint_for
from lorairo.public_api import exceptions as app_exc


@pytest.mark.unit
@pytest.mark.cli
def test_error_code_set_has_15_members() -> None:
    """エラーコードは全 15 種 (ADR 0057 §4)。"""
    assert len(list(ErrorCode)) == 15
    assert ErrorCode.RESULT_SET_TOO_LARGE in set(ErrorCode)


@pytest.mark.unit
@pytest.mark.cli
@pytest.mark.parametrize(
    ("code", "expected_exit"),
    [
        (ErrorCode.INVALID_INPUT, 2),
        (ErrorCode.VALIDATION_FAILED, 2),
        (ErrorCode.RESULT_SET_TOO_LARGE, 2),
        (ErrorCode.NETWORK_ERROR, 1),
        (ErrorCode.INTERNAL_ERROR, 1),
        (ErrorCode.AUTH_ERROR, 1),
        (ErrorCode.NOT_FOUND, 1),
    ],
)
def test_exit_code_policy(code: ErrorCode, expected_exit: int) -> None:
    """exit code は入力系 (2) と実行時 (1) で導出される (ADR 0057 §6 / 0060)。"""
    from lorairo.cli._errors import ErrorInfo

    assert ErrorInfo(code, retryable=False, user_action_required=False).exit_code == expected_exit


@pytest.mark.unit
@pytest.mark.cli
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ValueError("bad"), ErrorCode.INVALID_INPUT),
        (TimeoutError(), ErrorCode.TIMEOUT),
        (FileNotFoundError("missing"), ErrorCode.IO_ERROR),
        (KeyError("x"), ErrorCode.INTERNAL_ERROR),
        (ConnectionError("net"), ErrorCode.NETWORK_ERROR),
    ],
)
def test_classify_standard_exceptions(exc: BaseException, expected: ErrorCode) -> None:
    """標準例外が正しいコードに分類される。"""
    assert classify_exception(exc).code == expected


@pytest.mark.unit
@pytest.mark.cli
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (app_exc.ProjectNotFoundError("p"), ErrorCode.NOT_FOUND),
        (app_exc.ImageNotFoundError(7), ErrorCode.NOT_FOUND),
        (app_exc.ProjectAlreadyExistsError("p"), ErrorCode.ALREADY_EXISTS),
        (app_exc.DuplicateImageError("a.png", 3), ErrorCode.ALREADY_EXISTS),
        (app_exc.APIKeyNotConfiguredError("openai"), ErrorCode.AUTH_ERROR),
        (app_exc.InvalidInputError("name", "empty"), ErrorCode.VALIDATION_FAILED),
        (app_exc.InvalidFormatError("xyz", ["txt", "json"]), ErrorCode.INVALID_INPUT),
        (app_exc.DatabaseConnectionError("p", "locked"), ErrorCode.DB_ERROR),
        (app_exc.ResultSetTooLargeError(501, 500), ErrorCode.RESULT_SET_TOO_LARGE),
    ],
)
def test_classify_lorairo_exceptions(exc: BaseException, expected: ErrorCode) -> None:
    """LoRAIro 独自例外が正しいコードに分類される。"""
    assert classify_exception(exc).code == expected


@pytest.mark.unit
@pytest.mark.cli
def test_classify_resource_exhausted_by_name() -> None:
    """OOM 系 (ImageLoadMemoryError / OutOfMemoryError) は RESOURCE_EXHAUSTED。"""
    oom = type("ImageLoadMemoryError", (RuntimeError,), {})("fatal")
    assert classify_exception(oom).code == ErrorCode.RESOURCE_EXHAUSTED


@pytest.mark.unit
@pytest.mark.cli
def test_classify_resource_exhausted_by_runtime_message() -> None:
    """``RuntimeError('... out of memory ...')`` は RESOURCE_EXHAUSTED。"""
    assert classify_exception(RuntimeError("CUDA out of memory")).code == ErrorCode.RESOURCE_EXHAUSTED


@pytest.mark.unit
@pytest.mark.cli
def test_classify_walks_cause_chain_for_true_cause() -> None:
    """wrap された真因 (API キー未設定) を cause-chain で拾い AUTH_ERROR にする。"""
    try:
        try:
            raise app_exc.APIKeyNotConfiguredError("claude")
        except app_exc.APIKeyNotConfiguredError as cause:
            raise app_exc.AnnotationFailedError("m", 5, "wrapped") from cause
    except app_exc.AnnotationFailedError as exc:
        assert classify_exception(exc).code == ErrorCode.AUTH_ERROR


@pytest.mark.unit
@pytest.mark.cli
def test_classify_sdk_auth_and_rate_by_module() -> None:
    """プロバイダ SDK の AuthenticationError / RateLimitError を module で分類する。"""
    auth = type("AuthenticationError", (Exception,), {"__module__": "openai"})("401")
    rate = type("RateLimitError", (Exception,), {"__module__": "anthropic"})("429")
    assert classify_exception(auth).code == ErrorCode.AUTH_ERROR
    assert classify_exception(rate).code == ErrorCode.RATE_LIMITED


@pytest.mark.unit
@pytest.mark.cli
def test_classify_sqlalchemy_by_module() -> None:
    """sqlalchemy 由来の例外は DB_ERROR (eager import せず module で判定)。"""
    db = type("OperationalError", (Exception,), {"__module__": "sqlalchemy.exc"})("locked")
    assert classify_exception(db).code == ErrorCode.DB_ERROR


@pytest.mark.unit
@pytest.mark.cli
def test_classify_sqlite_lock_as_conflict() -> None:
    """SQLite の database is locked は再試行可能な CONFLICT に分類する (Issue #767)。"""
    locked = type("OperationalError", (Exception,), {"__module__": "sqlalchemy.exc"})(
        "(sqlite3.OperationalError) database is locked"
    )
    info = classify_exception(locked)
    assert info.code == ErrorCode.CONFLICT
    assert info.retryable is True


@pytest.mark.unit
@pytest.mark.cli
def test_classify_sqlite_lock_wrapped_in_cause_chain() -> None:
    """cause chain 下層の database is locked も CONFLICT として拾う (Issue #767)。"""
    orig = type("OperationalError", (Exception,), {"__module__": "sqlite3"})("database is locked")
    try:
        raise RuntimeError("save failed") from orig
    except RuntimeError as exc:
        assert classify_exception(exc).code == ErrorCode.CONFLICT


@pytest.mark.unit
@pytest.mark.cli
def test_classify_pydantic_validation_before_value_error() -> None:
    """Pydantic ValidationError は ValueError subclass だが VALIDATION_FAILED にする。"""
    pyd = type("ValidationError", (ValueError,), {"__module__": "pydantic"})("invalid")
    assert classify_exception(pyd).code == ErrorCode.VALIDATION_FAILED


@pytest.mark.unit
@pytest.mark.cli
def test_hint_for_known_codes() -> None:
    """対処ヒントが定義済みコードに返り、未定義には None。"""
    assert hint_for(ErrorCode.RESULT_SET_TOO_LARGE) is not None
    assert hint_for(ErrorCode.AUTH_ERROR) is not None
    assert hint_for(ErrorCode.CONFLICT) is not None
    assert hint_for(ErrorCode.INTERNAL_ERROR) is None
