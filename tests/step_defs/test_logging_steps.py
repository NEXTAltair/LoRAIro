# tests/step_defs/test_logging_steps.py

import builtins
import time
from functools import partial  # partial はフィルタ関数作成に必要
from pathlib import Path
from typing import Any

import loguru  # Import for type hint
import pytest
from loguru import logger
from pytest_bdd import given, parsers, scenarios, then, when

# Import functions to be tested and helper functions
from lorairo.utils import log as log_utils

# --- Feature File Binding ---
scenarios("../features/logging.feature")

# --- Fixtures ---


@pytest.fixture(scope="function")
def log_config_state() -> dict[str, Any]:
    """テストシナリオ内でログ設定を保持・変更するための辞書フィクスチャ。"""
    return {"log": {}}  # Initialize with top-level 'log' key


@pytest.fixture(scope="function")
def temp_log_dir(tmp_path: Path) -> Path:
    """一時的なログディレクトリを作成するフィクスチャ。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture(scope="function")
def log_file_path(temp_log_dir: Path) -> Path:
    """テストで使用するログファイルパスを定義するフィクスチャ。"""
    log_path = temp_log_dir / "test_app.log"
    # Ensure file is removed if it exists from previous runs before test starts
    if log_path.exists():
        log_path.unlink()
    return log_path


# --- Test Sink Fixture ---
@pytest.fixture(scope="function")
def log_records_list() -> list[dict[str, Any]]:
    """テスト中にログレコードを収集するリスト。"""
    return []


def _test_sink_level_filter(
    record: "loguru.Record", default_level_no: int, module_level_nos: dict[str, int]
) -> bool:
    """Custom filter for the test collecting sink.
    Prioritizes 'extra.name' (from logger.bind) for module name matching,
    then falls back to record['name']. This allows testing module-specific levels
    when logs are emitted directly from test steps using logger.bind(name=...).
    """
    record_level_no = record["level"].no
    # Prioritize name from extra if available (set by logger.bind in tests)
    module_name = record["extra"].get("name", record["name"])

    # Find the longest matching prefix in module_level_nos (similar to log.py)
    longest_match = None
    matched_level_no = default_level_no
    for prefix, level_no in module_level_nos.items():
        if module_name.startswith(prefix):
            # Check if this prefix is more specific (longer) than the current match
            if longest_match is None or len(prefix) > len(longest_match):
                longest_match = prefix
                matched_level_no = level_no

    return record_level_no >= matched_level_no


def collecting_sink(records_list: list[dict[str, Any]], message):
    """ログレコードを指定されたリストに追加するシンク関数。"""
    records_list.append(message.record)  # Reverted: No need to modify record name here


# --- Given Steps ---


@given(parsers.parse("一時的な設定ディレクトリが存在する"))
def given_temporary_config_directory(tmp_path: Path):
    pass  # tmp_path fixture handles this


@given(parsers.parse("一時的なログディレクトリが存在する"))
def given_temporary_logging_directory(temp_log_dir: Path):
    assert temp_log_dir.is_dir()


@given(parsers.parse('デフォルトのログレベルが "{level}" の基本ログ設定が存在する'))
def given_default_log_configuration(log_config_state: dict[str, Any], level: str):
    log_config_state["log"] = {"level": level.upper()}


@given(parsers.parse("ログ設定で一時ログディレクトリ内にログファイルパスが指定されている"))
def given_log_config_specifies_log_file(log_config_state: dict[str, Any], log_file_path: Path):
    if "log" not in log_config_state:
        log_config_state["log"] = {}
    log_config_state["log"]["file_path"] = str(log_file_path)
    # Ensure log file path is updated if this step runs after default setup
    # File existence check moved to log_file_path fixture


@given(parsers.parse('ログ設定でデフォルトレベルが "{level}" に設定されている'))
def given_log_config_sets_default_level(log_config_state: dict[str, Any], level: str):
    if "log" not in log_config_state:
        log_config_state["log"] = {}
    log_config_state["log"]["level"] = level.upper()


@given(parsers.parse('ログ設定でモジュール "{module_prefix}" のレベルが "{level}" に設定されている'))
def given_log_config_sets_module_level(log_config_state: dict[str, Any], module_prefix: str, level: str):
    if "log" not in log_config_state:
        log_config_state["log"] = {}
    if "levels" not in log_config_state["log"]:
        log_config_state["log"]["levels"] = {}
    log_config_state["log"]["levels"][module_prefix] = level.upper()


# --- When Steps ---


@when(parsers.parse("現在の設定でロガーが初期化される"))
def when_logger_is_initialized(log_config_state: dict[str, Any], log_records_list: list[dict[str, Any]]):
    """現在のlog_config_stateを使用してロガーを初期化し、テスト用シンクを追加します。"""
    logger.remove()  # Remove default and any previous sinks

    # Initialize logger with console/file sinks based on config
    try:
        log_utils.initialize_logging(log_config_state.get("log", {}))
    except Exception as e:
        pytest.fail(f"Logger initialization failed: {e}\nConfig state: {log_config_state}")

    # --- Add Test Sink ---
    # Parse levels again to create the *exact* filter used by initialize_logging
    default_level_no, module_level_nos = log_utils._parse_log_levels(
        log_config_state.get("log", {}), log_utils.LEVEL_NAME_TO_NO
    )
    test_filter_func = partial(
        _test_sink_level_filter,  # Use the custom filter for the test sink
        default_level_no=default_level_no,
        module_level_nos=module_level_nos,
    )

    # Add the collecting sink with the same filter as the main sinks
    try:
        logger.add(
            partial(collecting_sink, log_records_list),  # Pass list to sink
            level=0,  # Let the filter control everything
            filter=test_filter_func,  # Re-enable filter for the test sink
            format="{message}",  # Simple format for easy checking
            # No need for stderr redirection
        )
    except Exception as e:
        pytest.fail(f"Failed to add collecting sink: {e}")

    time.sleep(0.1)  # Short delay potentially needed for sink setup


@when(
    parsers.parse(
        'モジュール "{module_name}" からログレベル "{level}" のメッセージ "{message}" が出力される'
    )
)
def when_log_message_is_emitted(module_name: str, level: str, message: str):
    """指定されたレベルとメッセージでログを出力します (Loguru logger.bind 使用)。"""
    bound_logger = logger.bind(name=module_name)
    level_upper = level.upper()

    if hasattr(bound_logger, level_upper.lower()):
        getattr(bound_logger, level_upper.lower())(message)
    else:
        pytest.fail(f"Invalid log level specified in step: {level}")
    time.sleep(0.1)  # Delay for processing


@when(
    parsers.parse(
        '"{exception_type}" を発生させメッセージ "{message}" と共に logger.exception でログ記録する関数が呼び出される'
    )
)
def when_function_raises_and_logs_exception(exception_type: str, message: str):
    """例外を発生させ、logger.exceptionでログ記録する関数を呼び出します。"""
    exception_class = getattr(builtins, exception_type, ValueError)

    def faulty_function():
        try:
            raise exception_class(message)
        except exception_class:
            logger.exception(message)  # Log directly using Loguru's logger
            raise

    with pytest.raises(exception_class):
        faulty_function()
    time.sleep(0.1)  # Delay for processing


# --- Then Steps ---


def find_log_record(
    records: list[dict[str, Any]], message: str, level_name: str | None = None
) -> dict[str, Any] | None:
    """ログレコードのリストから特定のメッセージとレベルを持つレコードを検索します。"""
    for record in records:
        record_message = record.get("message", "")
        record_level_obj = record.get("level")
        record_level = record_level_obj.name if record_level_obj else None
        # print(f"Checking record: msg='{record_message}', lvl='{record_level}' against msg='{message}', lvl='{level_name}'") # Debug print
        if message in record_message:  # Use 'in' for flexibility
            if level_name is None or record_level == level_name.upper():
                return record
    return None


@then(parsers.parse('コンソール出力にメッセージ "{message}" が {should_or_not}'))
def then_collected_logs_contain_message(
    log_records_list: list[dict[str, Any]], message: str, should_or_not: str
):
    """収集されたログレコードに特定のメッセージが含まれるか/含まれないかを検証します。"""
    found_record = find_log_record(log_records_list, message)
    should_find = should_or_not == "should"

    print("\n--- Checking Collected Records ---")
    print(f"Should find message '{message}': {should_find}")
    print(f"Collected Records ({len(log_records_list)}):")
    for i, r in enumerate(log_records_list):
        # Correctly access the level name for printing
        level_obj = r.get("level")
        level_name_for_print = level_obj.name if level_obj else "N/A"
        print(
            # f"  {i}: Level={r.get('level', {}).get('name')}, Name={r.get('name')}, Msg={r.get('message')}" # Incorrect
            f"  {i}: Level={level_name_for_print}, Name={r.get('name')}, Msg={r.get('message')}"
        )
    print("--- End Checking ---")

    if should_find:
        assert found_record is not None, f"ログリストにメッセージ '{message}' が見つかりませんでした。"
    else:
        assert found_record is None, (
            f"ログリストにメッセージ '{message}' が含まれていましたが、含まれないはずでした。"
        )


@then(parsers.parse('ログファイルの内容にメッセージ "{message}" が含まれる'))
def then_log_file_content_contains(log_file_path: Path, message: str):
    """ログファイルの内容を検証します (含まれる)。"""
    if not log_file_path.is_file():
        pytest.fail(f"ログファイルが見つかりません: {log_file_path}")
    content = log_file_path.read_text(encoding="utf-8")
    assert message in content, (
        f"ログファイルにメッセージ '{message}' が含まれていませんでした。\n内容:\n{content}"
    )


@then(parsers.parse('ログファイルの内容にメッセージ "{message}" が含まれない'))
def then_log_file_content_does_not_contain(log_file_path: Path, message: str):
    """ログファイルの内容を検証します (含まれない)。"""
    if not log_file_path.is_file():
        return  # ファイルがなければメッセージは含まれない
    content = log_file_path.read_text(encoding="utf-8")
    assert message not in content, (
        f"ログファイルにメッセージ '{message}' が含まれていましたが、含まれないはずでした。\n内容:\n{content}"
    )


@then(parsers.parse('コンソール出力にログレベル "{level}" のメッセージ "{message}" が含まれる'))
def then_collected_logs_contain_level_message(
    log_records_list: list[dict[str, Any]], level: str, message: str
):
    """収集されたログレコードに特定のレベルとメッセージが含まれるか検証します。"""
    found_record = find_log_record(log_records_list, message, level)

    print("\n--- Checking Collected Records (Level Specific) ---")
    print(f"Should find message '{message}' with level '{level}': True")
    print(f"Collected Records ({len(log_records_list)}):")
    for i, r in enumerate(log_records_list):
        level_obj = r.get("level")
        print(
            f"  {i}: Level={level_obj.name if level_obj else 'N/A'}, Name={r.get('name')}, Msg={r.get('message')}"
        )
    print("--- End Checking ---")

    assert found_record is not None, (
        f"ログリストにレベル '{level}' のメッセージ '{message}' が見つかりませんでした。"
    )


@then(parsers.parse('コンソール出力にログレベル "{level}" のメッセージ "{message}" が含まれない'))
def then_collected_logs_does_not_contain_level_message(
    log_records_list: list[dict[str, Any]], level: str, message: str
):
    """収集されたログレコードに特定のレベルとメッセージが含まれないか検証します。"""
    found_record = find_log_record(log_records_list, message, level)

    print("\n--- Checking Collected Records (Level Specific) ---")
    print(f"Should find message '{message}' with level '{level}': False")
    print(f"Collected Records ({len(log_records_list)}):")
    for i, r in enumerate(log_records_list):
        level_obj = r.get("level")
        print(
            f"  {i}: Level={level_obj.name if level_obj else 'N/A'}, Name={r.get('name')}, Msg={r.get('message')}"
        )
    print("--- End Checking ---")

    assert found_record is None, (
        f"ログリストにレベル '{level}' のメッセージ '{message}' が含まれていましたが、含まれないはずでした。"
    )


@then(parsers.parse('ログファイルの内容にログレベル "{level}" のメッセージ "{message}" が含まれる'))
def then_log_file_content_contains_level_message(log_file_path: Path, level: str, message: str):
    """ログファイルの内容に特定のレベルとメッセージが含まれるか検証します。"""
    if not log_file_path.is_file():
        pytest.fail(f"ログファイルが見つかりません: {log_file_path}")
    content = log_file_path.read_text(encoding="utf-8")
    expected_pattern_level = f"| {level.upper(): <8} |"  # Format from log.py
    assert expected_pattern_level in content, f"ログファイルにレベル '{level}' が見つかりませんでした。"
    assert message in content, (
        f"ログファイルにメッセージ '{message}' が見つかりませんでした。\n内容:\n{content}"
    )


@then(parsers.parse('ログファイルの内容にログレベル "{level}" のメッセージ "{message}" が含まれない'))
def then_log_file_content_does_not_contain_level_message(log_file_path: Path, level: str, message: str):
    """ログファイルの内容に特定のレベルとメッセージが含まれないか検証します。"""
    if not log_file_path.is_file():
        return
    content = log_file_path.read_text(encoding="utf-8")
    # Check if the specific message exists first
    if message in content:
        # If message exists, check if the line also contains the level.
        # This is less strict than full parsing but avoids false positives if only level exists elsewhere.
        lines_with_message = [line for line in content.splitlines() if message in line]
        expected_pattern_level = f"| {level.upper(): <8} |"
        found_with_level = False
        for line in lines_with_message:
            if expected_pattern_level in line:
                found_with_level = True
                break
        assert not found_with_level, (
            f"ログファイルにレベル '{level}' のメッセージ '{message}' が含まれていましたが、含まれないはずでした。\n内容:\n{content}"
        )


@then(parsers.parse('コンソール出力にエラーメッセージ "{message}" が含まれる'))
def then_collected_logs_contain_error_message(log_records_list: list[dict[str, Any]], message: str):
    """収集されたログ（例外含む）に特定のエラーメッセージが含まれるか検証します。"""
    # Check both regular message and exception message
    found = False
    for record in log_records_list:
        if message in record.get("message", ""):
            found = True
            break
        exception_tuple = record.get("exception")
        if exception_tuple:
            exc_type, exc_value, exc_traceback = exception_tuple
            if exc_value and message in str(exc_value):
                found = True
                break
    assert found, f"収集されたログにエラーメッセージ '{message}' が見つかりませんでした。"


@then(parsers.parse('ログファイルの内容にエラーメッセージ "{message}" が含まれる'))
def then_log_file_content_contains_error_message(log_file_path: Path, message: str):
    """ログファイルの内容に特定のエラーメッセージが含まれるか検証します。"""
    if not log_file_path.is_file():
        pytest.fail(f"ログファイルが見つかりません: {log_file_path}")
    content = log_file_path.read_text(encoding="utf-8")
    assert message in content, (
        f"ログファイルにエラーメッセージ '{message}' が含まれていませんでした。\n内容:\n{content}"
    )


@then(parsers.parse('コンソール出力に "{exception_type}" のトレースバックが含まれる'))
def then_collected_logs_contain_traceback(log_records_list: list[dict[str, Any]], exception_type: str):
    """収集されたログレコードに特定の例外トレースバックが含まれるか検証します。"""
    found_traceback = False
    for record in log_records_list:
        exception_tuple = record.get("exception")
        if exception_tuple:
            exc_type, exc_value, exc_traceback = exception_tuple
            # Check if the exception type name matches
            if exc_type and exc_type.__name__ == exception_type:
                # Check if traceback object exists (basic check)
                # A more thorough check might inspect the traceback content if needed
                if exc_traceback:
                    found_traceback = True
                    break
    assert found_traceback, f"収集されたログに '{exception_type}' のトレースバックが見つかりませんでした。"


@then(parsers.parse('ログファイルの内容に "{exception_type}" のトレースバックが含まれる'))
def then_log_file_content_contains_traceback(log_file_path: Path, exception_type: str):
    """ログファイルの内容に特定の例外タイプのトレースバックが含まれるか検証します。"""
    if not log_file_path.is_file():
        pytest.fail(f"ログファイルが見つかりません: {log_file_path}")
    content = log_file_path.read_text(encoding="utf-8")
    assert "Traceback (most recent call last):" in content, (
        "ログファイルにトレースバックマーカーが見つかりませんでした。"
    )
    assert exception_type in content, (
        f"ログファイルに例外タイプ '{exception_type}' が見つかりませんでした。"
    )
