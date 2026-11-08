"""Verify shell-visible exit codes through main(), with isolated mocked services."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

CHILD = r"""
import socket
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

def no_network(*args, **kwargs):
    raise AssertionError("Process contract tests must not use the network")
socket.socket.connect = no_network
socket.create_connection = no_network

from lorairo.cli.main import main
from lorairo.cli.commands import batch, errors, images, processing, annotate, export
from lorairo.public_api.processing import ProcessingOutcome
from lorairo.public_api.types import RegistrationResult
from lorairo.services.batch_import_service import BatchImportResult

scenario, status = sys.argv[1:3]
del sys.argv[1:3]
good = int(status != "failed")
bad = int(status != "success")
container = MagicMock()
if scenario == "processing":
    processing.process_images = MagicMock(return_value=[
        *([ProcessingOutcome(1, "success", 512)] if good else []),
        *([ProcessingOutcome(2, "failed", 512, reason="fixture error")] if bad else []),
    ])
elif scenario == "register":
    images.api_get_project = MagicMock()
    images.get_service_container = lambda: container
    images.api_register_images = MagicMock(return_value=RegistrationResult(
        total=good + bad, successful=good, failed=bad, skipped=0,
        error_details=["fixture error"] if bad else [],
    ))
elif scenario == "resolve":
    errors.api_get_project = MagicMock()
    errors.get_service_container = lambda: container
    container.db_manager.error_record_repo.get_error_ids_by_filter.return_value = list(range(good + bad))
    container.db_manager.error_record_repo.mark_errors_resolved_batch.return_value = (not bad, good)
elif scenario == "update":
    from sqlalchemy.exc import SQLAlchemyError
    images.api_get_project = MagicMock()
    images.get_service_container = lambda: container
    container.db_manager.image_repo.get_image_metadata.return_value = {"id": 1}
    outcomes = ([(True, 1)] if good else []) + ([SQLAlchemyError("fixture error")] if bad else [])
    container.db_manager.annotation_repo.add_tag_to_images_batch.side_effect = outcomes
elif scenario == "export":
    export.api_get_project = MagicMock()
    export.get_service_container = lambda: container
    container.dataset_export_service.export_dataset_all_formats.return_value = SimpleNamespace(
        summary=lambda: dict(ok=not bad, status=status, requested=good + bad, exported=good,
            skipped=0, failed=bad, exported_ids=[1] if good else [], failed_ids=[2] if bad else [],
            error_details=[]),
    )
elif scenario == "import":
    batch._activate_project = lambda _: container
    batch._get_rating_breakdown = lambda *args: {}
    container.provider_batch_workflow_service.import_results.return_value = SimpleNamespace(
        imported_count=good, skipped_count=0, error_count=bad, total_count=good + bad,
        job_imported=not bad, already_imported_count=0, missing_custom_ids=(),
        failed_custom_ids=("fixture",) if bad else (), failed_image_ids=(2,) if bad else (),
        save_result=SimpleNamespace(error_details=["fixture error"] if bad else []),
    )
elif scenario == "legacy_import":
    annotate.get_service_container = lambda: container
    annotate.import_batch_annotations = MagicMock(return_value=BatchImportResult(
        total_records=good + bad, parsed_ok=good + bad, parse_errors=0,
        matched=good + bad, unmatched=0, saved=good, save_errors=bad, model_name="fixture",
        unmatched_ids=[], error_details=["fixture error"] if bad else [],
    ))
elif scenario == "crop_batch":
    from pathlib import Path
    from lorairo.domain.crop_rect_provider import CropRectCandidate
    from lorairo.domain.crop_request import CropRect
    from lorairo.services.crop_batch_service import CropBatchOutcome
    images.api_get_project = MagicMock()
    images.get_service_container = lambda: container
    Path("rects.jsonl").write_text(
        '{"image_id": 1, "x": 0, "y": 0, "width": 8, "height": 8}\n'
        '{"image_id": 2, "x": 0, "y": 0, "width": 8, "height": 8}\n',
        encoding="utf-8",
    )
    def fake_run(provider, parent_ids, *, on_outcome, **kwargs):
        statuses = {1: "created" if good else "failed", 2: "failed" if bad else "created"}
        for parent_id in parent_ids:
            for candidate in provider.candidates_for(parent_id):
                outcome = CropBatchOutcome(statuses[parent_id], parent_id, candidate,
                    child_image_id=10 if statuses[parent_id] == "created" else None,
                    reason=None if statuses[parent_id] == "created" else "invalid_rect", message="fixture")
                on_outcome(outcome)
        return []
    images.run_crop_batch = fake_run
elif scenario == "maintenance":
    import lorairo.public_api.maintenance as maintenance_api
    from lorairo.services.db_maintenance_check_service import MaintenanceFinding, MaintenanceReport
    maintenance_api.check_database = MagicMock(return_value=MaintenanceReport(
        scopes=["batch", "files"], limit=100,
        checks=[MaintenanceFinding("image_file_missing", "files", "image_id", bad, [2] if bad else [],
            False, "fixture")],
        checked_batch_jobs=0, checked_images=good + bad, checked_processed_images=0,
    ))
else:
    raise AssertionError(scenario)
main()
"""


@pytest.fixture(
    scope="module",
    params=[
        pytest.param((scenario, status, expected), id=f"{scenario}-{status}-{expected}")
        for scenario in (
            "processing",
            "register",
            "resolve",
            "import",
            "legacy_import",
            "update",
            "export",
            "crop_batch",
        )
        for status, expected in (("success", 0), ("partial_success", 3), ("failed", 1))
    ],
)
def process_case(request, tmp_path_factory):
    """Overlap two fresh CLI startups, keeping 48 independently reported cases.

    Only the JSON/non-JSON pair shares this fixture. At most two children run,
    including on two-core CI; each retains its own files and 60-second timeout.
    Snapshot the environment on the pytest thread before function fixtures run.
    """
    scenario, status, expected = request.param
    base_env = dict(os.environ)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = {
            json_mode: executor.submit(
                _run_process,
                tmp_path_factory.mktemp(f"exit-{scenario}-{status}-{json_mode}"),
                scenario,
                status,
                json_mode,
                base_env,
            )
            for json_mode in (True, False)
        }
        yield scenario, status, expected, results


def _run_process(tmp_path, scenario, status, json_mode, base_env):
    root = Path(__file__).resolve().parents[3]
    commands = {
        "processing": ["images", "process", "--image-ids", "1,2"],
        "register": ["images", "register", str(tmp_path)],
        "resolve": ["errors", "resolve", "--operation", "search"],
        "import": ["batch", "import", "1"],
        "legacy_import": ["annotate", "import-batch", str(tmp_path)],
        "update": [
            "images",
            "update",
            "--image-id",
            "1",
            "--tags",
            "cat,dog" if status == "partial_success" else "cat",
        ],
        "export": ["export", "create", "--image-ids", "1,2", "--output", str(tmp_path / "output")],
        "maintenance": ["maintenance", "check"],
        "crop_batch": ["images", "crop-batch", "--rects", "rects.jsonl"],
    }
    child_tmp = tmp_path / "tmp"
    child_tmp.mkdir()
    env = dict(base_env)
    env.update(
        LORAIRO_CONFIG_HOME=str(tmp_path / "config"),
        LORAIRO_CLI_LOG_PATH=str(tmp_path / "cli.log"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        NO_COLOR="1",
        TERM="dumb",
        TMP=str(child_tmp),
        TEMP=str(child_tmp),
        TMPDIR=str(child_tmp),
        PYTHONPATH=os.pathsep.join(
            str(root / path)
            for path in (
                "src",
                "local_packages/image-annotator-lib/src",
                "local_packages/genai-tag-db-tools/src",
            )
        ),
    )
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            CHILD,
            scenario,
            status,
            "--json" if json_mode else "--no-json",
            *commands[scenario],
            "--project",
            "fixture",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("json_mode", [True, False])
def test_process_exit_contract(process_case, json_mode):
    scenario, status, expected, results = process_case
    result = results[json_mode].result()
    assert result.returncode == expected, result.stdout + result.stderr
    if json_mode:
        row = json.loads(result.stdout.splitlines()[-1])
        assert row["kind"] == "result"
        if scenario == "update":
            assert row["added"] == int(status != "failed")
            assert bool(row["failed_tags"]) is (status != "success")
        else:
            assert row["status"] == status
            assert row["ok"] is (status == "success")


@pytest.mark.parametrize("json_mode", [True, False])
@pytest.mark.parametrize("findings", ["success", "failed"], ids=["clean", "issues"])
def test_maintenance_check_findings_still_exit_zero(tmp_path, json_mode, findings):
    """Read-only report: inconsistencies are data, not a command failure (ADR 0099)."""
    result = _run_process(tmp_path, "maintenance", findings, json_mode, dict(os.environ))
    assert result.returncode == 0, result.stdout + result.stderr
    if json_mode:
        row = json.loads(result.stdout.splitlines()[-1])
        assert row["kind"] == "result" and row["status"] == "success" and row["ok"] is True
        assert row["issues_found"] is (findings == "failed")
