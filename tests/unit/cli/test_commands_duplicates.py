"""Actual images duplicates command contract once registered by the integration layer."""

import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app, main
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
def test_duplicates_invalid_options_never_reach_api(report_api, option, value, capsys):
    # The installed entry point formats parse errors before the command boundary;
    # bare CliRunner(app) uses Click's human-readable parse-error handling.
    with pytest.raises(SystemExit) as caught:
        main(["--json", "images", "duplicates", "--project", "synthetic", option, value])
    assert caught.value.code == 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["code"] == "INVALID_INPUT"
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


# ---- 代表画像の出力 (#1604) ----


def _sized(image_id, phash, width, height):
    return SavedImageHash(
        image_id, phash, f"s/{image_id}.png", f"o/{image_id}.png", width=width, height=height
    )


@pytest.fixture
def representative_api(monkeypatch):
    images = [
        _sized(1, "0" * 16, 10, 10),
        _sized(2, "0" * 16, 30, 30),
        _sized(3, "ffffffffffffffff", 99, 99),  # 単独画像
        _sized(4, "00000000000000ff", 5, 5),
        _sized(5, "00000000000000ff", 5, 5),
        _sized(6, "ff00000000000000", 8, 8),
        _sized(7, "ff00000000000000", 9, 9),
    ]
    api = Mock(
        side_effect=lambda project, *, max_distance, limit: analyze_saved_hashes(
            images, max_distance=max_distance, limit=limit
        )
    )
    monkeypatch.setattr("lorairo.cli.commands.duplicates.report_duplicates", api)
    return api


def test_representatives_plain_stdout_is_integer_ids_only_and_summary_goes_to_stderr(representative_api):
    result = runner.invoke(
        app, ["images", "duplicates", "--project", "synthetic", "--max-distance", "0", "--representatives"]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["2", "4", "7"]
    assert "representative" in result.stderr.lower()
    assert "reference only" in result.stderr.lower()
    representative_api.assert_called_once_with("synthetic", max_distance=0, limit=100)


def test_representatives_json_rows_have_stable_contract(representative_api):
    result = runner.invoke(
        app,
        ["--json", "images", "duplicates", "-p", "synthetic", "--max-distance", "0", "--representatives"],
    )
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    items, summary = rows[:-1], rows[-1]
    assert [row["image_id"] for row in items] == [2, 4, 7]
    assert all(row["kind"] == "item" for row in items)
    assert items[0] == {
        "kind": "item",
        "image_id": 2,
        "cluster_id": 1,
        "member_count": 2,
        "width": 30,
        "height": 30,
        "pixel_count": 900,
    }
    assert summary["kind"] == "result" and summary["status"] == "success"
    assert summary["representatives_only"] is True
    assert summary["representative_count"] == 3
    assert summary["cluster_count"] == 3 and summary["unclustered_images"] == 1
    assert summary["read_only"] is True and summary["candidate_only"] is True
    assert "cluster_id" not in summary and 3 not in [row["image_id"] for row in items]
    # クラスタ報告の出力上限に関する値は代表モードの result に含めない
    assert {"limit", "returned_clusters", "clusters_truncated"}.isdisjoint(summary)


def test_representatives_json_reports_complete_count_and_review_cap(representative_api):
    result = runner.invoke(
        app, ["--json", "images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["representative_count"] == 3
    assert summary["review_max_images"] == 500 and summary["exceeds_review_max_images"] is False
    assert summary["reference_only"] is True


@pytest.mark.parametrize("json_mode", [False, True])
def test_representatives_reject_explicit_limit_without_calling_api(representative_api, json_mode):
    args = [*(["--json"] if json_mode else []), "images", "duplicates", "-p", "s", "--representatives"]
    result = runner.invoke(app, [*args, "--limit", "2"])
    assert result.exit_code == 2, result.output
    if json_mode:
        assert json.loads(result.stdout.splitlines()[-1])["code"] == "INVALID_INPUT"
    representative_api.assert_not_called()


def test_representatives_are_not_capped_by_the_default_limit_and_warn_above_review_cap(monkeypatch):
    images = [
        _sized(2 * pair + offset, f"{pair:016x}", 10 + offset, 10)
        for pair in range(1, 502)
        for offset in (1, 2)
    ]
    report = analyze_saved_hashes(images, max_distance=0, limit=100)
    monkeypatch.setattr("lorairo.cli.commands.duplicates.report_duplicates", Mock(return_value=report))
    plain = runner.invoke(
        app, ["images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    assert plain.exit_code == 0, plain.output
    ids = plain.stdout.splitlines()
    assert len(ids) == 501 and all(line.isdigit() for line in ids)
    assert "split" in plain.stderr and "500" in plain.stderr
    structured = runner.invoke(
        app, ["--json", "images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    summary = json.loads(structured.stdout.splitlines()[-1])
    assert summary["representative_count"] == 501 and summary["exceeds_review_max_images"] is True
    assert len(structured.stdout.splitlines()) == 502


def test_representatives_with_no_clusters_emit_nothing_on_stdout_and_exit_zero(monkeypatch):
    report = analyze_saved_hashes([_sized(1, "0" * 16, 1, 1), _sized(2, "f" * 16, 1, 1)], max_distance=0)
    monkeypatch.setattr("lorairo.cli.commands.duplicates.report_duplicates", Mock(return_value=report))
    plain = runner.invoke(
        app, ["images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    assert plain.exit_code == 0, plain.output
    assert plain.stdout == ""
    structured = runner.invoke(
        app, ["--json", "images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    rows = [json.loads(line) for line in structured.stdout.splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "result"
    assert rows[0]["representative_count"] == 0 and rows[0]["exceeds_review_max_images"] is False


def test_default_output_without_representatives_is_unchanged(representative_api):
    result = runner.invoke(app, ["--json", "images", "duplicates", "-p", "s", "--max-distance", "0"])
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert all("representatives_only" not in row and "image_id" not in row for row in rows)
    assert {"cluster_id"} <= set(rows[0])


def test_representatives_failures_use_the_same_structured_errors(representative_api):
    representative_api.side_effect = ResultSetTooLargeError(10_001, 10_000)
    result = runner.invoke(app, ["--json", "images", "duplicates", "-p", "s", "--representatives"])
    assert result.exit_code == 2
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 1 and rows[0]["code"] == "RESULT_SET_TOO_LARGE"


def test_representatives_result_has_no_cluster_report_cap_values_with_many_clusters(monkeypatch):
    images = [
        _sized(2 * pair + offset, f"{pair:016x}", 10 + offset, 10)
        for pair in range(1, 602)
        for offset in (1, 2)
    ]
    report = analyze_saved_hashes(images, max_distance=0, limit=100)
    assert report.clusters_truncated and report.returned_clusters == 100
    monkeypatch.setattr("lorairo.cli.commands.duplicates.report_duplicates", Mock(return_value=report))
    result = runner.invoke(
        app, ["--json", "images", "duplicates", "-p", "s", "--max-distance", "0", "--representatives"]
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    summary = rows[-1]
    assert len(rows) - 1 == summary["representative_count"] == 601
    assert {"limit", "returned_clusters", "clusters_truncated"}.isdisjoint(summary)
    assert summary["cluster_count"] == 601
