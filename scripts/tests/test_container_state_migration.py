"""Optional old container state and portable preferences survive migration."""

import base64
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrate_container_codex as migration
import private_backup


def assert_private_stream(destination):
    """Inspect the descriptor at Docker's first write, before any fixture bytes."""
    assert destination.tell() == 0
    if os.name == "nt":
        import msvcrt

        private_backup._windows_security().verify_handle(
            msvcrt.get_osfhandle(destination.fileno()), directory=False
        )
    else:
        assert stat.S_IMODE(os.fstat(destination.fileno()).st_mode) == 0o600


def run_windows_script(path, script):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    environment = dict(os.environ, LORAIRO_PRIVATE_TEST_PATH=str(path))
    environment.pop("PSModulePath", None)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    ).stdout


def windows_acl(path):
    """Independently inspect the native DACL on safe test paths, with no credentials."""
    return json.loads(
        run_windows_script(
            path,
            """
$p = $env:LORAIRO_PRIVATE_TEST_PATH
$a = if ([System.IO.Directory]::Exists($p)) {
  [System.IO.Directory]::GetAccessControl($p)
} else { [System.IO.File]::GetAccessControl($p) }
$sidType = [System.Security.Principal.SecurityIdentifier]
@{
  owner = $a.GetOwner($sidType).Value
  user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
  protected = $a.AreAccessRulesProtected
  rules = @($a.GetAccessRules($true, $true, $sidType) | ForEach-Object {
    @{ sid = $_.IdentityReference.Value; inherited = $_.IsInherited;
       rights = [int]$_.FileSystemRights; type = $_.AccessControlType.ToString() }
  })
} | ConvertTo-Json -Compress -Depth 4
""",
        )
    )


def assert_private_path(path, *, directory=False):
    if os.name == "nt":
        acl = windows_acl(path)
        assert acl["owner"] == acl["user"]
        assert acl["protected"]
        assert acl["rules"] == [
            {"sid": acl["user"], "inherited": False, "rights": 0x001F01FF, "type": "Allow"}
        ]
    else:
        info = path.lstat()
        assert info.st_uid == os.getuid()
        assert stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)


def test_absent_xdg_domains_create_empty_archives_without_copy_or_pause(tmp_path, monkeypatch):
    backup = tmp_path / "backup"
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
    migration.migrate_xdg("old", backup)
    assert len(restored) == 3
    assert len(json.loads((backup / "xdg-migration.json").read_text())) == 3
    assert not (backup / "linux.gitconfig").exists()
    for path in backup.iterdir():
        assert_private_path(path)


def test_private_creation_precedes_fixture_bytes_and_refuses_existing_paths(tmp_path):
    backup = tmp_path / "private backup 日本語"
    private_backup.create_private_directory(backup)
    assert_private_path(backup, directory=True)
    with pytest.raises(FileExistsError):
        private_backup.create_private_directory(backup)
    output = backup / "archive.tar"
    with private_backup.open_private_file(output) as destination:
        assert_private_stream(destination)
        destination.write(b"opaque test state")
    assert_private_path(output)
    with pytest.raises(FileExistsError):
        private_backup.open_private_file(output)
    assert output.read_bytes() == b"opaque test state"


@pytest.mark.skipif(os.name == "nt", reason="POSIX umask/mode contract")
def test_posix_umask_022_never_exposes_created_backup_bytes(tmp_path):
    previous = os.umask(0o022)
    try:
        backup = tmp_path / "backup"
        private_backup.create_private_directory(backup)
        assert_private_path(backup, directory=True)
        with private_backup.open_private_file(backup / "copied") as destination:
            assert_private_stream(destination)
            destination.write(b"test state")
        assert_private_path(backup / "copied")
    finally:
        os.umask(previous)


def test_existing_backup_directory_refused_before_docker(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(migration, "docker", lambda *a, **k: called.append(a))
    with pytest.raises(FileExistsError):
        migration.migrate("old", tmp_path, "new-volume")
    with pytest.raises(FileExistsError):
        migration.migrate_xdg("old", tmp_path)
    assert called == []


def test_privacy_creation_failure_stops_before_docker(tmp_path, monkeypatch):
    def denied(_path):
        raise PermissionError("Unsupported private storage")

    monkeypatch.setattr(migration, "create_private_directory", denied)
    monkeypatch.setattr(migration, "docker", lambda *a, **k: pytest.fail("Docker must not run"))
    for call in (
        lambda: migration.migrate("old", tmp_path / "new", "new-volume"),
        lambda: migration.migrate_xdg("old", tmp_path / "new"),
    ):
        with pytest.raises(PermissionError):
            call()


def test_file_privacy_failure_stops_before_pause_or_copy(tmp_path, monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args[0])
        assert args[0] == "inspect"
        return subprocess.CompletedProcess(
            args, 0, '[{"State":{"Running":true,"Paused":false},"Mounts":[]}]'
        )

    def denied(_path):
        raise PermissionError("Private file creation failed")

    monkeypatch.setattr(migration, "docker", docker)
    monkeypatch.setattr(migration, "open_private_file", denied)
    with pytest.raises(PermissionError):
        migration.migrate("old", tmp_path / "backup", "new-volume")
    assert calls == ["inspect"]


def test_reuse_refuses_directory_links_before_copy(tmp_path):
    target = tmp_path / "target"
    private_backup.create_private_directory(target)
    link = tmp_path / "link"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True
        )
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(PermissionError):
        private_backup.open_private_file(link / "config")
    assert not (target / "config").exists()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows ACL rejection")
def test_windows_reuse_refuses_broad_dacl_before_docker(tmp_path, monkeypatch):
    backup = tmp_path / "backup"
    private_backup.create_private_directory(backup)
    run_windows_script(
        backup,
        """
$p = $env:LORAIRO_PRIVATE_TEST_PATH
$a = [System.IO.Directory]::GetAccessControl($p)
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
  [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
  [System.Security.AccessControl.FileSystemRights]::Read,
  [System.Security.AccessControl.InheritanceFlags]::None,
  [System.Security.AccessControl.PropagationFlags]::None,
  [System.Security.AccessControl.AccessControlType]::Allow)
$a.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($p, $a)
""",
    )
    monkeypatch.setattr(migration, "docker", lambda *a, **k: pytest.fail("Docker must not run"))
    with pytest.raises(PermissionError):
        migration.migrate_xdg("old", backup, reuse_private_directory=True)
    assert list(backup.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Native Windows fail-closed creation")
def test_windows_unverifiable_file_is_closed_without_writing(tmp_path, monkeypatch):
    backup = tmp_path / "backup"
    private_backup.create_private_directory(backup)
    security = private_backup._windows_security()
    verify = security.verify_handle

    def denied(handle, *, directory):
        if directory:
            return verify(handle, directory=True)
        raise PermissionError("Filesystem did not enforce the security descriptor")

    monkeypatch.setattr(security, "verify_handle", denied)
    with pytest.raises(PermissionError):
        private_backup.open_private_file(backup / "config")
    # Opening/removing the empty file also proves no native HANDLE was leaked.
    output = backup / "config"
    assert output.read_bytes() == b""
    output.unlink()


def test_codex_and_xdg_docker_streams_are_private_before_copy(tmp_path, monkeypatch):
    backup = tmp_path / "backup"
    payload = b"test-only-credential-placeholder"
    credential_digest = hashlib.sha256(payload).hexdigest()
    copied = []

    def docker(*args, **kwargs):
        if args[0] == "inspect":
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    [{"Image": "test-image", "State": {"Running": True, "Paused": False}, "Mounts": []}]
                ),
            )
        if args[0] in ("pause", "unpause"):
            return subprocess.CompletedProcess(args, 0)
        if args[0] == "exec" and args[2] == "python3":
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "/home/vscode/.config": True,
                        "/home/vscode/.cache": True,
                        "/home/vscode/.local/state": True,
                        "/home/vscode/.gitconfig": True,
                    }
                ),
            )
        if args[0] == "cp" or (args[0] == "exec" and args[2] == "cat"):
            assert_private_path(backup, directory=True)
            destination = kwargs["stdout"]
            assert_private_stream(destination)
            if args[0] == "cp":
                assert args[-1] == "-", "Docker must write only through the private stream"
                member = ".codex/auth.json" if ".codex" in args[1] else "test-state"
                with tarfile.open(fileobj=destination, mode="w") as archive:
                    info = tarfile.TarInfo(member)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
            else:
                destination.write(b"[user]\nname = fixture\n")
            copied.append(args)
            return subprocess.CompletedProcess(args, 0)
        assert args[0] == "run"
        return subprocess.CompletedProcess(
            args, 0, credential_digest if kwargs.get("capture_output") else None
        )

    monkeypatch.setattr(migration, "docker", docker)
    migration.migrate("old", backup, "new-volume")
    migration.migrate_xdg("old", backup, reuse_private_directory=True)
    assert len(copied) == 5
    assert_private_path(backup, directory=True)
    for path in backup.iterdir():
        assert_private_path(path)
    assert (backup / "linux.gitconfig").read_bytes() == b"[user]\nname = fixture\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX reusing directory validation")
def test_xdg_reuse_refuses_broad_permissions_before_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "docker", lambda *a, **k: pytest.fail("Docker must not run"))
    tmp_path.chmod(0o755)
    with pytest.raises(PermissionError):
        migration.migrate_xdg("old", tmp_path, reuse_private_directory=True)


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
