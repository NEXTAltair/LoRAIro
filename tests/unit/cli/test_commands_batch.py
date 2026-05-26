"""Provider Batch CLI command tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.annotation_save_service import AnnotationSaveResult
from lorairo.services.provider_batch_service import (
    ProviderBatchArtifactRef,
    ProviderBatchError,
    ProviderBatchFetchResult,
)
from lorairo.services.provider_batch_workflow_service import (
    ProviderBatchImportResult,
    ProviderBatchResultApplyResult,
)

runner = CliRunner()


def _job(
    *,
    job_id: int = 7,
    provider: str = "openai",
    provider_job_id: str | None = "batch_123",
    status: str = "completed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=job_id,
        provider=provider,
        provider_job_id=provider_job_id,
        status=status,
        request_count=3,
        succeeded_count=2,
        failed_count=1,
        canceled_count=0,
        expired_count=0,
        submitted_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        imported_at=None,
    )


def _container() -> tuple[MagicMock, MagicMock, MagicMock]:
    workflow = MagicMock()
    repository = MagicMock()
    container = MagicMock()
    container.provider_batch_workflow_service = workflow
    container.image_repository = repository
    return container, workflow, repository


@pytest.mark.unit
@pytest.mark.cli
def test_batch_help_is_registered() -> None:
    result = runner.invoke(app, ["batch", "--help"])

    assert result.exit_code == 0
    assert "Provider Batch" in result.stdout
    assert "submit" in result.stdout
    assert "import" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_submit_calls_workflow_service(mock_get_container: MagicMock) -> None:
    container, workflow, _repository = _container()
    workflow.submit_images.return_value = 42
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--provider",
            "openai",
            "--model",
            "openai/gpt-4.1-mini",
            "--image-id",
            "10",
            "--image-id",
            "11",
            "--description",
            "nightly",
            "--model-id",
            "5",
        ],
    )

    assert result.exit_code == 0
    container.set_active_project.assert_called_once_with("demo")
    workflow.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="responses",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[10, 11],
        model_id=5,
        description="nightly",
    )
    assert "submitted: 42" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_submit_prints_service_error(mock_get_container: MagicMock) -> None:
    container, workflow, _repository = _container()
    workflow.submit_images.side_effect = ProviderBatchError("no images")
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "-p",
            "demo",
            "--provider",
            "openai",
            "--model",
            "openai/gpt-4.1-mini",
        ],
    )

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "no images" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_list_shows_jobs_with_filters(mock_get_container: MagicMock) -> None:
    container, _workflow, repository = _container()
    repository.list_provider_batch_jobs.return_value = [_job()]
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        ["batch", "list", "-p", "demo", "--provider", "openai", "--status", "completed"],
    )

    assert result.exit_code == 0
    repository.list_provider_batch_jobs.assert_called_once_with(
        provider="openai",
        status="completed",
        limit=100,
    )
    assert "Provider Batch Jobs" in result.stdout
    assert "batch_123" in result.stdout
    assert "2/3 ok" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_status_refreshes_by_default(mock_get_container: MagicMock) -> None:
    container, workflow, repository = _container()
    workflow.refresh.return_value = _job(status="running")
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "-p", "demo", "7"])

    assert result.exit_code == 0
    workflow.refresh.assert_called_once_with(7)
    repository.get_provider_batch_job.assert_not_called()
    assert "running" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_status_no_refresh_uses_database_state(mock_get_container: MagicMock) -> None:
    container, workflow, repository = _container()
    repository.get_provider_batch_job.return_value = _job(status="completed")
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "-p", "demo", "7", "--no-refresh"])

    assert result.exit_code == 0
    workflow.refresh.assert_not_called()
    repository.get_provider_batch_job.assert_called_once_with(7)
    assert "completed" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_status_no_refresh_reports_missing_job(mock_get_container: MagicMock) -> None:
    container, _workflow, repository = _container()
    repository.get_provider_batch_job.return_value = None
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "-p", "demo", "99", "--no-refresh"])

    assert result.exit_code == 1
    assert "job_id=99" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_cancel_calls_workflow_service(mock_get_container: MagicMock) -> None:
    container, workflow, _repository = _container()
    workflow.cancel.return_value = _job(status="canceled")
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "cancel", "-p", "demo", "7"])

    assert result.exit_code == 0
    workflow.cancel.assert_called_once_with(7)
    assert "canceled: 7 (canceled)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_fetch_calls_workflow_service(mock_get_container: MagicMock, tmp_path: Path) -> None:
    container, workflow, _repository = _container()
    artifact = ProviderBatchArtifactRef(
        artifact_type="output",
        local_path=tmp_path / "batch_123.jsonl",
        provider_file_id="file_123",
        sha256="abc",
    )
    workflow.fetch_results.return_value = ProviderBatchFetchResult(
        provider_job_id="batch_123",
        provider_status="completed",
        status="completed",
        artifacts=(artifact,),
        items=(SimpleNamespace(custom_id="img-1"),),
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        ["batch", "fetch", "-p", "demo", "7", "--destination-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    workflow.fetch_results.assert_called_once_with(7, tmp_path)
    assert "items=1, artifacts=1" in result.stdout
    assert "file_123" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_import_calls_workflow_service(mock_get_container: MagicMock, tmp_path: Path) -> None:
    container, workflow, _repository = _container()
    workflow.import_results.return_value = ProviderBatchImportResult(
        save_result=AnnotationSaveResult(success_count=2, skip_count=1, error_count=0, total_count=3),
        apply_result=ProviderBatchResultApplyResult(updated_count=3, missing_count=0, total_count=3),
        imported_count=2,
        skipped_count=1,
        error_count=0,
        total_count=3,
        job_imported=False,
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        ["batch", "import", "-p", "demo", "7", "--destination-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    workflow.import_results.assert_called_once_with(7, destination_dir=tmp_path)
    assert "imported=2" in result.stdout
    assert "skipped=1" in result.stdout
    assert "errors=0" in result.stdout
