"""Legacy commands remain portable; destructive tests only use temporary fixtures."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import dev_tasks
import safe_cleanup

SPEC = importlib.util.spec_from_file_location("generate_ui", Path(__file__).parents[1] / "generate_ui.py")
ui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ui)


def test_uic_uses_current_interpreter_and_list_arguments(tmp_path, monkeypatch):
    source = tmp_path / "日本語 space.ui"
    source.touch()
    output = source.with_name(source.stem + "_ui.py")
    output.write_text("def setupUi(self, Window):\n    pass\n", encoding="utf-8")
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(ui.subprocess, "run", runner)
    assert ui.check_pyside6_uic()
    assert ui.generate_python_from_ui(source)
    command = runner.call_args.args[0]
    assert command[0] == sys.executable
    assert str(source) in command
    assert not runner.call_args.kwargs.get("shell", False)
    assert "Window: QWidget" in output.read_text(encoding="utf-8")


def test_clean_is_bounded_and_preview_does_not_delete(tmp_path):
    disposable = tmp_path / "src" / "app" / "__pycache__" / "example.pyc"
    preserved = [
        tmp_path / path
        for path in (
            ".venv/lib/__pycache__/keep.pyc",
            ".agents/worktree/demo/src/__pycache__/keep.pyc",
            "local_packages/example/__pycache__/keep.pyc",
            "lorairo_data/keep.pyc",
            "src/nested/__pycache__/keep.pyc",
            "src/env/__pycache__/keep.pyc",
            "build/repository/__pycache__/keep.pyc",
        )
    ]
    for path in [disposable, *preserved]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (tmp_path / "src/nested/.git").touch()
    (tmp_path / "src/env/pyvenv.cfg").touch()
    (tmp_path / "build/repository/.git").mkdir()
    safe_cleanup.clean(tmp_path, dry_run=True)
    assert disposable.exists()
    safe_cleanup.clean(tmp_path, dry_run=False)
    assert not disposable.exists()
    assert all(path.exists() for path in preserved)


def test_clean_does_not_follow_symlinks(tmp_path):
    external = tmp_path / "outside"
    external.mkdir()
    (external / "keep.pyc").touch()
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    try:
        (root / "src/__pycache__").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation requires Windows Developer Mode or privilege")
    safe_cleanup.clean(root, dry_run=False)
    assert (external / "keep.pyc").exists()


def test_rebuild_preserves_backup_on_install_failure(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / ".venv").mkdir()
    (root / ".venv/keep").touch()
    monkeypatch.setattr(safe_cleanup, "shared_root", lambda _: root)
    monkeypatch.setattr(safe_cleanup, "build_plan", lambda *args: [{"argv": ["uv", "sync"], "env": {}}])
    runner = Mock(return_value=subprocess.CompletedProcess([], 9))
    monkeypatch.setattr(safe_cleanup.subprocess, "run", runner)
    assert safe_cleanup.rebuild(root, {}, dry_run=True) == 0
    runner.assert_not_called()
    assert (root / ".venv/keep").exists()
    assert safe_cleanup.rebuild(root, {}, dry_run=False) == 9
    assert not (root / ".venv").exists()
    assert len(list(root.glob(".venv.backup-*/keep"))) == 1


def test_rebuild_rejects_worktree_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(safe_cleanup, "shared_root", lambda _: tmp_path / "main")
    with pytest.raises(ValueError, match="main checkout"):
        safe_cleanup.rebuild(tmp_path, {}, dry_run=False)
    assert not list(tmp_path.iterdir())


def test_documentation_commands_preserve_check_and_separate_arguments(tmp_path):
    plan = dev_tasks.documentation_commands("adr-okf", tmp_path)
    assert len(plan) == 3
    assert "--require" in plan[0]
    assert all(command[-1] == "--check" for command in plan[1:])
    assert "ADR,タイトル,日付,ステータス" in plan[1]
    assert "Architecture Decision Records" in plan[2]
    assert len(dev_tasks.documentation_commands("docs-okf", tmp_path)) == 1
