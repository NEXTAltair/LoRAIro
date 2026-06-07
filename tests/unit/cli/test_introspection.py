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
    assert any(row["name"] == "ExportCreateInput" for row in model_rows)
    assert all(row["name"] != "ImageFilterCriteria" for row in model_rows)


def test_images_update_describes_only_supported_input_fields() -> None:
    result = runner.invoke(app, ["--json", "describe", "images update"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_rows = [row for row in rows if row.get("type") == "model" and row["role"] == "input"]
    assert [row["name"] for row in input_rows] == ["ImagesUpdateInput"]
    assert {field["name"] for field in input_rows[0]["fields"]} == {"project", "tags", "image_id"}


def test_describe_json_schema_wraps_cli_input_schema_in_item_payload() -> None:
    result = runner.invoke(app, ["--json", "describe", "export create", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert {row["kind"] for row in rows} <= {"item", "result"}
    schema_rows = [row for row in rows if row.get("type") == "schema"]
    assert schema_rows
    assert all(row["kind"] == "item" for row in schema_rows)

    input_schema = next(row for row in schema_rows if row["name"] == "ExportCreateInput")
    assert "properties" in input_schema["schema"]
    assert {"project", "output", "tags", "score_min", "score_max"} <= set(
        input_schema["schema"]["properties"]
    )
    assert "image_ids" not in input_schema["schema"]["properties"]
    assert "missing_model_litellm_id" not in input_schema["schema"]["properties"]
    assert "sql" not in json.dumps(input_schema["schema"]).lower()


def test_export_create_anyof_requires_non_null_non_empty_filter() -> None:
    """export create の anyOf は「キー存在」だけでなく非null/非空も要求する (Issue #659)。

    CLI 実体は ``_criteria_has_effective_filter`` で正規化後に truthy 判定するため、
    ``{tags: null}`` や ``--tags ""`` は UsageError で弾かれる。schema 側も string
    フィルタは minLength=1、score フィルタは number 型でこの契約に揃える。
    """
    result = runner.invoke(app, ["--json", "describe", "export create", "--schema", "json_schema"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_schema = next(
        row for row in rows if row.get("type") == "schema" and row["name"] == "ExportCreateInput"
    )
    branches = {
        tuple(branch["required"]): branch.get("properties", {})
        for branch in input_schema["schema"]["anyOf"]
    }
    # string フィルタ: 非空 (minLength=1) を要求
    for key in ("tags", "excluded_tags", "caption"):
        constraint = branches[(key,)][key]
        assert constraint["type"] == "string"
        assert constraint["minLength"] == 1
    # score フィルタ: number 型で null を除外
    for key in ("score_min", "score_max"):
        assert branches[(key,)][key]["type"] == "number"


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


def test_annotate_run_does_not_expose_public_search_schema() -> None:
    result = runner.invoke(app, ["--json", "describe", "annotate run", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert all(row.get("name") != "ImageFilterCriteria" for row in rows)


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
    # #656 merge: import-batch --json emits a JSONL result row, so it must advertise its output.
    output_row = next(
        row for row in rows if row.get("role") == "output" and row["name"] == "AnnotateImportBatchResult"
    )
    assert {"total_records", "matched", "saved", "dry_run"} <= {f["name"] for f in output_row["fields"]}


def test_cli_specific_output_json_schemas_match_item_rows() -> None:
    images_result = runner.invoke(app, ["--json", "describe", "images list", "--schema", "json_schema"])
    models_result = runner.invoke(app, ["--json", "describe", "models list", "--schema", "json_schema"])
    projects_result = runner.invoke(app, ["--json", "describe", "project list", "--schema", "json_schema"])
    images_update_result = runner.invoke(
        app, ["--json", "describe", "images update", "--schema", "json_schema"]
    )
    export_result = runner.invoke(app, ["--json", "describe", "export create", "--schema", "json_schema"])

    assert images_result.exit_code == 0
    assert models_result.exit_code == 0
    assert projects_result.exit_code == 0
    assert images_update_result.exit_code == 0
    assert export_result.exit_code == 0
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
    project_schema = next(
        row
        for row in _jsonl(projects_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output"
    )
    update_schema = next(
        row
        for row in _jsonl(images_update_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output"
    )
    export_schema = next(
        row
        for row in _jsonl(export_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output"
    )
    assert image_schema["name"] == "ImagesListItem"
    # #655 count-first / --fetch: item rows carry image_id/file_path, not id/filename/tags/annotated.
    assert set(image_schema["schema"]["properties"]) == {"image_id", "file_path"}
    assert "filename" not in image_schema["schema"]["properties"]
    # The count-first default path emits an ImagesListResult summary row instead of items.
    image_result_schema = next(
        row
        for row in _jsonl(images_result.stdout)
        if row.get("type") == "schema" and row["role"] == "output" and row["name"] == "ImagesListResult"
    )
    assert {"count", "total", "offset", "has_more"} <= set(image_result_schema["schema"]["properties"])
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
    assert project_schema["name"] == "ProjectListItem"
    assert {"name", "created", "path"} <= set(project_schema["schema"]["properties"])
    assert project_schema["schema"]["properties"]["created"]["type"] == "string"
    assert update_schema["name"] == "ImagesUpdateResult"
    assert {
        "project",
        "target_images",
        "tags",
        "added",
        "failed_tags",
    } <= set(update_schema["schema"]["properties"])
    assert export_schema["name"] == "ExportCreateResult"
    assert {"output_path"} <= set(export_schema["schema"]["properties"])


def test_remaining_cli_result_schemas_do_not_reuse_api_dtos() -> None:
    commands = {
        "project create": ("input", "ProjectCreateInput", {"name", "description"}, {"created"}),
        "project create result": ("output", "ProjectCreateResult", {"name", "path"}, {"created"}),
        "project delete": ("output", "ProjectDeleteResult", {"name"}, {"success", "data", "cancelled"}),
        "images register": (
            "output",
            "ImagesRegisterResult",
            {"total", "registered", "skipped", "errors", "error_details"},
            {"successful", "failed", "variant"},
        ),
        "models refresh": ("output", "ModelsRefreshResult", {"discovered", "summary"}, {"success", "data"}),
        "batch submit": ("output", "BatchJobResult", {"job_id", "job"}, {"success", "data"}),
        "batch cancel": ("output", "BatchJobResult", {"job_id", "job"}, {"success", "data"}),
        "batch fetch": (
            "output",
            "BatchFetchResult",
            {"job_id", "provider_status", "items", "succeeded", "failed", "artifacts"},
            {"success", "data"},
        ),
        "batch import": (
            "output",
            "BatchImportResult",
            {"imported", "skipped", "errors", "total", "job_imported"},
            {"success", "data"},
        ),
    }

    for command, (role, schema_name, required, forbidden) in commands.items():
        described = command.removesuffix(" result")
        result = runner.invoke(app, ["--json", "describe", described, "--schema", "json_schema"])
        assert result.exit_code == 0
        schema = next(
            row
            for row in _jsonl(result.stdout)
            if row.get("type") == "schema" and row["role"] == role and row["name"] == schema_name
        )
        properties = set(schema["schema"]["properties"])
        assert required <= properties
        assert forbidden.isdisjoint(properties)


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
