"""CLI-only image generation workflow; no raw database edits or GUI state simulation."""

import json
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
            )
        ]

    def refresh_available_models(self):
        return [MODEL]

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
    registration = invoke("images", "register", str(inputs), "-p", project)
    assert registration[-1]["registered"] == 1
    registration_items = [row for row in registration if row["kind"] == "item"]
    if registration_items:
        # #1307 supplies exact selected registration outcomes; never replace those with search.
        ids = [row["image_id"] for row in registration_items if row["selected"]]
    else:
        # Pre-#1307 base: this fresh project contains only the one registered input.
        # Final integration must exercise the selected-registration-outcome branch above.
        ids = [
            row["image_id"]
            for row in invoke("images", "search", "-p", project, "--query", '{"emit_ids":true}')
            if row["kind"] == "item"
        ]
    assert len(ids) == 1
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(map(str, ids)))
    before = invoke("images", "show", "-p", project, "--image-ids", str(ids[0]))
    processed = invoke("images", "process", "-p", project, "--image-ids-file", str(ids_file), "-r", "256")
    assert processed[-1]["processed_ids"] == ids
    processed_paths = [Path(row["output_path"]) for row in processed if row["kind"] == "item"]
    assert all(path.is_file() for path in processed_paths)
    rerun = invoke("images", "process", "-p", project, "--image-ids-file", str(ids_file), "-r", "256")
    assert rerun[-1]["skipped_ids"] == ids
    invoke(
        "annotate", "run", "-p", project, "--model", MODEL, "--image-id", str(ids[0]), "--resolution", "256"
    )
    assert fake.images_seen and all(max(size) == 256 for size in fake.images_seen)
    invoke(
        "batch",
        "submit",
        "-p",
        project,
        "--model",
        MODEL,
        "--provider",
        "anthropic",
        "--image-ids",
        str(ids[0]),
        "--resolution",
        "256",
    )
    submitted = batch.submit_images.call_args.kwargs
    assert submitted["image_ids"] == ids
    assert set(map(Path, submitted["image_paths"].values())) == set(processed_paths)
    imported = invoke("batch", "import", "42", "-p", project)
    assert imported[-1]["imported"] == 1
    output = tmp_path / "export"
    invoke(
        "export", "create", "-p", project, "--image-ids-file", str(ids_file), "-r", "256", "-o", str(output)
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
    ServiceContainer.reset_for_testing()
