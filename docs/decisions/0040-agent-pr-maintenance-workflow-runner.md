# ADR 0040: Agent PR Maintenance Workflow Runner

- **日付**: 2026-05-26
- **ステータス**: Accepted

## Context

ADR 0039 では、PR を作成したエージェントが同じセッションと同じ worktree で CI / Bot review /
修正 / merge まで継続する運用を定義した。この運用は短時間の保守には有効だが、エージェント
セッションが終了した場合に状態が失われ、人間が再度 Codex / Claude Code に続きを指示する
必要がある。

また、Draft PR の ready 化、Codex review artifact の観測、Bot review の blocking 判定、
自動修正で禁止される workflow / secret 関連変更の検出は、運用ルールだけではなく
GitHub 側の実行系で再現可能にする必要がある。

## Decision

`.github/workflows/agent-pr-maintainer.yml` を追加し、agent PR の状態監視と merge gate を
GitHub Actions 上で実行する。

対象 PR は以下のいずれかに該当するものとする。

- `agent-pr` label が付いている
- タイトルが `[codex]` または `[claude]` で始まる
- `workflow_dispatch` で PR 番号または URL が明示された

workflow runner は `pull_request_target` で起動し、policy script は base branch 側の trusted checkout
から実行する。PR head は `pr/` に別 checkout し、検査対象としてのみ扱う。

workflow runner は以下を行う。

1. base branch を `trusted/` に checkout し、PR branch を `pr/` に checkout する
2. `gh pr ready "$PR" || true` で Draft PR を ready 化する
3. PR 作成 / 更新で自動実行される Codex review artifact を観測する
4. PR state / checks / reviews / review comments / issue comments / reactions を `gh` / REST API で取得する
5. PR body に `agent-pr-maintainer` hidden marker を保存し、確認済み head SHA と状態を永続化する
6. 自動修正で禁止される `.github/workflows/**`、repository policy、secret / env 系 path を
   PR の実 base branch との差分で検出する。PR body marker は診断用としてのみ読み、禁止変更の
   bypass には使わない
7. 現在の head SHA に対する Codex bot review artifact が存在し、blocking finding が残っていないことを
   check として検証する
8. repository variable `AGENT_PR_AUTO_MERGE=true` が明示された場合のみ、
   `gh pr merge --squash --auto --delete-branch --match-head-commit "$HEAD_SHA"` を実行する

修正 commit の生成は、引き続き Codex / Claude Code の作業セッションが担当する。
GitHub Actions runner は GitHub コメント駆動の `@codex fix` を起動しない。
`GITHUB_TOKEN` の投稿者は `github-actions` になり Codex connector と紐付かないため、Codex review
trigger コメントも投稿しない。Codex review は repository-level Codex Automatic Reviews、または
接続済みの人間 / ユーザーによる手動依頼に任せる。

`pull_request_target` の opened / ready_for_review / synchronize / reopened / labeled では、
状態記録と artifact 収集だけを行い、現在 head の Codex review が未生成であることだけでは失敗させない。
gate 判定は `pull_request_review` の submitted / edited / dismissed、または
`chatgpt-codex-connector` / `chatgpt-codex-connector[bot]` の issue comment 到着時に実行する。
ただし、gate を通過できるのは現在の head SHA に対応する Codex review artifact がある場合だけである。
古い head SHA の review artifact や、`To use Codex here, create a Codex account and connect to github.`
のような connector failure comment は成功 artifact として扱わない。

## Rationale

GitHub Actions に ready 化、状態取得、gate 判定を移すことで、PR 作成エージェントの
セッションが落ちても、PR 側に次の判断材料が残る。PR body の hidden marker は、外部 storage を
導入せずに head SHA と loop/status を復元するための最小の永続化手段である。

policy script を PR head から実行すると、PR author が gate 自体を書き換えて通過できる。
そのため runner は base branch 側 checkout の script だけを実行し、PR head checkout は diff / file state
の検査対象としてのみ扱う。privileged workflow 内では PR head 側の Python module import、test 実行、
package install hook、任意 command 実行を行わない。

merge は GitHub の required checks / branch protection / auto-merge に寄せる。
Codex review は merge 判断の参考信号ではなく、`check_codex_review_gate.py` の exit code を通じて
required check 化できる信号として扱う。

`AGENT_PR_AUTO_MERGE` は初期値を `false` にする。branch protection / ruleset で required checks と
conversation resolution が確実に設定される前に、workflow だけで merge を進めないためである。

## Consequences

**良い点:**

- Draft PR の ready 化を人間の手順から外せる
- PR body marker により、別セッションでも確認済み head SHA と状態を復元できる
- Bot review blocking 判定と禁止変更検出が base branch 側 policy による機械的な check になる
- auto-merge は branch protection と `--match-head-commit` に委譲できる

**悪い点:**

- `.github/workflows/**` 変更を禁止する check と、この workflow 自体の導入は別扱いにする必要がある。
  bootstrap 例外は、base branch に該当 workflow がまだ存在しない場合の明示 path に限定する
- Bot review の blocking 判定は文言ベースを含むため、Codex 側の表現変更に合わせた調整が必要
- workflow は修正 commit を生成しないため、CI failure の自動修復には Codex / Claude Code の再実行が必要
- 初回導入 PR は base branch に runner / policy script がまだ存在しないため、人間レビューで
  bootstrap 変更として扱う必要がある

## Related

- ADR 0039 (Agent PR Maintenance Automation)
- `.github/workflows/agent-pr-maintainer.yml`
- `scripts/agent_pr_state.py`
- `scripts/check_codex_review_gate.py`
- `scripts/check_agent_forbidden_changes.py`
