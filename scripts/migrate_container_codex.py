"""Back up Linux Codex state and seed its new volume before a Dev Container rebuild.

Run on the Docker host after finishing agent work. Authentication is copied as opaque
bytes; this command never prints config, credentials, database rows or archive members.
"""

from __future__ import annotations

import argparse
import hashlib
import io
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


SHARED_EXTRAS = (
    # (コンテナ内パス, 永続ボリューム内パス, mode, 必須)
    ("/home/vscode/.local/bin/herdr", "bin/herdr", 0o755, True),
    ("/home/vscode/.claude.json", "claude.json", 0o600, True),
    ("/home/vscode/.ssh/authorized_keys", "ssh/authorized_keys", 0o600, True),
    ("/home/vscode/.ssh/known_hosts", "ssh/known_hosts", 0o644, False),
)


def preflight_shared_extras(container: str) -> dict[str, bool]:
    """Check that every required shared extra exists in the source before any volume is written."""
    check_sources = (
        "import json, pathlib; "
        f"print(json.dumps({{p: pathlib.Path(p).is_file() for p, _, _, _ in {SHARED_EXTRAS!r}}}))"
    )
    present: dict[str, bool] = json.loads(
        docker("exec", container, "python3", "-c", check_sources, capture_output=True, text=True).stdout
    )
    missing = [path for path, _, _, required in SHARED_EXTRAS if required and not present[path]]
    if missing:
        # 必須 source 欠落では成功 archive / manifest を作らない
        raise ValueError(f"Required shared extras missing in source container: {', '.join(missing)}")
    return present


def migrate_shared_extras(
    container: str,
    backup_dir: Path,
    volume: str = "lorairo-shared-persist",
    *,
    reuse_private_directory: bool = False,
) -> None:
    """Opt-in: seed the shared-worktree profile's persistent volume (Herdr, ~/.claude.json, authorized_keys).

    Files are copied as opaque bytes into a private tar, never printed. A nonempty destination volume
    (including a partial earlier attempt) is refused; the backup is always retained.
    """
    if reuse_private_directory:
        validate_private_directory(backup_dir)
    else:
        create_private_directory(backup_dir)
    info = json.loads(docker("inspect", container, capture_output=True, text=True).stdout)[0]
    if not info["State"]["Running"] or info["State"]["Paused"]:
        raise ValueError("Source container must be running and unpaused")
    present = preflight_shared_extras(container)
    archive = backup_dir / "shared-extras.tar"
    digests: dict[str, str] = {}
    with open_private_file(archive) as destination, tarfile.open(fileobj=destination, mode="w") as contents:
        for source_path, relative, mode, _ in SHARED_EXTRAS:
            if not present[source_path]:
                continue
            data = docker("exec", container, "cat", source_path, capture_output=True).stdout
            digests[relative] = hashlib.sha256(data).hexdigest()
            for parent in reversed(Path(relative).parents[:-1]):
                directory = tarfile.TarInfo(parent.as_posix())
                directory.type, directory.mode = tarfile.DIRTYPE, 0o700
                if parent.as_posix() not in contents.getnames():
                    contents.addfile(directory)
            member = tarfile.TarInfo(relative)
            member.size, member.mode = len(data), mode
            contents.addfile(member, io.BytesIO(data))
    restore = """
set -eu
if [ -n "$(ls -A /restore)" ]; then
    echo 'Destination shared persist volume is not empty; refusing to overwrite it.' >&2
    exit 1
fi
tar -xpf - -C /restore
chown -R 1000:1000 /restore
"""
    with archive.open("rb") as source:
        docker(
            "run",
            "--rm",
            "-i",
            "--user",
            "0",
            "--mount",
            f"source={volume},target=/restore,type=volume",
            "--entrypoint",
            "bash",
            info["Image"],
            "-c",
            restore,
            stdin=source,
        )
    verify = (
        "import hashlib, json, pathlib; "
        f"rel = {[r for _, r, _, _ in SHARED_EXTRAS]!r}; "
        "print(json.dumps({r: hashlib.sha256(pathlib.Path('/persist', r).read_bytes()).hexdigest() "
        "for r in rel if pathlib.Path('/persist', r).is_file()}))"
    )
    verified = json.loads(
        docker(
            "run",
            "--rm",
            "--mount",
            f"source={volume},target=/persist,type=volume,readonly",
            "--entrypoint",
            "python3",
            info["Image"],
            "-c",
            verify,
            capture_output=True,
            text=True,
        ).stdout
    )
    if verified != digests:
        raise ValueError("Shared extras verification failed; backup retained")
    with open_private_file(backup_dir / "shared-extras-migration.json") as destination:
        destination.write(
            (
                json.dumps({"container": container, "volume": volume, "seeded_sha256": digests}, indent=2)
                + "\n"
            ).encode("utf-8")
        )
    print(
        f"Shared-worktree extras seeded into volume {volume}: {len(digests)} file(s); contents not shown."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--volume", default="lorairo-codex-config")
    parser.add_argument(
        "--project-config",
        type=Path,
        help="Original project config, to retain only portable sandbox/inherit preferences",
    )
    extras = parser.add_mutually_exclusive_group()
    extras.add_argument(
        "--shared-extras-only",
        action="store_true",
        help="Opt-in: only seed the shared-worktree persist volume (Codex/XDG already live in named volumes)",
    )
    extras.add_argument(
        "--with-shared-extras",
        action="store_true",
        help="Opt-in: additionally seed the shared-worktree persist volume",
    )
    parser.add_argument("--shared-volume", default="lorairo-shared-persist")
    args = parser.parse_args(argv)
    if args.shared_extras_only:
        migrate_shared_extras(args.container, args.backup_dir, args.shared_volume)
        return
    if args.with_shared_extras:
        # Codex / XDG volume を書く前に必須 source を確認し、部分 migration を避ける
        preflight_shared_extras(args.container)
    migrate(args.container, args.backup_dir, args.volume, args.project_config)
    migrate_xdg(args.container, args.backup_dir, reuse_private_directory=True)
    if args.with_shared_extras:
        migrate_shared_extras(
            args.container, args.backup_dir, args.shared_volume, reuse_private_directory=True
        )


if __name__ == "__main__":
    main()
