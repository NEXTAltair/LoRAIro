# ADR 0039: Agent PR Maintenance Automation

- **日付**: 2026-05-25
- **ステータス**: Accepted

## Context

LoRAIro では Codex / Claude Code などのエージェントが issue 対応や機能実装を行い、
PR を作成する運用が増えている。PR 作成後は CI、Bot によるコードレビュー、人間レビューの
結果を確認し、必要に応じて修正 commit を追加し、問題がなければ squash merge する必要がある。

現状、この PR 作成後の保守ループは人間が以下を手動で行っている:

1. CI 完了を待つ
2. CI 失敗ログを読む
3. コードレビューコメントを読む
4. エージェントへ修正指示を出す
5. 修正後に再度 CI / レビュー結果を確認する
6. 問題がなければ squash merge する

この手動部分は定型化できる一方、レビュー修正が連鎖する場合は局所修正ではなく設計判断が
必要になっている可能性がある。そのため、完全自動化しつつも、修正ループの上限と
設計エスカレーション条件を明確にする必要がある。

## Decision

### 1. PR 作成エージェントが PR 保守を継続する

PR を作成したエージェントが、同じセッションと同じ worktree で CI / レビュー完了まで
保守ループを継続する。

- PR 作成後に別 watcher へ即時委譲しない
- `@codex fix` のような GitHub コメント駆動の修正コマンドは使わない
- 修正はコンテナ内の Codex CLI / Claude Code CLI が、既存の作業文脈を持ったまま行う
- 作業場所は PR 作成に使った専用 worktree を継続利用する

この方針は、GitHub コメント経由の修正タスクよりも、実装時の文脈を保持しやすいことを優先する。

### 2. CI / レビュー完了待ちは polling で行う

PR 作成後、エージェントは `gh` コマンドで PR 状態を polling する。

- 最大待機時間: 20分
- polling 間隔: 3分
- CI 状態、CI 失敗ログ、レビューコメントは `gh` / `gh api` で取得する
- 20分を超えても完了しない場合は PR コメントで状況を通知し、一旦停止する

想定する基本コマンド:

```bash
gh pr view "$PR" --json \
  number,title,isDraft,headRefName,headRefOid,baseRefName,mergeStateStatus,reviewDecision,statusCheckRollup,labels

gh pr checks "$PR" --json name,state,bucket,link,startedAt,completedAt,workflow

gh run view "$RUN_ID" --log-failed
```

レビューコメントの取得は、必要に応じて REST API と GraphQL API を併用する。
ただし review thread は自動 resolve しない。

### 3. 修正ループ上限

CI 失敗またはレビューコメントがある場合、エージェントは同じ worktree で修正し、既存運用どおり
テスト、Ruff、mypy などの検証を行ってから commit / push する。

- 修正ループは最大4回まで許可する
- 4回目の修正でも CI / レビュー問題が解消しない場合は自動修正を停止する
- レビューコメント対応後に追加レビューコメントが連鎖する場合は、設計自体に問題がある可能性として扱う

### 4. レビューコメント返信

全レビューコメントに日本語で返信する。

- 修正した場合は、修正内容、commit、検証結果を簡潔に返信する
- 修正しない場合は、対応不要と判断した理由を返信する
- review thread は自動 resolve しない

### 5. 自動 merge 条件

以下を満たす場合、人間を介さず squash merge する。

- Bot レビューで blocking な問題が残っていない
- CI / required checks が成功している
- PR が draft ではない
- merge 対象の head SHA が確認済み SHA と一致している
- 自動修正ループが上限に達していない
- 設計エスカレーション状態ではない

merge は squash merge に統一する。

```bash
gh pr merge "$PR" --squash --auto --delete-branch --match-head-commit "$HEAD_SHA"
```

### 6. 設計エスカレーション

以下の場合、エージェントは自動修正を停止し、設計変更検討としてエスカレーションする。

- 4回目の修正でも CI / レビュー問題が解消しない
- 同じ責務境界や同じファイル群でレビュー指摘が連鎖する
- 局所修正ではなく public API、worker lifecycle、GUI signal-slot 構造などの設計判断が必要
- workflow / 権限 / secret / main 直 push / 履歴改変 / 大規模設計変更が必要

エスカレーション時は以下を行う。

1. PR に状況と設計上の選択肢を日本語でコメントする
2. 設計検討 Issue を作成する
3. PR と Issue に設計検討用ラベルを追加する

### 7. 許可・禁止操作

自動修正で許可する操作:

- アプリケーションコード修正
- テスト追加・修正
- ドキュメント更新
- DB migration 追加・修正
- 依存関係更新と lock file 更新

自動修正で禁止する操作:

- `.github/workflows/**` の変更
- GitHub Actions 権限変更
- secret / env 設定変更
- main / default branch への直接 push
- Git 履歴改変
- 大規模設計変更

禁止操作が必要な場合は、実装せず設計エスカレーションに切り替える。

### 8. 状態管理

当面、状態永続化は行わない。

- 同じエージェントセッション内のメモリで loop count と確認済み head SHA を管理する
- セッションが落ちた場合は人間が手動で再指示する
- 将来、長時間運用や復旧性が必要になった場合は PR コメントの HTML marker 等で状態永続化を追加する

## Rationale

**同一エージェントが保守する理由**: PR 作成直後のエージェントは、設計意図、変更理由、
既に試した検証を最も多く保持している。GitHub コメントから新しい cloud task を起動する方式は
文脈が薄くなりやすいため、修正精度よりも制御の単純さを優先する場面以外では採用しない。

**polling を採用する理由**: LoRAIro の通常 CI / Bot レビュー待ちは20分を超えることが稀であり、
webhook watcher や常駐 daemon を先に導入するより、PR 作成エージェントが `gh` で短時間 polling
する方が実装と運用が単純である。

**4回上限の理由**: CI 失敗は一時的な環境差や単純なテスト漏れで複数回の修正が必要になることがある。
一方で4回修正しても解消しない場合、局所修正の積み増しより設計変更検討へ切り替える方が安全である。

**review thread を自動 resolve しない理由**: 返信は自動化してよいが、解決済み扱いにするかは
レビューの意味論に関わる。自動 resolve はレビュアーの確認を省略したように見えるため、初期運用では
返信のみに留める。

## Consequences

**良い点:**

- PR 作成後の CI / レビュー確認、修正指示、再確認、merge の手作業が減る
- PR 作成エージェントの実装文脈を保ったまま修正できる
- 4回上限と設計エスカレーションにより、局所修正の無限ループを避けられる
- `gh` を GitHub I/O の境界にするため、LLM に未整理の GitHub 状態を直接探索させずに済む

**悪い点:**

- PR 作成エージェントのセッションが CI / レビュー完了まで最大20分占有される
- セッションが落ちた場合、自動復旧せず人間の再指示が必要
- polling 型のため、長時間CIや遅延レビューが増えた場合は別 watcher / GitHub Actions への移行が必要
- 人間を介さない merge は required checks と Bot レビュー品質に強く依存する

## Related

- ADR 0014 (Agent Teams Integration)
- ADR 0020 (CLI Message Language Policy)
- `.agents/skills/agent-pr-maintainer/SKILL.md`
- `AGENTS.md` (Agent Git Workflow / Codex Parallel Agent Workflow)
