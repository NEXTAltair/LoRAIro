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
from pathlib import Path


def docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, **kwargs)


def migrate(container: str, backup_dir: Path, volume: str) -> None:
    backup_dir.mkdir(parents=True, exist_ok=False)
    archive = backup_dir / "codex-linux.tar"
    info = json.loads(docker("inspect", container, capture_output=True, text=True).stdout)[0]
    if not info["State"]["Running"] or info["State"]["Paused"]:
        raise ValueError("Source container must be running and unpaused")
    if any(m["Destination"] == "/home/vscode/.codex" for m in info["Mounts"]):
        raise ValueError("Codex already has a mounted home; back up that volume instead")
    # Freeze the writers for the entire copy, including SQLite WAL/SHM files.
    docker("pause", container, stdout=subprocess.DEVNULL)
    try:
        with archive.open("xb") as destination:
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
    (backup_dir / "migration.json").write_text(
        json.dumps(
            {
                "container": container,
                "volume": volume,
                "archive_sha256": digest,
                "credential_bytes_match": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Linux Codex backup and volume migration verified; Windows Codex home was not accessed.")


def migrate_xdg(container: str, backup_dir: Path) -> None:
    """Retain GitHub/Qt preferences, caches and state which new XDG mounts would hide."""
    info = json.loads(docker("inspect", container, capture_output=True, text=True).stdout)[0]
    domains = (
        ("/home/vscode/.config", ".config", "lorairo-linux-config"),
        ("/home/vscode/.cache", ".cache", "lorairo-linux-cache"),
        ("/home/vscode/.local/state", "state", "lorairo-linux-state"),
    )
    manifest = {}
    for path, basename, volume in domains:
        archive = backup_dir / f"linux-{basename.lstrip('.')}.tar"
        docker("pause", container, stdout=subprocess.DEVNULL)
        try:
            with archive.open("xb") as destination:
                docker("cp", f"{container}:{path}", "-", stdout=destination)
        finally:
            docker("unpause", container, stdout=subprocess.DEVNULL)
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
    docker("cp", f"{container}:/home/vscode/.gitconfig", str(gitconfig))
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
    (backup_dir / "xdg-migration.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Linux XDG settings, caches, state and global Git config backed up and migrated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--volume", default="lorairo-codex-config")
    args = parser.parse_args()
    migrate(args.container, args.backup_dir, args.volume)
    migrate_xdg(args.container, args.backup_dir)
