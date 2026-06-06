"""CLI 中央エラー境界 (``lorairo.cli.main``) の test (ADR 0057 §6/§7)。"""

from __future__ import annotations

import json

import click
import pytest

from lorairo.api import exceptions as app_exc
from lorairo.cli._errors import ErrorCode, classify_exception
from lorairo.cli.commands.annotate import AnnotationRunFailedError, AnnotationSelectionError
from lorairo.cli.main import _handle_cli_exception, _handle_click_exception


def _stdout_error_line(captured: str) -> dict:
    lines = [line for line in captured.splitlines() if line.strip()]
    return json.loads(lines[-1])


@pytest.mark.unit
@pytest.mark.cli
def test_handle_cli_exception_value_error_json(capsys: pytest.CaptureFixture[str]) -> None:
    """ValueError → INVALID_INPUT 行 + exit 2 (JSONL モード)。"""
    exit_code = _handle_cli_exception(ValueError("bad arg"), json_mode=True)
    line = _stdout_error_line(capsys.readouterr().out)
    assert exit_code == 2
    assert line["kind"] == "error"
    assert line["code"] == "INVALID_INPUT"
    assert line["ok"] is False


@pytest.mark.unit
@pytest.mark.cli
def test_handle_cli_exception_not_found_returns_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    """ProjectNotFoundError → NOT_FOUND 行 + exit 1。"""
    exit_code = _handle_cli_exception(app_exc.ProjectNotFoundError("p"), json_mode=True)
    line = _stdout_error_line(capsys.readouterr().out)
    assert exit_code == 1
    assert line["code"] == "NOT_FOUND"


@pytest.mark.unit
@pytest.mark.cli
def test_handle_cli_exception_internal_writes_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    """INTERNAL_ERROR のみ stderr に traceback、stdout は JSONL 行のみ。"""
    try:
        raise KeyError("boom")
    except KeyError as exc:
        exit_code = _handle_cli_exception(exc, json_mode=True)
    captured = capsys.readouterr()
    line = _stdout_error_line(captured.out)
    assert exit_code == 1
    assert line["code"] == "INTERNAL_ERROR"
    assert "Traceback" in captured.err


@pytest.mark.unit
@pytest.mark.cli
def test_handle_click_exception_maps_to_invalid_input(capsys: pytest.CaptureFixture[str]) -> None:
    """Click usage error → INVALID_INPUT 行 + exit 2。"""
    exit_code = _handle_click_exception(click.UsageError("no such option"), json_mode=True)
    line = _stdout_error_line(capsys.readouterr().out)
    assert exit_code == 2
    assert line["code"] == "INVALID_INPUT"


@pytest.mark.unit
@pytest.mark.cli
def test_handle_cli_exception_rich_mode_keeps_stdout_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """rich モードでは stdout に JSON を出さず、エラーは stderr へ。"""
    exit_code = _handle_cli_exception(ValueError("bad"), json_mode=False)
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out.strip() == ""
    assert "Error" in captured.err


@pytest.mark.unit
@pytest.mark.cli
def test_classify_annotation_selection_as_user_action_error() -> None:
    """Annotation selection failures are user-action/precondition errors."""
    info = classify_exception(AnnotationSelectionError("No images selected"))

    assert info.code == ErrorCode.PRECONDITION_FAILED
    assert info.user_action_required is True


@pytest.mark.unit
@pytest.mark.cli
def test_classify_annotation_run_failure_as_user_action_error() -> None:
    """Annotation terminal run failures are not internal crashes."""
    info = classify_exception(AnnotationRunFailedError("Annotation produced no results"))

    assert info.code == ErrorCode.PRECONDITION_FAILED
    assert info.user_action_required is True


@pytest.mark.unit
@pytest.mark.cli
def test_classify_batch_import_error_as_validation_error() -> None:
    """Malformed batch import input is classified as user-fixable validation."""
    info = classify_exception(app_exc.BatchImportError("bad JSONL"))

    assert info.code == ErrorCode.VALIDATION_FAILED
    assert info.user_action_required is True
