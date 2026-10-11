"""Portable Claude skill copies avoid OS-specific symlinks and NTFS junctions."""

import hashlib
from pathlib import Path

MANIFEST = ".lorairo-projections.json"


def ignored(relative: Path) -> bool:
    return any(part in {".git", "__pycache__"} for part in relative.parts) or relative.suffix == ".pyc"


def tree_digest(root: Path) -> str:
    """Hash the portable source files, rejecting links that would escape a skill."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ignored(relative):
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Skill projections cannot contain filesystem links: {relative}")
        if path.is_file():
            digest.update(relative.as_posix().encode("utf-8") + b"\0")
            content = path.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()
