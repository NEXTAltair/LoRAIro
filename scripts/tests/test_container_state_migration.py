"""Optional old container state and portable preferences survive migration."""

import json
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrate_container_codex as migration


def test_absent_xdg_domains_create_empty_archives_without_copy_or_pause(tmp_path, monkeypatch):
    restored = []

    def docker(*args, **kwargs):
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, '[{"Image":"test-image"}]')
        if args[0] == "exec":
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "/home/vscode/.config": False,
                        "/home/vscode/.cache": False,
                        "/home/vscode/.local/state": False,
                        "/home/vscode/.gitconfig": False,
                    }
                ),
            )
        assert args[0] == "run", "Missing sources must never be copied or paused"
        with tarfile.open(fileobj=kwargs["stdin"]) as archive:
            assert archive.getnames() == []
        restored.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(migration, "docker", docker)
    migration.migrate_xdg("old", tmp_path)
    assert len(restored) == 3
    assert len(json.loads((tmp_path / "xdg-migration.json").read_text())) == 3
    assert not (tmp_path / "linux.gitconfig").exists()


def test_project_preferences_retain_linux_environment_without_copying_windows_paths(tmp_path, monkeypatch):
    project = tmp_path / "old-project.toml"
    project.write_text(
        'sandbox_mode = "danger-full-access"\n[shell_environment_policy]\ninherit = "all"\n'
        '[shell_environment_policy.set]\nUV_PROJECT_ENVIRONMENT = "H:/Windows/.venv"\n',
        encoding="utf-8",
    )
    original = (
        'model = "personal"\n[shell_environment_policy.set]\nUV_PROJECT_ENVIRONMENT = "/linux/.venv"\n'
    )
    writes = []

    def docker(*args, **kwargs):
        assert args[0] == "run"
        if kwargs.get("capture_output"):
            assert any(item.endswith("readonly") for item in args)
            return subprocess.CompletedProcess(args, 0, original)
        writes.append(tomllib.loads(kwargs["input"].decode()))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(migration, "docker", docker)
    assert migration.preserve_project_preferences("image", "linux-volume", project)
    assert writes[0]["model"] == "personal"
    assert writes[0]["sandbox_mode"] == "danger-full-access"
    assert writes[0]["shell_environment_policy"]["inherit"] == "all"
    assert writes[0]["shell_environment_policy"]["set"]["UV_PROJECT_ENVIRONMENT"] == "/linux/.venv"
