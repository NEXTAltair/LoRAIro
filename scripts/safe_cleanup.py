"""Explicit, bounded artifact cleanup and recoverable main-environment rebuild."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from dev_tasks import ROOT, build_plan, shared_root

CACHES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def linked(path: Path) -> bool:
    """Do not follow Unix links or Windows junctions."""
    return path.is_symlink() or path.is_junction()


def artifacts(root: Path) -> list[Path]:
    """Only inspect app-owned source roots and named top-level build outputs."""
    root = root.resolve()
    found = []
    for name in sorted(CACHES | {"build", "dist", ".coverage", "coverage.xml"}):
        path = root / name
        if path.exists() and not linked(path):
            found.append(path)
    for name in ("src", "tests", "scripts"):
        start = root / name
        if (
            not start.is_dir()
            or linked(start)
            or (start / ".git").exists()
            or (start / "pyvenv.cfg").exists()
        ):
            continue
        for current, directories, files in os.walk(start, followlinks=False):
            directory = Path(current)
            retained = []
            for child in directories:
                path = directory / child
                if linked(path) or (path / ".git").exists() or (path / "pyvenv.cfg").exists():
                    continue
                if child in CACHES or child.endswith(".egg-info"):
                    found.append(path)
                elif child not in {".venv", "venv", ".git", ".agents", "node_modules"}:
                    retained.append(child)
            directories[:] = retained
            found.extend(directory / file for file in files if file.endswith(".pyc"))
    return [path for path in found if safe_tree(path)]


def safe_tree(path: Path) -> bool:
    """A cache containing a repository, environment or link is not disposable."""
    if linked(path):
        return False
    if path.is_dir():
        for current, directories, files in os.walk(path, followlinks=False):
            if ".git" in directories + files or "pyvenv.cfg" in files:
                return False
            if any(linked(Path(current) / name) for name in directories + files):
                return False
    return True


def clean(root: Path, *, dry_run: bool) -> None:
    for path in artifacts(root):
        # Revalidate immediately before deletion. Never cross a link boundary.
        relative = path.relative_to(root.resolve())
        if not safe_tree(path) or any(linked(root / parent) for parent in relative.parents):
            raise ValueError(f"Refusing linked cleanup target: {path}")
        print(f"{'Would remove' if dry_run else 'Removing'}: {relative}")
        if not dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def rebuild(root: Path, env: dict[str, str], *, dry_run: bool) -> int:
    root = root.resolve()
    if root != shared_root(root):
        raise ValueError("Rebuild is only allowed in the main checkout.")
    plan = build_plan("install-dev", root, env)
    venv = root / ".venv"
    if linked(venv):
        raise ValueError("Refusing to rebuild a linked .venv.")
    if Path(sys.executable).resolve().is_relative_to(venv.resolve()):
        raise ValueError("Use a system Python, not the environment being rebuilt.")
    backup = root / f".venv.backup-{uuid4().hex}"
    print(f"Existing environment will be preserved at {backup}; stop other environment users first.")
    if dry_run:
        return 0
    if venv.exists():
        venv.rename(backup)
    command = plan[0]
    result = subprocess.run(command["argv"], cwd=root, env={**env, **command["env"]}, check=False)
    if result.returncode:
        print(
            f"Install failed. Backup is preserved at {backup}; no automatic deletion or restore performed."
        )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("clean", "venv-rebuild"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.task == "clean":
            clean(ROOT, dry_run=args.dry_run)
            return 0
        return rebuild(ROOT, dict(os.environ), dry_run=args.dry_run)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cleanup error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
