"""Verify shell-visible exit codes through main(), with isolated mocked services."""

import json
import os
import subprocess
import sys
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
else:
    raise AssertionError(scenario)
main()
"""


@pytest.mark.parametrize("json_mode", [True, False])
@pytest.mark.parametrize("status,expected", [("success", 0), ("partial_success", 3), ("failed", 1)])
@pytest.mark.parametrize(
    "scenario", ["processing", "register", "resolve", "import", "legacy_import", "update", "export"]
)
def test_process_exit_contract(tmp_path, scenario, status, expected, json_mode):
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
    }
    env = dict(os.environ)
    env.update(
        LORAIRO_CONFIG_HOME=str(tmp_path / "config"),
        LORAIRO_CLI_LOG_PATH=str(tmp_path / "cli.log"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        NO_COLOR="1",
        TERM="dumb",
        PYTHONPATH=os.pathsep.join(
            str(root / path)
            for path in (
                "src",
                "local_packages/image-annotator-lib/src",
                "local_packages/genai-tag-db-tools/src",
            )
        ),
    )
    result = subprocess.run(
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
