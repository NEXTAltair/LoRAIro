"""Isolated CLI execution with real durable state and mocked provider boundaries."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import typer
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli._output_mode import set_json_mode
from lorairo.cli.commands import annotate
from lorairo.services.annotation_run_ledger import AnnotationRunLedger
from lorairo.services.annotation_save_service import AnnotationSaveResult

pytestmark = [pytest.mark.unit, pytest.mark.cli]


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    database = project / "image_database.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE saved (image_id INTEGER PRIMARY KEY)")
    records = {}
    for image_id in range(1, 4):
        path = project / f"processed-{image_id}.png"
        Image.new("RGB", (8, 8), (image_id, 0, 0)).save(path)
        records[image_id] = {
            "id": image_id,
            "uuid": f"uuid-{image_id}",
            "phash": str(image_id),
            "stored_image_path": str(path),
        }
    repo = MagicMock()
    repo.get_images_by_filter.side_effect = lambda _: (list(records.values()), len(records))
    repo.get_images_by_ids.side_effect = lambda ids: [dict(records[i]) for i in ids if i in records]
    repo.get_candidate_image_ids.side_effect = lambda ids, _criteria=None: list(ids)
    settings = {"prompts": {"additional": "fixture prompt"}, "api": {"openai_key": "fixture-secret"}}
    library_settings = {"fixture-model": {"temperature": 0.2, "max_tokens": 64}}
    monkeypatch.setattr(
        sys.modules["image_annotator_lib.core.config"],
        "config_registry",
        SimpleNamespace(get_all_config=lambda: library_settings),
    )
    config_service = SimpleNamespace(get_all_settings=lambda: settings)
    provider = MagicMock()
    provider.annotate.side_effect = lambda images, litellm_model_ids, phash_list: {
        phash_list[0]: {model: {"tags": ["fixture"], "error": None} for model in litellm_model_ids}
    }
    saver = MagicMock()

    def save(results, *, allowed_image_ids, confirmed_outcomes):
        image_id = next(iter(allowed_image_ids))
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("INSERT OR IGNORE INTO saved VALUES (?)", (image_id,))
        confirmed_outcomes[image_id] = "success"
        return AnnotationSaveResult(1, 0, 0, 1, image_outcomes={image_id: "success"})

    saver.save_annotation_results.side_effect = save
    container = SimpleNamespace(
        db_manager=SimpleNamespace(image_repo=repo, model_repo=MagicMock()),
        config_service=config_service,
        annotator_library=provider,
        annotation_save_service=saver,
        set_active_project=lambda _: None,
    )
    monkeypatch.setattr(annotate, "api_get_project", lambda _: SimpleNamespace(path=project))
    monkeypatch.setattr(annotate, "get_service_container", lambda: container)
    monkeypatch.setattr(annotate, "_resolve_model_identifier", lambda _repo, model: model)
    monkeypatch.setattr(
        "lorairo.cli._annotation_resume._make_preflight", lambda _container, _models, **_kwargs: None
    )
    # Exercise the actual Typer command without root initialization or live config/logging.
    app = typer.Typer()
    app.add_typer(annotate.app, name="annotate")

    def invoke(*args):
        set_json_mode(True)
        try:
            return CliRunner().invoke(
                app, ["annotate", "run", "--project", "fixture", "--model", "fixture-model", *args]
            )
        finally:
            set_json_mode(False)

    def rows():
        with AnnotationRunLedger(project, "run1").locked(resume=True) as ledger:
            return ledger.images()

    return SimpleNamespace(
        project=project,
        database=database,
        records=records,
        settings=settings,
        library_settings=library_settings,
        container=container,
        provider=provider,
        saver=saver,
        invoke=invoke,
        rows=rows,
        save=save,
    )


def _summary(result):
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")][-1]


def test_interrupt_then_resume_runs_only_pending_and_repeated_resume_is_noop(isolated_run):
    run = isolated_run
    annotate_image = run.provider.annotate.side_effect

    def interrupt(images, **kwargs):
        if kwargs["phash_list"] == ["2"]:
            raise KeyboardInterrupt
        return annotate_image(images, **kwargs)

    run.provider.annotate.side_effect = interrupt
    first = run.invoke("--run-id", "run1")
    assert first.exit_code == 3, first.output
    assert [row["state"] for row in run.rows()] == ["completed", "in_flight", "pending"]
    assert _summary(first)["interrupted"] is True
    run.provider.annotate.side_effect = annotate_image
    run.provider.reset_mock()
    resumed = run.invoke("--resume", "run1")
    assert resumed.exit_code == 3, resumed.output
    assert run.provider.annotate.call_args.kwargs["phash_list"] == ["3"]
    assert run.provider.annotate.call_count == 1
    assert [row["state"] for row in run.rows()] == ["completed", "in_flight", "completed"]
    assert _summary(resumed)["pending"] == 0
    assert _summary(resumed)["in_flight"] == 1
    run.provider.reset_mock()
    assert run.invoke("--resume", "run1").exit_code == 3
    run.provider.annotate.assert_not_called()


def test_committed_database_result_with_crash_before_ledger_is_never_repeated(isolated_run):
    run = isolated_run

    def commit_then_interrupt(results, **kwargs):
        run.save(results, **kwargs)
        raise KeyboardInterrupt

    run.saver.save_annotation_results.side_effect = commit_then_interrupt
    assert run.invoke("--run-id", "run1").exit_code == 1
    with closing(sqlite3.connect(run.database)) as connection:
        assert connection.execute("SELECT image_id FROM saved").fetchall() == [(1,)]
    assert [row["state"] for row in run.rows()] == ["in_flight", "pending", "pending"]
    run.provider.reset_mock()
    run.saver.save_annotation_results.side_effect = run.save
    assert run.invoke("--resume", "run1").exit_code == 3
    assert [call.kwargs["phash_list"] for call in run.provider.annotate.call_args_list] == [["2"], ["3"]]


@pytest.mark.parametrize("change", ["model", "settings", "library_settings", "image", "uuid", "database"])
def test_changed_binding_refuses_before_any_provider_call(isolated_run, change):
    run = isolated_run
    run.provider.annotate.side_effect = KeyboardInterrupt
    assert run.invoke("--run-id", "run1").exit_code == 1
    extra = []
    if change == "model":
        extra = ["--model", "different-model"]
    elif change == "settings":
        run.settings["prompts"]["additional"] = "different prompt"
    elif change == "library_settings":
        run.library_settings["fixture-model"]["max_tokens"] = 65
    elif change == "image":
        Image.new("RGB", (8, 8), "red").save(run.records[2]["stored_image_path"])
    elif change == "uuid":
        run.records[2]["uuid"] = "replacement"
    else:
        run.database.rename(run.project / "old.sqlite3")
        run.database.write_bytes(b"replacement database")
    run.provider.reset_mock()
    result = run.invoke("--resume", "run1", *extra)
    assert result.exit_code == 2, result.output
    run.provider.annotate.assert_not_called()


def test_credential_rotation_does_not_invalidate_run_or_persist_secrets(isolated_run):
    run = isolated_run
    provider = run.provider.annotate.side_effect
    run.provider.annotate.side_effect = KeyboardInterrupt
    run.invoke("--run-id", "run1")
    run.settings["api"]["openai_key"] = "new-fixture-secret"
    run.provider.annotate.side_effect = provider
    assert run.invoke("--resume", "run1").exit_code == 3
    ledger_bytes = (run.project / ".lorairo/annotation-runs/run1.sqlite3").read_bytes()
    assert b"fixture-secret" not in ledger_bytes
    assert b"fixture prompt" not in ledger_bytes


def test_provider_failure_is_terminal_and_never_automatically_retried(isolated_run):
    run = isolated_run
    run.provider.annotate.side_effect = lambda images, **kwargs: {
        kwargs["phash_list"][0]: {"fixture-model": {"error": "fixture provider failure"}}
    }
    run.saver.save_annotation_results.side_effect = lambda *_args, **_kwargs: AnnotationSaveResult(
        0, 1, 0, 1
    )
    result = run.invoke("--run-id", "run1")
    assert result.exit_code == 1
    assert all(row["state"] == "failed" for row in run.rows())
    run.provider.reset_mock()
    assert run.invoke("--resume", "run1").exit_code == 1
    run.provider.annotate.assert_not_called()


def test_in_flight_is_durable_before_moderation_and_interrupt_is_not_retried(isolated_run, monkeypatch):
    run = isolated_run

    def moderate(paths):
        # Read a separate connection while the executor holds the run lock.
        path = run.project / ".lorairo/annotation-runs/run1.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            assert (
                connection.execute("SELECT state FROM images WHERE image_id=1").fetchone()[0] == "in_flight"
            )
        raise KeyboardInterrupt

    preflight = SimpleNamespace(apply=moderate)
    monkeypatch.setattr(
        "lorairo.cli._annotation_resume._make_preflight", lambda _container, _models, **_kwargs: preflight
    )
    assert run.invoke("--run-id", "run1").exit_code == 1
    run.provider.annotate.assert_not_called()
    assert run.rows()[0]["state"] == "in_flight"


def test_existing_run_id_cannot_be_overwritten_and_selection_flags_are_rejected(isolated_run):
    run = isolated_run
    assert run.invoke("--run-id", "run1").exit_code == 0
    run.provider.reset_mock()
    assert run.invoke("--run-id", "run1").exit_code != 0
    assert run.invoke("--resume", "run1", "--unrated").exit_code == 2
    assert run.invoke("--resume", "run1", "--run-id", "other").exit_code == 2
    assert run.invoke("--run-id", "../escape").exit_code == 2
    assert run.invoke("--run-id", "CON").exit_code == 2
    assert run.invoke("--resume", "missing").exit_code == 2
    run.provider.annotate.assert_not_called()


def test_resume_uses_fixed_selection_without_reapplying_mutable_filters(isolated_run):
    run = isolated_run
    provider = run.provider.annotate.side_effect
    run.provider.annotate.side_effect = KeyboardInterrupt
    run.invoke("--run-id", "run1", "--unrated")
    run.container.db_manager.image_repo.get_images_by_filter.side_effect = AssertionError("do not reselect")
    run.provider.annotate.side_effect = provider
    assert run.invoke("--resume", "run1").exit_code == 3


def test_run_lock_refuses_concurrent_execution_and_releases_on_exit(isolated_run):
    run = isolated_run
    assert run.invoke("--run-id", "run1").exit_code == 0
    run.provider.reset_mock()
    with AnnotationRunLedger(run.project, "run1").locked(resume=True):
        assert run.invoke("--resume", "run1").exit_code != 0
    assert run.invoke("--resume", "run1").exit_code == 0
    run.provider.annotate.assert_not_called()


def test_hard_process_exit_keeps_in_flight_and_releases_lock(tmp_path):
    script = """
import os, sys
from pathlib import Path
from lorairo.services.annotation_run_ledger import AnnotationRunLedger
with AnnotationRunLedger(Path(sys.argv[1]), 'crashed').locked(resume=False) as ledger:
    ledger.initialize({}, [{'image_id': 1, 'identity': 'fixture', 'state': 'pending'}])
    ledger.transition(1, 'in_flight')
    os._exit(23)
"""
    result = subprocess.run([sys.executable, "-B", "-c", script, str(tmp_path)], timeout=15, check=False)
    assert result.returncode == 23
    with AnnotationRunLedger(tmp_path, "crashed").locked(resume=True) as ledger:
        assert ledger.images()[0]["state"] == "in_flight"
        with pytest.raises(ValueError, match="refusing to repeat"):
            ledger.transition(1, "in_flight")


def test_explicit_id_selection_is_fixed_and_completed_run_is_noop(isolated_run):
    run = isolated_run
    result = run.invoke("--run-id", "run1", "--image-id", "3", "--image-id", "1")
    assert result.exit_code == 0, result.output
    assert [row["image_id"] for row in run.rows()] == [1, 3]
    run.provider.reset_mock()
    assert run.invoke("--resume", "run1").exit_code == 0
    run.provider.annotate.assert_not_called()


def test_without_durable_flags_does_not_create_run_directory(isolated_run, monkeypatch):
    run = isolated_run
    from lorairo.cli.commands.annotate import _StreamAnnotateSummary

    monkeypatch.setattr(annotate, "_validate_required_api_keys", lambda *_: None)
    monkeypatch.setattr(annotate, "selection_includes_webapi_model", lambda *_: False)
    monkeypatch.setattr(annotate, "_warn_deprecated_models", lambda *_: None)
    monkeypatch.setattr(
        annotate,
        "_stream_annotate",
        lambda **_: _StreamAnnotateSummary(total_loaded=3, total_results=3, saved=3, any_success=True),
    )
    assert run.invoke().exit_code == 0
    assert not (run.project / ".lorairo").exists()


@pytest.mark.parametrize("failed,saved,expected", [(0, 3, 0), (1, 2, 3), (3, 0, 1)])
@pytest.mark.parametrize("json_mode", [False, True])
def test_legacy_stream_exit_codes_cover_partial_and_full_failures(
    isolated_run, monkeypatch, failed, saved, expected, json_mode
):
    run = isolated_run
    from lorairo.cli.commands.annotate import _StreamAnnotateSummary

    monkeypatch.setattr(annotate, "_validate_required_api_keys", lambda *_: None)
    monkeypatch.setattr(annotate, "selection_includes_webapi_model", lambda *_: False)
    monkeypatch.setattr(annotate, "_warn_deprecated_models", lambda *_: None)
    monkeypatch.setattr(
        annotate,
        "_stream_annotate",
        lambda **_: _StreamAnnotateSummary(
            total_loaded=3, total_results=3, saved=saved, save_errors=failed, any_success=True
        ),
    )
    if not json_mode:
        monkeypatch.setattr(annotate, "is_json_mode", lambda: False)
    result = run.invoke()
    assert result.exit_code == expected, result.output
    if json_mode:
        assert _summary(result)["status"] == {0: "success", 3: "partial_success", 1: "failed"}[expected]


def test_actual_root_command_publishes_resume_json_contract(isolated_run, monkeypatch):
    from lorairo.cli.main import app

    monkeypatch.setattr("lorairo.cli.main.initialize_logging", lambda *_: None)
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "annotate",
            "run",
            "--project",
            "fixture",
            "--model",
            "fixture-model",
            "--run-id",
            "run1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert _summary(result)["run_id"] == "run1"
    assert _summary(result)["pending"] == 0


def test_processed_resolution_is_saved_and_all_missing_is_failure(isolated_run):
    run = isolated_run
    run.container.db_manager.image_repo.get_processed_image_paths_by_resolution.return_value = {}
    result = run.invoke("--run-id", "run1", "--resolution", "1024")
    assert result.exit_code == 1
    assert _summary(result)["resolution_skipped"] == 3
    run.provider.annotate.assert_not_called()
    assert run.invoke("--resume", "run1").exit_code == 1


def test_original_image_guard_remains_before_all_provider_calls(isolated_run):
    run = isolated_run
    run.records[2]["stored_image_path"] = "image_dataset/original_images/test.png"
    result = run.invoke("--run-id", "run1")
    assert result.exit_code == 2
    run.provider.annotate.assert_not_called()


def test_partial_model_result_is_failed_and_not_automatically_retried(isolated_run):
    run = isolated_run
    provider = run.provider.annotate.side_effect

    def partial(images, **kwargs):
        results = provider(images, **kwargs)
        results[kwargs["phash_list"][0]]["second-model"]["error"] = "fixture failure"
        return results

    run.provider.annotate.side_effect = partial
    result = run.invoke("--run-id", "run1", "--model", "second-model")
    assert result.exit_code == 3
    assert all(row["state"] == "failed" and row["saved"] for row in run.rows())
    run.provider.reset_mock()
    assert run.invoke("--resume", "run1", "--model", "second-model").exit_code == 3
    run.provider.annotate.assert_not_called()


def test_identity_change_during_run_leaves_next_image_pending(isolated_run):
    run = isolated_run
    provider = run.provider.annotate.side_effect

    def change_next_image(images, **kwargs):
        Image.new("RGB", (8, 8), "blue").save(run.records[2]["stored_image_path"])
        return provider(images, **kwargs)

    run.provider.annotate.side_effect = change_next_image
    assert run.invoke("--run-id", "run1").exit_code == 3
    assert [row["state"] for row in run.rows()] == ["completed", "pending", "pending"]
    assert run.provider.annotate.call_count == 1


def test_legacy_exact_ids_partial_failure_exits_three_without_ledger(isolated_run, monkeypatch):
    run = isolated_run
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    provider = run.provider.annotate.side_effect

    def partial(images, **kwargs):
        results = provider(images, **kwargs)
        if kwargs["phash_list"] == ["2"]:
            results["2"]["fixture-model"]["error"] = "fixture failure"
        return results

    run.provider.annotate.side_effect = partial
    result = run.invoke("--image-id", "1", "--image-id", "2", "--batch-size", "1")
    assert result.exit_code == 3, result.output
    assert _summary(result)["status"] == "partial_success"
    assert not (run.project / ".lorairo").exists()
