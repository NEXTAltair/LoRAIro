from __future__ import annotations

from helpers import load_script_module

forbidden_reasons = load_script_module("check_agent_forbidden_changes").forbidden_reasons


def test_forbidden_reasons_reject_workflow_changes() -> None:
    reasons = forbidden_reasons([".github/workflows/ci.yml"])

    assert reasons == ["workflow changes are not allowed in automatic repair: .github/workflows/ci.yml"]


def test_forbidden_reasons_reject_secret_paths() -> None:
    reasons = forbidden_reasons(["config/.env.local", "secrets/prod.json"])

    assert reasons == [
        "secret/env related changes require escalation: config/.env.local",
        "secret/env related changes require escalation: secrets/prod.json",
    ]


def test_forbidden_reasons_allows_application_changes() -> None:
    assert forbidden_reasons(["src/lorairo/main.py", "tests/unit/test_main.py"]) == []
