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


def forbidden_reasons(paths: Iterable[str], *, allowed_workflow_paths: set[str] | None = None) -> list[str]:
    allowed_workflow_paths = allowed_workflow_paths or set()
    reasons: list[str] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip()).as_posix()
        if not path:
            continue
        if WORKFLOW_RE.search(path) and path not in allowed_workflow_paths:
            reasons.append(f"workflow changes are not allowed in automatic repair: {path}")
        if REPOSITORY_POLICY_RE.search(path):
            reasons.append(f"repository policy changes require escalation: {path}")
        if SECRET_PATH_RE.search(path):
            reasons.append(f"secret/env related changes require escalation: {path}")
    return reasons


def _paths_from_name_status(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            paths.extend([parts[1], parts[2]])
        else:
            paths.append(parts[-1])
    return paths


def _changed_paths(base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-status", "-M", f"{base_ref}...HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return _paths_from_name_status(result.stdout)


def _path_exists_at(ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _bootstrap_workflow_paths(
    base_ref: str, paths: Iterable[str], bootstrap_workflow: str | None
) -> set[str]:
    if bootstrap_workflow is None:
        return set()

    workflow_path = PurePosixPath(bootstrap_workflow).as_posix()
    changed_paths = {PurePosixPath(path).as_posix() for path in paths}
    if workflow_path not in changed_paths:
        return set()
    if _path_exists_at(base_ref, workflow_path):
        return set()
    if not _path_exists_at("HEAD", workflow_path):
        return set()
    return {workflow_path}


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
        help="PR body file containing the agent-pr-maintainer marker. Used for diagnostics only.",
    )
    parser.add_argument(
        "--bootstrap-workflow",
        help="Workflow path that may be introduced only when absent from the trusted base ref.",
    )
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    status = _marker_status(args.state_marker_body)
    paths = args.paths if args.paths else _changed_paths(args.base_ref)
    allowed_workflow_paths = _bootstrap_workflow_paths(args.base_ref, paths, args.bootstrap_workflow)
    reasons = forbidden_reasons(paths, allowed_workflow_paths=allowed_workflow_paths)
    if not reasons:
        if allowed_workflow_paths:
            print(
                "Allowing bootstrap workflow introduction from trusted base state: "
                + ", ".join(sorted(allowed_workflow_paths))
            )
        elif args.state_marker_body is not None:
            print(f"No forbidden changes detected for marker status: {status or 'absent'}")
        else:
            print("No forbidden automatic-repair changes detected")
        return 0

    for reason in reasons:
        print(f"::error::{reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
