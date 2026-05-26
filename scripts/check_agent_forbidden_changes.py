"""Reject changes that automatic agent repair must not make."""

from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Iterable
from pathlib import PurePosixPath

WORKFLOW_RE = re.compile(r"^\.github/workflows/")
SECRET_PATH_RE = re.compile(
    r"(^|/)(\.env($|[./-])|env\.|secrets?($|[./_-])|credentials?($|[./_-])|\.?npmrc$|\.?pypirc$)",
    re.IGNORECASE,
)


def forbidden_reasons(paths: Iterable[str]) -> list[str]:
    reasons: list[str] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip()).as_posix()
        if not path:
            continue
        if WORKFLOW_RE.search(path):
            reasons.append(f"workflow changes are not allowed in automatic repair: {path}")
        if SECRET_PATH_RE.search(path):
            reasons.append(f"secret/env related changes require escalation: {path}")
    return reasons


def _changed_paths(base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    paths = args.paths if args.paths else _changed_paths(args.base_ref)
    reasons = forbidden_reasons(paths)
    if not reasons:
        print("No forbidden automatic-repair changes detected")
        return 0

    for reason in reasons:
        print(f"::error::{reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
