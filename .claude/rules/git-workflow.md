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

- 原則としてワークツリー内に `.venv` を作らない（共有 `/workspaces/LoRAIro/.venv` を使う、named volume で高速）
- `/tmp/worktrees/` 配下で `uv` を実行する場合は、共有実行環境 `/workspaces/LoRAIro/.venv` を使う。
- **共有 `.venv` の指定はツール側の環境設定で常設し、コマンドには毎回 env prefix を付けない**のが標準運用。
  - **Claude Code**: `.claude/settings.json` の `env` に `UV_PROJECT_ENVIRONMENT = "/workspaces/LoRAIro/.venv"` を設定済み。
    worktree からでも素の `uv run ...` で共有 `.venv` を使える（許可は `Bash(uv *)` で済み、env prefix の個別 allowlist は不要）。
    PreToolUse Hook (`hook_pre_commands.py`) の worktree gate も `os.environ` の `UV_PROJECT_ENVIRONMENT` を見るため、素の `uv run` を通す。
  - **Codex**: `.codex/config.toml` の `[shell_environment_policy.set]` に
    `UV_PROJECT_ENVIRONMENT = "/workspaces/LoRAIro/.venv"` を設定し、`uv run ruff ...` のように env prefix なしで実行する。
- その環境設定が効かない shell（手動端末など）では `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv ...` を明示する。
- read-only 検証で対象 checkout を固定したい場合は、`uv run --no-sync` と `PYTHONPATH` 明示を併用する。
- `uv` 単体の help/inspection は venv を作らないため例外として許可する
- ワークツリー固有の `.venv` が必要な特殊事情がある場合は、理由を明示してから実行する
- 並列で `uv run` を実行する場合の詳細ルールは [parallel-execution.md](parallel-execution.md) を参照

### Codex / Claude Code 設定差分

| | 共有 `.venv` 常設方法 | コマンド記法 |
|---|---|---|
| Claude Code | `.claude/settings.json` の `env` | `uv run ...`（env prefix 不要） |
| Codex | `.codex/config.toml` の `[shell_environment_policy.set]` | `uv run ...`（env prefix 不要） |

どちらも常設設定が効かない shell では `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv ...` を明示する。
