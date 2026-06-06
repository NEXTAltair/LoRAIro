#!/usr/bin/env python3
"""Remove clean, merged agent worktrees under /workspaces/LoRAIro/.agents/worktree."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

WORKTREE_ROOT = Path("/workspaces/LoRAIro/.agents/worktree")
DEFAULT_BASE = "origin/main"


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str | None
    branch: str | None


def run_git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def run_gh(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def parse_worktrees(output: str) -> list[Worktree]:
    worktrees: list[Worktree] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line:
            if current:
                worktrees.append(_worktree_from_record(current))
                current = {}
            continue

        key, _, value = line.partition(" ")
        current[key] = value

    if current:
        worktrees.append(_worktree_from_record(current))

    return worktrees


def _worktree_from_record(record: dict[str, str]) -> Worktree:
    branch_ref = record.get("branch")
    branch = branch_ref.removeprefix("refs/heads/") if branch_ref else None
    return Worktree(path=Path(record["worktree"]), head=record.get("HEAD"), branch=branch)


def has_local_changes(path: Path) -> bool:
    result = run_git(["status", "--porcelain"], cwd=path)
    return bool(result.stdout.strip())


def head_is_merged(worktree: Worktree, *, repo: Path, base: str) -> bool:
    if not worktree.head:
        return False

    result = run_git(["merge-base", "--is-ancestor", worktree.head, base], cwd=repo, check=False)
    return result.returncode == 0


def pr_is_merged(worktree: Worktree, *, repo: Path) -> bool:
    if not worktree.branch:
        return False

    result = run_gh(
        [
            "pr",
            "list",
            "--head",
            worktree.branch,
            "--state",
            "merged",
            "--json",
            "number,mergedAt",
            "--limit",
            "1",
        ],
        cwd=repo,
    )
    if result.returncode != 0:
        return False

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False

    return bool(prs)


def removable_reason(worktree: Worktree, *, repo: Path, base: str) -> str | None:
    if not worktree.path.is_relative_to(WORKTREE_ROOT):
        return None
    if not worktree.path.exists():
        return None
    if has_local_changes(worktree.path):
        return None
    if pr_is_merged(worktree, repo=repo):
        return "merged PR"
    if head_is_merged(worktree, repo=repo, base=base):
        return f"HEAD is ancestor of {base}"
    return None


def remove_worktree(worktree: Worktree, *, repo: Path, force: bool) -> subprocess.CompletedProcess[str]:
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree.path))
    return run_git(args, cwd=repo, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", default=DEFAULT_BASE, help=f"base ref used for ancestry checks (default: {DEFAULT_BASE})"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="list removable worktrees without deleting them"
    )
    parser.add_argument("--force", action="store_true", help="pass --force to git worktree remove")
    args = parser.parse_args()

    repo = Path(run_git(["rev-parse", "--show-toplevel"], cwd=Path.cwd()).stdout.strip())
    worktree_list = run_git(["worktree", "list", "--porcelain"], cwd=repo).stdout
    worktrees = parse_worktrees(worktree_list)

    matched = 0
    removed = 0
    for worktree in worktrees:
        reason = removable_reason(worktree, repo=repo, base=args.base)
        if reason is None:
            continue

        matched += 1
        branch = worktree.branch or "(detached)"
        if args.dry_run:
            print(f"would remove {worktree.path} [{branch}]: {reason}")
            continue

        result = remove_worktree(worktree, repo=repo, force=args.force)
        if result.returncode == 0:
            removed += 1
            print(f"removed {worktree.path} [{branch}]: {reason}")
        else:
            print(
                f"failed to remove {worktree.path} [{branch}]: {result.stderr.strip()}",
                file=sys.stderr,
            )

    if matched == 0:
        print("no clean merged worktrees found under /workspaces/LoRAIro/.agents/worktree")
        return 0
    elif args.dry_run:
        print(f"found {matched} removable worktree(s)")
        return 0

    print(f"removed {removed} merged worktree(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
