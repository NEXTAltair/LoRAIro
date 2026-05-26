"""Maintain the hidden PR state marker used by the agent PR watcher."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MARKER_NAME = "agent-pr-maintainer"
MARKER_RE = re.compile(
    rf"<!--\s*{MARKER_NAME}\s*(?P<payload>\{{.*?\}})\s*-->",
    re.DOTALL,
)


@dataclass(frozen=True)
class AgentPrState:
    loop: int
    last_checked_head_sha: str
    last_reviewed_head_sha: str | None
    status: str


def extract_state(markdown: str) -> AgentPrState | None:
    match = MARKER_RE.search(markdown)
    if match is None:
        return None

    payload = json.loads(match.group("payload"))
    return AgentPrState(
        loop=int(payload.get("loop", 0)),
        last_checked_head_sha=str(payload["last_checked_head_sha"]),
        last_reviewed_head_sha=payload.get("last_reviewed_head_sha"),
        status=str(payload.get("status", "observing")),
    )


def render_marker(state: AgentPrState) -> str:
    payload = json.dumps(asdict(state), ensure_ascii=False, indent=2, sort_keys=True)
    return f"<!-- {MARKER_NAME}\n{payload}\n-->"


def upsert_state(markdown: str, state: AgentPrState) -> str:
    marker = render_marker(state)
    if MARKER_RE.search(markdown):
        return MARKER_RE.sub(marker, markdown, count=1)

    if not markdown.strip():
        return marker + "\n"

    return markdown.rstrip() + "\n\n" + marker + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _build_state(
    *,
    pr_state_path: Path,
    existing_body_path: Path,
    status: str,
    loop: int | None,
) -> AgentPrState:
    pr_state = _read_json(pr_state_path)
    body = existing_body_path.read_text(encoding="utf-8")
    existing_state = extract_state(body)

    head_sha = str(pr_state["headRefOid"])
    next_loop = loop if loop is not None else (existing_state.loop if existing_state is not None else 0)
    reviewed_sha = existing_state.last_reviewed_head_sha if existing_state is not None else None

    return AgentPrState(
        loop=next_loop,
        last_checked_head_sha=head_sha,
        last_reviewed_head_sha=reviewed_sha,
        status=status,
    )


def update_body(args: argparse.Namespace) -> int:
    body = Path(args.body_file).read_text(encoding="utf-8")
    state = _build_state(
        pr_state_path=Path(args.state_file),
        existing_body_path=Path(args.body_file),
        status=args.status,
        loop=args.loop,
    )
    Path(args.output).write_text(upsert_state(body, state), encoding="utf-8")
    return 0


def show(args: argparse.Namespace) -> int:
    body = Path(args.body_file).read_text(encoding="utf-8")
    state = extract_state(body)
    if state is None:
        return 1
    print(json.dumps(asdict(state), ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(required=True)

    update_parser = subparsers.add_parser("update-body")
    update_parser.add_argument("--body-file", required=True)
    update_parser.add_argument("--state-file", required=True)
    update_parser.add_argument("--output", required=True)
    update_parser.add_argument("--status", default="observing")
    update_parser.add_argument("--loop", type=int)
    update_parser.set_defaults(func=update_body)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--body-file", required=True)
    show_parser.set_defaults(func=show)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
