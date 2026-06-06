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
    result = runner.invoke(app, ["--json", "describe", "images update"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert {row["kind"] for row in rows} <= {"item", "result"}
    assert rows[0]["type"] == "tool"
    assert rows[0]["path"] == "images update"
    assert rows[-1]["kind"] == "result"
    assert rows[-1]["schema"] == "compact"

    model_rows = [row for row in rows if row.get("type") == "model"]
    assert {row["role"] for row in model_rows} >= {"input", "output", "error"}
    assert any(row["name"] == "ImageFilterCriteria" for row in model_rows)


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


def test_describe_unknown_command_uses_existing_error_kind() -> None:
    result = runner.invoke(app, ["--json", "describe", "missing command"])

    assert result.exit_code != 0
    rows = _jsonl(result.stdout)
    assert rows[-1]["kind"] == "error"
    assert rows[-1]["code"] == "INVALID_INPUT"
