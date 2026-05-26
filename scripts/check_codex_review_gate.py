"""Fail when Codex bot review artifacts contain blocking findings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BOT_LOGIN_RE = re.compile(r"(codex|chatgpt-codex|openai-codex)", re.IGNORECASE)
BLOCKING_BODY_RE = re.compile(
    r"\b(P0|P1|blocking|must\s+fix|changes?\s+requested|security\s+regression|risky\s+behavior)\b",
    re.IGNORECASE,
)
UNAVAILABLE_BODY_RE = re.compile(
    r"(to use codex here|create a codex account|connect to github|unable to run codex|codex.*not.*connected)",
    re.IGNORECASE,
)
APPROVAL_REACTIONS = {"+1", "hooray"}


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, list):
        raise ValueError(f"{path} must contain a JSON array")
    return [item for item in loaded if isinstance(item, dict)]


def _login_from(item: dict[str, Any]) -> str:
    user = item.get("user")
    if isinstance(user, dict):
        return str(user.get("login", ""))
    return str(item.get("author", {}).get("login", "")) if isinstance(item.get("author"), dict) else ""


def _is_bot_artifact(item: dict[str, Any]) -> bool:
    login = _login_from(item)
    return bool(BOT_LOGIN_RE.search(login))


def _body_from(item: dict[str, Any]) -> str:
    body = item.get("body")
    return body if isinstance(body, str) else ""


def _has_blocking_text(item: dict[str, Any]) -> bool:
    return bool(BLOCKING_BODY_RE.search(_body_from(item)))


def _is_unavailable_response(item: dict[str, Any]) -> bool:
    return bool(UNAVAILABLE_BODY_RE.search(_body_from(item)))


def _review_reasons(reviews: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    bot_artifact_seen = False
    reasons: list[str] = []
    for review in reviews:
        if not _is_bot_artifact(review):
            continue
        bot_artifact_seen = True
        state = str(review.get("state", "")).upper()
        if state == "CHANGES_REQUESTED":
            reasons.append(f"bot review requested changes: {_login_from(review)}")
        if _has_blocking_text(review):
            reasons.append(f"bot review body has blocking text: {_login_from(review)}")
    return bot_artifact_seen, reasons


def _comment_reasons(comments: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
    bot_artifact_seen = False
    reasons: list[str] = []
    unavailable_reasons: list[str] = []
    for comment in comments:
        if not _is_bot_artifact(comment):
            continue
        if _is_unavailable_response(comment):
            unavailable_reasons.append(f"Codex review did not run: {_login_from(comment)}")
            continue
        bot_artifact_seen = True
        if _has_blocking_text(comment):
            reasons.append(f"bot comment has blocking text: {_login_from(comment)}")
    return bot_artifact_seen, reasons, unavailable_reasons


def _has_approval_reaction(reactions: list[dict[str, Any]]) -> bool:
    return any(
        _is_bot_artifact(reaction) and str(reaction.get("content", "")) in APPROVAL_REACTIONS
        for reaction in reactions
    )


def evaluate(
    *,
    reviews: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    issue_comments: list[dict[str, Any]],
    reactions: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    review_artifact_seen, review_reasons = _review_reasons(reviews)
    comment_artifact_seen, comment_reasons, unavailable_reasons = _comment_reasons(
        [*review_comments, *issue_comments]
    )
    bot_artifact_seen = review_artifact_seen or comment_artifact_seen or _has_approval_reaction(reactions)
    reasons.extend(review_reasons)
    reasons.extend(comment_reasons)

    if not bot_artifact_seen:
        reasons.extend(sorted(set(unavailable_reasons)) or ["no Codex bot review artifact found"])

    return len(reasons) == 0, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--review-comments", required=True)
    parser.add_argument("--issue-comments", required=True)
    parser.add_argument("--reactions", required=True)
    args = parser.parse_args()

    ok, reasons = evaluate(
        reviews=_read_json_array(Path(args.reviews)),
        review_comments=_read_json_array(Path(args.review_comments)),
        issue_comments=_read_json_array(Path(args.issue_comments)),
        reactions=_read_json_array(Path(args.reactions)),
    )
    if ok:
        print("Codex review gate passed")
        return 0

    for reason in reasons:
        print(f"::error::{reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
