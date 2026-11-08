"""CLI contract for the read-only `maintenance check` command (ADR 0099)."""

import json
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from lorairo.cli.introspection import MaintenanceCheckItem, MaintenanceCheckResult
from lorairo.cli.main import app
from lorairo.database import db_core
from lorairo.database.access_policy import is_read_only
from lorairo.database.schema import Image, ProviderBatchItem, ProviderBatchJob
from lorairo.public_api.exceptions import ReadOnlyPreconditionError
from lorairo.public_api.maintenance import check_database
from lorairo.services.db_maintenance_check_service import MaintenanceFinding, MaintenanceReport
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.utils.config import resolve_runtime_configuration, runtime_configuration_scope

pytestmark = pytest.mark.unit
runner = CliRunner()


def _report(count: int) -> MaintenanceReport:
    return MaintenanceReport(
        scopes=["batch", "files"],
        limit=1,
        checks=[
            MaintenanceFinding(
                "batch_unlinked_items", "batch", "job_id", count, [7][:count], count > 1, "d"
            ),
            MaintenanceFinding("image_file_missing", "files", "image_id", 0, [], False, "d"),
        ],
        checked_batch_jobs=3,
        checked_images=4,
        checked_processed_images=0,
    )


@pytest.mark.parametrize("count", [0, 2])
def test_check_emits_item_per_check_and_exits_zero_even_with_findings(monkeypatch, count):
    api = Mock(return_value=_report(count))
    monkeypatch.setattr("lorairo.public_api.maintenance.check_database", api)
    result = runner.invoke(
        app,
        [
            "--json",
            "maintenance",
            "check",
            "-p",
            "fixture",
            "--scope",
            "files",
            "--scope",
            "BATCH",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    api.assert_called_once_with("fixture", ["files", "batch"], limit=1)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    items, final = rows[:-1], rows[-1]
    for row in items:
        MaintenanceCheckItem.model_validate(row)
    MaintenanceCheckResult.model_validate(final)
    assert [row["check"] for row in items] == ["batch_unlinked_items", "image_file_missing"]
    assert items[0]["ids_truncated"] is (count > 1)
    assert final["status"] == "success" and final["ok"] is True and final["read_only"] is True
    assert final["issue_count"] == count and final["issues_found"] is (count > 0)
    assert final["provider_queried"] is False and final["repaired"] is False
    assert "checks" not in final


def test_check_human_output_states_report_only(monkeypatch):
    monkeypatch.setattr("lorairo.public_api.maintenance.check_database", Mock(return_value=_report(2)))
    result = runner.invoke(app, ["--no-json", "maintenance", "check", "-p", "fixture"])
    assert result.exit_code == 0, result.output
    assert "batch_unlinked_items: 2 job_ids [7] ..." in result.stdout
    assert "nothing was repaired" in result.stdout


@pytest.mark.parametrize("args", [["--limit", "0"], ["--limit", "501"], ["--scope", "sqlite"]])
def test_check_rejects_invalid_options_before_api(monkeypatch, args):
    api = Mock()
    monkeypatch.setattr("lorairo.public_api.maintenance.check_database", api)
    result = runner.invoke(app, ["--json", "maintenance", "check", "-p", "fixture", *args])
    assert result.exit_code == 2
    api.assert_not_called()


def _snapshot(workspace):
    return {
        str(path.relative_to(workspace)): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    }


@pytest.mark.parametrize("database_state", ["current", "missing"])
def test_check_uses_real_read_only_database_without_side_effects(tmp_path, monkeypatch, database_state):
    workspace = tmp_path / "maintenance-workspace"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    configuration = resolve_runtime_configuration(workspace, None)
    with runtime_configuration_scope(configuration):
        info = ProjectManagementService().create_project("project")
    db = info.path / "image_database.db"
    engine = db_core._prepare_project_database(db)
    (info.path / "image_dataset").mkdir(exist_ok=True)
    (info.path / "image_dataset" / "1.png").write_bytes(b"x")
    with Session(engine) as session:
        for image_id in (1, 2):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"synthetic-{image_id}",
                    phash=f"synthetic-{image_id}",
                    original_image_path=f"/nowhere/{image_id}.png",
                    stored_image_path=f"image_dataset/{image_id}.png",
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
            )
        session.add(ProviderBatchJob(id=5, provider="openai", provider_job_id="b5", status="completed"))
        session.flush()
        session.add(
            ProviderBatchItem(job_id=5, custom_id="c", image_id=None, task_type="tags", status="succeeded")
        )
        session.commit()
    engine.dispose()
    if database_state == "missing":
        db.unlink()

    before = _snapshot(workspace)
    monkeypatch.setattr(
        "socket.socket.connect", Mock(side_effect=AssertionError("Forbidden network access"))
    )
    previous_db = db_core.IMG_DB_PATH
    with runtime_configuration_scope(configuration):
        if database_state == "current":
            report = check_database("project")
            findings = {finding.check: finding for finding in report.checks}
            assert findings["image_file_missing"].ids == [2]
            assert findings["batch_unlinked_items"].ids == [5]
        else:
            with pytest.raises(ReadOnlyPreconditionError):
                check_database("project")
    result = runner.invoke(
        app,
        [
            "--json",
            "--log-level",
            "ERROR",
            "--workspace",
            str(workspace),
            "maintenance",
            "check",
            "-p",
            "project",
        ],
    )
    payload = json.loads(result.stdout.splitlines()[-1])
    if database_state == "current":
        assert result.exit_code == 0, result.output
        assert payload["issue_count"] == 2 and payload["checked_images"] == 2
    else:
        assert result.exit_code == 1, result.output
        assert payload["code"] == "PRECONDITION_FAILED"
    assert db_core.IMG_DB_PATH == previous_db and not is_read_only()
    assert _snapshot(workspace) == before
