# Git Workflow Rules

Issue解決・機能開発時のブランチ戦略とワークツリー運用ルール。

## ブランチ運用

### mainブランチでの直接作業禁止
- Issue解決・機能開発は必ず専用ブランチで行う
- ブランチ命名: `fix/issue-{番号}`, `feat/issue-{番号}`, `refactor/issue-{番号}`

### ブランチ作成タイミング
- Issueやタスクの実装開始時に作成
- 単純なtypo修正や1行変更でも原則ブランチを切る

## ワークツリー運用

### 配置先
- **必ず `/tmp/worktrees/` 配下に作成する**（named volume、Linux内で高速I/O）
- `/workspaces/LoRAIro/` 配下には作成しない（bind mountでI/Oオーバーヘッドが発生する）

```bash
# 正しい
git worktree add /tmp/worktrees/fix-issue-123 -b fix/issue-123

# 禁止: bind mount上に作成
git worktree add ../fix-issue-123 -b fix/issue-123
```

### Agent呼び出し時
- 実装タスクの Agent 呼び出しでは `isolation: "worktree"` を活用する
- メインワークスペースの作業状態を汚さない

### クリーンアップ
- マージ完了後は、PR 作業で使ったワークツリーを即削除する
- 作業中のカレントディレクトリが削除対象の場合は、共有 checkout (`/workspaces/LoRAIro`) に戻ってから削除する
- 複数の残骸をまとめて掃除する場合は、共有 checkout から `make worktree-cleanup-merged` を実行する
- `make worktree-cleanup-merged` は `/tmp/worktrees/` 配下に限定し、未コミット変更がなく、merged PR または `origin/main` へ到達済みの worktree だけを削除する

```bash
git worktree remove /tmp/worktrees/fix-issue-123
# または
make worktree-cleanup-merged
```

## venv（ワークツリー内）

- ワークツリー内で `uv sync` する場合、venv は `/tmp/worktrees/` のボリューム上に作られるため高速
- プロジェクトルートの `.venv` とは別管理になる
- 並列で `uv run` を実行する場合の詳細ルールは [parallel-execution.md](parallel-execution.md) を参照
