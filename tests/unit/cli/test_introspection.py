"""CLI introspection command tests."""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _jsonl(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_list_commands_emits_tool_items_and_result() -> None:
    result = runner.invoke(app, ["--json", "list-commands"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[-1]["kind"] == "result"
    assert rows[-1]["ok"] is True

    items = rows[:-1]
    assert items
    assert {row["kind"] for row in rows} <= {"item", "result"}
    assert {row["type"] for row in items} == {"tool"}
    assert "images update" in {row["path"] for row in items}
    assert "annotate run" in {row["path"] for row in items}

    images_update = next(row for row in items if row["path"] == "images update")
    assert images_update["read_only"] is False
    assert "db_write" in images_update["side_effects"]


def test_describe_compact_emits_tool_model_items_and_result() -> None:
    result = runner.invoke(app, ["--json", "describe", "export create"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert {row["kind"] for row in rows} <= {"item", "result"}
    assert rows[0]["type"] == "tool"
    assert rows[0]["path"] == "export create"
    assert rows[-1]["kind"] == "result"
    assert rows[-1]["schema"] == "compact"

    model_rows = [row for row in rows if row.get("type") == "model"]
    assert {row["role"] for row in model_rows} >= {"input", "output", "error"}
    assert any(row["name"] == "ImageFilterCriteria" for row in model_rows)


def test_images_update_describes_only_supported_input_fields() -> None:
    result = runner.invoke(app, ["--json", "describe", "images update"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_rows = [row for row in rows if row.get("type") == "model" and row["role"] == "input"]
    assert [row["name"] for row in input_rows] == ["ImagesUpdateInput"]
    assert {field["name"] for field in input_rows[0]["fields"]} == {"project", "tags", "image_id"}


def test_describe_json_schema_wraps_public_schema_in_item_payload() -> None:
    result = runner.invoke(app, ["--json", "describe", "annotate run", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert {row["kind"] for row in rows} <= {"item", "result"}
    schema_rows = [row for row in rows if row.get("type") == "schema"]
    assert schema_rows
    assert all(row["kind"] == "item" for row in schema_rows)

    filter_schema = next(row for row in schema_rows if row["name"] == "ImageFilterCriteria")
    assert "properties" in filter_schema["schema"]
    assert "image_ids" in filter_schema["schema"]["properties"]
    assert "sql" not in json.dumps(filter_schema["schema"]).lower()


def test_annotate_run_describes_only_supported_flags() -> None:
    result = runner.invoke(app, ["--json", "describe", "annotate run"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "AnnotateRunInput"
    )
    field_names = {field["name"] for field in input_row["fields"]}
    assert field_names == {
        "project",
        "model",
        "limit",
        "offset",
        "image_id",
        "batch_size",
        "unrated",
        "missing_model",
    }
    assert "tags" not in field_names


def test_import_batch_describes_actual_argument_names() -> None:
    result = runner.invoke(app, ["--json", "describe", "annotate import-batch"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "AnnotateImportBatchInput"
    )
    fields = {field["name"]: field for field in input_row["fields"]}
    assert set(fields) == {"project", "jsonl_dir", "dry_run", "model_name"}
    assert fields["project"]["required"] is True
    assert fields["jsonl_dir"]["required"] is True
    assert fields["dry_run"]["default"] is False


def test_cli_specific_output_json_schemas_match_item_rows() -> None:
    images_result = runner.invoke(app, ["--json", "describe", "images list", "--schema", "json_schema"])
    models_result = runner.invoke(app, ["--json", "describe", "models list", "--schema", "json_schema"])

    assert images_result.exit_code == 0
    assert models_result.exit_code == 0
    image_schema = next(
        row
        for row in _jsonl(images_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output"
    )
    model_schema = next(
        row
        for row in _jsonl(models_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output"
    )
    assert image_schema["name"] == "ImagesListItem"
    assert set(image_schema["schema"]["properties"]) == {"id", "filename", "tags", "annotated"}
    assert "file_path" not in image_schema["schema"]["properties"]
    assert model_schema["name"] == "ModelsListItem"
    assert set(model_schema["schema"]["properties"]) == {
        "provider",
        "route",
        "litellm_id",
        "type",
        "category",
        "available",
        "deprecated",
    }
    assert "requires_api_key" not in model_schema["schema"]["properties"]


def test_error_json_schema_matches_cli_boundary_contract() -> None:
    result = runner.invoke(app, ["--json", "describe", "project list", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    error_schema = next(row for row in rows if row.get("type") == "schema" and row["role"] == "error")
    properties = error_schema["schema"]["properties"]
    assert error_schema["name"] == "CliErrorResponse"
    assert {"kind", "ok", "code", "message", "retryable", "user_action_required"} <= set(properties)
    assert "error_code" not in properties
    assert "error_message" not in properties


def test_describe_unknown_command_uses_existing_error_kind() -> None:
    result = runner.invoke(app, ["--json", "describe", "missing command"])

    assert result.exit_code != 0
    rows = _jsonl(result.stdout)
    assert rows[-1]["kind"] == "error"
    assert rows[-1]["code"] == "INVALID_INPUT"
