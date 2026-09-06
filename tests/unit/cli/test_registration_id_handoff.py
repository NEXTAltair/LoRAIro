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


@pytest.mark.parametrize("count", [0, 1, 500, 501, 100000, 100001])
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
    save.save_annotation_results.side_effect = lambda results, allowed_image_ids, confirmed_outcomes=None: (
        AnnotationSaveResult(
            success_count=len(allowed_image_ids),
            skip_count=0,
            error_count=0,
            total_count=len(allowed_image_ids),
            image_outcomes=dict.fromkeys(allowed_image_ids, "success"),
        )
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


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("inference failed"), KeyboardInterrupt(), click.UsageError("inference refused")],
)
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
    submit(container, [*range(1, count + 1), 1])
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


@pytest.mark.parametrize("failure", ["missing_path", "corrupt_path", "bad_request"])
def test_batch_validates_last_chunk_before_first_provider_call(tmp_path, failure):
    container = container_for_ids(tmp_path, 501)
    repo = container.db_manager.image_repo
    original = repo.get_processed_image_paths_by_resolution.side_effect
    if failure in ("missing_path", "corrupt_path"):
        bad = tmp_path / "corrupt.png"
        bad.write_text("not an image")

        def selected(ids, resolution):
            result = original(ids, resolution)
            if 501 in result:
                if failure == "missing_path":
                    result.pop(501)
                else:
                    result[501] = str(bad)
            return result

        repo.get_processed_image_paths_by_resolution.side_effect = selected
    else:
        container.provider_batch_workflow_service.build_submit_request.side_effect = [
            None,
            ValueError("bad metadata"),
        ]
    with pytest.raises((click.UsageError, ValueError)):
        submit(container, list(range(1, 502)))
    container.provider_batch_workflow_service.submit_images.assert_not_called()


def test_batch_interrupt_preserves_job_assignment(tmp_path, capsys):
    container = container_for_ids(tmp_path, 1001)
    container.provider_batch_workflow_service.submit_images.side_effect = [42, KeyboardInterrupt()]
    with pytest.raises(typer.Exit):
        submit(container, list(range(1, 1002)))
    output = rows(capsys)
    assert output[-1]["interrupted"]
    assert output[-1]["job_ids"] == [42]
    assert [row["status"] for row in output[:-1]] == ["submitted", "failed", "unsubmitted"]


def test_annotation_filter_order_offset_missing_resolution_and_unrelated_ids(tmp_path, monkeypatch, capsys):
    container = container_for_ids(tmp_path, 1001)
    repo = container.db_manager.image_repo
    repo.get_candidate_image_ids.side_effect = lambda ids, criteria=None: (
        ids if criteria is None else [i for i in ids if i != 2]
    )
    original = repo.get_processed_image_paths_by_resolution.side_effect
    repo.get_processed_image_paths_by_resolution.side_effect = lambda ids, resolution: {
        i: path for i, path in original(ids, resolution).items() if i != 4
    }
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    run_id_annotation(
        container,
        image_ids=[5, 4, 3, 2, 1, 1],
        file_input=True,
        project="demo",
        criteria=ImageFilterCriteria(only_unrated=True),
        offset=1,
        limit=2,
        resolution=512,
        batch_size=2,
        models=["fake"],
    )
    output = rows(capsys)
    outcomes = {r["image_id"]: r["status"] for r in output if r.get("type") == "annotation_outcome"}
    assert outcomes == {1: "skipped", 2: "skipped", 3: "completed", 4: "skipped", 5: "skipped"}
    assert output[-1]["resolution_skipped"] == 1
    assert output[-1]["skipped"] == 4
    assert output[-1]["ok"]
    assert [call.args[0] for call in repo.get_images_by_ids.call_args_list] == [[3]]
    repo.get_images_by_filter.assert_not_called()


@pytest.mark.parametrize("command", ["annotate", "batch"])
@pytest.mark.parametrize("case", ["empty", "invalid", "missing", "conflict"])
def test_cli_explicit_bad_id_files_never_fall_back(tmp_path, monkeypatch, command, case):
    from typer.testing import CliRunner

    from lorairo.cli.main import app

    file = tmp_path / "ids.txt"
    if case != "missing":
        file.write_text("" if case == "empty" else "not-id" if case == "invalid" else "1", encoding="utf-8")
    get_project = MagicMock(side_effect=AssertionError("project touched before bad input rejected"))
    boundary = "api_get_project" if command == "annotate" else "_activate_project"
    monkeypatch.setattr(f"lorairo.cli.commands.{command}.{boundary}", get_project)
    args = [
        "--json",
        command,
        "run" if command == "annotate" else "submit",
        "--project",
        "demo",
        "--model",
        "fake",
        "--image-ids-file",
        str(file),
    ]
    if case == "conflict":
        args.extend(["--image-id" if command == "annotate" else "--image-ids", "1"])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["code"] == "INVALID_INPUT"
    get_project.assert_not_called()


def test_emitted_registration_annotation_batch_rows_match_published_schemas(tmp_path, monkeypatch, capsys):
    from lorairo.cli._emit import emit_item
    from lorairo.cli.introspection import (
        AnnotateRunOutcome,
        AnnotateRunResult,
        BatchJobResult,
        BatchSubmissionItem,
        ImagesRegisterItem,
    )

    manager = MagicMock()
    manager.register_image_with_side_effects.return_value = RegistrationSideEffectResult(
        RegistrationOutcome.REGISTERED, 1, {}
    )
    _register_into_db(manager, MagicMock(), [Path("incoming.png")], project_name="demo", on_item=emit_item)
    ImagesRegisterItem.model_validate(rows(capsys)[0])
    container = container_for_ids(tmp_path, 1)
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    run_id_annotation(
        container,
        image_ids=[1],
        file_input=True,
        project="demo",
        criteria=ImageFilterCriteria(),
        offset=0,
        limit=None,
        resolution=512,
        batch_size=10,
        models=["fake"],
    )
    annotation = rows(capsys)
    AnnotateRunOutcome.model_validate(next(r for r in annotation if r.get("type") == "annotation_outcome"))
    AnnotateRunResult.model_validate(annotation[-1])
    submit(container, [1])
    batch = rows(capsys)
    BatchSubmissionItem.model_validate(batch[0])
    BatchJobResult.model_validate(batch[-1])


@pytest.mark.parametrize("fallback", [False, True])
def test_mid_save_interrupt_emits_real_committed_ids_and_exact_counts(
    tmp_path, monkeypatch, capsys, fallback
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from lorairo.database.repository.annotation_record import AnnotationRepository
    from lorairo.database.schema import Base, Caption, Model
    from lorairo.database.schema import Image as ImageRow
    from lorairo.services.annotation_save_service import AnnotationSaveService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add(Model(id=1, name="fake", litellm_model_id="fake"))
        session.add_all(
            ImageRow(
                id=i,
                uuid=str(i),
                phash=str(i),
                original_image_path=f"{i}.png",
                stored_image_path=f"{i}.png",
                width=16,
                height=16,
                format="PNG",
                extension="png",
                filename=f"{i}.png",
            )
            for i in range(1, 4)
        )
        session.commit()
    annotation_repo = AnnotationRepository(session_factory=factory)
    container = container_for_ids(tmp_path, 3)
    image_repo = container.db_manager.image_repo
    image_repo.find_image_ids_by_phashes_multi.side_effect = lambda phashes: {p: [int(p)] for p in phashes}
    model_repo = MagicMock()
    model_repo.get_models_by_litellm_ids.return_value = {"fake": SimpleNamespace(id=1)}
    service = AnnotationSaveService(annotation_repo, image_repo, model_repo, MagicMock())
    container.annotation_save_service = service
    container.annotator_library.annotate.side_effect = lambda images, litellm_model_ids, phash_list: {
        p: {"fake": {"captions": ["persisted caption"], "tags": [], "error": None}} for p in phash_list
    }
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", lambda *_: None)
    if fallback:
        monkeypatch.setattr(
            annotation_repo, "save_annotations_batch", MagicMock(side_effect=RuntimeError("fallback"))
        )
        original = annotation_repo.save_annotations

        def persist_one(image_id, *args, **kwargs):
            if image_id == 2:
                raise KeyboardInterrupt()
            return original(image_id, *args, **kwargs)

        monkeypatch.setattr(annotation_repo, "save_annotations", persist_one)
    else:
        monkeypatch.setattr(service, "_annotation_save_chunk_size", lambda: 1)
        original = annotation_repo.save_annotations_batch

        def persist_chunk(items, **kwargs):
            if items[0].image_id == 2:
                raise KeyboardInterrupt()
            return original(items, **kwargs)

        monkeypatch.setattr(annotation_repo, "save_annotations_batch", persist_chunk)
    with pytest.raises(typer.Exit) as caught:
        run_id_annotation(
            container,
            image_ids=[1, 2, 3],
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
    outcomes = {row["image_id"]: row for row in output if row.get("type") == "annotation_outcome"}
    assert {i: row["status"] for i, row in outcomes.items()} == {
        1: "completed",
        2: "failed",
        3: "unexecuted",
    }
    assert outcomes[1]["saved"] is True
    assert outcomes[2]["saved"] is False
    assert {key: output[-1][key] for key in ("annotated", "completed", "errors", "unexecuted")} == {
        "annotated": 1,
        "completed": 1,
        "errors": 1,
        "unexecuted": 1,
    }
    assert output[-1]["interrupted"] and output[-1]["status"] == "partial_success"
    with factory() as session:
        assert list(session.scalars(select(Caption.image_id))) == [1]
    engine.dispose()


@pytest.mark.parametrize("count", [100, 101])
@pytest.mark.parametrize("collect_items", [False, True])
def test_registration_streaming_error_sample_is_bounded_without_losing_items(count, collect_items):
    manager = MagicMock()
    manager.register_image_with_side_effects.side_effect = ValueError("full failure detail")
    emitted = []
    result = _register_into_db(
        manager,
        MagicMock(),
        [Path(f"{i}.png") for i in range(count)],
        collect_items=collect_items,
        on_item=emitted.append,
    )
    assert len(emitted) == result.failed == count
    assert all(item.error == "full failure detail" for item in emitted)
    assert len(result.error_details) == (count if collect_items else min(count, 100))
    assert result.error_details_truncated is (not collect_items and count > 100)
    assert result.target_count == 0


def test_cli_registration_terminal_exposes_truncated_error_sample(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from lorairo.cli.introspection import ImagesRegisterResult
    from lorairo.cli.main import app

    manager = MagicMock()
    manager.register_image_with_side_effects.side_effect = ValueError("full failure detail")
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock())
    monkeypatch.setattr("lorairo.cli.commands.images.get_service_container", MagicMock())
    monkeypatch.setattr(
        "lorairo.cli.commands.images.api_register_images",
        lambda path, skip_duplicates, **kwargs: _register_into_db(
            manager,
            MagicMock(),
            [Path(f"{i}.png") for i in range(101)],
            skip_duplicates=skip_duplicates,
            **kwargs,
        ),
    )
    result = CliRunner().invoke(app, ["--json", "images", "register", str(tmp_path), "--project", "demo"])
    assert result.exit_code == 1
    output = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(output) == 102
    assert all(row["error"] == "full failure detail" for row in output[:-1])
    terminal = ImagesRegisterResult.model_validate(output[-1])
    assert ImagesRegisterResult.model_json_schema()["properties"]["error_details"]["maxItems"] == 100
    assert terminal.errors == 101 and terminal.error_details_truncated
    assert len(terminal.error_details) == 100
    assert not terminal.ok and terminal.status == "failed"


@pytest.mark.parametrize("selection", ["filter", "offset", "limit"])
def test_all_filtered_annotation_ids_emit_complete_skipped_result(tmp_path, capsys, selection):
    container = container_for_ids(tmp_path, 2)
    repo = container.db_manager.image_repo
    if selection == "filter":
        repo.get_candidate_image_ids.side_effect = lambda ids, criteria=None: (
            ids if criteria is None else []
        )
    run_id_annotation(
        container,
        image_ids=[2, 1],
        file_input=True,
        project="demo",
        criteria=ImageFilterCriteria(only_unrated=True),
        offset=2 if selection == "offset" else 0,
        limit=0 if selection == "limit" else None,
        resolution=512,
        batch_size=2,
        models=["fake"],
    )
    output = rows(capsys)
    outcomes = {r["image_id"]: r["status"] for r in output if r.get("type") == "annotation_outcome"}
    assert outcomes == {1: "skipped", 2: "skipped"}
    result = output[-1]
    assert result["kind"] == "result"
    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["total"] == result["skipped"] == 2
    assert result["completed"] == result["errors"] == result["unexecuted"] == 0
    assert result["resolution_skipped"] == 0
    repo.get_images_by_ids.assert_not_called()
    repo.get_processed_image_paths_by_resolution.assert_not_called()
    container.annotator_library.annotate.assert_not_called()
    container.annotation_save_service.save_annotation_results.assert_not_called()


@pytest.mark.parametrize(
    "classification,outcome,skip_duplicates,selected",
    [
        ("new", "registered", True, True),
        ("variant", "variant", True, True),
        ("duplicate", "duplicate", True, False),
        ("duplicate", "duplicate", False, True),
    ],
)
@pytest.mark.parametrize("failure", [RuntimeError("sidecar database locked"), KeyboardInterrupt()])
def test_sidecar_failure_preserves_authoritative_registration(
    classification, outcome, skip_duplicates, selected, failure
):
    from lorairo.database.db_manager import ImageDatabaseManager

    manager = ImageDatabaseManager.__new__(ImageDatabaseManager)
    manager.register_original_image = MagicMock(return_value=(42, {"phash_classification": classification}))
    manager._import_associated_files = MagicMock(side_effect=failure)
    manager.image_repo = MagicMock()
    emitted = []
    result = _register_into_db(
        manager,
        MagicMock(),
        [Path("committed.png")],
        skip_duplicates=skip_duplicates,
        project_name="demo",
        on_item=emitted.append,
    )
    assert len(emitted) == 1
    item = emitted[0]
    assert (item.outcome, item.image_id, item.selected) == (outcome, 42, selected)
    assert item.error == (str(failure) or type(failure).__name__)
    assert result.failed == 1
    assert result.successful + result.variant + result.skipped == 0
    assert result.target_count == int(selected)
    assert result.interrupted is isinstance(failure, KeyboardInterrupt)
    assert result.unprocessed == 0
    assert manager.image_repo.mock_calls == []  # Never infer the ID via a second DB lookup.
    manager.register_original_image.assert_called_once()
    # The default GUI/direct manager contract still propagates the original side-effect exception.
    with pytest.raises(type(failure)):
        manager.register_image_with_side_effects(Path("committed.png"), MagicMock())


@pytest.mark.parametrize("failure", [RuntimeError("preflight setup failed"), KeyboardInterrupt()])
def test_annotation_preflight_setup_failure_partitions_validated_ids(
    tmp_path, monkeypatch, capsys, failure
):
    container = container_for_ids(tmp_path, 3)
    monkeypatch.setattr("lorairo.cli._annotation_ids._make_preflight", MagicMock(side_effect=failure))
    with pytest.raises(typer.Exit) as caught:
        run_id_annotation(
            container,
            image_ids=[1, 2, 3],
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
    assert {r["image_id"]: r["status"] for r in output if r.get("type") == "annotation_outcome"} == {
        1: "unexecuted",
        2: "unexecuted",
        3: "unexecuted",
    }
    assert output[-1]["status"] == "failed"
    assert output[-1]["unexecuted"] == 3
    assert output[-1]["interrupted"] is isinstance(failure, KeyboardInterrupt)
    container.annotator_library.annotate.assert_not_called()


def test_annotation_preflight_input_error_keeps_validation_boundary(tmp_path, monkeypatch, capsys):
    container = container_for_ids(tmp_path, 1)
    monkeypatch.setattr(
        "lorairo.cli._annotation_ids._make_preflight",
        MagicMock(side_effect=click.UsageError("missing key")),
    )
    with pytest.raises(click.UsageError, match="missing key"):
        run_id_annotation(
            container,
            image_ids=[1],
            file_input=True,
            project="demo",
            criteria=ImageFilterCriteria(),
            offset=0,
            limit=None,
            resolution=512,
            batch_size=2,
            models=["fake"],
        )
    assert rows(capsys) == []
    container.annotator_library.annotate.assert_not_called()


@pytest.mark.parametrize("first_lookup", [None, RuntimeError("metadata unavailable")])
def test_batch_first_job_metadata_never_comes_from_later_job(tmp_path, capsys, first_lookup):
    container = container_for_ids(tmp_path, 501)
    lookup = container.db_manager.provider_batch_repo.get_provider_batch_job
    lookup.side_effect = [first_lookup, SimpleNamespace(id=41)]
    submit(container, list(range(1, 502)))
    output = rows(capsys)
    assert output[-1]["job_ids"] == [40, 41]
    assert output[-1]["job_id"] == 40
    assert output[-1]["job"] is None
    lookup.assert_called_once_with(40)
    assert output[-1]["submitted"] == 501
