"""Isolated task plans exercise real Git worktree metadata on both platforms."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import venv
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
    spec = tasks.TASKS[task]
    for command in plan:
        expected_python = sys.executable if spec.runtime == "stdlib" else str(interpreter)
        assert command["argv"][0] == expected_python
        assert "uv" not in command["argv"]
        assert "sync" not in command["argv"]
        if spec.runtime == "stdlib":
            assert command["env"] == {}
        else:
            assert command["env"]["UV_PROJECT_ENVIRONMENT"] == str(root / ".venv")
            assert command["env"]["VIRTUAL_ENV"] == str(root / ".venv")
            assert command["env"]["PATH"].split(os.pathsep)[0] == str(interpreter.parent)
        if spec.imports_source:
            paths = command["env"]["PYTHONPATH"].split(os.pathsep)
            assert paths == [
                str(linked / "src"),
                *[str(linked / "local_packages" / name / "src") for name in spec.packages],
            ]
        else:
            assert "PYTHONPATH" not in command["env"]
        assert ("QT_QPA_PLATFORM" in command["env"]) == spec.headless
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


def test_gui_entrypoint_preserves_exit_code(checkout):
    _, linked, _ = checkout
    command = tasks.build_plan("run-gui", linked, {})[0]
    assert "sys.exit(main())" in command["argv"][-1]
    assert "QT_QPA_PLATFORM" not in command["env"]


def test_docs_okf_validates_root_without_initialized_submodules(checkout):
    _, linked, _ = checkout
    for package in tasks.PACKAGES:
        (linked / "local_packages" / package / "pyproject.toml").unlink()
    plan = tasks.build_plan("docs-okf", linked, {})
    assert len(plan) == 1
    assert plan[0]["argv"][-4:] == [
        "docs",
        "--skip-missing",
        "--exclude",
        "README.md,CHANGELOG.md,CLAUDE.md,AGENTS.md,GEMINI.md,SKILL.md",
    ]


@pytest.mark.parametrize("task", ["adr-drift", "adr-index", "adr-okf", "docs-okf"])
def test_stdlib_tasks_execute_without_git_uv_venv_or_submodules(tmp_path, task):
    """Exercise the actual CLI in a source export, with no tools on PATH."""
    root = tmp_path / "日本語 source export"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for filename in ("dev_tasks.py", "check_adr_drift.py"):
        shutil.copy2(tasks.ROOT / "scripts" / filename, scripts / filename)
    okf = Path(".agents/skills/okf-bundle/scripts")
    shutil.copytree(tasks.ROOT / okf, root / okf, ignore=shutil.ignore_patterns("__pycache__"))
    docs = root / "docs/decisions"
    docs.mkdir(parents=True)
    (docs / "0001-test.md").write_text(
        "---\ntype: ADR\ntitle: Fixture\nstatus: Accepted\ntimestamp: 2026-09-05\n---\n# Fixture\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PATH": "", "UV_PROJECT_ENVIRONMENT": "/workspaces/stale/.venv"}
    command = [sys.executable, "-X", "utf8", str(scripts / "dev_tasks.py")]
    if task == "adr-okf":
        subprocess.run([*command, "adr-index"], cwd=root, env=env, check=True, capture_output=True)
    result = subprocess.run(
        [*command, task], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / ".venv").exists()
    assert not (root / "uv.lock").exists()


@pytest.mark.parametrize("task", tasks.TASKS)
@pytest.mark.parametrize("missing_package", tasks.PACKAGES)
def test_each_task_checks_only_its_declared_packages(checkout, task, missing_package):
    root, linked, _ = checkout
    spec = tasks.TASKS[task]
    selected = root if spec.runtime == "sync" else linked
    (selected / "local_packages" / missing_package / "pyproject.toml").unlink()
    if missing_package in spec.packages:
        with pytest.raises(ValueError, match="Local packages are missing"):
            tasks.build_plan(task, selected, {})
    else:
        assert tasks.build_plan(task, selected, {})


@pytest.mark.parametrize("task", [name for name, spec in tasks.TASKS.items() if spec.runtime == "shared"])
def test_every_shared_task_requires_installed_python(checkout, task):
    _, linked, interpreter = checkout
    interpreter.unlink()
    with pytest.raises(ValueError, match="Shared Python is missing"):
        tasks.build_plan(task, linked, {})


def test_package_status_query_does_not_include_unrelated_submodules(checkout, monkeypatch):
    _, linked, _ = checkout
    read_git = Mock(return_value="+123 local_packages/image-annotator-lib (branch)")
    monkeypatch.setattr(tasks, "git", read_git)
    tasks.check_submodules(linked, (tasks.PACKAGES[0],))
    assert read_git.call_args.args[1:] == (
        "submodule",
        "status",
        "--recursive",
        "--",
        "local_packages/image-annotator-lib",
    )
    read_git.return_value = "U123 local_packages/image-annotator-lib"
    with pytest.raises(ValueError, match="conflicted"):
        tasks.check_submodules(linked, (tasks.PACKAGES[0],))


def test_shared_tool_executes_without_uv_or_unrelated_checkouts(checkout):
    """Use a disposable real interpreter, never install into the user's venv."""
    root, linked, interpreter = checkout
    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    for package in tasks.PACKAGES:
        (linked / "local_packages" / package / "pyproject.toml").unlink()
    # A minimal installed tool records its real execution context. No uv, pip,
    # dependencies, subprocess mocks, or external services are involved.
    result = subprocess.check_output(
        [str(interpreter), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    tool = Path(result.strip()) / "ruff.py"
    tool.write_text(
        "import json, os, shutil, sys\n"
        "print(json.dumps([sys.prefix, os.getcwd(), os.environ['VIRTUAL_ENV'], "
        "sys.executable, shutil.which('python')]))\n",
        encoding="utf-8",
    )
    plan = tasks.build_plan("lint", linked, {"PATH": ""})
    for entry in plan:
        result = subprocess.run(
            entry["argv"],
            cwd=entry["cwd"],
            env={**os.environ, **entry["env"]},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        prefix, cwd, active, executable, found = json.loads(result.stdout)
        assert Path(prefix) == root / ".venv"
        assert Path(cwd) == linked
        assert Path(active) == root / ".venv"
        assert Path(executable) == interpreter
        assert Path(found) == interpreter
    assert not (linked / ".venv").exists()
    assert not (root / "uv.lock").exists()


def test_actual_git_submodule_pathspec_ignores_uninitialized_sibling(tmp_path):
    """A real gitlink, not just a directory, must obey the package boundary."""
    source = tmp_path / "local package source"
    source.mkdir()
    tasks.git(source, "init")
    (source / "pyproject.toml").touch()
    tasks.git(source, "add", ".")
    tasks.git(source, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "pkg")
    commit = tasks.git(source, "rev-parse", "HEAD")
    root = tmp_path / "partial checkout"
    root.mkdir()
    tasks.git(root, "init")
    tasks.git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "--quiet",
        str(source),
        f"local_packages/{tasks.PACKAGES[0]}",
    )
    # Register a second gitlink without fetching/initializing its checkout.
    modules = root / ".gitmodules"
    modules.write_text(
        modules.read_text(encoding="utf-8")
        + f'\n[submodule "local_packages/{tasks.PACKAGES[1]}"]\n'
        + f"\tpath = local_packages/{tasks.PACKAGES[1]}\n\turl = {source.as_posix()}\n",
        encoding="utf-8",
    )
    tasks.git(root, "add", ".gitmodules")
    tasks.git(
        root, "update-index", "--add", "--cacheinfo", f"160000,{commit},local_packages/{tasks.PACKAGES[1]}"
    )
    tasks.check_submodules(root, (tasks.PACKAGES[0],))
    with pytest.raises(ValueError, match="Local packages are missing"):
        tasks.check_submodules(root, tasks.PACKAGES)
