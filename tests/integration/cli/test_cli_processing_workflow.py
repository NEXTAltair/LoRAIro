"""CLI-only image generation workflow; no raw database edits or GUI state simulation."""

import json
import random
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

MODEL = "offline-workflow-tagger"
RATING_MODEL = "openai/omni-moderation-latest"


class OfflineAnnotator:
    """Deterministic local inference boundary; persistence remains real."""

    def __init__(self):
        self.images_seen = []

    def list_annotator_info(self):
        return [
            SimpleNamespace(
                name=MODEL,
                model_type="tagger",
                capabilities=frozenset(),
                is_local=True,
                is_api=False,
                device=None,
                provider="local",
                litellm_model_id=MODEL,
                estimated_size_gb=0.0,
                discontinued_at=None,
            ),
            SimpleNamespace(
                name=RATING_MODEL,
                model_type="rating",
                capabilities=frozenset(),
                is_local=False,
                is_api=True,
                device=None,
                provider="openai",
                litellm_model_id=RATING_MODEL,
                estimated_size_gb=0.0,
                discontinued_at=None,
            ),
        ]

    def refresh_available_models(self):
        return [MODEL, RATING_MODEL]

    def is_model_deprecated(self, model_name):
        return False

    def annotate(self, images, litellm_model_ids, phash_list=None):
        self.images_seen.extend(image.size for image in images)
        return {
            phash: {
                model: SimpleNamespace(
                    tags=["offline_tag"],
                    captions=["offline caption"],
                    scores=None,
                    score_labels=None,
                    ratings=None,
                    error=None,
                )
                for model in litellm_model_ids
            }
            for phash in phash_list
        }


def invoke(*args):
    result = CliRunner().invoke(app, ["--json", *args])
    assert result.exit_code == 0, result.stdout + result.stderr + repr(result.exception)
    return [json.loads(line) for line in result.stdout.splitlines()]


@pytest.mark.integration
@pytest.mark.cli
@pytest.mark.e2e
def test_cli_register_process_annotate_batch_export(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    original_init = ProjectManagementService.__init__
    monkeypatch.setattr(
        ProjectManagementService,
        "__init__",
        lambda self, projects_base_dir=None: original_init(self, projects),
    )
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    monkeypatch.setattr(
        socket.socket, "connect", MagicMock(side_effect=AssertionError("network forbidden"))
    )
    ServiceContainer.reset_for_testing()
    fake = OfflineAnnotator()
    monkeypatch.setattr(ServiceContainer, "annotator_library", property(lambda self: fake))
    batch = MagicMock()
    batch.submit_images.return_value = 42
    batch.import_results.return_value = SimpleNamespace(
        imported_count=1,
        skipped_count=0,
        error_count=0,
        total_count=1,
        job_imported=True,
        missing_custom_ids=(),
    )
    monkeypatch.setattr(ServiceContainer, "provider_batch_workflow_service", property(lambda self: batch))
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    source = inputs / "synthetic.png"
    Image.new("RGB", (96, 64), color=(90, 130, 190)).save(source)
    source_bytes = source.read_bytes()
    project = "offline-workflow"
    invoke("project", "create", project)
    invoke("models", "refresh", "-p", project)
    unrelated = tmp_path / "unrelated.png"
    rng = random.Random(1307)
    Image.frombytes("RGB", (96, 64), rng.randbytes(96 * 64 * 3)).save(unrelated)
    existing = invoke("images", "register", str(unrelated), "-p", project)
    unrelated_ids = {row["image_id"] for row in existing if row.get("selected")}
    registration = invoke("images", "register", str(inputs), "-p", project)
    assert registration[-1]["registered"] == 1
    registration_items = [row for row in registration if row["kind"] == "item"]
    assert registration_items and all(row["project"] == project for row in registration_items)
    ids = [row["image_id"] for row in registration_items if row["selected"]]
    assert set(ids).isdisjoint(unrelated_ids)
    assert registration[-1]["target_count"] == len(ids)
    rereregister = invoke("images", "register", str(inputs), "-p", project)
    assert rereregister[-1]["target_count"] == 0
    assert all(not row.get("selected") for row in rereregister)
    included = invoke("images", "register", str(inputs), "-p", project, "--include-duplicates")
    assert [row["image_id"] for row in included if row.get("selected")] == ids
    assert len(ids) == 1
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(map(str, ids)))
    before = invoke("images", "show", "-p", project, "--image-ids", str(ids[0]))
    processed = invoke(
        "images", "process", "-p", project, "--image-ids-file", str(ids_file), "-r", "512", "--rebuild"
    )
    assert processed[-1]["processed_ids"] == ids
    processed_paths = [Path(row["output_path"]) for row in processed if row["kind"] == "item"]
    assert all(path.is_file() for path in processed_paths)
    rerun = invoke("images", "process", "-p", project, "--image-ids-file", str(ids_file), "-r", "512")
    assert rerun[-1]["skipped_ids"] == ids
    invoke(
        "annotate",
        "run",
        "-p",
        project,
        "--model",
        MODEL,
        "--image-ids-file",
        str(ids_file),
        "--resolution",
        "512",
    )
    assert fake.images_seen and all(max(size) == 512 for size in fake.images_seen)
    invoke(
        "batch",
        "submit",
        "-p",
        project,
        "--model",
        RATING_MODEL,
        "--task-type",
        "rating_preflight",
        "--image-ids-file",
        str(ids_file),
        "--resolution",
        "512",
    )
    submitted = batch.submit_images.call_args.kwargs
    assert submitted["image_ids"] == ids
    assert submitted["task_type"] == "rating_preflight"
    assert submitted["endpoint"] == "/v1/moderations"
    assert len(fake.images_seen) == len(ids)
    assert set(map(Path, submitted["image_paths"].values())) == set(processed_paths)
    imported = invoke("batch", "import", "42", "-p", project)
    assert imported[-1]["imported"] == 1
    output = tmp_path / "export"
    invoke(
        "export", "create", "-p", project, "--image-ids-file", str(ids_file), "-r", "512", "-o", str(output)
    )
    assert any(path.read_text() == "offline tag" for path in output.glob("*.txt"))
    assert any(path.read_text() == "offline caption" for path in output.glob("*.caption"))
    assert source.read_bytes() == source_bytes
    after = invoke("images", "show", "-p", project, "--image-ids", str(ids[0]))
    before_image = next(row for row in before if row["kind"] == "item")
    after_image = next(row for row in after if row["kind"] == "item")
    assert before_image["metadata"] == after_image["metadata"]
    # The original-image annotation guard remains active without an explicit resolution.
    rejected = CliRunner().invoke(
        app, ["--json", "annotate", "run", "-p", project, "--model", MODEL, "--image-id", str(ids[0])]
    )
    assert rejected.exit_code == 2
    # Real mixed DB outcomes: another-directory duplicates, variant, new, corrupt.
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "copy-a.png").write_bytes(source_bytes)
    (mixed / "copy-b.png").write_bytes(source_bytes)
    Image.new("RGB", (192, 128), color=(90, 130, 190)).save(mixed / "variant.png")
    Image.frombytes("RGB", (96, 64), rng.randbytes(96 * 64 * 3)).save(mixed / "new.png")
    (mixed / "broken.png").write_bytes(b"not an image")
    mixed_run = CliRunner().invoke(app, ["--json", "images", "register", str(mixed), "-p", project])
    assert mixed_run.exit_code == 1
    mixed_rows = [json.loads(line) for line in mixed_run.stdout.splitlines()]
    items = [row for row in mixed_rows if row["kind"] == "item"]
    outcomes = {Path(row["input_path"]).name: row for row in items}
    assert outcomes["copy-a.png"]["image_id"] == outcomes["copy-b.png"]["image_id"] == ids[0]
    assert outcomes["copy-a.png"]["outcome"] == outcomes["copy-b.png"]["outcome"] == "duplicate"
    assert outcomes["variant.png"]["outcome"] == "variant"
    assert outcomes["new.png"]["outcome"] == "registered"
    assert outcomes["broken.png"]["outcome"] == "failed"
    assert outcomes["broken.png"]["image_id"] is None
    assert len({row["image_id"] for row in items if row["selected"]}) == 2
    assert mixed_rows[-1]["target_count"] == 2
    assert [mixed_rows[-1][key] for key in ("registered", "variant", "skipped", "errors")] == [1, 1, 2, 1]
    ServiceContainer.reset_for_testing()
