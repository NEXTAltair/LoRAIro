"""Offline processing CLI contract and ID input boundaries."""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.public_api.processing import ProcessingOutcome

runner = CliRunner()


@pytest.mark.parametrize(
    ("count", "file_input", "expected"),
    [(0, False, 2), (1, False, 0), (500, False, 0), (501, False, 2), (501, True, 0)],
)
def test_processing_id_boundaries(tmp_path, monkeypatch, count, file_input, expected):
    fake = MagicMock(
        side_effect=lambda project, ids, resolution, **kwargs: [
            ProcessingOutcome(image_id, "success", resolution, f"processed/{image_id}.webp", image_id)
            for image_id in ids
        ]
    )
    monkeypatch.setattr("lorairo.cli.commands.processing.process_images", fake)
    values = ",".join(map(str, range(1, count + 1)))
    option = "--image-ids"
    if file_input:
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text(values)
        values = str(ids_file)
        option = "--image-ids-file"
    result = runner.invoke(app, ["--json", "images", "process", "-p", "project", option, values])
    assert result.exit_code == expected
    if expected:
        fake.assert_not_called()
    else:
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        from lorairo.cli.introspection import ImagesProcessItem, ImagesProcessResult

        for row in rows[:-1]:
            ImagesProcessItem.model_validate(row)
        ImagesProcessResult.model_validate(rows[-1])
        assert len(rows) == count + 1
        assert rows[-1]["processed"] == count
        assert rows[-1]["status"] == "success"


@pytest.mark.parametrize(
    ("statuses", "exit_code", "status"),
    [
        (["success"], 0, "success"),
        (["skipped"], 0, "success"),
        (["success", "failed"], 1, "partial_success"),
        (["skipped", "failed"], 1, "partial_success"),
        (["failed"], 1, "failed"),
    ],
)
def test_processing_outcomes(monkeypatch, statuses, exit_code, status):
    outcomes = [
        ProcessingOutcome(index, value, 768, reason="failure" if value == "failed" else None)
        for index, value in enumerate(statuses, 1)
    ]
    fake = MagicMock(return_value=outcomes)
    monkeypatch.setattr("lorairo.cli.commands.processing.process_images", fake)
    result = runner.invoke(
        app,
        ["--json", "images", "process", "-p", "project", "--image-ids", "1,2", "-r", "768", "--rebuild"],
    )
    assert result.exit_code == exit_code
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["status"] for row in rows[:-1]] == statuses
    assert rows[-1]["ok"] is (not exit_code)
    assert rows[-1]["status"] == status
    assert rows[-1]["total"] == len(statuses)
    fake.assert_called_once_with("project", [1, 2], 768, rebuild=True)


@pytest.mark.parametrize("resolution", [0, 1, 31, 33, 8193])
def test_processing_resolution_validation(monkeypatch, resolution):
    fake = MagicMock()
    monkeypatch.setattr("lorairo.cli.commands.processing.process_images", fake)
    result = runner.invoke(
        app, ["--json", "images", "process", "-p", "project", "--image-ids", "1", "-r", str(resolution)]
    )
    assert result.exit_code == 2
    fake.assert_not_called()


def test_processing_describe_schema_and_help():
    result = runner.invoke(app, ["--json", "describe", "images process", "--schema", "json_schema"])
    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    schemas = {row["name"]: row for row in rows if row.get("type") == "schema"}
    assert {"ImagesProcessInput", "ImagesProcessItem", "ImagesProcessResult"} <= schemas.keys()
    help_result = runner.invoke(app, ["images", "process", "--help"])
    assert help_result.exit_code == 0
    assert "--image-ids-file" in help_result.stdout
    assert "--rebuild" in help_result.stdout
