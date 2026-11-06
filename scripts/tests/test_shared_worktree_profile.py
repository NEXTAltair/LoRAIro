"""Opt-in shared-worktree profile: config shape, bootstrap restore/save and extras migration."""

import hashlib
import importlib
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
migration = importlib.import_module("migrate_container_codex")


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


posix_only = pytest.mark.skipif(os.name == "nt", reason="bootstrap.sh runs in the Linux container")


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


@posix_only
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


@posix_only
def test_restore_refuses_differing_existing_files_and_keeps_them(seeded) -> None:
    home, persist = seeded
    write(home / ".claude.json", b"different settings")
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 1
    assert "refusing to overwrite" in result.stderr
    assert (home / ".claude.json").read_bytes() == b"different settings"
    # 他の欠落ファイルは復元される
    assert (home / ".local/bin/herdr").is_file()


@posix_only
def test_restore_from_empty_volume_fails_instead_of_reporting_success(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    home.mkdir()
    persist.mkdir()
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 1
    assert result.stderr.count("required file not seeded") == 3
    assert not (home / ".local/bin/herdr").exists()


@posix_only
def test_intentional_fresh_container_may_opt_out_of_required_seeding(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    home.mkdir()
    persist.mkdir()
    env = dict(os.environ, HOME=str(home), LORAIRO_PERSIST_DIR=str(persist), LORAIRO_ALLOW_UNSEEDED="1")
    result = subprocess.run(
        ["bash", str(PROFILE / "bootstrap.sh"), "restore"], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0
    assert result.stdout.count("not seeded") == 4


@posix_only
def test_restore_never_replaces_symlinks_directories_or_special_files(seeded) -> None:
    home, persist = seeded
    (home / ".claude.json").symlink_to(home / "missing-target")  # 切れた symlink
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/herdr").mkdir()  # directory
    (home / ".ssh").mkdir()
    real = home / "real-keys"
    real.write_bytes(b"ssh-ed25519 AAAA test\n")  # 内容が同じでも symlink は置換しない
    (home / ".ssh/authorized_keys").symlink_to(real)
    result = bootstrap(home, persist, "restore")
    assert result.returncode == 1
    assert (home / ".claude.json").is_symlink() and not (home / ".claude.json").exists()
    assert (home / ".local/bin/herdr").is_dir()
    assert (home / ".ssh/authorized_keys").is_symlink()
    assert result.stderr.count("refusing to overwrite") == 3
    assert not list(home.rglob("*.??????"))  # temp が残らない


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX special file")
@posix_only
def test_restore_never_replaces_a_fifo(seeded) -> None:
    home, persist = seeded
    os.mkfifo(home / ".claude.json")
    assert bootstrap(home, persist, "restore").returncode == 1
    assert (home / ".claude.json").is_fifo()


@posix_only
def test_save_copies_live_files_and_keeps_previous_bytes_on_update(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    write(home / ".local/bin/herdr", b"herdr-0.9.3", 0o755)
    write(home / ".claude.json", b"v1")
    write(home / ".ssh/authorized_keys", b"key")
    first = bootstrap(home, persist, "save")
    assert first.returncode == 0, first.stderr
    assert (persist / "bin/herdr").read_bytes() == b"herdr-0.9.3"
    write(home / ".claude.json", b"v2")
    assert bootstrap(home, persist, "save").returncode == 0
    assert (persist / "claude.json").read_bytes() == b"v2"
    backups = list((persist / "backups").iterdir())
    assert [p.read_bytes() for p in backups] == [b"v1"]
    assert backups[0].stat().st_mode & 0o777 == 0o600
    write(home / ".local/bin/herdr", b"other", 0o755)
    result = bootstrap(home, persist, "save")
    assert result.returncode == 1
    assert (persist / "bin/herdr").read_bytes() == b"herdr-0.9.3"


@posix_only
def test_save_fails_when_a_required_live_file_is_missing(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    write(home / ".claude.json", b"v1")
    result = bootstrap(home, persist, "save")
    assert result.returncode == 1
    assert "required live file missing" in result.stderr


@posix_only
def test_known_hosts_is_optional_but_preserved_when_seeded(seeded) -> None:
    home, persist = seeded
    write(persist / "ssh/known_hosts", b"host key line\n", 0o644)
    assert bootstrap(home, persist, "restore").returncode == 0
    assert (home / ".ssh/known_hosts").read_bytes() == b"host key line\n"


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
            return done(json.dumps({p: p in self.files for p, _, _, _ in migration.SHARED_EXTRAS}))
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
    if os.name != "nt":  # Windows の保護 DACL は private_backup 側のテストで検証
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


def test_shared_extras_reject_missing_required_source_without_any_artifact(tmp_path, monkeypatch) -> None:
    files = dict(HOST_FILES)
    del files["/home/vscode/.local/bin/herdr"]
    fake = FakeDocker(files)
    monkeypatch.setattr(migration, "docker", fake)
    with pytest.raises(ValueError, match="Required shared extras missing"):
        migration.migrate_shared_extras("old", tmp_path / "backup")
    assert fake.volume == {}
    assert not (tmp_path / "backup" / "shared-extras.tar").exists()
    assert not (tmp_path / "backup" / "shared-extras-migration.json").exists()


def test_shared_extras_seed_optional_known_hosts_when_present(tmp_path, monkeypatch) -> None:
    fake = FakeDocker({**HOST_FILES, "/home/vscode/.ssh/known_hosts": b"hosts"})
    monkeypatch.setattr(migration, "docker", fake)
    migration.migrate_shared_extras("old", tmp_path / "backup")
    assert fake.volume["ssh/known_hosts"] == b"hosts"


@posix_only
@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a non-root POSIX user")
def test_save_with_unreadable_source_publishes_nothing_and_leaves_no_temp(tmp_path) -> None:
    home, persist = tmp_path / "home", tmp_path / "persist"
    write(home / ".local/bin/herdr", b"herdr", 0o755)
    write(home / ".claude.json", b"secret", 0o000)  # cp が失敗する
    write(home / ".ssh/authorized_keys", b"key")
    result = bootstrap(home, persist, "save")
    assert result.returncode == 1
    assert "could not save" in result.stderr
    assert not (persist / "claude.json").exists()  # 空/切り詰めファイルを公開しない
    assert [p.name for p in persist.rglob("*") if re.search(r"\.[A-Za-z0-9]{6}$", p.name)] == []
    (home / ".claude.json").chmod(0o600)


@posix_only
def test_install_new_never_links_into_a_destination_that_became_a_directory(tmp_path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"data")
    destination = tmp_path / "dest"
    destination.mkdir()
    script = f'source "{PROFILE / "bootstrap.sh"}"; set +e; install_new "{source}" "{destination}" 600; echo rc=$?'
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=dict(os.environ, HOME=str(tmp_path))
    )
    assert "rc=1" in result.stdout
    assert list(destination.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dest", "source"]


def test_with_shared_extras_aborts_before_any_codex_or_xdg_write_when_required_source_is_missing(
    tmp_path, monkeypatch
) -> None:
    files = dict(HOST_FILES)
    del files["/home/vscode/.ssh/authorized_keys"]
    fake = FakeDocker(files)
    monkeypatch.setattr(migration, "docker", fake)
    monkeypatch.setattr(
        migration, "migrate", lambda *a, **k: pytest.fail("Codex volume must stay untouched")
    )
    monkeypatch.setattr(
        migration, "migrate_xdg", lambda *a, **k: pytest.fail("XDG volumes must stay untouched")
    )
    with pytest.raises(ValueError, match="Required shared extras missing"):
        migration.main(["--container", "c", "--backup-dir", str(tmp_path / "b"), "--with-shared-extras"])
    assert not (tmp_path / "b").exists()
