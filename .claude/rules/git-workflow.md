# Git Workflow Rules

Issue解決・機能開発時のブランチ戦略とワークツリー運用ルール。

## 実装作業は worktree から開始（必須）

Issue解決・機能開発・PR準備・複数ファイル実装は、**必ず `/tmp/worktrees/` 配下の専用 worktree から開始する**。共有 checkout `/workspaces/LoRAIro` で実装作業の edit / stage / commit / push / rebase をしない。

### worktree + PR を要さない例外（共有 checkout / main 直 push 可）

以下は worktree も PR も介さず、共有 checkout で作業し main へ直接 push してよい（**新規作成・更新の両方**）:

- **ドキュメント系のみ**: ADR (`docs/decisions/`)、`docs/` 配下、README 等の作成・更新（コード変更を伴わないもの）
- **開発ツール周りの chore**: SKILL (`.agents/skills/`, `.claude/skills/`)、プロンプト/コマンド (`.claude/commands/`)、Agent 定義、`.claude/` / `.codex/` の設定・hook・rules、`.gitignore` 等の作成・更新
- read-only 調査、ツール検証、worktree 掃除

判断基準: **アプリのソース（`src/`, `tests/`, `local_packages/*/src`）や schema/migration を触るか**。触るなら worktree + PR、触らない docs/tooling chore なら共有 checkout で直接でよい（[[feedback_chore_main_direct_push]] と整合）。

```bash
# 実装着手時の標準手順
git fetch origin
git worktree add /tmp/worktrees/issue-123 -b fix/issue-123 origin/main
# 以降の編集・コミット・push はこの worktree 内で行う
```

完了の定義（ユーザーが明示的に「publish 前で止めて」「draft のまま」と言わない限り）:
1. worktree で実装
2. CI-equivalent filter で検証（[testing.md](testing.md)）
3. commit & push
4. ready-for-review な PR を起票
5. PR 保守自走（CI / bot レビュー）を回し、safe なら squash merge
6. merge 後 worktree を `git worktree remove` で即削除

ローカル実装だけで作業を終えない。PR URL と最終監視状態を成果として報告する。auth / network / 検証失敗 / スコープ不明で PR 起票がブロックされた場合は、黙ってローカル変更で止めず blocker を明示する。

> 注: Agent tool の `isolation: "worktree"` はこのリポジトリで壊れている。手動 `git worktree add` + 共有 `.venv` で運用する。

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
- 実装タスクの Agent には、リード側で `git worktree add` した専用 worktree のパスを渡す（`isolation: "worktree"` はこのリポジトリで壊れているため使わない）
- 並列実装では worker ごとに別 worktree を割り当て、書き込みスコープ（担当ファイル/モジュール）を分離する
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
- **注意**: この常設 `UV_PROJECT_ENVIRONMENT` は全 Bash コマンドに継承される。package 隔離した別 uv プロジェクト（`local_packages/genai-tag-db-tools` 等）を実行する recipe は、共有 `.venv` を誤って使わないよう自前の `UV_PROJECT_ENVIRONMENT` を明示する（`make test-genai-tag` 参照）。
- 並列で `uv run` を実行する場合の詳細ルールは [parallel-execution.md](parallel-execution.md) を参照

### Codex / Claude Code 設定差分

| | 共有 `.venv` 常設方法 | コマンド記法 |
|---|---|---|
| Claude Code | `.claude/settings.json` の `env` | `uv run ...`（env prefix 不要） |
| Codex | `.codex/config.toml` の `[shell_environment_policy.set]` | `uv run ...`（env prefix 不要） |

どちらも常設設定が効かない shell では `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv ...` を明示する。
