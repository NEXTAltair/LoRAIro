"""CLI introspection command tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
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

    paths = {row["path"] for row in items}
    assert "images search" in paths
    assert "tags add" in paths
    assert "tags remove" in paths
    assert "tags replace" in paths


def test_list_commands_includes_version_and_status() -> None:
    """version / status も introspection に載る (Issue #662)。"""
    result = runner.invoke(app, ["--json", "list-commands"])

    assert result.exit_code == 0
    items = [row for row in _jsonl(result.stdout) if row["kind"] == "item"]
    by_path = {row["path"]: row for row in items}

    assert "version" in by_path
    assert by_path["version"]["read_only"] is True
    assert by_path["version"]["side_effects"] == []

    assert "status" in by_path
    assert by_path["status"]["read_only"] is True
    assert "file_read" in by_path["status"]["side_effects"]


def test_describe_status_exposes_status_result_schema() -> None:
    """describe status が StatusResult 出力スキーマを返す (Issue #662)。"""
    result = runner.invoke(app, ["--json", "describe", "status", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_rows = [row for row in rows if row.get("type") == "schema"]
    status_schema = next(row for row in schema_rows if row["name"] == "StatusResult")
    properties = set(status_schema["schema"]["properties"])
    assert {"environment", "phase", "config_found", "api_keys"} <= properties


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

    input_row = next(row for row in model_rows if row["name"] == "ExportCreateInput")
    field_names = {f["name"] for f in input_row["fields"]}
    assert "image_ids" in field_names
    assert "tags" not in field_names


def test_images_update_describes_only_supported_input_fields() -> None:
    result = runner.invoke(app, ["--json", "describe", "images update"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_rows = [row for row in rows if row.get("type") == "model" and row["role"] == "input"]
    assert [row["name"] for row in input_rows] == ["GlobalOptions", "ImagesUpdateInput"]
    assert {field["name"] for field in input_rows[0]["fields"]} == {
        "workspace",
        "config",
        "log_level",
        "json_output",
        "install_completion",
        "show_completion",
    }
    assert {field["name"] for field in input_rows[1]["fields"]} == {"project", "tags", "image_id"}


def test_describe_images_list_documents_count_first_gate() -> None:
    """images list の fetch/limit/offset が count-first gate を説明する (Issue #663)。"""
    result = runner.invoke(app, ["--json", "describe", "images list"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_model = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "ImagesListInput"
    )
    fields = {field["name"]: field.get("description", "") for field in input_model["fields"]}

    # fetch は総数 <= 500 のときだけ成功し、超過時は RESULT_SET_TOO_LARGE になる旨を明示。
    assert "RESULT_SET_TOO_LARGE" in fields["fetch"]
    assert "500" in fields["fetch"]
    # limit/offset は count-first gate を回避しないことを明示。
    assert "500" in fields["limit"]
    assert "bypass" in fields["limit"].lower()
    assert "500" in fields["offset"]


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
    assert {"project", "output", "image_ids", "resolution", "tag_languages"} <= set(
        input_schema["schema"]["properties"]
    )
    # 旧フィルタ API は削除済み
    for old_field in ("tags", "excluded_tags", "caption", "score_min", "score_max"):
        assert old_field not in input_schema["schema"]["properties"]
    assert "missing_model_litellm_id" not in input_schema["schema"]["properties"]
    assert "sql" not in json.dumps(input_schema["schema"]).lower()


def test_export_create_image_ids_inputs_and_no_filter_anyof() -> None:
    """export create は image_ids / image_ids_file を受け、旧フィルタ anyOf は削除済み。

    新 API は image_ids (CSV) または image_ids_file (bulk、Issue #1216) を受け付け、
    tags/score/caption フィルタは受け付けない。
    """
    result = runner.invoke(app, ["--json", "describe", "export create", "--schema", "json_schema"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_schema = next(
        row for row in rows if row.get("type") == "schema" and row["name"] == "ExportCreateInput"
    )
    schema = input_schema["schema"]
    properties = schema.get("properties", {})
    # image_ids / image_ids_file は「どちらか一方」で単独必須ではない (Issue #1216)
    assert "image_ids" not in schema.get("required", [])
    assert "image_ids" in properties
    assert "image_ids_file" in properties
    # 旧フィルタ anyOf は削除済み
    assert "anyOf" not in schema
    # 旧フィルタフィールドは存在しない
    for old_field in ("tags", "excluded_tags", "caption", "score_min", "score_max"):
        assert old_field not in properties


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
        "output",
        "resolution",
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


def test_batch_submit_describes_csv_image_ids() -> None:
    result = runner.invoke(app, ["--json", "describe", "batch submit"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "BatchSubmitInput"
    )
    fields = {field["name"]: field for field in input_row["fields"]}

    assert "image_id" not in fields
    assert fields["image_ids"]["type"] == "str"
    assert fields["image_ids"]["required"] is True
    assert "Comma-separated" in fields["image_ids"]["description"]


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


def test_project_delete_input_advertises_json_mode_force_requirement() -> None:
    """describe project delete の force フィールドは JSON mode 必須要件を明示する (Issue #659)。

    JSON mode で --force 必須を強制 (INVALID_INPUT) する一方、introspection 契約で
    force を optional/default のまま放置すると agent が {name} 単独を valid と誤認する。
    field description で必須要件を contract として明示する。
    """
    result = runner.invoke(app, ["--json", "describe", "project delete"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "ProjectDeleteInput"
    )
    force_field = next(field for field in input_row["fields"] if field["name"] == "force")
    assert "JSON mode" in force_field["description"]
    assert "INVALID_INPUT" in force_field["description"]


def test_remaining_cli_result_schemas_do_not_reuse_api_dtos() -> None:
    commands = {
        "project create": ("input", "ProjectCreateInput", {"name", "description"}, {"created"}),
        "project create result": ("output", "ProjectCreateResult", {"name", "path"}, {"created"}),
        "project delete": ("output", "ProjectDeleteResult", {"name"}, {"success", "data", "cancelled"}),
        "images register": (
            "output",
            "ImagesRegisterResult",
            {"total", "registered", "skipped", "errors", "error_details"},
            {"successful", "failed"},
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


def test_batch_status_describes_items_option_and_outputs() -> None:
    """batch status が --items / --limit / --offset / --item-status を describe する (Issue #673)。"""
    result = runner.invoke(app, ["--json", "describe", "batch status"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "BatchStatusInput"
    )
    field_names = {f["name"] for f in input_row["fields"]}
    assert {"job_id", "project", "refresh", "items", "limit", "offset", "item_status"} <= field_names

    output_names = {
        row["name"] for row in rows if row.get("type") == "model" and row.get("role") == "output"
    }
    assert "ProviderBatchItemRecord" in output_names
    assert "BatchStatusResult" in output_names


def test_batch_status_result_schema_includes_items_pagination_fields() -> None:
    """BatchStatusResult / ProviderBatchItemRecord スキーマが items フィールドを持つ (Issue #673)。"""
    result = runner.invoke(app, ["--json", "describe", "batch status", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    result_schema = next(
        row for row in rows if row.get("type") == "schema" and row.get("name") == "BatchStatusResult"
    )
    props = set(result_schema["schema"]["properties"])
    assert {"items_count", "items_limit", "items_offset", "items_has_more"} <= props

    item_schema = next(
        row for row in rows if row.get("type") == "schema" and row.get("name") == "ProviderBatchItemRecord"
    )
    assert {
        "id",
        "job_id",
        "custom_id",
        "image_id",
        "model_id",
        "task_type",
        "status",
        "error_type",
    } <= set(item_schema["schema"]["properties"])


def test_describe_images_search_exposes_query_schema() -> None:
    """describe images search が ImageSearchQuery ボディスキーマを返す (Issue #702)。

    ImagesSearchInput は schema_model を持たないため json_schema モードでは出力されない。
    ImageSearchQuery (--query / --query-file で渡す JSON ボディ) は json_schema モードで出力される。
    """
    result = runner.invoke(app, ["--json", "describe", "images search", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_rows = [row for row in rows if row.get("type") == "schema"]
    names = {row["name"] for row in schema_rows}
    assert "ImageSearchQuery" in names

    query_schema = next(row for row in schema_rows if row["name"] == "ImageSearchQuery")
    props = set(query_schema["schema"]["properties"])
    assert {"tags", "excluded_tags", "limit", "offset"} <= props
    assert "image_ids" in props

    # compact モードでは ImagesSearchInput が出力される
    compact_result = runner.invoke(app, ["--json", "describe", "images search"])
    assert compact_result.exit_code == 0
    compact_rows = _jsonl(compact_result.stdout)
    assert any(r.get("name") == "ImagesSearchInput" for r in compact_rows)


def test_describe_tags_add_exposes_required_fields() -> None:
    """describe tags add が image_ids / tags 必須フィールドを返す (Issue #702)。"""
    result = runner.invoke(app, ["--json", "describe", "tags add"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "tags add"

    input_row = next(row for row in rows if row.get("type") == "model" and row["name"] == "TagsAddInput")
    fields = {f["name"]: f for f in input_row["fields"]}
    assert fields["project"]["required"] is True
    assert fields["tags"]["required"] is True
    assert fields["apply"]["default"] is False
    # image_ids / image_ids_file は「どちらか一方」で単独必須ではない (Issue #1216)
    assert fields["image_ids"]["required"] is False
    assert "image_ids_file" in fields


def test_describe_tags_remove_exposes_required_fields() -> None:
    """describe tags remove が image_ids / tags 必須フィールドを返す (Issue #702)。"""
    result = runner.invoke(app, ["--json", "describe", "tags remove"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "tags remove"

    input_row = next(row for row in rows if row.get("type") == "model" and row["name"] == "TagsRemoveInput")
    fields = {f["name"]: f for f in input_row["fields"]}
    assert fields["tags"]["required"] is True
    # image_ids / image_ids_file は「どちらか一方」で単独必須ではない (Issue #1216)
    assert fields["image_ids"]["required"] is False
    assert "image_ids_file" in fields


def test_describe_tags_replace_exposes_from_to_fields() -> None:
    """describe tags replace が from_tag / to_tag 必須フィールドを返す (Issue #702)。"""
    result = runner.invoke(app, ["--json", "describe", "tags replace"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "tags replace"

    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "TagsReplaceInput"
    )
    fields = {f["name"]: f for f in input_row["fields"]}
    assert fields["from_tag"]["required"] is True
    assert fields["to_tag"]["required"] is True
    assert fields["apply"]["default"] is False


def test_describe_tags_add_json_schema_includes_edit_item_and_result() -> None:
    """tags add --schema json_schema が TagsAddInput / TagsEditItem / TagsAddResult スキーマを返す (Issue #702)。"""
    result = runner.invoke(app, ["--json", "describe", "tags add", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_names = {row["name"] for row in rows if row.get("type") == "schema"}
    assert "TagsAddInput" in schema_names
    assert "TagsEditItem" in schema_names
    assert "TagsAddResult" in schema_names

    input_schema = next(row for row in rows if row.get("name") == "TagsAddInput")
    input_props = set(input_schema["schema"]["properties"])
    assert {"project", "image_ids", "tags", "apply"} <= input_props

    result_schema = next(row for row in rows if row.get("name") == "TagsAddResult")
    props = set(result_schema["schema"]["properties"])
    assert {"target_images", "tags", "added", "dry_run"} <= props


def test_describe_tags_remove_json_schema_includes_input_and_result() -> None:
    """tags remove --schema json_schema が TagsRemoveInput / TagsEditItem / TagsRemoveResult スキーマを返す (Issue #702b)。"""
    result = runner.invoke(app, ["--json", "describe", "tags remove", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_names = {row["name"] for row in rows if row.get("type") == "schema"}
    assert "TagsRemoveInput" in schema_names
    assert "TagsEditItem" in schema_names
    assert "TagsRemoveResult" in schema_names

    input_schema = next(row for row in rows if row.get("name") == "TagsRemoveInput")
    input_props = set(input_schema["schema"]["properties"])
    assert {"project", "image_ids", "tags", "apply"} <= input_props


def test_describe_tags_replace_json_schema_includes_input_and_result() -> None:
    """tags replace --schema json_schema が TagsReplaceInput / TagsEditItem / TagsReplaceResult スキーマを返す (Issue #702b)。"""
    result = runner.invoke(app, ["--json", "describe", "tags replace", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_names = {row["name"] for row in rows if row.get("type") == "schema"}
    assert "TagsReplaceInput" in schema_names
    assert "TagsEditItem" in schema_names
    assert "TagsReplaceResult" in schema_names

    input_schema = next(row for row in rows if row.get("name") == "TagsReplaceInput")
    input_props = set(input_schema["schema"]["properties"])
    assert {"project", "image_ids", "from_tag", "to_tag", "apply"} <= input_props


def test_errors_commands_in_list_commands() -> None:
    """errors list / errors resolve が list-commands に現れる (Issue #714)。"""
    result = runner.invoke(app, ["--json", "list-commands"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    paths = {r.get("path") for r in rows if r.get("kind") == "item"}
    assert "errors list" in paths
    assert "errors resolve" in paths


def test_describe_errors_list_exposes_required_fields() -> None:
    """describe errors list が project 必須フィールドを返す (Issue #714)。"""
    result = runner.invoke(app, ["--json", "describe", "errors list"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "errors list"


def test_describe_errors_resolve_exposes_required_fields() -> None:
    """describe errors resolve が project 必須フィールドを返す (Issue #714)。"""
    result = runner.invoke(app, ["--json", "describe", "errors resolve"])
    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "errors resolve"


def test_list_commands_includes_images_show() -> None:
    """images show が list-commands に現れ read-only である。"""
    result = runner.invoke(app, ["--json", "list-commands"])

    assert result.exit_code == 0
    items = [row for row in _jsonl(result.stdout) if row["kind"] == "item"]
    by_path = {row["path"]: row for row in items}

    assert "images show" in by_path
    assert by_path["images show"]["read_only"] is True
    assert by_path["images show"]["side_effects"] == ["db_read"]


def test_describe_images_show_exposes_required_fields() -> None:
    """describe images show が project / image_ids 必須フィールドを返す。"""
    result = runner.invoke(app, ["--json", "describe", "images show"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "images show"

    input_row = next(row for row in rows if row.get("type") == "model" and row["name"] == "ImagesShowInput")
    fields = {f["name"]: f for f in input_row["fields"]}
    assert fields["project"]["required"] is True
    assert fields["image_ids"]["required"] is True
    assert fields["include_rejected"]["default"] is False


def test_describe_images_show_json_schema_includes_item_and_result() -> None:
    """images show --schema json_schema が Input/Item/Result スキーマを返す。"""
    result = runner.invoke(app, ["--json", "describe", "images show", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_names = {row["name"] for row in rows if row.get("type") == "schema"}
    assert "ImagesShowInput" in schema_names
    assert "ImagesShowItem" in schema_names
    assert "ImagesShowResult" in schema_names

    item_schema = next(row for row in rows if row.get("name") == "ImagesShowItem")
    item_props = set(item_schema["schema"]["properties"])
    assert {"image_id", "tags", "captions", "scores", "score_labels", "ratings", "quality_summary"} <= (
        item_props
    )


def test_list_commands_includes_translations_delete_suppress_unsuppress() -> None:
    """tags translations delete/suppress/unsuppress が list-commands に載る (Issue #1237)。"""
    result = runner.invoke(app, ["--json", "list-commands"])

    assert result.exit_code == 0
    items = [row for row in _jsonl(result.stdout) if row["kind"] == "item"]
    by_path = {row["path"]: row for row in items}

    for path in ("tags translations delete", "tags translations suppress", "tags translations unsuppress"):
        assert path in by_path
        assert by_path[path]["read_only"] is False
        assert "db_write" in by_path[path]["side_effects"]


def test_describe_translations_delete_documents_not_found_status() -> None:
    """describe tags translations delete が base DB 由来行の not_found 挙動を明示する。"""
    result = runner.invoke(app, ["--json", "describe", "tags translations delete"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "TagsTranslationsDeleteInput"
    )
    field_names = {f["name"] for f in input_row["fields"]}
    assert {"tag", "lang", "text", "project", "apply"} <= field_names

    item_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "TagsTranslationsDeleteItem"
    )
    status_field = next(f for f in item_row["fields"] if f["name"] == "status")
    assert "not_found" in status_field["type"]
    assert "suppress" in status_field["description"]


def test_describe_translations_suppress_and_unsuppress_expose_apply_field() -> None:
    """describe tags translations suppress/unsuppress が dry-run既定の --apply フィールドを返す。"""
    for command, input_name in (
        ("tags translations suppress", "TagsTranslationsSuppressInput"),
        ("tags translations unsuppress", "TagsTranslationsUnsuppressInput"),
    ):
        result = runner.invoke(app, ["--json", "describe", command])
        assert result.exit_code == 0
        rows = _jsonl(result.stdout)
        input_row = next(row for row in rows if row.get("type") == "model" and row["name"] == input_name)
        apply_field = next(f for f in input_row["fields"] if f["name"] == "apply")
        assert apply_field["default"] is False


@pytest.mark.parametrize(
    "command,model",
    [
        ("images register", "ImagesRegisterResult"),
        ("annotate import-batch", "AnnotateImportBatchResult"),
        ("batch import", "BatchImportResult"),
        ("errors resolve", "ErrorsResolveResult"),
    ],
)
def test_partial_failure_status_exposed_in_both_schema_modes(command, model):
    compact = runner.invoke(app, ["--json", "describe", command])
    assert compact.exit_code == 0
    result_model = next(row for row in _jsonl(compact.stdout) if row.get("name") == model)
    fields = {field["name"]: field for field in result_model["fields"]}
    assert "partial_success" in fields["status"]["type"]
    assert "exit 1" in fields["status"]["description"]
    schema_result = runner.invoke(app, ["--json", "describe", command, "--schema", "json_schema"])
    assert schema_result.exit_code == 0
    schema = next(row["schema"] for row in _jsonl(schema_result.stdout) if row.get("name") == model)
    assert schema["properties"]["status"]["enum"] == ["success", "partial_success", "failed"]
    assert schema["properties"]["ok"]["type"] == "boolean"


def test_registered_leaves_have_explicit_catalog_policy() -> None:
    from lorairo.cli.introspection import INTROSPECTION_EXCLUSIONS, iter_tool_specs
    from lorairo.cli.introspection_schema import command_tree

    _, leaves = command_tree()
    specs = {spec.path for spec in iter_tool_specs()}
    assert set(leaves) == specs | set(INTROSPECTION_EXCLUSIONS)
    assert not specs & set(INTROSPECTION_EXCLUSIONS)
    rows = _jsonl(runner.invoke(app, ["--json", "list-commands"]).stdout)
    assert rows[-1]["excluded_commands"] == INTROSPECTION_EXCLUSIONS
    assert rows[-1]["count"] == len(specs)


def _catalog_paths() -> list[str]:
    from lorairo.cli.introspection import iter_tool_specs

    return [spec.path for spec in iter_tool_specs()]


@pytest.mark.parametrize("path", _catalog_paths())
def test_every_leaf_help_and_argument_destinations_match_schema(path: str) -> None:
    from lorairo.cli.introspection import get_tool_spec
    from lorairo.cli.introspection_schema import command_tree

    _, leaves = command_tree()
    command = leaves[path]
    result = runner.invoke(app, [*path.split(), "--help"])
    assert result.exit_code == 0
    spec = get_tool_spec(path)
    fields = spec.inputs[0].schema_model.model_json_schema()["properties"] if spec.inputs else {}
    destinations = {destination for prop in fields.values() for destination in prop["x-cli-destinations"]}
    assert destinations == {param.name for param in command.params if not param.is_eager}
    for parameter in command.params:
        if parameter.is_eager:
            continue
        prop = next(prop for prop in fields.values() if parameter.name in prop["x-cli-destinations"])
        assert set(parameter.opts) <= set(prop["x-cli-options"])
        assert set(getattr(parameter, "secondary_opts", [])) <= set(prop["x-cli-options"])


@pytest.mark.parametrize("path", _catalog_paths())
def test_every_public_model_has_matching_compact_and_json_schema(path: str) -> None:
    from lorairo.cli.introspection_schema import compact_type

    compact = _jsonl(runner.invoke(app, ["--json", "describe", path]).stdout)
    complete = _jsonl(runner.invoke(app, ["--json", "describe", path, "--schema", "json_schema"]).stdout)
    models = {row["name"]: row for row in compact if row.get("type") == "model"}
    schemas = {row["name"]: row for row in complete if row.get("type") == "schema"}
    assert models.keys() == schemas.keys()
    for output in (compact, complete):
        tool = next(row for row in output if row.get("type") == "tool")
        assert tool["global_options"] == models["GlobalOptions"]["fields"]
    for name, model in models.items():
        schema = schemas[name]["schema"]
        fields = {item["name"]: item for item in model["fields"]}
        assert fields.keys() == schema["properties"].keys()
        assert model["role"] == schemas[name]["role"]
        for field_name, prop in schema["properties"].items():
            compact_field = fields[field_name]
            assert compact_field["required"] == (field_name in schema.get("required", []))
            assert compact_field["type"] == compact_type(prop)
            assert compact_field["schema"] == prop
            assert ("default" in compact_field) == ("default" in prop)
            if "default" in prop:
                assert compact_field["default"] == prop["default"]


@pytest.mark.parametrize("path,minimum", [("annotate run", 1), ("batch submit", None)])
def test_resolution_constraints_match_execution(path: str, minimum: int | None) -> None:
    from pydantic import ValidationError

    from lorairo.cli.introspection import get_tool_spec

    model = get_tool_spec(path).inputs[0].schema_model
    schema = model.model_json_schema()
    prop = schema["properties"]["resolution"]
    assert prop["default"] is None
    integer = next(choice for choice in prop["anyOf"] if choice.get("type") == "integer")
    assert integer.get("minimum") == minimum
    base = {"project": "temporary", "model": ["fake"] if path == "annotate run" else "fake"}
    if path == "batch submit":
        base["image_ids"] = "1"
    assert model.model_validate(base).resolution is None
    if minimum:
        with pytest.raises(ValidationError):
            model.model_validate({**base, "resolution": 0})
    else:
        assert model.model_validate({**base, "resolution": 0}).resolution == 0


def test_json_query_body_and_aliases_stay_distinct() -> None:
    from lorairo.cli.introspection import get_tool_spec

    search = get_tool_spec("images search")
    assert [model.name for model in search.inputs] == ["ImagesSearchInput", "ImageSearchQuery"]
    arguments, body = (model.schema_model.model_json_schema() for model in search.inputs)
    assert {"query", "query_file", "project"} == set(arguments["properties"])
    assert "tags" in body["properties"] and "query" not in body["properties"]
    alias = get_tool_spec("tags alias").inputs[0].schema_model.model_json_schema()
    assert alias["properties"]["from"]["x-cli-options"] == ["--from"]
    assert alias["properties"]["from"]["x-cli-destinations"] == ["from_tag"]
    show = get_tool_spec("images show").inputs[0].schema_model.model_json_schema()
    assert set(show["properties"]["image_ids"]["x-cli-destinations"]) == {
        "image_ids_positional",
        "image_ids_csv",
    }


def test_global_defaults_and_case_insensitive_log_level_match_parser() -> None:
    from pydantic import ValidationError

    from lorairo.cli.introspection import get_global_options

    model = get_global_options().schema_model
    defaults = model.model_validate({})
    assert defaults.log_level == "INFO"
    assert defaults.json_output is None
    assert defaults.workspace is None
    assert defaults.config is None
    assert model.model_validate({"log_level": "debug"}).log_level == "debug"
    with pytest.raises(ValidationError):
        model.model_validate({"log_level": "unrecognized"})


@pytest.mark.parametrize("path", _catalog_paths())
def test_argument_required_and_defaults_come_from_parser(path: str) -> None:
    from enum import Enum

    from lorairo.cli.introspection import get_tool_spec
    from lorairo.cli.introspection_schema import command_tree

    _, leaves = command_tree()
    spec = get_tool_spec(path)
    if not spec.inputs:
        assert not leaves[path].params
        return
    schema = spec.inputs[0].schema_model.model_json_schema()
    for parameter in leaves[path].params:
        if parameter.is_eager:
            continue
        name, prop = next(
            (name, prop)
            for name, prop in schema["properties"].items()
            if parameter.name in prop["x-cli-destinations"]
        )
        if path == "images show" and name == "image_ids":
            # One logical required selector has positional and option aliases.
            assert name in schema["required"]
            continue
        assert (name in schema.get("required", [])) == parameter.required
        if not parameter.required:
            default = parameter.default
            if isinstance(default, Enum):
                default = default.value
            if getattr(parameter, "multiple", False) and default is not None:
                default = list(default)
            assert prop.get("default") == default


def test_errors_pagination_schema_includes_body_validation_bounds() -> None:
    from pydantic import ValidationError

    from lorairo.cli.commands.errors import MAX_LIST_LIMIT
    from lorairo.cli.introspection import get_tool_spec

    model = get_tool_spec("errors list").inputs[0].schema_model
    props = model.model_json_schema()["properties"]
    assert props["limit"]["minimum"] == 0
    assert props["limit"]["maximum"] == MAX_LIST_LIMIT
    assert props["offset"]["minimum"] == 0
    assert "maximum" not in props["offset"]
    for value in (-1, MAX_LIST_LIMIT + 1):
        with pytest.raises(ValidationError):
            model.model_validate({"project": "temporary", "limit": value})
    assert model.model_validate({"project": "temporary", "limit": 0}).limit == 0


def test_generated_docs_match_schemas_and_preserve_migration_guidance() -> None:
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    generator = runpy.run_path(str(root / "scripts" / "generate_cli_docs.py"))
    rendered = generator["render"]()
    assert rendered == (root / "docs" / "cli.md").read_text(encoding="utf-8")
    assert "部分失敗と既存スクリプトの移行 (#1313)" in rendered
    assert "`--output` の移行 (#1310)" in rendered
    assert "read_only" in rendered
