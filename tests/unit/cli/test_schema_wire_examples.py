"""Exercise list terminal schemas and success/empty/error wire variants offline."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()
pytestmark = pytest.mark.unit


def rows(result):
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.stdout.splitlines()]


@pytest.mark.parametrize("count", [0, 1])
def test_models_list_item_and_empty_terminal(count, monkeypatch):
    container = MagicMock()
    container.config_service.get_setting.side_effect = lambda section, key, default="": default
    container.annotator_library.is_model_deprecated.return_value = False
    container.annotator_library.list_annotator_info.return_value = [
        SimpleNamespace(
            name="synthetic-local",
            model_type="tagger",
            is_local=True,
            is_api=False,
            capabilities=frozenset(),
            device="cpu",
            provider=None,
            litellm_model_id=None,
        )
    ] * count
    monkeypatch.setattr("lorairo.cli.commands.models.get_service_container", lambda: container)
    output = rows(runner.invoke(app, ["--json", "models", "list"]))
    assert output[-1]["count"] == count
    assert len(output) == count + 1


@pytest.mark.parametrize("count", [0, 1])
def test_batch_list_item_and_empty_terminal(count, monkeypatch):
    from lorairo.cli.commands.batch import _JOB_DETAIL_FIELDS

    job = dict.fromkeys(_JOB_DETAIL_FIELDS)
    job.update(
        id=42,
        provider="openai",
        status="submitted",
        request_count=1,
        succeeded_count=0,
        failed_count=0,
        canceled_count=0,
        expired_count=0,
    )
    container = MagicMock()
    container.db_manager.provider_batch_repo.list_provider_batch_jobs.return_value = [
        SimpleNamespace(**job)
    ] * count
    monkeypatch.setattr("lorairo.cli.commands.batch._activate_project", lambda project: container)
    output = rows(runner.invoke(app, ["--json", "batch", "list", "-p", "temporary"]))
    assert output[-1]["count"] == count
    assert len(output) == count + 1


@pytest.mark.parametrize("sync_errors", [[], ["synthetic sync failure"]])
def test_models_refresh_success_and_sync_failure(sync_errors, monkeypatch):
    container = MagicMock()
    container.annotator_library.refresh_available_models.return_value = ["synthetic"]
    container.model_sync_service.sync_available_models.return_value = SimpleNamespace(
        errors=sync_errors, summary="synthetic registry refresh"
    )
    monkeypatch.setattr("lorairo.cli.commands.models.get_service_container", lambda: container)
    result = runner.invoke(app, ["--json", "models", "refresh"])
    output = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.exit_code == (1 if sync_errors else 0)
    assert output[-1]["kind"] == ("error" if sync_errors else "result")


def test_batch_cancel_result_without_provider_job(monkeypatch):
    container = MagicMock()
    container.provider_batch_workflow_service.cancel.return_value = None
    monkeypatch.setattr("lorairo.cli.commands.batch._activate_project", lambda project: container)
    output = rows(runner.invoke(app, ["--json", "batch", "cancel", "42", "-p", "temporary"]))
    assert output[-1]["job_id"] == 42
    assert output[-1]["job"] is None


def test_batch_fetch_empty_results(monkeypatch):
    container = MagicMock()
    container.provider_batch_workflow_service.fetch_results.return_value = SimpleNamespace(
        provider_status="completed", items=[], artifacts=[]
    )
    monkeypatch.setattr("lorairo.cli.commands.batch._activate_project", lambda project: container)
    output = rows(runner.invoke(app, ["--json", "batch", "fetch", "42", "-p", "temporary"]))
    assert output[-1]["items"] == 0
    assert output[-1]["succeeded"] == 0
    assert output[-1]["failed"] == 0


@pytest.mark.parametrize("command", ["version", "status"])
def test_root_result_schemas_in_temporary_workspace(command, tmp_path):
    output = rows(runner.invoke(app, ["--workspace", str(tmp_path), "--json", command]))
    assert output[-1]["kind"] == "result"
    assert output[-1]["ok"] is True


@pytest.mark.parametrize("count", [0, 1])
def test_project_list_item_and_empty_terminal(count, tmp_path, monkeypatch):
    from datetime import UTC, datetime

    projects = [
        SimpleNamespace(name="synthetic", created=datetime(2026, 1, 1, tzinfo=UTC), path=tmp_path)
    ] * count
    monkeypatch.setattr("lorairo.cli.commands.project.api_list_projects", lambda: projects)
    output = rows(runner.invoke(app, ["--json", "project", "list"]))
    assert output[-1]["count"] == count
    assert len(output) == count + 1


@pytest.mark.parametrize("variant", ["empty", "success", "partial"])
def test_images_update_terminal_variants_match_schema(variant, monkeypatch):
    container = MagicMock()
    container.db_manager.image_repo.get_images_by_filter.return_value = (
        [] if variant == "empty" else [{"id": 1}],
        0 if variant == "empty" else 1,
    )
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", lambda _: None)
    monkeypatch.setattr("lorairo.cli.commands.images.get_service_container", lambda: container)
    monkeypatch.setattr(
        "lorairo.cli.commands.images._apply_tags_to_images",
        lambda *_: (1, ["synthetic failure"] if variant == "partial" else []),
    )
    result = runner.invoke(app, ["--json", "images", "update", "-p", "temporary", "--tags", "synthetic"])
    output = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.exit_code == (1 if variant == "partial" else 0)
    assert output[-1]["kind"] == "result"
    if variant == "empty":
        assert output[-1]["count"] == 0
    else:
        assert output[-1]["target_images"] == 1
