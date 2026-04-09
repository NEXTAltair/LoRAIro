# tests/bdd/steps/test_logging.py
"""logging.feature のステップ定義

LoRAIro のログ機能（loguru ベース）をBDDシナリオで検証する。
テスト隔離: initialize_logging() が毎回 logger.remove() するため自動リセット。
コンソール出力キャプチャ: io.StringIO に initialize_logging() と同じフィルタを適用。
"""

import io
from functools import partial
from pathlib import Path

import pytest
from loguru import logger
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.utils.log import (
    LEVEL_NAME_TO_NO,
    _level_filter,
    _parse_log_levels,
    initialize_logging,
)

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "logging.feature"
scenarios(str(_FEATURE_FILE))


# ===== Fixtures =====


@pytest.fixture
def log_config() -> dict:
    """テスト用ログ設定の基底辞書"""
    return {"level": "INFO"}


@pytest.fixture
def console_capture() -> io.StringIO:
    """コンソール出力キャプチャ用の StringIO"""
    return io.StringIO()


@pytest.fixture(autouse=True)
def cleanup_logger():
    """テスト後にロガーをクリーンアップ"""
    yield
    logger.remove()


# ===== Background Steps =====


@given("一時的な設定ディレクトリが存在する", target_fixture="config_dir")
def given_temp_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@given("一時的なログディレクトリが存在する", target_fixture="log_dir")
def given_temp_log_dir(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@given(
    parsers.parse('デフォルトのログレベルが "{default_level}" の基本ログ設定が存在する'),
    target_fixture="log_config",
)
def given_basic_log_config(default_level: str) -> dict:
    return {"level": default_level}


# ===== Scenario 1: 基本的なログ記録 =====


@given("ログ設定で一時ログディレクトリ内にログファイルパスが指定されている")
def given_log_file_path(log_config: dict, log_dir: Path) -> None:
    log_config["file_path"] = str(log_dir / "test.log")


@when("現在の設定でロガーが初期化される")
def when_logger_initialized(log_config: dict, console_capture: io.StringIO) -> None:
    initialize_logging(log_config)
    # initialize_logging と同じフィルタをテスト用 StringIO sink に適用
    default_level_no, module_level_nos = _parse_log_levels(log_config, LEVEL_NAME_TO_NO)
    filter_func = partial(
        _level_filter, default_level_no=default_level_no, module_level_nos=module_level_nos
    )
    logger.add(
        console_capture,
        level=0,
        filter=filter_func,
        format="{level} | {name} | {message}",
        colorize=False,
        backtrace=True,
        diagnose=True,
    )


@when(
    parsers.parse(
        'モジュール "{module_name}" からログレベル "{level}" のメッセージ "{message}" が出力される'
    )
)
def when_log_message(module_name: str, level: str, message: str) -> None:
    # record["name"] を上書きしてモジュール名ベースのフィルタを正しく動作させる
    logger.patch(lambda r: r.update(name=module_name)).log(level, message)


@then(parsers.parse('コンソール出力にログレベル "{level}" のメッセージ "{message}" が含まれる'))
def then_console_contains_message(console_capture: io.StringIO, level: str, message: str) -> None:
    output = console_capture.getvalue()
    assert message in output, (
        f"メッセージ '{message}' がコンソール出力に見つかりません。\n出力内容:\n{output}"
    )


@then(parsers.parse('コンソール出力にログレベル "{level}" のメッセージ "{message}" が含まれない'))
def then_console_not_contains_message(console_capture: io.StringIO, level: str, message: str) -> None:
    output = console_capture.getvalue()
    assert message not in output, (
        f"メッセージ '{message}' がコンソール出力に存在すべきではありません。\n出力内容:\n{output}"
    )


@then(parsers.parse('ログファイルの内容にログレベル "{level}" のメッセージ "{message}" が含まれる'))
def then_logfile_contains_message(log_config: dict, level: str, message: str) -> None:
    log_path = Path(log_config["file_path"])
    assert log_path.exists(), f"ログファイルが存在しません: {log_path}"
    content = log_path.read_text(encoding="utf-8")
    assert message in content, (
        f"メッセージ '{message}' がログファイルに見つかりません。\nファイル内容:\n{content}"
    )


@then(parsers.parse('ログファイルの内容にログレベル "{level}" のメッセージ "{message}" が含まれない'))
def then_logfile_not_contains_message(log_config: dict, level: str, message: str) -> None:
    log_path = Path(log_config["file_path"])
    if not log_path.exists():
        # ファイルが存在しなければ当然含まれない
        return
    content = log_path.read_text(encoding="utf-8")
    assert message not in content, (
        f"メッセージ '{message}' がログファイルに存在すべきではありません。\nファイル内容:\n{content}"
    )


# ===== Scenario Outline: ログレベル制御 =====


@given(parsers.parse('ログ設定でデフォルトレベルが "{level}" に設定されている'))
def given_log_level_set(log_config: dict, level: str) -> None:
    log_config["level"] = level


@then(parsers.parse('コンソール出力にメッセージ "{message}" が {should_or_not}'))
def then_console_should_or_not(console_capture: io.StringIO, message: str, should_or_not: str) -> None:
    output = console_capture.getvalue()
    if should_or_not.strip() == "should":
        assert message in output, (
            f"メッセージ '{message}' がコンソール出力に見つかりません (should)。\n出力内容:\n{output}"
        )
    else:
        assert message not in output, (
            f"メッセージ '{message}' がコンソール出力に存在すべきではありません (should not)。"
            f"\n出力内容:\n{output}"
        )


# ===== Scenario Outline: モジュール固有ログレベル制御 =====


@given(parsers.parse('ログ設定でモジュール "{module_prefix}" のレベルが "{level}" に設定されている'))
def given_module_log_level(log_config: dict, module_prefix: str, level: str) -> None:
    if "levels" not in log_config:
        log_config["levels"] = {}
    log_config["levels"][module_prefix] = level


# ===== Scenario: 例外ログ記録 =====


@when(
    parsers.parse(
        '"{exception_type}" を発生させメッセージ "{message}" と共に'
        " logger.exception でログ記録する関数が呼び出される"
    )
)
def when_exception_logged(exception_type: str, message: str) -> None:
    exception_classes: dict[str, type] = {
        "ValueError": ValueError,
        "TypeError": TypeError,
        "RuntimeError": RuntimeError,
    }
    exc_class = exception_classes.get(exception_type, Exception)
    try:
        raise exc_class("テスト用例外")
    except Exception:
        logger.exception(message)


@then(parsers.parse('コンソール出力にエラーメッセージ "{message}" が含まれる'))
def then_console_contains_error(console_capture: io.StringIO, message: str) -> None:
    output = console_capture.getvalue()
    assert message in output, (
        f"エラーメッセージ '{message}' がコンソール出力に見つかりません。\n出力内容:\n{output}"
    )


@then(parsers.parse('コンソール出力に "{exception_type}" のトレースバックが含まれる'))
def then_console_contains_traceback(console_capture: io.StringIO, exception_type: str) -> None:
    output = console_capture.getvalue()
    assert exception_type in output, (
        f"'{exception_type}' のトレースバックがコンソール出力に見つかりません。\n出力内容:\n{output}"
    )


@then(parsers.parse('ログファイルの内容にエラーメッセージ "{message}" が含まれる'))
def then_logfile_contains_error(log_config: dict, message: str) -> None:
    log_path = Path(log_config["file_path"])
    assert log_path.exists(), f"ログファイルが存在しません: {log_path}"
    content = log_path.read_text(encoding="utf-8")
    assert message in content, (
        f"エラーメッセージ '{message}' がログファイルに見つかりません。\nファイル内容:\n{content}"
    )


@then(parsers.parse('ログファイルの内容に "{exception_type}" のトレースバックが含まれる'))
def then_logfile_contains_traceback(log_config: dict, exception_type: str) -> None:
    log_path = Path(log_config["file_path"])
    assert log_path.exists(), f"ログファイルが存在しません: {log_path}"
    content = log_path.read_text(encoding="utf-8")
    assert exception_type in content, (
        f"'{exception_type}' のトレースバックがログファイルに見つかりません。\nファイル内容:\n{content}"
    )
