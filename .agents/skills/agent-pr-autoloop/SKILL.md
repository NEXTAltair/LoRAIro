---
name: agent-pr-autoloop
version: "1.0.0"
description: "Run LoRAIro PR maintenance to completion automatically after an agent creates a PR or a draft PR becomes ready for review: keep polling CI and bot review with gh, repair failures and reply in Japanese in the same worktree, escalate design loops, and squash merge when safe, without waiting for a human to restart each poll cycle. Use right after an agent-created PR exists or transitions draft-to-ready. Do NOT use for human-authored PRs, and do NOT redefine repair/merge/escalation policy here (that lives in agent-pr-maintainer)."
metadata:
  short-description: "PR作成後の保守ループを人手の再起動なしに最後まで自走させる共通スキル。作法差分はCLAUDE.md/AGENTS.mdで吸収。"
dependencies:
  - agent-pr-maintainer
  - github-ops
---

# Agent PR Autoloop

Automatically drive the agent PR maintenance loop to a terminal state after a PR is created, without a
human restarting each poll. This skill is shared by Codex and Claude Code; only the non-blocking wait
mechanism differs per agent and is absorbed by each agent guide (see "Per-Agent Wait Mechanism").

## Relationship to agent-pr-maintainer

This skill is the **autonomous looping layer**. It does not define policy.

- All policy — draft gates, repair rules, repair-loop limit (4), Japanese review replies, design escalation,
  merge conditions, post-merge worktree cleanup — comes from the `agent-pr-maintainer` skill and ADR 0039.
- This skill only specifies the contract for **how to keep the loop running by itself** until a terminal state.

If anything here appears to conflict with `agent-pr-maintainer`, `agent-pr-maintainer` wins on policy and this
skill wins only on "do not stall waiting for a human between polls".

## When to Use

Use immediately when any of these is true:

- This agent just created a LoRAIro PR (`gh pr create`), including a draft created only because workflow says so.
- A draft agent PR transitioned to ready for review (including a manual transition by the user).
- The user asks to continue/finish an agent-created PR through CI, review, repair, and merge.

First enforce the no-draft postcondition from `agent-pr-maintainer` (ready the PR if it is reviewable), then
enter the loop. Do not stop at the PR URL when the PR is reviewable.

## Autoloop Contract (agent-agnostic)

Treat maintenance as a self-paced poll loop. One loop cycle:

1. Gather state with `gh` — **all four checks are mandatory every cycle; never skip based on CI status**:

   ```bash
   # (a) PR fields — isDraft, mergeStateStatus, reviewDecision, head SHA
   gh pr view "$PR" --repo "$REPO" \
     --json number,isDraft,headRefOid,mergeStateStatus,reviewDecision,statusCheckRollup,labels

   # (b) Check run statuses
   gh pr checks "$PR" --repo "$REPO" \
     --json name,state,bucket,link,startedAt,completedAt,workflow

   # (c) Bot reactions on the PR issue (Codex signals: +1=clean, eyes=in-progress)
   gh api "repos/$REPO/issues/$PR_NUM/reactions"

   # (d) Inline review comments — detect P1/P2 badge findings from Codex
   gh api "repos/$REPO/pulls/$PR_NUM/comments"
   ```

   `$REPO` is `owner/repo` (e.g. `NEXTAltair/LoRAIro` or `NEXTAltair/genai-tag-db-tools`).
   `mergeStateStatus=CLEAN` means GitHub merge preconditions pass; it does **not** mean bot review is complete.

2. Classify the cycle into exactly one outcome:
   - **continue** — any of these: CI checks still running (step b has pending checks); no `chatgpt-codex-connector[bot]` reaction yet on the PR issue (step c is empty or only `eyes`); CI is green but Codex review/reaction has not posted yet → schedule the next cycle.
   - **repair** — any of these: CI checks failed (step b); Codex review state is `COMMENTED` and step d contains P1/P2 badge findings → fix in the PR worktree, validate, push, reply in Japanese per `agent-pr-maintainer`, then continue (count the repair against the limit).
   - **escalate** — repair limit reached, recurring findings in the same boundary, or a forbidden change is required → open the design issue, comment in Japanese, stop.
   - **merge** — **all** of the following are true (verified from step 1 data above):
     1. CI: all required checks pass (step b — no failed or pending).
     2. Draft: `isDraft == false` (step a).
     3. Codex reaction: `chatgpt-codex-connector[bot]` has a `+1` reaction on the PR issue (step c). `eyes` alone → **continue**, not merge.
     4. No blocking findings: step d has no unaddressed P1/P2 Codex comments.

     ⚠️ `mergeStateStatus=CLEAN` with `reviewDecision=""` alone does **not** satisfy this gate.
     → squash merge, clean up the worktree, stop.
   - **timeout** — total elapsed reached the polling window with no terminal result → comment in Japanese that CI/review did not complete in the window, stop.
3. If the outcome is **continue**, wait the poll interval and start the next cycle automatically.

### Loop parameters (ADR 0039)

- Poll interval: about **3 minutes** between cycles.
- Polling window: at most **20 minutes** total (about 6–7 cycles).
- Keep loop count and the last checked head SHA in session memory; track repair count with a todo per ADR 0039 §8.
- Never let the loop idle waiting for a human to manually re-trigger the next poll. The whole point of this
  skill is that "continue" reschedules itself.

## Per-Agent Wait Mechanism

The only agent-specific part is **how you wait the poll interval without blocking your runtime**. Do not
hardcode a single mechanism here; follow your agent guide:

- **Claude Code** → `CLAUDE.md` section "agent-pr-autoloop の Claude Code 実装" (ScheduleWakeup self-pacing;
  fallback bounded `bash until` loop; never `sleep && <next>`).
- **Codex** → `AGENTS.md` "Agent Git Workflow" (inline session polling; no ScheduleWakeup).

If your agent guide has no entry, fall back to the most conservative non-blocking poll your runtime supports
and report which mechanism you used.

## Stop Conditions

Stop the loop (and report the final monitored state) on **merge**, **escalate**, or **timeout**. Do not merge
on **continue**, and do not treat an empty review/comment set as a clean review (it means "review not completed
yet" per `agent-pr-maintainer`).

## References

- `.agents/skills/agent-pr-maintainer/SKILL.md` — policy this skill executes.
- `docs/decisions/0039-agent-pr-maintenance-automation.md` — decision record.
- `CLAUDE.md` / `AGENTS.md` — per-agent wait mechanism.
