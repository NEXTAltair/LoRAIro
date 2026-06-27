---
name: agent-pr-maintainer
version: "1.0.0"
description: "Maintain an agent-created LoRAIro pull request after creation or after draft-to-ready transition: mark reviewable draft PRs ready, poll CI and review comments with gh, repair failures in the same worktree/session, reply in Japanese, escalate design loops, and squash merge when safe. Use after creating PRs or when asked to continue PR maintenance automation."
metadata:
  short-description: "PR作成後のCI/レビュー監視、修正、返信、設計エスカレーション、squash mergeを共通運用する。"
dependencies:
  - github-ops
---

# Agent PR Maintainer

Follow ADR 0039 when maintaining a PR created by Codex or Claude Code.

## When to Use

Use this skill after an agent creates a LoRAIro PR, including a draft PR, or when asked to continue an
agent-created PR through CI, review comments, repair commits, and merge.

Also use this skill immediately after an agent-created draft PR becomes ready for review, even when the
ready-for-review transition was performed manually by the user outside the agent session. Treat that transition
as the start signal for CI and review-state monitoring.

If the PR was opened as draft only because repository workflow says to create draft PRs, and the implementation
has already passed the agreed local validation, mark it ready for review in the same session and immediately
enter the polling workflow. Do not leave a reviewable draft PR idle just because it was created with `--draft`.

This skill is shared by Codex and Claude Code. GitHub I/O goes through `gh`; the agent-specific part is only
the code-editing session that applies fixes in the existing worktree.

## Core Policy

- Continue in the same agent session and same dedicated worktree used to create the PR.
- Create agent PRs ready for review by default. Do not pass `--draft` to `gh pr create` unless the user
  explicitly asked for draft-only publication or the implementation is not reviewable yet.
- Immediately after creating a PR, enforce the no-draft postcondition before polling CI or setting up auto-merge:

  ```bash
  IS_DRAFT="$(gh pr view "$PR" --json isDraft -q .isDraft)"
  if [ "$IS_DRAFT" = "true" ]; then
    gh pr ready "$PR"
  fi

  IS_DRAFT="$(gh pr view "$PR" --json isDraft -q .isDraft)"
  if [ "$IS_DRAFT" = "true" ]; then
    echo "PR is still draft; aborting auto-merge setup."
    exit 1
  fi
  ```

- Do not stop at the draft PR URL when the PR is reviewable. First mark it ready for review, then immediately
  enter the polling workflow.
- Leave a PR in draft only when the user explicitly asked for draft-only publication, local validation is
  incomplete or failing, the scope is intentionally not ready for review, or a blocker must be reported.
- If the user says they manually changed a draft PR to ready, immediately enter the polling workflow.
- Do not use `@codex fix` or GitHub comment-driven repair commands.
- Poll for at most 20 minutes, every 3 minutes.
- Use `gh` / `gh api` for PR state, checks, failed logs, comments, issue creation, labels, replies, and merge.
- Repair CI failures and review findings in the same worktree, then run the repo's normal pre-push validation.
- Reply to every review comment in Japanese.
- Do not auto-resolve review threads.
- Allow up to 4 repair loops.
- If repair loops continue after the 4th attempt, or review fixes create more design-level review findings,
  stop and escalate to design discussion.
- Merge without human intervention only when bot review has completed cleanly and required checks are clean.
- Treat an empty review/comment set as "review not completed yet", not as clean.
- Use squash merge.
- After a PR is merged, immediately clean up the merged `/tmp/worktrees/` checkout so its `.venv` does not
  remain in `docker_data.vhdx`.

## Polling Workflow

After opening the PR, record the PR number and current head SHA in session memory. If `isDraft` is true,
decide whether the PR is reviewable:

- If reviewable, run `gh pr ready "$PR"` before polling.
- If not reviewable, comment or report why maintenance cannot continue yet, and stop without merging.

Then loop until success, repair-needed, escalation, timeout, or merge.

Commands to gather state:

```bash
gh pr view "$PR" --json \
  number,title,isDraft,headRefName,headRefOid,baseRefName,mergeStateStatus,reviewDecision,statusCheckRollup,labels

gh pr checks "$PR" --json name,state,bucket,link,startedAt,completedAt,workflow
```

Review completion gate:

- Do not merge immediately after CI success.
- Continue polling until the expected Codex/Bot review signal appears as a PR review, review comment,
  issue comment, issue reaction, or other repository-standard bot review artifact.
- Codex review state is signaled by reactions from `chatgpt-codex-connector[bot]` on the PR issue:
  - `eyes` reaction: review is in progress — keep polling, do not merge yet.
  - `+1` reaction: clean review completed — treat as a completed clean bot review when there are no
    blocking review comments.
- **Codex findings are posted as inline pull request review comments, not issue-level comments.**
  `gh pr view --comments` does not return inline review comments. Always fetch them separately
  using the pull request review comments endpoint:

  ```bash
  gh api "repos/{OWNER}/{REPO}/pulls/$PR/comments" \
    --jq '[.[] | select(.user.login == "chatgpt-codex-connector[bot]") | {path, body: .body[:300]}]'
  ```

- A Codex inline comment containing a P1 or P2 badge is a blocking finding. Treat any unresolved
  P1/P2 inline comment as "review has blocking findings" regardless of the `+1` reaction.
- If CI is green but there are no reviews/comments/reactions yet, keep waiting until the 20 minute polling timeout.
- Only treat review as clean after a bot review artifact exists and contains no blocking findings.
- If no bot review artifact appears within 20 minutes, comment on the PR in Japanese that CI is green but
  review did not complete within the polling window, then stop without merging.

Commands to gather clean-reaction state:

```bash
gh api "repos/NEXTAltair/LoRAIro/issues/$PR/reactions"
```

For failed CI jobs, use `gh` to fetch failed logs:

```bash
gh run view "$RUN_ID" --log-failed
```

Use `gh api` for review comments and review threads when `gh pr view` is insufficient. Keep GitHub API
responses bounded and summarize large logs before reasoning over them.

## Repair Rules

When CI fails or review comments require changes:

1. Read the failed logs and review comments.
2. Decide whether each finding is valid.
3. Apply the smallest coherent fix in the existing PR worktree.
4. Run the repository's normal validation before push, including tests, Ruff, and mypy as applicable.
5. Commit and push the repair.
6. Reply to every review comment in Japanese.

Reply format:

```markdown
対応しました。

- 修正内容: ...
- 修正commit: ...
- 検証: `...` passed
```

If not changing code for a comment:

```markdown
この指摘は対応不要と判断しました。

- 理由: ...
- 確認内容: ...
```

## Escalation Rules

Stop automatic repair and escalate when any of these occur:

- The 4th repair attempt still does not clear CI or review findings.
- Review comments recur in the same responsibility boundary after a repair.
- The fix requires workflow/permission/secret changes.
- The fix requires direct push to main/default branch or history rewriting.
- The fix requires a large design change rather than local repair.

Allowed in automatic repair:

- Application code changes
- Tests
- Docs
- DB migrations
- Dependency and lockfile updates

Not allowed in automatic repair:

- `.github/workflows/**` changes
- GitHub Actions permission changes
- Secret or environment configuration changes
- Direct push to main/default branch
- Git history rewriting
- Large design rewrites

On escalation:

1. Add design/escalation labels to the PR when available.
2. Create a GitHub issue describing the design problem and options.
3. Comment on the PR in Japanese with the issue link, summary, options, and what user decision is needed.
4. Stop without merging.

## Merge Rules

Before merge, verify:

- PR is not draft.
- The PR creation postcondition confirmed `isDraft == false`; if the PR is still draft, do not run
  `gh pr merge --auto`.
- Head SHA matches the last checked SHA.
- Required checks are successful.
- Bot review has completed and has no blocking findings.
- PR reviews/comments or PR issue reactions contain an expected bot review artifact.
- Repair loop count is below the escalation threshold.
- The PR is not in escalation state.

Then run:

```bash
gh pr merge "$PR" --squash --auto --delete-branch --match-head-commit "$HEAD_SHA"
```

After GitHub reports the PR as merged, switch to the shared checkout and remove the merged worktree:

```bash
cd /workspaces/LoRAIro
make worktree-cleanup-merged
```

If only the current PR worktree should be removed, use `git worktree remove "$WORKTREE_PATH"` from outside that
worktree. Do not leave the merged worktree or its `.venv` behind.

## State

Keep loop count, latest checked head SHA, and review-generation observations in session memory. Do not add
persistent state for now. If the session is lost, stop; the user will give a fresh instruction.

## References

- `docs/decisions/0039-agent-pr-maintenance-automation.md`
- `AGENTS.md`
