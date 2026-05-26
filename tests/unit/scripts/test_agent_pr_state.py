from __future__ import annotations

import json

from helpers import load_script_module

agent_pr_state = load_script_module("agent_pr_state")
AgentPrState = agent_pr_state.AgentPrState
extract_state = agent_pr_state.extract_state
render_marker = agent_pr_state.render_marker
upsert_state = agent_pr_state.upsert_state


def test_upsert_state_adds_hidden_marker() -> None:
    state = AgentPrState(
        loop=1,
        last_checked_head_sha="abc123",
        last_reviewed_head_sha=None,
        status="observing",
    )

    updated = upsert_state("PR body", state)

    assert "PR body" in updated
    assert "<!-- agent-pr-maintainer" in updated
    assert extract_state(updated) == state


def test_upsert_state_replaces_existing_marker() -> None:
    first = AgentPrState(
        loop=1,
        last_checked_head_sha="abc123",
        last_reviewed_head_sha=None,
        status="observing",
    )
    second = AgentPrState(
        loop=2,
        last_checked_head_sha="def456",
        last_reviewed_head_sha="abc123",
        status="repairing",
    )
    body = upsert_state("PR body", first)

    updated = upsert_state(body, second)

    assert updated.count("<!-- agent-pr-maintainer") == 1
    assert extract_state(updated) == second


def test_render_marker_outputs_json_payload() -> None:
    state = AgentPrState(
        loop=0,
        last_checked_head_sha="abc123",
        last_reviewed_head_sha=None,
        status="observing",
    )

    marker = render_marker(state)
    payload = marker.removeprefix("<!-- agent-pr-maintainer\n").removesuffix("\n-->")

    assert json.loads(payload)["last_checked_head_sha"] == "abc123"
