"""CLI workflow E2E tests.

These tests keep the full workflow in-process with Typer's CliRunner so pytest
fixtures can isolate project storage and inject a deterministic annotator.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import imagehash
import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

FAKE_MODEL_ID = "lorairo-e2e-fake-tagger"
FAKE_TAG = "lorairoe2etag"
FAKE_CAPTION = "lorairo e2e caption"


class FakeAnnotatorLibrary:
    """Deterministic annotator used at the ServiceContainer boundary."""

    def __init__(self) -> None:
        self.annotate_calls = 0

    def list_annotator_info(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                name=FAKE_MODEL_ID,
                model_type="tagger",
                capabilities=frozenset(),
                is_local=True,
                is_api=False,
                device=None,
                provider="local",
                litellm_model_id=FAKE_MODEL_ID,
                estimated_size_gb=0.0,
                discontinued_at=None,
            )
        ]

    def refresh_available_models(self) -> list[str]:
        return [FAKE_MODEL_ID]

    def is_model_deprecated(self, model_name: str) -> bool:
        return False

    def annotate(
        self,
        images: list[Image.Image],
        litellm_model_ids: list[str],
        phash_list: list[str] | None = None,
    ) -> dict[str, dict[str, SimpleNamespace]]:
        self.annotate_calls += 1
        phashes = phash_list or [str(imagehash.phash(image)) for image in images]
        return {
            phash: {
                model_id: SimpleNamespace(
                    tags=[FAKE_TAG],
                    captions=[FAKE_CAPTION],
                    scores=None,
                    score_labels=None,
                    ratings=None,
                    error=None,
                )
                for model_id in litellm_model_ids
            }
            for phash in phashes
        }


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    ServiceContainer.reset_for_testing()
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=projects_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)
    return projects_dir


@pytest.fixture
def input_image_dir(tmp_path: Path) -> Path:
    image_dir = tmp_path / "input_images"
    image_dir.mkdir()
    image = Image.new("RGB", (96, 96), color=(96, 128, 160))
    image.save(image_dir / "sample.png")
    return image_dir


def _install_fake_annotator() -> None:
    container = ServiceContainer()
    container._annotator_library = FakeAnnotatorLibrary()
    container._model_registry = None
    container._model_sync_service = None


def _switch_registered_images_to_processed_paths(project_dir: Path) -> None:
    """Simulate the GUI-safe processed image path before CLI annotation."""
    db_path = project_dir / "image_database.db"
    processed_dir = project_dir / "image_dataset" / "processed_images"
    processed_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT id, stored_image_path FROM images").fetchall()
        for image_id, stored_image_path in rows:
            source_path = project_dir / stored_image_path
            processed_relative = Path("image_dataset") / "processed_images" / source_path.name
            shutil.copy2(source_path, project_dir / processed_relative)
            conn.execute(
                "UPDATE images SET stored_image_path = ? WHERE id = ?",
                (processed_relative.as_posix(), image_id),
            )
        conn.commit()


@pytest.mark.integration
@pytest.mark.cli
@pytest.mark.e2e
def test_cli_full_workflow_with_fake_annotator(
    cli_runner: CliRunner,
    isolated_projects_dir: Path,
    input_image_dir: Path,
    tmp_path: Path,
) -> None:
    """Project creation, image registration, annotation, and export work together."""
    _install_fake_annotator()

    project_name = "cli-e2e"

    create_result = cli_runner.invoke(app, ["project", "create", project_name])
    assert create_result.exit_code == 0, create_result.stdout
    assert any(path.name.startswith(f"{project_name}_") for path in isolated_projects_dir.iterdir())

    refresh_result = cli_runner.invoke(app, ["models", "refresh", "--project", project_name])
    assert refresh_result.exit_code == 0, refresh_result.stdout
    assert "1 model(s) discovered" in refresh_result.stdout

    register_result = cli_runner.invoke(
        app,
        ["images", "register", str(input_image_dir), "--project", project_name],
    )
    assert register_result.exit_code == 0, register_result.stdout
    assert "Registered" in register_result.stdout
    project_dir = next(
        path for path in isolated_projects_dir.iterdir() if path.name.startswith(project_name)
    )
    _switch_registered_images_to_processed_paths(project_dir)

    annotate_result = cli_runner.invoke(
        app,
        ["annotate", "run", "--project", project_name, "--model", FAKE_MODEL_ID],
    )
    assert annotate_result.exit_code == 0, annotate_result.stdout + annotate_result.stderr
    assert "Annotation completed successfully" in annotate_result.stdout

    export_dir = tmp_path / "export"
    export_result = cli_runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            project_name,
            "--tags",
            FAKE_TAG,
            "--output",
            str(export_dir),
        ],
    )
    assert export_result.exit_code == 0, export_result.stdout
    assert "Export completed successfully" in export_result.stdout
    assert any(path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} for path in export_dir.iterdir())
    assert any(path.read_text(encoding="utf-8") == FAKE_TAG for path in export_dir.glob("*.txt"))
    assert any(path.read_text(encoding="utf-8") == FAKE_CAPTION for path in export_dir.glob("*.caption"))


@pytest.mark.integration
@pytest.mark.cli
@pytest.mark.e2e
def test_cli_unknown_model_exits_before_annotation(
    cli_runner: CliRunner,
    isolated_projects_dir: Path,
    input_image_dir: Path,
) -> None:
    """Unknown model IDs fail at CLI resolution before calling the annotator."""
    _install_fake_annotator()

    project_name = "cli-e2e-unknown-model"
    assert cli_runner.invoke(app, ["project", "create", project_name]).exit_code == 0
    assert cli_runner.invoke(app, ["models", "refresh", "--project", project_name]).exit_code == 0
    assert (
        cli_runner.invoke(
            app, ["images", "register", str(input_image_dir), "--project", project_name]
        ).exit_code
        == 0
    )

    container = ServiceContainer()
    fake = container.annotator_library
    calls_before = getattr(fake, "annotate_calls", 0)

    result = cli_runner.invoke(
        app,
        ["annotate", "run", "--project", project_name, "--model", "missing-model"],
    )

    assert result.exit_code == 2
    assert "Unknown model 'missing-model'" in result.stderr
    assert getattr(fake, "annotate_calls", 0) == calls_before
