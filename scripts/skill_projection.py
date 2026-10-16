"""Portable Claude skill copies avoid OS-specific symlinks and NTFS junctions."""

import hashlib
from pathlib import Path

MANIFEST = ".lorairo-projections.json"


def linux_reparse_link(path: Path) -> bool:
    """Windows does not report WSL-created LX symlinks as normal symlinks."""
    try:
        return getattr(path.lstat(), "st_reparse_tag", 0) == 0xA000001D
    except FileNotFoundError:
        return False


def filesystem_link(path: Path) -> bool:
    return linux_reparse_link(path) or path.is_symlink() or path.is_junction()


def ignored(relative: Path) -> bool:
    return any(part in {".git", "__pycache__"} for part in relative.parts) or relative.suffix == ".pyc"


def tree_digest(root: Path) -> str:
    """Hash the portable source files, rejecting links that would escape a skill."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ignored(relative):
            continue
        if filesystem_link(path):
            raise ValueError(f"Skill projections cannot contain filesystem links: {relative}")
        if path.is_file():
            digest.update(relative.as_posix().encode("utf-8") + b"\0")
            content = path.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()
