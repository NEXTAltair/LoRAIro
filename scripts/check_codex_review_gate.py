"""Fail when Codex bot review artifacts contain blocking findings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TRUSTED_BOT_LOGINS = {"chatgpt-codex-connector", "chatgpt-codex-connector[bot]"}
BLOCKING_BODY_RE = re.compile(
    r"\b(P0|P1|must\s+fix|security\s+regression|risky\s+behavior)\b|(?<!non-)\bblocking\b",
    re.IGNORECASE,
)
NEGATED_BLOCKING_RE = re.compile(
    r"\b(non-blocking|not\s+blocking|no\s+blocking|no\s+changes?\s+requested|no\s+P[01](\s+findings?)?)\b",
    re.IGNORECASE,
)
UNAVAILABLE_BODY_RE = re.compile(
    r"(to use codex here|create a codex account|connect to github|unable to run codex|codex.*not.*connected)",
    re.IGNORECASE,
)
APPROVAL_REACTIONS = {"+1", "hooray"}


def _flatten_json_items(loaded: Any) -> list[dict[str, Any]]:
    if not isinstance(loaded, list):
        raise ValueError("artifact JSON must be an array")

    items: list[dict[str, Any]] = []
    for item in loaded:
        if isinstance(item, list):
            items.extend(_flatten_json_items(item))
        elif isinstance(item, dict):
            items.append(item)
    return items


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return _flatten_json_items(json.load(handle))


def _login_from(item: dict[str, Any]) -> str:
    user = item.get("user")
    if isinstance(user, dict):
        return str(user.get("login", ""))
    return str(item.get("author", {}).get("login", "")) if isinstance(item.get("author"), dict) else ""


def _is_bot_artifact(item: dict[str, Any]) -> bool:
    return _login_from(item).lower() in TRUSTED_BOT_LOGINS


def _body_from(item: dict[str, Any]) -> str:
    body = item.get("body")
    return body if isinstance(body, str) else ""


def _has_blocking_text(item: dict[str, Any]) -> bool:
    body = _body_from(item)
    if NEGATED_BLOCKING_RE.search(body):
        return False
    if re.search(r"\bP[01]\b", body, re.IGNORECASE):
        return True
    return bool(BLOCKING_BODY_RE.search(body))


def _is_unavailable_response(item: dict[str, Any]) -> bool:
    return bool(UNAVAILABLE_BODY_RE.search(_body_from(item)))


def _commit_matches(item: dict[str, Any], head_sha: str | None) -> bool:
    if head_sha is None:
        return True

    commit = item.get("commit")
    commit_sha = commit.get("oid") if isinstance(commit, dict) else item.get("commit_id")
    if not isinstance(commit_sha, str) or not commit_sha:
        return False
    return commit_sha == head_sha or commit_sha.startswith(head_sha[:10])


def _submitted_at(item: dict[str, Any]) -> str:
    submitted_at = item.get("submittedAt")
    if isinstance(submitted_at, str):
        return submitted_at
    submitted_at = item.get("submitted_at")
    if isinstance(submitted_at, str):
        return submitted_at
    created_at = item.get("created_at")
    return created_at if isinstance(created_at, str) else ""


def _latest_bot_review(reviews: list[dict[str, Any]], head_sha: str | None) -> dict[str, Any] | None:
    matching_reviews = [
        review
        for review in reviews
        if _is_bot_artifact(review)
        and _commit_matches(review, head_sha)
        and str(review.get("state", "")).upper() != "DISMISSED"
    ]
    if not matching_reviews:
        return None
    return max(matching_reviews, key=_submitted_at)


def _review_reasons(reviews: list[dict[str, Any]], head_sha: str | None) -> tuple[bool, list[str]]:
    latest_review = _latest_bot_review(reviews, head_sha)
    if latest_review is None:
        return False, []

    reasons: list[str] = []
    state = str(latest_review.get("state", "")).upper()
    if state == "CHANGES_REQUESTED":
        reasons.append(f"bot review requested changes: {_login_from(latest_review)}")
    if _has_blocking_text(latest_review):
        reasons.append(f"bot review body has blocking text: {_login_from(latest_review)}")
    return True, reasons


def _comment_reasons(
    *,
    comments: list[dict[str, Any]],
    head_sha: str | None,
    require_head_match: bool,
) -> tuple[bool, list[str], list[str]]:
    bot_artifact_seen = False
    reasons: list[str] = []
    unavailable_reasons: list[str] = []
    for comment in comments:
        if not _is_bot_artifact(comment):
            continue
        if require_head_match and not _commit_matches(comment, head_sha):
            continue
        if _is_unavailable_response(comment):
            unavailable_reasons.append(f"Codex review did not run: {_login_from(comment)}")
            continue
        bot_artifact_seen = True
        if _has_blocking_text(comment):
            reasons.append(f"bot comment has blocking text: {_login_from(comment)}")
    return bot_artifact_seen, reasons, unavailable_reasons


def _has_approval_reaction(reactions: list[dict[str, Any]], head_sha: str | None) -> bool:
    if head_sha is not None:
        return False
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
    head_sha: str | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    review_artifact_seen, review_reasons = _review_reasons(reviews, head_sha)
    review_comment_artifact_seen, review_comment_reasons, _ = _comment_reasons(
        comments=review_comments,
        head_sha=head_sha,
        require_head_match=True,
    )
    issue_comment_artifact_seen, issue_comment_reasons, unavailable_reasons = _comment_reasons(
        comments=issue_comments,
        head_sha=head_sha,
        require_head_match=False,
    )
    bot_artifact_seen = (
        review_artifact_seen
        or review_comment_artifact_seen
        or (head_sha is None and issue_comment_artifact_seen)
        or _has_approval_reaction(reactions, head_sha)
    )
    reasons.extend(review_reasons)
    reasons.extend(review_comment_reasons)
    if head_sha is None:
        reasons.extend(issue_comment_reasons)

    if not bot_artifact_seen:
        reasons.extend(sorted(set(unavailable_reasons)) or ["no Codex bot review artifact found"])

    return len(reasons) == 0, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--review-comments", required=True)
    parser.add_argument("--issue-comments", required=True)
    parser.add_argument("--reactions", required=True)
    parser.add_argument("--head-sha")
    args = parser.parse_args()

    ok, reasons = evaluate(
        reviews=_read_json_array(Path(args.reviews)),
        review_comments=_read_json_array(Path(args.review_comments)),
        issue_comments=_read_json_array(Path(args.issue_comments)),
        reactions=_read_json_array(Path(args.reactions)),
        head_sha=args.head_sha,
    )
    if ok:
        print("Codex review gate passed")
        return 0

    for reason in reasons:
        print(f"::error::{reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
