"""Provider Batch CLI command tests."""

from __future__ import annotations

import json
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
    container.db_manager.image_repo.get_images_by_ids.return_value = [
        {"id": 1, "stored_image_path": "image_dataset/processed_images/1.jpg"},
        {"id": 2, "stored_image_path": "image_dataset/processed_images/2.jpg"},
    ]
    container.db_manager.provider_batch_repo.get_provider_batch_job.return_value = _job()
    container.provider_batch_workflow_service.submit_images.return_value = 42
    return container


def _batch_item(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": 1,
        "job_id": 42,
        "custom_id": "img-1-mod-7",
        "image_id": 1,
        "model_id": 7,
        "task_type": "rating_preflight",
        "status": "succeeded",
        "error_type": None,
        "error_message": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
            "--image-ids",
            "1,2",
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
        image_paths=None,
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
            "--image-ids",
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
        image_paths=None,
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
            "--image-ids",
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
        image_paths=None,
    )
    assert "Provider Batch job submitted" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_batch_submit_help_documents_rating_preflight_constraints() -> None:
    result = runner.invoke(app, ["batch", "submit", "--help"])

    assert result.exit_code == 0
    assert "rating_preflight" in result.stdout
    assert "--image-ids" in result.stdout
    assert "repeatable" not in result.stdout
    assert "requires direct openai" in result.stdout
    assert "/v1/moderations" in result.stdout
    assert "openai/omni-moderation-*" in result.stdout
    assert "ratings" in result.stdout
    assert "model_type" in result.stdout


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
            "--image-ids",
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
            "--image-ids",
            "1",
        ],
    )

    # click.UsageError → INVALID_INPUT → exit 2 (入力検証、ADR 0057 §6)。
    assert result.exit_code == 2
    assert "endpoint /v1/moderations" in result.output
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
            "--image-ids",
            "1",
        ],
    )

    # click.UsageError → INVALID_INPUT → exit 2 (入力検証、ADR 0057 §6)。
    assert result.exit_code == 2
    assert "Google Provider Batch submit is disabled" in result.output
    container.provider_batch_workflow_service.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rejects_invalid_image_ids_csv(mock_get_container: MagicMock) -> None:
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
            "--image-ids",
            "1,,x",
        ],
    )

    assert result.exit_code == 2
    assert "--image-ids must be a comma-separated list" in result.output
    assert "invalid token(s): x" in result.output
    assert "empty item(s)" in result.output
    container.provider_batch_workflow_service.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_submit_rejects_original_image_records(mock_get_container: MagicMock) -> None:
    container = _container()
    container.db_manager.image_repo.get_images_by_ids.return_value = [
        {
            "id": 1,
            "stored_image_path": "image_dataset/original_images/2026/06/sample.jpg",
        }
    ]
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
            "--image-ids",
            "1",
        ],
    )

    assert result.exit_code == 2
    assert "cannot operate directly on original images" in result.output
    assert "1:image_dataset/original_images/2026/06/sample.jpg" in result.output
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
def test_batch_fetch_derives_counts_from_items_when_provider_counts_missing(
    mock_get_container: MagicMock,
    tmp_path: Path,
) -> None:
    container = _container()
    container.provider_batch_workflow_service.fetch_results.return_value = SimpleNamespace(
        provider_status="completed",
        items=(
            SimpleNamespace(custom_id="img-1", status="succeeded"),
            SimpleNamespace(custom_id="img-2", status="failed"),
        ),
        succeeded_count=None,
        failed_count=None,
        artifacts=(),
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "fetch", "42", "--project", "demo", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "items=2" in result.stdout
    assert "succeeded=1" in result.stdout
    assert "failed=1" in result.stdout


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


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_with_items_shows_items_table(mock_get_container: MagicMock) -> None:
    """--items で items テーブルが人間向けモードに表示される。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(id=1, status="succeeded"),
        _batch_item(id=2, custom_id="img-2-mod-7", image_id=2, status="failed", error_type="server_error"),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo", "--items"])

    assert result.exit_code == 0
    container.db_manager.provider_batch_repo.list_provider_batch_items.assert_called_once_with(
        42, status=None, limit=500, offset=0
    )
    assert "Provider Batch Items" in result.stdout
    assert "img-1-mod-7" in result.stdout
    assert "succeeded" in result.stdout
    assert "server_error" in result.stdout
    assert "2 item(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_with_items_json_emits_item_rows_then_result(mock_get_container: MagicMock) -> None:
    """--items --json で ProviderBatchItemRecord item 行の後に BatchStatusResult が来る。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(id=1),
        _batch_item(id=2, custom_id="img-2-mod-7", image_id=2),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(app, ["--json", "batch", "status", "42", "--project", "demo", "--items"])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    item_rows = [row for row in rows if row["kind"] == "item"]
    result_row = next(row for row in rows if row["kind"] == "result")

    assert len(item_rows) == 2
    assert item_rows[0]["custom_id"] == "img-1-mod-7"
    assert item_rows[0]["status"] == "succeeded"
    assert item_rows[1]["custom_id"] == "img-2-mod-7"
    assert result_row["ok"] is True
    assert result_row["items_count"] == 2
    assert result_row["items_limit"] == 500
    assert result_row["items_offset"] == 0
    assert result_row["items_has_more"] is False
    # _ITEM_DETAIL_FIELDS の全フィールドが item 行に含まれることを確認する。
    for field in (
        "id",
        "job_id",
        "custom_id",
        "image_id",
        "model_id",
        "task_type",
        "status",
        "error_type",
        "error_message",
    ):
        assert field in item_rows[0], f"item row is missing field: {field}"


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_without_items_does_not_call_list_items(mock_get_container: MagicMock) -> None:
    """--no-items（デフォルト）では list_provider_batch_items が呼ばれない。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    container.db_manager.provider_batch_repo.list_provider_batch_items.assert_not_called()
    assert "Provider Batch Items" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_items_passes_filter_options_to_repo(mock_get_container: MagicMock) -> None:
    """--item-status / --limit / --offset が list_provider_batch_items に正しく渡る。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(status="failed", error_type="server_error"),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        [
            "batch",
            "status",
            "42",
            "--project",
            "demo",
            "--items",
            "--item-status",
            "failed",
            "--limit",
            "10",
            "--offset",
            "5",
        ],
    )

    assert result.exit_code == 0
    container.db_manager.provider_batch_repo.list_provider_batch_items.assert_called_once_with(
        42, status="failed", limit=10, offset=5
    )


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_has_more_when_items_fill_limit(mock_get_container: MagicMock) -> None:
    """items 数が limit に達したとき items_has_more=True になる（JSON mode）。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(id=i, custom_id=f"img-{i}-mod-7", image_id=i) for i in range(1, 4)
    ]
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        ["--json", "batch", "status", "42", "--project", "demo", "--items", "--limit", "3"],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    result_row = next(row for row in rows if row["kind"] == "result")
    assert result_row["items_has_more"] is True
    assert result_row["items_count"] == 3
    assert result_row["items_limit"] == 3


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_has_more_false_when_items_below_limit(mock_get_container: MagicMock) -> None:
    """items 数が limit 未満のとき items_has_more=False になる（JSON mode）。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(id=1),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(
        app,
        ["--json", "batch", "status", "42", "--project", "demo", "--items", "--limit", "10"],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    result_row = next(row for row in rows if row["kind"] == "result")
    assert result_row["items_has_more"] is False
    assert result_row["items_count"] == 1


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_submit_with_resolution_resolves_processed_paths(mock_get_container: MagicMock) -> None:
    """--resolution 512 指定時に processed image path が解決されて submit_images に渡される。"""
    container = _container()
    container.db_manager.image_repo.get_processed_image.side_effect = lambda image_id, resolution: {
        1: {"id": 10, "stored_image_path": "image_dataset/processed_images/512/1.jpg"},
        2: {"id": 11, "stored_image_path": "image_dataset/processed_images/512/2.jpg"},
    }.get(image_id)
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
            "--image-ids",
            "1,2",
            "--resolution",
            "512",
        ],
    )

    assert result.exit_code == 0, result.stdout
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/chat/completions",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=7,
        description=None,
        task_type="annotation",
        image_paths={
            1: "image_dataset/processed_images/512/1.jpg",
            2: "image_dataset/processed_images/512/2.jpg",
        },
    )
    # --resolution 指定時は original image guard をスキップ
    container.db_manager.image_repo.get_images_by_ids.assert_not_called()
    assert "512px" in result.stdout
    assert "Provider Batch job submitted" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_submit_with_resolution_missing_processed_image_errors(mock_get_container: MagicMock) -> None:
    """指定解像度の processed image が存在しない image_id はエラーを返す。"""
    container = _container()
    # image_id=1 は見つかるが image_id=2 は None
    container.db_manager.image_repo.get_processed_image.side_effect = lambda image_id, resolution: (
        {"id": 10, "stored_image_path": "image_dataset/processed_images/512/1.jpg"}
        if image_id == 1
        else None
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
            "openai/gpt-4.1-mini",
            "--image-ids",
            "1,2",
            "--resolution",
            "512",
        ],
    )

    assert result.exit_code != 0
    assert "2" in result.stdout or "2" in str(result.exception)
    container.provider_batch_workflow_service.submit_images.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_submit_without_resolution_uses_stored_path(mock_get_container: MagicMock) -> None:
    """--resolution なしの場合は従来通り image_paths=None で submit し、original guard を実行する。"""
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
            "--image-ids",
            "1,2",
        ],
    )

    assert result.exit_code == 0, result.stdout
    container.provider_batch_workflow_service.submit_images.assert_called_once_with(
        provider="openai",
        endpoint="/v1/chat/completions",
        litellm_model_id="openai/gpt-4.1-mini",
        prompt_profile="default",
        image_ids=[1, 2],
        model_id=7,
        description=None,
        task_type="annotation",
        image_paths=None,
    )
    # original image guard が呼ばれること
    container.db_manager.image_repo.get_images_by_ids.assert_called_once_with([1, 2])
    assert "get_processed_image" not in str(container.db_manager.image_repo.mock_calls)
    assert result_row["items_limit"] == 10


# --- _print_job_status_hint のテスト ---


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_hint_fetch_waiting_shows_hint_and_next_command(
    mock_get_container: MagicMock,
) -> None:
    """job=completed/provider=completed/items=running の場合、fetch 待ち hint と Next コマンドを表示する。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(
        status="completed",
        provider_status="completed",
        request_count=300,
        succeeded_count=300,
        imported_at=None,
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    assert "Provider job is completed" in result.stdout
    assert "results have not been fetched/imported yet" in result.stdout
    assert "lorairo-cli batch fetch 42 --project demo" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_hint_fetch_waiting_no_next_when_counts_mismatch(
    mock_get_container: MagicMock,
) -> None:
    """succeeded_count != request_count の場合、fetch hint は表示されるが Next コマンドは表示しない。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(
        status="completed",
        provider_status="completed",
        request_count=300,
        succeeded_count=200,  # 一部失敗または処理中
        imported_at=None,
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    assert "Provider job is completed" in result.stdout
    assert "results have not been fetched/imported yet" in result.stdout
    # 件数が一致しないため Next コマンドは表示しない
    assert "lorairo-cli batch fetch" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_hint_fetched_shows_import_hint(mock_get_container: MagicMock) -> None:
    """job=fetched/imported_at=None の場合、import hint と Next コマンドを表示する。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(
        status="fetched",
        provider_status="completed",
        imported_at=None,
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    assert "Results are fetched" in result.stdout
    assert "lorairo-cli batch import 42 --project demo" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_hint_imported_shows_fully_imported(mock_get_container: MagicMock) -> None:
    """job=imported の場合、"fully imported" を表示する。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(
        status="imported",
        provider_status="completed",
        imported_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    assert "fully imported" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_hint_no_hint_in_json_mode(mock_get_container: MagicMock) -> None:
    """--json モードでは hint を表示しない（JSON 出力に含まない）。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job(
        status="completed",
        provider_status="completed",
        request_count=300,
        succeeded_count=300,
        imported_at=None,
    )
    mock_get_container.return_value = container

    result = runner.invoke(app, ["--json", "batch", "status", "42", "--project", "demo"])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    # JSON 出力は result 行のみ (hint テキストは含まない)
    assert all(row["kind"] in {"item", "result"} for row in rows)
    assert "Provider job is completed" not in result.stdout
    assert "lorairo-cli batch fetch" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.batch.get_service_container")
def test_batch_status_items_table_header_shows_lorairo_status(mock_get_container: MagicMock) -> None:
    """--items の items テーブルに LoRAIro 側ステータスであることを示すヘッダーが表示される。"""
    container = _container()
    container.provider_batch_workflow_service.refresh.return_value = _job()
    container.db_manager.provider_batch_repo.list_provider_batch_items.return_value = [
        _batch_item(id=1, status="running"),
    ]
    mock_get_container.return_value = container

    result = runner.invoke(app, ["batch", "status", "42", "--project", "demo", "--items"])

    assert result.exit_code == 0
    # LoRAIro 側ステータスであることをヘッダーで示す
    assert "LoRAIro" in result.stdout
