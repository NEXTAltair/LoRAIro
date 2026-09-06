"""Operation summaries retain counts while exposing failures to shell callers (#1313)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.introspection import (
    AnnotateImportBatchResult,
    ErrorsResolveResult,
    ImagesRegisterResult,
)
from lorairo.cli.introspection import (
    BatchImportResult as BatchImportResultSchema,
)
from lorairo.cli.main import app
from lorairo.public_api.types import RegistrationResult
from lorairo.services.batch_import_service import BatchImportResult

runner = CliRunner()
pytestmark = [pytest.mark.unit, pytest.mark.cli]


def check_terminal(result, json_mode, expected_status):
    assert result.exit_code == (0 if expected_status == "success" else 1), result.output
    if json_mode:
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == 1
        assert rows[0]["kind"] == "result"
        assert rows[0]["ok"] is (expected_status == "success")
        assert rows[0]["status"] == expected_status
        row = rows[0]
        schema = (
            ImagesRegisterResult
            if "registered" in row
            else AnnotateImportBatchResult
            if "total_records" in row
            else BatchImportResultSchema
            if "job_id" in row
            else ErrorsResolveResult
        )
        schema.model_validate(row)
        assert set(row) <= set(schema.model_fields)
        return row
    return None


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "success,variant,skip,failed,status",
    [
        (2, 0, 0, 0, "success"),
        (0, 0, 0, 0, "success"),
        (0, 0, 2, 0, "success"),
        (1, 0, 0, 1, "partial_success"),
        (0, 1, 0, 1, "partial_success"),
        (0, 0, 0, 2, "failed"),
    ],
)
def test_registration_terminal(monkeypatch, tmp_path, json_mode, success, variant, skip, failed, status):
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock())
    monkeypatch.setattr("lorairo.cli.commands.images.get_service_container", MagicMock())
    outcome = RegistrationResult(
        total=success + variant + skip + failed,
        successful=success,
        variant=variant,
        skipped=skip,
        failed=failed,
        error_details=["broken.png: invalid image"] if failed else None,
    )
    monkeypatch.setattr("lorairo.cli.commands.images.api_register_images", MagicMock(return_value=outcome))
    result = runner.invoke(
        app, (["--json"] if json_mode else []) + ["images", "register", str(tmp_path), "-p", "demo"]
    )
    row = check_terminal(result, json_mode, status)
    if row:
        assert (row["registered"], row["skipped"], row["errors"]) == (success, skip, failed)
        if failed:
            assert "broken.png" in row["error_details"][0]


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "saved,parse_errors,unmatched,save_errors,dry_run,status",
    [
        (2, 0, 0, 0, False, "success"),
        (0, 0, 0, 0, False, "success"),
        (0, 0, 0, 0, True, "success"),
        (1, 0, 0, 1, False, "partial_success"),
        (1, 1, 0, 0, False, "partial_success"),
        (1, 0, 1, 0, False, "partial_success"),
        (0, 0, 0, 2, False, "failed"),
        (0, 2, 0, 0, False, "failed"),
        (0, 0, 2, 0, False, "failed"),
        (0, 1, 0, 0, True, "partial_success"),
    ],
)
def test_legacy_import_terminal(
    monkeypatch, tmp_path, json_mode, saved, parse_errors, unmatched, save_errors, dry_run, status
):
    matched = 2 if dry_run else saved + save_errors
    outcome = BatchImportResult(
        total_records=matched + parse_errors + unmatched,
        parsed_ok=matched + unmatched,
        parse_errors=parse_errors,
        matched=matched,
        unmatched=unmatched,
        saved=saved,
        save_errors=save_errors,
        model_name="fake",
        unmatched_ids=["missing"] if unmatched else [],
        error_details=["input.jsonl: bad row"] if parse_errors or save_errors else [],
    )
    monkeypatch.setattr("lorairo.cli.commands.annotate.get_service_container", MagicMock())
    monkeypatch.setattr(
        "lorairo.cli.commands.annotate.import_batch_annotations", MagicMock(return_value=outcome)
    )
    result = runner.invoke(
        app,
        (["--json"] if json_mode else [])
        + ["annotate", "import-batch", str(tmp_path), "-p", "demo"]
        + (["--dry-run"] if dry_run else []),
    )
    row = check_terminal(result, json_mode, status)
    if row:
        assert row["saved"] == saved
        assert row["unmatched_ids"] == outcome.unmatched_ids
        assert row["error_details"] == outcome.error_details


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "imported,skip,errors,total,job_imported,already,status",
    [
        (2, 0, 0, 2, True, 0, "success"),
        (0, 0, 0, 0, False, 0, "success"),
        (0, 2, 0, 2, True, 2, "success"),
        (1, 0, 1, 2, False, 0, "partial_success"),
        (0, 0, 2, 2, False, 0, "failed"),
        (1, 1, 0, 2, False, 0, "partial_success"),
        (0, 2, 0, 2, False, 0, "failed"),
    ],
)
def test_provider_import_terminal(
    monkeypatch, json_mode, imported, skip, errors, total, job_imported, already, status
):
    container = MagicMock()
    container.provider_batch_workflow_service.import_results.return_value = SimpleNamespace(
        imported_count=imported,
        skipped_count=skip,
        error_count=errors,
        total_count=total,
        job_imported=job_imported,
        already_imported_count=already,
        missing_custom_ids=("missing-id",) if skip and not already else (),
        failed_custom_ids=("unconfirmed-save-id",) if errors or (skip and not already) else (),
        save_result=SimpleNamespace(error_details=["image 5: write failed"] if errors else []),
    )
    monkeypatch.setattr("lorairo.cli.commands.batch._activate_project", lambda _: container)
    monkeypatch.setattr("lorairo.cli.commands.batch._get_rating_breakdown", lambda *_: {})
    result = runner.invoke(app, (["--json"] if json_mode else []) + ["batch", "import", "42", "-p", "demo"])
    row = check_terminal(result, json_mode, status)
    if row:
        assert (row["imported"], row["skipped"], row["errors"]) == (imported, skip, errors)
        assert row["job_id"] == 42
        assert row["failed_custom_ids"] == (
            ["unconfirmed-save-id"] if errors or (skip and not already) else []
        )
        if status != "success":
            assert "batch status 42" in row["hint"]


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "success,updated,ids,dry_run,status",
    [
        (True, 2, [1, 2], False, "success"),
        (True, 0, [], False, "success"),
        (True, 0, [1, 2], True, "success"),
        (True, 0, [1, 2], False, "success"),
        (False, 1, [1, 2], False, "partial_success"),
        (False, 0, [1, 2], False, "failed"),
    ],
)
def test_errors_resolve_terminal(monkeypatch, json_mode, success, updated, ids, dry_run, status):
    container = MagicMock()
    repo = container.db_manager.error_record_repo
    repo.get_error_ids_by_filter.return_value = ids
    repo.mark_errors_resolved_batch.return_value = success, updated
    monkeypatch.setattr("lorairo.cli.commands.errors.get_service_container", lambda: container)
    monkeypatch.setattr("lorairo.cli.commands.errors.api_get_project", MagicMock())
    result = runner.invoke(
        app,
        (["--json"] if json_mode else [])
        + ["errors", "resolve", "-p", "demo", "--operation", "search"]
        + (["--dry-run"] if dry_run else []),
    )
    row = check_terminal(result, json_mode, status)
    if row:
        assert row["resolved"] == (len(ids) if dry_run else updated)
    if dry_run or not ids:
        repo.mark_errors_resolved_batch.assert_not_called()
