"""Reject changes that automatic agent repair must not make."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import PurePosixPath

WORKFLOW_RE = re.compile(r"^\.github/workflows/")
REPOSITORY_POLICY_RE = re.compile(
    r"^\.github/(rulesets/|branch-protection|settings\.ya?ml$|CODEOWNERS$)",
    re.IGNORECASE,
)
SECRET_PATH_RE = re.compile(
    r"(^|/)(\.env($|[./-])|env\.|secrets?($|[./_-])|credentials?($|[./_-])|\.?npmrc$|\.?pypirc$)",
    re.IGNORECASE,
)
MARKER_RE = re.compile(r"<!--\s*agent-pr-maintainer\s*(?P<payload>\{.*?\})\s*-->", re.DOTALL)


def forbidden_reasons(paths: Iterable[str]) -> list[str]:
    reasons: list[str] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip()).as_posix()
        if not path:
            continue
        if WORKFLOW_RE.search(path):
            reasons.append(f"workflow changes are not allowed in automatic repair: {path}")
        if REPOSITORY_POLICY_RE.search(path):
            reasons.append(f"repository policy changes require escalation: {path}")
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


def _marker_status(body_file: str | None) -> str | None:
    if body_file is None:
        return None

    with open(body_file, encoding="utf-8") as handle:
        body = handle.read()
    match = MARKER_RE.search(body)
    if match is None:
        return None

    payload = json.loads(match.group("payload"))
    status = payload.get("status")
    return status if isinstance(status, str) else None


def should_enforce_for_status(status: str | None) -> bool:
    return status == "repairing"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--state-marker-body",
        help="PR body file containing the agent-pr-maintainer marker. If provided, enforce only in repairing state.",
    )
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    status = _marker_status(args.state_marker_body)
    if args.state_marker_body is not None and not should_enforce_for_status(status):
        print(f"Skipping forbidden automatic-repair check for marker status: {status or 'absent'}")
        return 0

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
