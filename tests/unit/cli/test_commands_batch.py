"""Provider Batch CLI command tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")


def _job(**overrides):
    values = {
        "id": 42,
        "provider": "openai",
        "provider_job_id": "batch_42",
        "status": "submitted",
        "provider_status": "validating",
        "endpoint": "/v1/chat/completions",
        "model_id": 7,
        "request_count": 2,
        "succeeded_count": 0,
        "failed_count": 0,
        "canceled_count": 0,
        "expired_count": 0,
        "submitted_at": datetime(2026, 1, 1, tzinfo=UTC),
        "completed_at": None,
        "canceled_at": None,
        "expires_at": None,
        "imported_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _model(**overrides):
    values = {
        "id": 7,
        "provider": "openai",
        "litellm_model_id": "openai/gpt-4.1-mini",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _container() -> MagicMock:
    container = MagicMock()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model()
    container.db_manager.model_repo.get_models_by_name.return_value = []
    container.db_manager.provider_batch_repo.get_provider_batch_job.return_value = _job()
    container.provider_batch_workflow_service.submit_images.return_value = 42
    return container


@pytest.mark.unit
@pytest.mark.cli
def test_batch_help_registered() -> None:
    result = runner.invoke(app, ["batch", "--help"])

    assert result.exit_code == 0
    assert "Provider Batch" in result.stdout
    assert "submit" in result.stdout
    assert "import" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_calls_workflow_service(mock_get_container: MagicMock) -> None:
    container = _container()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model(
        provider="anthropic",
        litellm_model_id="anthropic/claude-3-5-haiku-latest",
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "anthropic/claude-3-5-haiku-latest",
            "--image-id",
            "1",
            "--image-id",
            "2",
            "--description",
            "nightly",
        ],
    )

    assert result.exit_code == 0
    container.set_active_project.assert_called_once_with("demo")
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="anthropic",
        endpoint="/v1/messages",
        litellm_model_id="anthropic/claude-3-5-haiku-latest",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=7,
        description="nightly",
        task_type="annotation",
    )
    assert "Provider Batch job submitted" in result.stdout
    assert "batch_42" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_accepts_openai_annotation(mock_get_container: MagicMock) -> None:
    """OpenAI annotation Batch (#518) は `/v1/chat/completions` 経路で submit できる。"""
    container = _container()
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "openai/gpt-4.1-mini",
            "--image-id",
            "1",
        ],
    )

    assert result.exit_code == 0
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/chat/completions",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[1],
        model_id=7,
        description=None,
        task_type="annotation",
    )
    assert "Provider Batch job submitted" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rating_preflight_calls_workflow_service(mock_get_container: MagicMock) -> None:
    container = _container()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model(
        id=11,
        litellm_model_id="openai/omni-moderation-latest",
        model_types=(SimpleNamespace(name="ratings"),),
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "openai/omni-moderation-latest",
            "--task-type",
            "rating_preflight",
            "--image-id",
            "1",
        ],
    )

    assert result.exit_code == 0
    container.set_active_project.assert_called_once_with("demo")
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/moderations",
        litellm_model_id="openai/omni-moderation-latest",
        prompt_profile="default",
        image_ids=[1],
        model_id=11,
        description=None,
        task_type="rating_preflight",
    )
    assert "Provider Batch job submitted" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rating_preflight_normalizes_endpoint_override(
    mock_get_container: MagicMock,
) -> None:
    container = _container()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model(
        id=11,
        litellm_model_id="openai/omni-moderation-latest",
        model_types=(SimpleNamespace(name="ratings"),),
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "openai/omni-moderation-latest",
            "--task-type",
            "rating_preflight",
            "--endpoint",
            "v1/moderations/",
            "--image-id",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert (
        container.provider_batch_workflow_service.submit_images.call_args.kwargs["endpoint"]
        == "/v1/moderations"
    )


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rating_preflight_rejects_non_moderations_endpoint(
    mock_get_container: MagicMock,
) -> None:
    container = _container()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model(
        id=11,
        litellm_model_id="openai/omni-moderation-latest",
        model_types=(SimpleNamespace(name="ratings"),),
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "openai/omni-moderation-latest",
            "--task-type",
            "rating_preflight",
            "--endpoint",
            "/v1/chat/completions",
            "--image-id",
            "1",
        ],
    )

    assert result.exit_code == 1
    assert "endpoint /v1/moderations" in result.stdout
    container.provider_batch_workflow_service.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rejects_google_until_phase3(mock_get_container: MagicMock) -> None:
    container = _container()
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = _model(
        provider="google",
        litellm_model_id="google/gemini-2.5-pro",
    )
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "submit",
            "--project",
            "demo",
            "--model",
            "google/gemini-2.5-pro",
            "--image-id",
            "1",
        ],
    )

    assert result.exit_code == 1
    assert "Google Provider Batch submit is disabled" in result.stdout
    container.provider_batch_workflow_service.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_list_shows_persisted_jobs(mock_get_container: MagicMock) -> None:
    container = _container()
    container.db_manager.provider_batch_repo.list_provider_batch_jobs.return_value = [
        _job(id=1, provider="openai"),
        _job(id=2, provider="anthropic", provider_status="in_progress"),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "list", "--project", "demo", "--status", "submitted"])

    assert result.exit_code == 0
    container.db_manager.provider_batch_repo.list_provider_batch_jobs.assert_called_once_with(
        provider=None,
        status="submitted",
        limit=100,
        offset=0,
    )
    assert "Provider Batch Jobs" in result.stdout
    assert "anthropic" in result.stdout
    assert "2 job(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_refreshes_by_default(mock_get_container: MagicMock) -> None:
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(status="running")
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    container.provider_batch_workflow_service.refresh.assert_called_once_with(42)
    assert "running" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_cancel_calls_workflow_service(mock_get_container: MagicMock) -> None:
    container = _container()
    container.provider_batch_workflow_service.cancel.return_value = _job(status="canceling")
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "cancel", "42", "--project", "demo"])

    assert result.exit_code == 0
    container.provider_batch_workflow_service.cancel.assert_called_once_with(42)
    assert "cancel requested" in result.stdout
    assert "canceling" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_fetch_shows_artifacts(mock_get_container: MagicMock, tmp_path: Path) -> None:
    container = _container()
    container.provider_batch_workflow_service.fetch_results.return_value = SimpleNamespace(
        provider_status="completed",
        items=(SimpleNamespace(custom_id="img-1"),),
        succeeded_count=1,
        failed_count=0,
        artifacts=(
            SimpleNamespace(
                artifact_type="output",
                local_path=tmp_path / "batch.jsonl",
                provider_file_id="file_1",
            ),
        ),
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "fetch", "42", "--project", "demo", "-o", str(tmp_path)])

    assert result.exit_code == 0
    container.provider_batch_workflow_service.fetch_results.assert_called_once_with(42, tmp_path)
    assert "Provider Batch results fetched" in result.stdout
    assert "batch.jsonl" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_import_shows_summary(mock_get_container: MagicMock, tmp_path: Path) -> None:
    container = _container()
    container.provider_batch_workflow_service.import_results.return_value = SimpleNamespace(
        imported_count=2,
        skipped_count=1,
        error_count=0,
        total_count=3,
        job_imported=True,
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "import", "42", "--project", "demo", "-o", str(tmp_path)])

    assert result.exit_code == 0
    container.provider_batch_workflow_service.import_results.assert_called_once_with(
        42,
        destination_dir=tmp_path,
    )
    assert "Provider Batch Import" in result.stdout
    assert "Summary" in result.stdout
    assert "Imported" in result.stdout
    assert "yes" in result.stdout
