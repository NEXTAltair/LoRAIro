"""Actual images duplicates command contract once registered by the integration layer."""

import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.public_api.exceptions import ReadOnlyPreconditionError, ResultSetTooLargeError
from lorairo.services.duplicate_report_service import SavedImageHash, analyze_saved_hashes

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture
def report_api(monkeypatch):
    result = analyze_saved_hashes(
        [
            SavedImageHash(index, "0" * 16, f"stored/{index}.png", f"original/{index}.png")
            for index in (1, 2)
        ],
        max_distance=1,
        limit=1,
    )
    api = Mock(return_value=result)
    monkeypatch.setattr("lorairo.cli.commands.duplicates.report_duplicates", api)
    return api


@pytest.mark.parametrize("strict", [False, True])
def test_duplicates_json_returns_bounded_clusters_and_complete_counts(report_api, strict):
    result = runner.invoke(
        app,
        [
            "--json",
            *(["--read-only"] if strict else []),
            "images",
            "duplicates",
            "--project",
            "synthetic",
            "--max-distance",
            "1",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 2
    assert rows[0]["kind"] == "item" and rows[0]["cluster_id"] == 1
    assert rows[0]["member_count"] == 2 and rows[0]["members_truncated"]
    assert rows[0]["members"][0]["image_id"] == 1
    assert rows[1]["kind"] == "result" and rows[1]["status"] == "success"
    assert rows[1]["read_only"] and rows[1]["candidate_only"]
    assert rows[1]["total_images"] == rows[1]["clustered_images"] == 2
    assert rows[1]["max_images"] == 10_000
    report_api.assert_called_once_with("synthetic", max_distance=1, limit=1)


def test_duplicates_human_output_identifies_candidates(report_api):
    result = runner.invoke(app, ["images", "duplicates", "--project", "synthetic"])
    assert result.exit_code == 0, result.output
    assert "Duplicate candidates" in result.stdout
    assert "connected chains" in result.stdout
    report_api.assert_called_once_with("synthetic", max_distance=4, limit=100)


@pytest.mark.parametrize(
    "option,value",
    [("--max-distance", "-1"), ("--max-distance", "65"), ("--limit", "0"), ("--limit", "501")],
)
def test_duplicates_invalid_options_never_reach_api(report_api, option, value):
    result = runner.invoke(app, ["--json", "images", "duplicates", "--project", "synthetic", option, value])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout.splitlines()[-1])["code"] == "INVALID_INPUT"
    report_api.assert_not_called()


@pytest.mark.parametrize(
    "error,exit_code,code",
    [
        (ResultSetTooLargeError(10_001, 10_000), 2, "RESULT_SET_TOO_LARGE"),
        (
            ReadOnlyPreconditionError("requires preparation", reason="schema_upgrade_required"),
            1,
            "PRECONDITION_FAILED",
        ),
    ],
)
def test_duplicates_failures_are_structured_without_cluster_output(report_api, error, exit_code, code):
    report_api.side_effect = error
    result = runner.invoke(app, ["--json", "images", "duplicates", "--project", "synthetic"])
    assert result.exit_code == exit_code, result.output
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "error" and rows[0]["code"] == code
