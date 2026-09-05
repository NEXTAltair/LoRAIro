"""Isolated task plans exercise real Git worktree metadata on both platforms."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location("dev_tasks", Path(__file__).parents[1] / "dev_tasks.py")
assert SPEC and SPEC.loader
tasks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tasks)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "日本語 main checkout"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    for name in tasks.PACKAGES:
        package = root / "local_packages" / name
        package.mkdir(parents=True)
        (package / "pyproject.toml").touch()
    tasks.git(root, "add", ".")
    tasks.git(root, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "fixture")
    linked = tmp_path / "日本語 linked checkout"
    tasks.git(root, "worktree", "add", "-b", "test-linked", str(linked))
    interpreter = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    return root, linked, interpreter


@pytest.mark.parametrize("task", [task for task in tasks.TASKS if not task.startswith("install")])
def test_non_install_tasks_never_sync_or_create_environment(checkout, task):
    root, linked, interpreter = checkout
    before = sorted(str(p) for p in linked.rglob("*"))
    plan = tasks.build_plan(task, linked, {})
    assert plan
    for command in plan:
        assert command["argv"][:6] == ["uv", "run", "--no-sync", "--python", str(interpreter), "python"]
        assert "sync" not in command["argv"]
        assert command["env"]["UV_PROJECT_ENVIRONMENT"] == str(root / ".venv")
        paths = command["env"]["PYTHONPATH"].split(os.pathsep)
        assert paths[0] == str(linked / "src")
        assert all(Path(path).is_relative_to(linked) for path in paths)
        assert ("QT_QPA_PLATFORM" in command["env"]) == task.startswith("test")
    assert before == sorted(str(p) for p in linked.rglob("*"))
    assert not (linked / ".venv").exists()


def test_test_all_keeps_package_boundaries_and_excludes_paid_tests(checkout):
    _, linked, _ = checkout
    plan = tasks.build_plan("test-all", linked, {})
    assert [entry["cwd"] for entry in plan] == [
        str(linked),
        *[str(linked / "local_packages" / name) for name in tasks.PACKAGES],
    ]
    assert all(entry["argv"][-1] == tasks.SAFE_MARKERS for entry in plan)


@pytest.mark.parametrize("configured", ["relative/.venv", "/workspaces/stale/.venv", ""])
def test_rejects_stale_or_relative_environment(checkout, configured):
    _, linked, _ = checkout
    with pytest.raises(ValueError, match="Correct the shell/session"):
        tasks.build_plan("test", linked, {"UV_PROJECT_ENVIRONMENT": configured})


def test_rejects_worktree_environment_even_when_present(checkout):
    _, linked, _ = checkout
    (linked / ".venv").mkdir()
    with pytest.raises(ValueError, match="absolute shared path"):
        tasks.build_plan("lint", linked, {"UV_PROJECT_ENVIRONMENT": str(linked / ".venv")})


def test_missing_shared_python_is_setup_error(checkout):
    _, linked, interpreter = checkout
    interpreter.unlink()
    with pytest.raises(ValueError, match="install-dev"):
        tasks.build_plan("test", linked, {})
    assert not (linked / ".venv").exists()


@pytest.mark.parametrize("task", ["install", "install-dev"])
def test_only_explicit_install_from_main_allows_missing_python(checkout, task):
    root, linked, interpreter = checkout
    interpreter.unlink()
    plan = tasks.build_plan(task, root, {})
    assert plan[0]["argv"] == ["uv", "sync"] + (
        ["--dev", "--all-packages", "--all-groups"] if task == "install-dev" else []
    )
    with pytest.raises(ValueError, match="main checkout"):
        tasks.build_plan(task, linked, {})


def test_missing_submodule_does_not_fetch(checkout):
    _, linked, _ = checkout
    (linked / "local_packages" / tasks.PACKAGES[0] / "pyproject.toml").unlink()
    with pytest.raises(ValueError, match="submodule update --init --recursive explicitly"):
        tasks.build_plan("test", linked, {})


def test_explicit_correct_environment_is_accepted(checkout):
    root, linked, _ = checkout
    assert (
        tasks.resolve_shared_environment(linked, {"UV_PROJECT_ENVIRONMENT": str(root / ".venv")})
        == root / ".venv"
    )


def test_dry_run_is_json_and_never_executes(checkout, monkeypatch, capsys):
    _, linked, _ = checkout
    plan = tasks.build_plan("test-all", linked, {})
    monkeypatch.setattr(tasks, "build_plan", Mock(return_value=plan))
    runner = Mock(side_effect=AssertionError("must not run"))
    monkeypatch.setattr(tasks.subprocess, "run", runner)
    assert tasks.main(["test-all", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out) == plan
    runner.assert_not_called()


def test_failure_propagates_and_stops_later_sessions(checkout, monkeypatch):
    _, linked, _ = checkout
    plan = tasks.build_plan("test-all", linked, {})
    monkeypatch.setattr(tasks, "build_plan", Mock(return_value=plan))
    runner = Mock(return_value=subprocess.CompletedProcess([], 7))
    monkeypatch.setattr(tasks.subprocess, "run", runner)
    assert tasks.main(["test-all"]) == 7
    assert runner.call_count == 1
    assert runner.call_args.kwargs["env"]["QT_QPA_PLATFORM"] == "offscreen"
