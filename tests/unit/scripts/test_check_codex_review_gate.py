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
