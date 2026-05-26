from __future__ import annotations

from helpers import load_script_module

check_agent_forbidden_changes = load_script_module("check_agent_forbidden_changes")
forbidden_reasons = check_agent_forbidden_changes.forbidden_reasons
marker_status = check_agent_forbidden_changes._marker_status
should_enforce_for_status = check_agent_forbidden_changes.should_enforce_for_status


def test_forbidden_reasons_reject_workflow_changes() -> None:
    reasons = forbidden_reasons([".github/workflows/ci.yml"])

    assert reasons == ["workflow changes are not allowed in automatic repair: .github/workflows/ci.yml"]


def test_forbidden_reasons_reject_secret_paths() -> None:
    reasons = forbidden_reasons(["config/.env.local", "secrets/prod.json"])

    assert reasons == [
        "secret/env related changes require escalation: config/.env.local",
        "secret/env related changes require escalation: secrets/prod.json",
    ]


def test_forbidden_reasons_reject_repository_policy_paths() -> None:
    reasons = forbidden_reasons([".github/rulesets/main.json", ".github/settings.yml"])

    assert reasons == [
        "repository policy changes require escalation: .github/rulesets/main.json",
        "repository policy changes require escalation: .github/settings.yml",
    ]


def test_forbidden_reasons_allows_application_changes() -> None:
    assert forbidden_reasons(["src/lorairo/main.py", "tests/unit/test_main.py"]) == []


def test_marker_status_reads_repairing_state(tmp_path) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text(
        """Body

<!-- agent-pr-maintainer
{
  "loop": 1,
  "last_checked_head_sha": "abc123",
  "last_reviewed_head_sha": null,
  "status": "repairing"
}
-->
""",
        encoding="utf-8",
    )

    assert marker_status(str(body_file)) == "repairing"


def test_bootstrap_marker_status_does_not_enforce_repair_guard() -> None:
    assert not should_enforce_for_status(None)
    assert not should_enforce_for_status("observing")


def test_repairing_marker_status_enforces_repair_guard() -> None:
    assert should_enforce_for_status("repairing")
