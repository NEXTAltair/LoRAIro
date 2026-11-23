"""Verify shell-visible exit codes through main(), with isolated mocked services.

シナリオ × 状態の写像 (0 / 3 / 1) は in-process の ``main()`` 呼び出しで全件検証し、
「その値が実際にインタプリタの終了コードとして shell に出る」ことは代表ケースだけを
fresh な子プロセスで検証する (子プロセスの cold import は 1 回 4 秒前後かかるため)。
"""

import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from lorairo.cli.commands import annotate, batch, errors, export, images, processing
from lorairo.public_api.processing import ProcessingOutcome
from lorairo.public_api.types import RegistrationResult
from lorairo.services.batch_import_service import BatchImportResult

SCENARIOS = (
    "processing",
    "register",
    "resolve",
    "import",
    "legacy_import",
    "update",
    "export",
    "crop_batch",
)
STATUS_EXIT_CODES = (("success", 0), ("partial_success", 3), ("failed", 1))

# 子プロセスで同じ install_scenario() を使い、シナリオ定義を 1 か所に保つ。
CHILD = r"""
import importlib.util
import socket
import sys

def no_network(*args, **kwargs):
    raise AssertionError("Process contract tests must not use the network")
socket.socket.connect = no_network
socket.create_connection = no_network

spec = importlib.util.spec_from_file_location("_exit_code_scenarios", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
scenario, status = sys.argv[2:4]
del sys.argv[1:4]
module.install_scenario(scenario, status, setattr)

from lorairo.cli.main import main
main()
"""


Patch = Callable[[Any, str, Any], None]


def _install_processing(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(
        processing,
        "process_images",
        MagicMock(
            return_value=[
                *([ProcessingOutcome(1, "success", 512)] if good else []),
                *([ProcessingOutcome(2, "failed", 512, reason="fixture error")] if bad else []),
            ]
        ),
    )


def _install_register(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(images, "api_get_project", MagicMock())
    patch(images, "get_service_container", lambda: container)
    patch(
        images,
        "api_register_images",
        MagicMock(
            return_value=RegistrationResult(
                total=good + bad,
                successful=good,
                failed=bad,
                skipped=0,
                error_details=["fixture error"] if bad else [],
            )
        ),
    )


def _install_resolve(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(errors, "api_get_project", MagicMock())
    patch(errors, "get_service_container", lambda: container)
    repo = container.db_manager.error_record_repo
    repo.get_error_ids_by_filter.return_value = list(range(good + bad))
    repo.mark_errors_resolved_batch.return_value = (not bad, good)


def _install_update(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    patch(images, "api_get_project", MagicMock())
    patch(images, "get_service_container", lambda: container)
    container.db_manager.image_repo.get_image_metadata.return_value = {"id": 1}
    outcomes = ([(True, 1)] if good else []) + ([SQLAlchemyError("fixture error")] if bad else [])
    container.db_manager.annotation_repo.add_tag_to_images_batch.side_effect = outcomes


def _install_export(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(export, "api_get_project", MagicMock())
    patch(export, "get_service_container", lambda: container)
    container.dataset_export_service.export_dataset_all_formats.return_value = SimpleNamespace(
        summary=lambda: {
            "ok": not bad,
            "status": status,
            "requested": good + bad,
            "exported": good,
            "skipped": 0,
            "failed": bad,
            "exported_ids": [1] if good else [],
            "failed_ids": [2] if bad else [],
            "error_details": [],
        },
    )


def _install_import(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(batch, "_activate_project", lambda _: container)
    patch(batch, "_get_rating_breakdown", lambda *args: {})
    container.provider_batch_workflow_service.import_results.return_value = SimpleNamespace(
        imported_count=good,
        skipped_count=0,
        error_count=bad,
        total_count=good + bad,
        job_imported=not bad,
        already_imported_count=0,
        missing_custom_ids=(),
        failed_custom_ids=("fixture",) if bad else (),
        failed_image_ids=(2,) if bad else (),
        save_result=SimpleNamespace(error_details=["fixture error"] if bad else []),
    )


def _install_legacy_import(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    patch(annotate, "get_service_container", lambda: container)
    patch(
        annotate,
        "import_batch_annotations",
        MagicMock(
            return_value=BatchImportResult(
                total_records=good + bad,
                parsed_ok=good + bad,
                parse_errors=0,
                matched=good + bad,
                unmatched=0,
                saved=good,
                save_errors=bad,
                model_name="fixture",
                unmatched_ids=[],
                error_details=["fixture error"] if bad else [],
            )
        ),
    )


def _install_crop_batch(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    from lorairo.services.crop_batch_service import CropBatchOutcome

    patch(images, "api_get_project", MagicMock())
    patch(images, "get_service_container", lambda: container)
    Path("rects.jsonl").write_text(
        '{"image_id": 1, "x": 0, "y": 0, "width": 8, "height": 8}\n'
        '{"image_id": 2, "x": 0, "y": 0, "width": 8, "height": 8}\n',
        encoding="utf-8",
    )

    def fake_run(provider, parent_ids, *, on_outcome, **kwargs):
        statuses = {1: "created" if good else "failed", 2: "failed" if bad else "created"}
        for parent_id in parent_ids:
            for candidate in provider.candidates_for(parent_id):
                created = statuses[parent_id] == "created"
                on_outcome(
                    CropBatchOutcome(
                        statuses[parent_id],
                        parent_id,
                        candidate,
                        child_image_id=10 if created else None,
                        reason=None if created else "invalid_rect",
                        message="fixture",
                    )
                )
        return []

    patch(images, "run_crop_batch", fake_run)


def _install_maintenance(status: str, good: int, bad: int, container: MagicMock, patch: Patch) -> None:
    import lorairo.public_api.maintenance as maintenance_api
    from lorairo.services.db_maintenance_check_service import MaintenanceFinding, MaintenanceReport

    patch(
        maintenance_api,
        "check_database",
        MagicMock(
            return_value=MaintenanceReport(
                scopes=["batch", "files"],
                limit=100,
                checks=[
                    MaintenanceFinding(
                        "image_file_missing",
                        "files",
                        "image_id",
                        bad,
                        [2] if bad else [],
                        False,
                        "fixture",
                    )
                ],
                checked_batch_jobs=0,
                checked_images=good + bad,
                checked_processed_images=0,
            )
        ),
    )


def install_scenario(scenario: str, status: str, patch: Patch) -> None:
    """CLI コマンドの境界を status に応じた結果を返すモックへ差し替える。

    Args:
        scenario: 対象コマンドの識別子。
        status: ``success`` / ``partial_success`` / ``failed``。
        patch: ``setattr`` 互換の差し替え関数 (in-process では ``monkeypatch.setattr``)。
    """
    installers = {
        "processing": _install_processing,
        "register": _install_register,
        "resolve": _install_resolve,
        "update": _install_update,
        "export": _install_export,
        "import": _install_import,
        "legacy_import": _install_legacy_import,
        "crop_batch": _install_crop_batch,
        "maintenance": _install_maintenance,
    }
    installers[scenario](status, int(status != "failed"), int(status != "success"), MagicMock(), patch)


def _command_args(scenario: str, status: str, tmp_path: Path, json_mode: bool) -> list[str]:
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
    return ["--json" if json_mode else "--no-json", *commands[scenario], "--project", "fixture"]


def _run_process(tmp_path, scenario, status, json_mode, base_env):
    root = Path(__file__).resolve().parents[3]
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
            str(Path(__file__).resolve()),
            scenario,
            status,
            *_command_args(scenario, status, tmp_path, json_mode),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def _run_in_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    scenario: str,
    status: str,
    json_mode: bool,
) -> tuple[int, str, str]:
    """子プロセス版と同じ argv / 差し替えで main() を呼び、(終了コード, stdout, stderr) を返す。"""
    from lorairo.cli.main import main

    def no_network(*args, **kwargs):
        raise AssertionError("Process contract tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LORAIRO_CLI_JSON", raising=False)
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    monkeypatch.setattr("lorairo.cli.main.initialize_logging", MagicMock())
    install_scenario(scenario, status, monkeypatch.setattr)
    capsys.readouterr()
    try:
        main(_command_args(scenario, status, tmp_path, json_mode))
    except SystemExit as exc:
        code = exc.code
    else:
        code = 0
    captured = capsys.readouterr()
    assert isinstance(code, int), (code, captured.out + captured.err)
    return code, captured.out, captured.err


def _assert_json_result(stdout: str, scenario: str, status: str) -> None:
    row = json.loads(stdout.splitlines()[-1])
    assert row["kind"] == "result"
    if scenario == "update":
        assert row["added"] == int(status != "failed")
        assert bool(row["failed_tags"]) is (status != "success")
    else:
        assert row["status"] == status
        assert row["ok"] is (status == "success")


@pytest.mark.parametrize("json_mode", [True, False])
@pytest.mark.parametrize(
    ("scenario", "status", "expected"),
    [
        pytest.param(scenario, status, expected, id=f"{scenario}-{status}-{expected}")
        for scenario in SCENARIOS
        for status, expected in STATUS_EXIT_CODES
    ],
)
def test_main_exit_contract(monkeypatch, capsys, tmp_path, scenario, status, expected, json_mode):
    """main() が各コマンドの結果を exit 0 / 3 / 1 と最終 JSON 行へ写す。"""
    code, stdout, stderr = _run_in_process(monkeypatch, capsys, tmp_path, scenario, status, json_mode)
    assert code == expected, stdout + stderr
    if json_mode:
        _assert_json_result(stdout, scenario, status)


# 終了コード 0 / 3 / 1 がそれぞれ実プロセスの returncode として出ることを、出力モードも
# 両方含む代表 3 ケースで確かめる。3 本は同時に起動して cold import を 1 波に収める。
PROCESS_CASES = (
    ("processing", "success", 0, True),
    ("export", "partial_success", 3, False),
    ("crop_batch", "failed", 1, True),
)


@pytest.fixture(scope="module")
def process_results(tmp_path_factory):
    base_env = dict(os.environ)
    with ThreadPoolExecutor(max_workers=len(PROCESS_CASES)) as executor:
        futures = {
            case: executor.submit(
                _run_process,
                tmp_path_factory.mktemp(f"exit-{case[0]}-{case[1]}"),
                case[0],
                case[1],
                case[3],
                base_env,
            )
            for case in PROCESS_CASES
        }
        return {case: future.result() for case, future in futures.items()}


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=f"{case[0]}-{case[1]}-{case[2]}-{'json' if case[3] else 'nojson'}")
        for case in PROCESS_CASES
    ],
)
def test_process_exit_contract(process_results, case):
    """interpreter の終了コードと実 stdout パイプに main() の写像がそのまま出る。"""
    scenario, status, expected, json_mode = case
    result = process_results[case]
    assert result.returncode == expected, result.stdout + result.stderr
    if json_mode:
        _assert_json_result(result.stdout, scenario, status)


@pytest.mark.parametrize("json_mode", [True, False])
@pytest.mark.parametrize("findings", ["success", "failed"], ids=["clean", "issues"])
def test_maintenance_check_findings_still_exit_zero(monkeypatch, capsys, tmp_path, json_mode, findings):
    """Read-only report: inconsistencies are data, not a command failure (ADR 0099)."""
    code, stdout, stderr = _run_in_process(
        monkeypatch, capsys, tmp_path, "maintenance", findings, json_mode
    )
    assert code == 0, stdout + stderr
    if json_mode:
        row = json.loads(stdout.splitlines()[-1])
        assert row["kind"] == "result" and row["status"] == "success" and row["ok"] is True
        assert row["issues_found"] is (findings == "failed")
