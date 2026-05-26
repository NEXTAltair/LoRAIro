from __future__ import annotations

from helpers import load_script_module

evaluate = load_script_module("check_codex_review_gate").evaluate


def test_gate_passes_for_clean_codex_approval_reaction() -> None:
    ok, reasons = evaluate(
        reviews=[],
        review_comments=[],
        issue_comments=[],
        reactions=[{"user": {"login": "chatgpt-codex-connector[bot]"}, "content": "+1"}],
    )

    assert ok
    assert reasons == []


def test_gate_fails_without_bot_artifact() -> None:
    ok, reasons = evaluate(reviews=[], review_comments=[], issue_comments=[], reactions=[])

    assert not ok
    assert reasons == ["no Codex bot review artifact found"]


def test_gate_fails_for_codex_changes_requested_review() -> None:
    ok, reasons = evaluate(
        reviews=[{"user": {"login": "chatgpt-codex-connector[bot]"}, "state": "CHANGES_REQUESTED"}],
        review_comments=[],
        issue_comments=[],
        reactions=[],
    )

    assert not ok
    assert reasons == ["bot review requested changes: chatgpt-codex-connector[bot]"]


def test_gate_fails_for_blocking_codex_comment() -> None:
    ok, reasons = evaluate(
        reviews=[],
        review_comments=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "body": "P1: missing regression test for this path.",
            }
        ],
        issue_comments=[],
        reactions=[],
    )

    assert not ok
    assert reasons == ["bot comment has blocking text: chatgpt-codex-connector[bot]"]


def test_gate_fails_when_codex_connector_is_unavailable() -> None:
    ok, reasons = evaluate(
        reviews=[],
        review_comments=[],
        issue_comments=[
            {
                "user": {"login": "chatgpt-codex-connector"},
                "body": "To use Codex here, create a Codex account and connect to github.",
            }
        ],
        reactions=[],
    )

    assert not ok
    assert reasons == ["Codex review did not run: chatgpt-codex-connector"]


def test_gate_ignores_stale_unavailable_comment_after_clean_review() -> None:
    ok, reasons = evaluate(
        reviews=[{"user": {"login": "chatgpt-codex-connector[bot]"}, "state": "COMMENTED"}],
        review_comments=[],
        issue_comments=[
            {
                "user": {"login": "chatgpt-codex-connector"},
                "body": "To use Codex here, create a Codex account and connect to github.",
            }
        ],
        reactions=[],
    )

    assert ok
    assert reasons == []


def test_gate_ignores_untrusted_codex_named_account_reaction() -> None:
    ok, reasons = evaluate(
        reviews=[],
        review_comments=[],
        issue_comments=[],
        reactions=[{"user": {"login": "random-codex-user"}, "content": "+1"}],
    )

    assert not ok
    assert reasons == ["no Codex bot review artifact found"]


def test_gate_uses_latest_bot_review_for_current_head() -> None:
    ok, reasons = evaluate(
        reviews=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "state": "CHANGES_REQUESTED",
                "submittedAt": "2026-05-26T01:00:00Z",
                "commit": {"oid": "abc123"},
            },
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "state": "COMMENTED",
                "submittedAt": "2026-05-26T02:00:00Z",
                "commit": {"oid": "def456"},
            },
        ],
        review_comments=[],
        issue_comments=[],
        reactions=[],
        head_sha="def456",
    )

    assert ok
    assert reasons == []


def test_gate_ignores_review_comments_from_old_head() -> None:
    ok, reasons = evaluate(
        reviews=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "state": "COMMENTED",
                "submittedAt": "2026-05-26T02:00:00Z",
                "commit": {"oid": "def456"},
            }
        ],
        review_comments=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "body": "P1: old finding.",
                "commit_id": "abc123",
            }
        ],
        issue_comments=[],
        reactions=[],
        head_sha="def456",
    )

    assert ok
    assert reasons == []


def test_gate_does_not_block_negated_phrase() -> None:
    ok, reasons = evaluate(
        reviews=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "state": "COMMENTED",
                "body": "No changes requested. This is a non-blocking suggestion.",
            }
        ],
        review_comments=[],
        issue_comments=[],
        reactions=[],
    )

    assert ok
    assert reasons == []


def test_gate_does_not_accept_issue_comment_as_current_head_review() -> None:
    ok, reasons = evaluate(
        reviews=[],
        review_comments=[],
        issue_comments=[
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "body": "Task summary from an older Codex run.",
            }
        ],
        reactions=[],
        head_sha="def456",
    )

    assert not ok
    assert reasons == ["no Codex bot review artifact found"]
