from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-pr-maintainer.yml")


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_slurps_paginated_artifact_json() -> None:
    text = workflow_text()

    assert 'gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/pulls/${PR}/reviews"' in text
    assert 'gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/pulls/${PR}/comments"' in text
    assert 'gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments"' in text
    assert 'gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/issues/${PR}/reactions"' in text


def test_workflow_recomputes_on_review_comment_lifecycle() -> None:
    text = workflow_text()

    assert "pull_request_review_comment:" in text
    assert "types: [created, edited, deleted]" in text
    assert "github.event_name == 'pull_request_review_comment'" in text


def test_workflow_requires_codex_gate_pass_before_auto_merge() -> None:
    text = workflow_text()

    assert "id: codex_gate" in text
    assert "github.event_name != 'pull_request_target'" in text
    assert "steps.codex_gate.outcome == 'success'" in text
    auto_merge_section = text.split("- name: Enable auto-merge when explicitly allowed", maxsplit=1)[1]
    assert "steps.codex_gate.outcome == 'success'" in auto_merge_section


def test_workflow_dispatch_verifies_agent_pr_scope() -> None:
    dispatch_section = (
        workflow_text()
        .split('if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ]; then', maxsplit=1)[1]
        .split("exit 0", maxsplit=1)[0]
    )

    assert 'gh pr view "$PR" --json title,labels' in dispatch_section
    assert 'echo "is_agent_pr=${is_agent_pr}"' in dispatch_section
    assert 'echo "is_agent_pr=true"' not in dispatch_section
