"""Back up Linux Codex state and seed its new volume before a Dev Container rebuild.

Run on the Docker host after finishing agent work. Authentication is copied as opaque
bytes; this command never prints config, credentials, database rows or archive members.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import tomllib
from pathlib import Path

from configure_agent_environment import migrate_codex_local_preferences
from private_backup import create_private_directory, open_private_file, validate_private_directory


def docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, **kwargs)


def preserve_project_preferences(image: str, volume: str, project_config: Path) -> bool:
    """Keep formerly active portable sandbox/inherit preferences, never project environment paths."""
    project = tomllib.loads(project_config.read_text(encoding="utf-8"))
    read_config = "import pathlib, sys; p=pathlib.Path('/home/vscode/.codex/config.toml'); sys.stdout.write(p.read_text() if p.is_file() else '')"
    original = docker(
        "run",
        "--rm",
        "--mount",
        f"source={volume},target=/home/vscode/.codex,type=volume,readonly",
        "--entrypoint",
        "python3",
        image,
        "-c",
        read_config,
        capture_output=True,
        text=True,
    ).stdout
    migrated = migrate_codex_local_preferences(original, project)
    if migrated == original:
        return False
    original_digest = hashlib.sha256(original.encode()).hexdigest()
    write_config = """
import hashlib, pathlib, sys
p = pathlib.Path('/home/vscode/.codex/config.toml')
original = p.read_bytes() if p.is_file() else b''
assert hashlib.sha256(original).hexdigest() == sys.argv[1], 'Linux config changed; refusing overwrite'
if original:
    backup = p.parent / 'lorairo-config-backups' / (sys.argv[1] + '-config.toml')
    backup.parent.mkdir(mode=0o700, exist_ok=True)
    if backup.exists():
        assert backup.read_bytes() == original, 'Existing backup differs'
    else:
        backup.write_bytes(original)
        backup.chmod(0o600)
p.write_bytes(sys.stdin.buffer.read())
p.chmod(0o600)
"""
    docker(
        "run",
        "--rm",
        "-i",
        "--user",
        "1000:1000",
        "--mount",
        f"source={volume},target=/home/vscode/.codex,type=volume",
        "--entrypoint",
        "python3",
        image,
        "-c",
        write_config,
        original_digest,
        input=migrated.encode(),
    )
    return True


def migrate(container: str, backup_dir: Path, volume: str, project_config: Path | None = None) -> None:
    create_private_directory(backup_dir)
    archive = backup_dir / "codex-linux.tar"
    info = json.loads(docker("inspect", container, capture_output=True, text=True).stdout)[0]
    if not info["State"]["Running"] or info["State"]["Paused"]:
        raise ValueError("Source container must be running and unpaused")
    if any(m["Destination"] == "/home/vscode/.codex" for m in info["Mounts"]):
        raise ValueError("Codex already has a mounted home; back up that volume instead")
    # Freeze the writers for the entire copy, including SQLite WAL/SHM files.
    with open_private_file(archive) as destination:
        docker("pause", container, stdout=subprocess.DEVNULL)
        try:
            docker("cp", f"{container}:/home/vscode/.codex", "-", stdout=destination)
        finally:
            docker("unpause", container, stdout=subprocess.DEVNULL)
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    with tarfile.open(archive) as contents:
        try:
            auth = contents.extractfile(".codex/auth.json")
        except KeyError:
            auth = None
        auth_digest = hashlib.file_digest(auth, "sha256").hexdigest() if auth else None
    # Refuse existing state, including a failed/partial earlier migration.
    restore = """
set -eu
if [ -n "$(ls -A /restore/.codex)" ]; then
    echo 'Destination Codex volume is not empty; refusing to overwrite it.' >&2
    exit 1
fi
tar -xpf - -C /restore
chown -R 1000:1000 /restore/.codex
chmod 700 /restore/.codex
"""
    with archive.open("rb") as source:
        docker(
            "run",
            "--rm",
            "-i",
            "--user",
            "0",
            "--mount",
            f"source={volume},target=/restore/.codex,type=volume",
            "--entrypoint",
            "bash",
            info["Image"],
            "-c",
            restore,
            stdin=source,
        )
    verify = """
import hashlib, pathlib
p = pathlib.Path('/home/vscode/.codex/auth.json')
print(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'absent')
"""
    verified = docker(
        "run",
        "--rm",
        "--mount",
        f"source={volume},target=/home/vscode/.codex,type=volume,readonly",
        "--entrypoint",
        "python3",
        info["Image"],
        "-c",
        verify,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if verified != (auth_digest or "absent"):
        raise ValueError("Credential migration verification failed; backup retained")
    preferences_migrated = (
        preserve_project_preferences(info["Image"], volume, project_config) if project_config else False
    )
    with open_private_file(backup_dir / "migration.json") as destination:
        destination.write(
            (
                json.dumps(
                    {
                        "container": container,
                        "volume": volume,
                        "archive_sha256": digest,
                        "credential_bytes_match": True,
                        "portable_project_preferences_migrated": preferences_migrated,
                    },
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
        )
    print("Linux Codex backup and volume migration verified; Windows Codex home was not accessed.")


def migrate_xdg(container: str, backup_dir: Path, *, reuse_private_directory: bool = False) -> None:
    """Retain GitHub/Qt preferences, caches and state which new XDG mounts would hide."""
    if reuse_private_directory:
        validate_private_directory(backup_dir)
    else:
        create_private_directory(backup_dir)
    info = json.loads(docker("inspect", container, capture_output=True, text=True).stdout)[0]
    domains = (
        ("/home/vscode/.config", ".config", "lorairo-linux-config"),
        ("/home/vscode/.cache", ".cache", "lorairo-linux-cache"),
        ("/home/vscode/.local/state", "state", "lorairo-linux-state"),
    )
    # Old images need not have created any XDG state or a legacy global Git config.
    source_paths = {path: "is_dir" for path, _, _ in domains}
    source_paths["/home/vscode/.gitconfig"] = "is_file"
    check_sources = (
        "import json, pathlib; "
        f"checks = {source_paths!r}; "
        "print(json.dumps({p: getattr(pathlib.Path(p), check)() for p, check in checks.items()}))"
    )
    present = json.loads(
        docker("exec", container, "python3", "-c", check_sources, capture_output=True, text=True).stdout
    )
    manifest = {}
    for path, basename, volume in domains:
        archive = backup_dir / f"linux-{basename.lstrip('.')}.tar"
        if present[path]:
            with open_private_file(archive) as destination:
                docker("pause", container, stdout=subprocess.DEVNULL)
                try:
                    docker("cp", f"{container}:{path}", "-", stdout=destination)
                finally:
                    docker("unpause", container, stdout=subprocess.DEVNULL)
        else:
            with open_private_file(archive) as destination, tarfile.open(fileobj=destination, mode="w"):
                pass
        with archive.open("rb") as source:
            manifest[volume] = hashlib.file_digest(source, "sha256").hexdigest()
        restore = f"""
set -eu
if [ -n "$(ls -A /restore/{basename})" ]; then
    echo 'Destination XDG volume is not empty; refusing to overwrite it.' >&2
    exit 1
fi
tar -xpf - -C /restore
chown -R 1000:1000 /restore/{basename}
"""
        with archive.open("rb") as source:
            docker(
                "run",
                "--rm",
                "-i",
                "--user",
                "0",
                "--mount",
                f"source={volume},target=/restore/{basename},type=volume",
                "--entrypoint",
                "bash",
                info["Image"],
                "-c",
                restore,
                stdin=source,
            )
    # Persist the old global Git config in XDG; never mix it with Windows Git settings.
    gitconfig = backup_dir / "linux.gitconfig"
    install_gitconfig = """
set -eu
mkdir -p /config/git
if [ -e /config/git/config ]; then
    echo 'Existing XDG Git config retained; old global config remains in the backup.' >&2
else
    cat > /config/git/config
    chown 1000:1000 /config/git /config/git/config
    chmod 600 /config/git/config
fi
"""
    if present["/home/vscode/.gitconfig"]:
        # Docker must never create a host destination using inherited permissions.
        with open_private_file(gitconfig) as destination:
            docker("exec", container, "cat", "/home/vscode/.gitconfig", stdout=destination)
        with gitconfig.open("rb") as source:
            docker(
                "run",
                "--rm",
                "-i",
                "--user",
                "0",
                "--mount",
                "source=lorairo-linux-config,target=/config,type=volume",
                "--entrypoint",
                "bash",
                info["Image"],
                "-c",
                install_gitconfig,
                stdin=source,
            )
    with open_private_file(backup_dir / "xdg-migration.json") as destination:
        destination.write((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print("Linux XDG settings, caches, state and global Git config backed up and migrated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--volume", default="lorairo-codex-config")
    parser.add_argument(
        "--project-config",
        type=Path,
        help="Original project config, to retain only portable sandbox/inherit preferences",
    )
    args = parser.parse_args()
    migrate(args.container, args.backup_dir, args.volume, args.project_config)
    migrate_xdg(args.container, args.backup_dir, reuse_private_directory=True)
