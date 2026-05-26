# ADR 0040: Agent PR Maintenance Workflow Runner

- **日付**: 2026-05-26
- **ステータス**: Accepted

## Context

ADR 0039 では、PR を作成したエージェントが同じセッションと同じ worktree で CI / Bot review /
修正 / merge まで継続する運用を定義した。この運用は短時間の保守には有効だが、エージェント
セッションが終了した場合に状態が失われ、人間が再度 Codex / Claude Code に続きを指示する
必要がある。

また、Draft PR の ready 化、Codex review の明示トリガー、Bot review の blocking 判定、
自動修正で禁止される workflow / secret 関連変更の検出は、運用ルールだけではなく
GitHub 側の実行系で再現可能にする必要がある。

## Decision

`.github/workflows/agent-pr-maintainer.yml` を追加し、agent PR の状態監視と merge gate を
GitHub Actions 上で実行する。

対象 PR は以下のいずれかに該当するものとする。

- `agent-pr` label が付いている
- タイトルが `[codex]` または `[claude]` で始まる
- `workflow_dispatch` で PR 番号または URL が明示された

workflow runner は以下を行う。

1. PR branch を checkout する
2. `gh pr ready "$PR" || true` で Draft PR を ready 化する
3. `CODEX_BOT_TOKEN` が設定されている場合のみ、
   `@codex review for security regressions, missing tests, and risky behavior changes.` を投稿する
4. PR state / checks / reviews / review comments / issue comments / reactions を `gh` / REST API で取得する
5. PR body に `agent-pr-maintainer` hidden marker を保存し、確認済み head SHA と状態を永続化する
6. PR marker が `repairing` の場合、自動修正で禁止される `.github/workflows/**` と
   secret / env 系 path を検出する
7. Codex bot review artifact が存在し、blocking finding が残っていないことを check として検証する
8. repository variable `AGENT_PR_AUTO_MERGE=true` が明示された場合のみ、
   `gh pr merge --squash --auto --delete-branch --match-head-commit "$HEAD_SHA"` を実行する

修正 commit の生成は、引き続き Codex / Claude Code の作業セッションが担当する。
GitHub Actions runner は GitHub コメント駆動の `@codex fix` を起動しない。
`GITHUB_TOKEN` の投稿者は `github-actions` になり Codex connector と紐付かないため、Codex review
trigger には使わない。

## Rationale

GitHub Actions に ready 化、review trigger、状態取得、gate 判定を移すことで、PR 作成エージェントの
セッションが落ちても、PR 側に次の判断材料が残る。PR body の hidden marker は、外部 storage を
導入せずに head SHA と loop/status を復元するための最小の永続化手段である。

merge は GitHub の required checks / branch protection / auto-merge に寄せる。
Codex review は merge 判断の参考信号ではなく、`check_codex_review_gate.py` の exit code を通じて
required check 化できる信号として扱う。

`AGENT_PR_AUTO_MERGE` は初期値を `false` にする。branch protection / ruleset で required checks と
conversation resolution が確実に設定される前に、workflow だけで merge を進めないためである。

## Consequences

**良い点:**

- Draft PR の ready 化と Codex review trigger を人間の手順から外せる
- PR body marker により、別セッションでも確認済み head SHA と状態を復元できる
- Bot review blocking 判定と禁止変更検出が機械的な check になる
- auto-merge は branch protection と `--match-head-commit` に委譲できる

**悪い点:**

- `.github/workflows/**` 変更を禁止する check と、この workflow 自体の導入は別扱いにする必要がある
- Bot review の blocking 判定は文言ベースを含むため、Codex 側の表現変更に合わせた調整が必要
- workflow は修正 commit を生成しないため、CI failure の自動修復には Codex / Claude Code の再実行が必要

## Related

- ADR 0039 (Agent PR Maintenance Automation)
- `.github/workflows/agent-pr-maintainer.yml`
- `scripts/agent_pr_state.py`
- `scripts/check_codex_review_gate.py`
- `scripts/check_agent_forbidden_changes.py`
