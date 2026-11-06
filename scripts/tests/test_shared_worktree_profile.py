"""Opt-in shared-worktree profile: config shape, bootstrap restore/save and extras migration."""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / ".devcontainer" / "shared-worktree"
sys.path.insert(0, str(ROOT / "scripts"))
import migrate_container_codex as migration


def load_config(path: Path) -> dict:
    return json.loads(re.sub(r"^\s*//.*$", "", path.read_text(encoding="utf-8"), flags=re.M))


def test_profile_keeps_rw_workspace_and_unifies_uv_environment() -> None:
    config = load_config(PROFILE / "devcontainer.json")
    assert config["workspaceFolder"] == "/workspaces/LoRAIro"
    assert "readonly" not in config["workspaceMount"]
    assert config["containerEnv"]["UV_PROJECT_ENVIRONMENT"] == "/workspaces/LoRAIro/.venv"
    assert config["remoteEnv"]["UV_PROJECT_ENVIRONMENT"] == "/workspaces/LoRAIro/.venv"
    mounts = "\n".join(config["mounts"])
    assert "source=lorairo-venv,target=/workspaces/LoRAIro/.venv" in mounts
    assert "LoRAIro-linux" not in json.dumps(config)
    # 既存 named volume を再利用し、.local/bin 全体は volume 化しない
    for volume in ("lorairo-codex-config", "lorairo-claude-config", "lorairo-linux-config"):
        assert f"source={volume}," in mounts
    assert "target=/home/vscode/.local/bin" not in mounts


def test_profile_uses_feature_default_ssh_port_without_root_or_trust_changes() -> None:
    text = (PROFILE / "devcontainer.json").read_text(encoding="utf-8")
    config = load_config(PROFILE / "devcontainer.json")
    sshd = config["features"]["ghcr.io/devcontainers/features/sshd:1"]
    assert set(sshd) <= {"version", "gatewayPorts"}
    assert "2222:2222" in config["runArgs"]
    assert "StrictHostKeyChecking" not in text
    assert "10-val-port22" not in text
    command = config["postCreateCommand"]
    for forbidden in ("make setup", "uv sync", "git clone", "initialize-linux-workspace"):
        assert forbidden not in command


def test_default_profile_is_unchanged() -> None:
    default = (ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
    assert "readonly" in default
    assert '"workspaceFolder": "/workspaces/LoRAIro-linux"' in default
    assert "shared-worktree" not in default


def bootstrap(home: Path, persist: Path, mode: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), LORAIRO_PERSIST_DIR=str(persist))
    return subprocess.run(
        ["bash", str(PROFILE / "bootstrap.sh"), mode], capture_output=True, text=True, env=env
    )


def write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


@pytest.fixture
def seeded(tmp_path):
    home, persist = tmp_path / "home", tmp_path / "persist"
    home.mkdir()
    write(persist / "bin/herdr", b"\x00herdr-binary\xff", 0o755)
    write(persist / "claude.json", b'{"opaque": true}')
    write(persist / "ssh/authorized_keys", b"ssh-ed25519 AAAA test\n")
    return home, persist


def test_restore_into_new_container_keeps_bytes_and_modes(seeded) -> None:
    home, persist = seeded
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 0, result.stderr
    assert (home / ".local/bin/herdr").read_bytes() == b"\x00herdr-binary\xff"
    assert os.access(home / ".local/bin/herdr", os.X_OK)
    assert (home / ".claude.json").read_bytes() == b'{"opaque": true}'
    assert (home / ".ssh/authorized_keys").stat().st_mode & 0o777 == 0o600
    assert "AAAA" not in result.stdout + result.stderr
    # 再実行は冪等
    assert bootstrap(home, persist, "restore").returncode == 0


def test_restore_refuses_differing_existing_files_and_keeps_them(seeded) -> None:
    home, persist = seeded
    write(home / ".claude.json", b"different settings")
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 1
    assert "refusing to overwrite" in result.stderr
    assert (home / ".claude.json").read_bytes() == b"different settings"
    # 他の欠落ファイルは復元される
    assert (home / ".local/bin/herdr").is_file()


def test_restore_with_unseeded_volume_skips_without_failing(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    home.mkdir()
    persist.mkdir()
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 0
    assert result.stdout.count("not seeded") == 3
    assert not (home / ".claude.json").exists()


def test_save_copies_live_files_and_refuses_to_replace_a_different_herdr(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    write(home / ".local/bin/herdr", b"herdr-0.9.3", 0o755)
    write(home / ".claude.json", b"v1")
    assert bootstrap(home, persist, "save").returncode == 0
    assert (persist / "bin/herdr").read_bytes() == b"herdr-0.9.3"
    write(home / ".claude.json", b"v2")  # 設定は更新を保存する
    assert bootstrap(home, persist, "save").returncode == 0
    assert (persist / "claude.json").read_bytes() == b"v2"
    write(home / ".local/bin/herdr", b"other", 0o755)
    result = bootstrap(home, persist, "save")
    assert result.returncode == 1
    assert (persist / "bin/herdr").read_bytes() == b"herdr-0.9.3"


class FakeDocker:
    """Docker 呼び出しの最小模擬。ボリューム内容は辞書で保持する。"""

    def __init__(self, files: dict[str, bytes], volume: dict[str, bytes] | None = None, running=True):
        self.files, self.volume, self.running = files, volume or {}, running
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)

        def done(out=""):
            return subprocess.CompletedProcess(args, 0, out)

        if args[0] == "inspect":
            state = {"Running": self.running, "Paused": False}
            return done(json.dumps([{"Image": "img", "State": state}]))
        assert args[0] in {"exec", "run"}, f"unexpected docker command {args[0]}"
        if args[0] == "exec" and args[2] == "python3":
            return done(json.dumps({p: p in self.files for p, _, _ in migration.SHARED_EXTRAS}))
        if args[0] == "exec":
            return subprocess.CompletedProcess(args, 0, self.files[args[3]])
        if "readonly" in " ".join(args):
            return done(json.dumps({k: hashlib.sha256(v).hexdigest() for k, v in self.volume.items()}))
        if self.volume:
            raise subprocess.CalledProcessError(1, args)
        with tarfile.open(fileobj=io.BytesIO(kwargs["stdin"].read())) as archive:
            for member in archive:
                if member.isfile():
                    self.volume[member.name] = archive.extractfile(member).read()
        return done()


HOST_FILES = {
    "/home/vscode/.local/bin/herdr": b"\x00opaque-binary\xfe",
    "/home/vscode/.claude.json": b'{"secret": "do-not-print"}',
    "/home/vscode/.ssh/authorized_keys": b"ssh-ed25519 AAAA\n",
}


def test_shared_extras_seed_opaque_bytes_without_printing_them(tmp_path, monkeypatch, capsys) -> None:
    fake = FakeDocker(dict(HOST_FILES))
    monkeypatch.setattr(migration, "docker", fake)
    migration.migrate_shared_extras("old", tmp_path / "backup")
    assert fake.volume == {
        "bin/herdr": b"\x00opaque-binary\xfe",
        "claude.json": b'{"secret": "do-not-print"}',
        "ssh/authorized_keys": b"ssh-ed25519 AAAA\n",
    }
    assert not any(c[0] in {"pause", "unpause", "cp"} for c in fake.calls)
    output = capsys.readouterr()
    assert "do-not-print" not in output.out + output.err
    manifest = (tmp_path / "backup" / "shared-extras-migration.json").read_text()
    assert "do-not-print" not in manifest
    for path in (tmp_path / "backup").iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_shared_extras_refuse_nonempty_volume_and_keep_backup(tmp_path, monkeypatch) -> None:
    fake = FakeDocker(dict(HOST_FILES), volume={"claude.json": b"existing"})
    monkeypatch.setattr(migration, "docker", fake)
    with pytest.raises(subprocess.CalledProcessError):
        migration.migrate_shared_extras("old", tmp_path / "backup")
    assert fake.volume == {"claude.json": b"existing"}
    assert (tmp_path / "backup" / "shared-extras.tar").is_file()
    assert not (tmp_path / "backup" / "shared-extras-migration.json").exists()


def test_shared_extras_reject_stopped_source_before_any_write(tmp_path, monkeypatch) -> None:
    fake = FakeDocker(dict(HOST_FILES), running=False)
    monkeypatch.setattr(migration, "docker", fake)
    with pytest.raises(ValueError, match="running"):
        migration.migrate_shared_extras("old", tmp_path / "backup")
    assert [c[0] for c in fake.calls] == ["inspect"]


def test_default_cli_flow_does_not_touch_shared_extras(tmp_path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(migration, "migrate", lambda *a, **k: calls.append("codex"))
    monkeypatch.setattr(migration, "migrate_xdg", lambda *a, **k: calls.append("xdg"))
    monkeypatch.setattr(migration, "migrate_shared_extras", lambda *a, **k: calls.append("extras"))
    base = ["--container", "c", "--backup-dir", str(tmp_path / "b")]
    migration.main(base)
    assert calls == ["codex", "xdg"]
    calls.clear()
    migration.main([*base, "--shared-extras-only"])
    assert calls == ["extras"]
    calls.clear()
    migration.main([*base, "--with-shared-extras"])
    assert calls == ["codex", "xdg", "extras"]
