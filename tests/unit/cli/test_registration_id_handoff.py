"""Authoritative registration IDs and bounded downstream processing (#1307)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import click
import pytest
import typer
from PIL import Image

from lorairo.cli._annotation_ids import run_id_annotation
from lorairo.cli._batch_submission import submit_validated_ids
from lorairo.cli._image_ids import parse_image_ids_file
from lorairo.cli._output_mode import set_json_mode
from lorairo.database.db_manager import RegistrationOutcome, RegistrationSideEffectResult
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.images import _register_into_db
from lorairo.services.annotation_save_service import AnnotationSaveResult

pytestmark = [pytest.mark.unit, pytest.mark.cli]


@pytest.fixture(autouse=True)
def output_mode():
    set_json_mode(True)
    yield
    set_json_mode(False)


def rows(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


@pytest.mark.parametrize("include_duplicates", [False, True])
def test_registration_outcomes_define_unique_ids_even_for_other_directory_duplicates(include_duplicates):
    paths = [Path(f"incoming/{i}.png") for i in range(5)]
    manager = MagicMock()
    manager.register_image_with_side_effects.side_effect = [
        RegistrationSideEffectResult(RegistrationOutcome.REGISTERED, 1, {}),
        RegistrationSideEffectResult(RegistrationOutcome.VARIANT, 2, {}),
        RegistrationSideEffectResult(RegistrationOutcome.DUPLICATE, 99, {}),
        RegistrationSideEffectResult(RegistrationOutcome.DUPLICATE, 1, {}),
        RegistrationSideEffectResult(RegistrationOutcome.FAILED, None, None),
    ]
    emitted = []
    result = _register_into_db(
        manager,
        MagicMock(),
        paths,
        project_name="demo",
        skip_duplicates=not include_duplicates,
        on_item=emitted.append,
        collect_items=False,
    )
    assert result.items == []
    assert [item.input_path for item in emitted] == list(map(str, paths))
    assert [item.image_id for item in emitted] == [1, 2, 99, 1, None]
    assert {item.project for item in emitted} == {"demo"}
    assert [item.image_id for item in emitted if item.selected] == (
        [1, 2, 99] if include_duplicates else [1, 2]
    )
    assert result.target_count == (3 if include_duplicates else 2)
    assert (result.successful, result.variant, result.skipped, result.failed) == (
        (3, 1, 0, 1) if include_duplicates else (1, 1, 2, 1)
    )
    assert result.total == 5
    manager.detect_duplicate_image.assert_not_called()


def test_registration_output_failure_is_not_counted_as_another_db_failure():
    manager = MagicMock()
    manager.register_image_with_side_effects.return_value = RegistrationSideEffectResult(
        RegistrationOutcome.REGISTERED, 1, {}
    )
    with pytest.raises(OSError, match="output full"):
        _register_into_db(
            manager,
            MagicMock(),
            [Path("a.png"), Path("b.png")],
            on_item=MagicMock(side_effect=OSError("output full")),
        )
    assert manager.register_image_with_side_effects.call_count == 1


def test_registration_interrupt_keeps_completed_results_and_unprocessed_count():
    manager = MagicMock()
    manager.register_image_with_side_effects.side_effect = [
        RegistrationSideEffectResult(RegistrationOutcome.REGISTERED, 1, {}),
        KeyboardInterrupt(),
    ]
    result = _register_into_db(manager, MagicMock(), [Path(f"{i}.png") for i in range(3)])
    assert result.interrupted
    assert result.unprocessed == 2
    assert result.target_count == 1
    assert result.items[0].image_id == 1


@pytest.mark.parametrize("count", [0, 1, 500, 501, 100001])
def test_id_file_boundaries(tmp_path, count):
    path = tmp_path / "ids.txt"
    path.write_text("\n".join(map(str, range(1, count + 1))), encoding="utf-8")
    if count in (0, 100001):
        with pytest.raises(click.UsageError):
            parse_image_ids_file(str(path))
    else:
        assert parse_image_ids_file(str(path)) == list(range(1, count + 1))


@pytest.mark.parametrize("content", [b"1,wat", b"1,-2", b"0", b"\xff", b"\n,\n"])
def test_bad_id_file_is_machine_readable_input_error(tmp_path, content):
    path = tmp_path / "ids.txt"
    path.write_bytes(content)
    with pytest.raises(click.UsageError):
        parse_image_ids_file(str(path))


def container_for_ids(tmp_path, count):
    path = tmp_path / "processed_images" / "small.png"
    path.parent.mkdir(exist_ok=True)
    Image.new("RGB", (16, 16), "blue").save(path)
    ids = list(range(1, count + 1))
    repo = MagicMock()
    repo.get_candidate_image_ids.side_effect = lambda requested, criteria=None: [
        i for i in requested if i in ids
    ]
    repo.get_images_by_ids.side_effect = lambda requested: [
        {"id": i, "phash": str(i), "stored_image_path": str(path)} for i in requested if i in ids
    ]
    repo.get_processed_image_paths_by_resolution.side_effect = lambda requested, resolution: {
        i: str(path) for i in requested if i in ids
    }
    repo.get_images_by_filter.side_effect = AssertionError("unrelated metadata must not be loaded")
    annotator = MagicMock()
    annotator.annotate.side_effect = lambda images, litellm_model_ids, phash_list: {
        p: {"fake": {"tags": ["tag"], "error": None}} for p in phash_list
    }
    save = MagicMock()
    save.save_annotation_results.side_effect = lambda results, allowed_image_ids: AnnotationSaveResult(
        success_count=len(allowed_image_ids),
        skip_count=0,
        error_count=0,
        total_count=len(allowed_image_ids),
        image_outcomes={i: "success" for i in allowed_image_ids},
    )
    workflow = MagicMock()
    workflow.submit_images.side_effect = range(40, 100)
    container = SimpleNamespace(
        db_manager=SimpleNamespace(image_repo=repo, provider_batch_repo=MagicMock()),
        provider_batch_workflow_service=workflow,
        annotation_save_service=save,
        annotator_library=annotator,
    )
    container.db_manager.provider_batch_repo.get_provider_batch_job.return_value = None
    return container


@pytest.mark.parametrize("count", [1, 500, 501])
def test_annotation_id_input_is_complete_and_bounded(tmp_path, monkeypatch, capsys, count):
    container = container_for_ids(tmp_path, count)
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    run_id_annotation(
        container,
        image_ids=list(range(count, 0, -1)),
        file_input=True,
        project="demo",
        criteria=ImageFilterCriteria(),
        offset=0,
        limit=None,
        resolution=512,
        batch_size=13,
        models=["fake"],
    )
    output = rows(capsys)
    outcomes = [row for row in output if row.get("type") == "annotation_outcome"]
    assert {row["image_id"] for row in outcomes} == set(range(1, count + 1))
    assert all(row["status"] == "completed" for row in outcomes)
    assert output[-1]["annotated"] == count
    assert output[-1]["ok"]
    assert (
        max(
            len(call.args[0])
            for call in container.db_manager.image_repo.get_candidate_image_ids.call_args_list
        )
        <= 500
    )
    assert (
        max(len(call.args[0]) for call in container.db_manager.image_repo.get_images_by_ids.call_args_list)
        <= 13
    )
    assert max(len(call.args[0]) for call in container.annotator_library.annotate.call_args_list) <= 13
    container.db_manager.image_repo.get_images_by_filter.assert_not_called()


@pytest.mark.parametrize("failure", [RuntimeError("inference failed"), KeyboardInterrupt()])
def test_annotation_interruption_partitions_all_input_ids(tmp_path, monkeypatch, capsys, failure):
    container = container_for_ids(tmp_path, 5)
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    container.annotator_library.annotate.side_effect = [
        {"1": {"fake": {"tags": ["x"]}}, "2": {"fake": {"tags": ["x"]}}},
        failure,
    ]
    with pytest.raises(typer.Exit) as caught:
        run_id_annotation(
            container,
            image_ids=[1, 2, 3, 4, 5],
            file_input=True,
            project="demo",
            criteria=ImageFilterCriteria(),
            offset=0,
            limit=None,
            resolution=512,
            batch_size=2,
            models=["fake"],
        )
    assert caught.value.exit_code == 1
    output = rows(capsys)
    outcomes = {r["image_id"]: r["status"] for r in output if r.get("type") == "annotation_outcome"}
    assert outcomes == {1: "completed", 2: "completed", 3: "failed", 4: "failed", 5: "unexecuted"}
    assert output[-1]["status"] == "partial_success"


def submit(container, ids):
    submit_validated_ids(
        container,
        image_ids=ids,
        project="demo",
        resolution=512,
        provider="openai",
        endpoint="/v1/moderations",
        model_id=1,
        litellm_model_id="openai/omni-moderation-latest",
        prompt_profile="default",
        task_type="rating_preflight",
        description=None,
    )


def test_batch_failure_emits_already_submitted_and_unsent_assignments(tmp_path, capsys):
    container = container_for_ids(tmp_path, 1001)
    container.provider_batch_workflow_service.submit_images.side_effect = [
        42,
        RuntimeError("transport failed"),
    ]
    with pytest.raises(typer.Exit):
        submit(container, list(range(1, 1002)))
    output = rows(capsys)
    assert output[0]["job_id"] == 42
    assert output[0]["image_ids"] == list(range(1, 501))
    assert output[1]["status"] == "failed"
    assert output[1]["image_ids"] == list(range(501, 1001))
    assert output[2]["status"] == "unsubmitted"
    assert output[2]["image_ids"] == [1001]
    assert output[-1]["job_ids"] == [42]
    assert (output[-1]["submitted"], output[-1]["failed"], output[-1]["unsubmitted"]) == (500, 500, 1)
    assert container.provider_batch_workflow_service.submit_images.call_count == 2
    assert container.provider_batch_workflow_service.build_submit_request.call_count == 3


@pytest.mark.parametrize("count", [1, 500, 501])
def test_batch_all_ids_sent_once_with_bounded_processed_lookup(tmp_path, capsys, count):
    container = container_for_ids(tmp_path, count)
    submit(container, list(range(1, count + 1)) + [1])
    output = rows(capsys)
    assigned = [i for row in output if row.get("status") == "submitted" for i in row["image_ids"]]
    assert assigned == list(range(1, count + 1))
    assert output[-1]["ok"]
    assert (
        max(
            len(call.args[0])
            for call in container.db_manager.image_repo.get_processed_image_paths_by_resolution.call_args_list
        )
        <= 500
    )
    container.db_manager.image_repo.get_processed_image.assert_not_called()


def test_batch_late_missing_id_prevents_all_submissions(tmp_path):
    container = container_for_ids(tmp_path, 501)
    with pytest.raises(Exception, match="502"):
        submit(container, list(range(1, 503)))
    container.provider_batch_workflow_service.submit_images.assert_not_called()
