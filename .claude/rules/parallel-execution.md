# Parallel Execution Rules

複数の `uv` コマンドを並列に走らせた際の `.venv` 破損事故（Issue #222）を再発させないための運用ルール。プロジェクトルート `.venv` を共有するすべての `uv` 操作に適用。

## 核心ルール

**並列で `uv` を走らせる場合は同一 `.venv` を共有しない。** worktree 分離か、`uv run --active` を使わない（`--active` なしの `uv run` は uv-managed venv で並列セーフ）。

## Hook で自動ブロックされる操作

`uv run --active` は `.claude/hooks/rules/hook_pre_commands_rules.json` で機械的にブロックされる。Claude が以下のコマンドを発行すると PreToolUse Hook が exit code 2 で停止する:

```bash
# 禁止（Hook で自動ブロック）
uv run --active pytest
uv run --active python script.py
uv run --no-sync --active mypy

# 正しい
uv run pytest                  # uv-managed venv、並列セーフ
.venv/bin/pytest               # 直接呼び出し（手動 activate 済みの場合）
```

`--active` が必要な特殊ケースでも、Hook ブロックを回避するために以下を使う:
- `.venv/bin/<command>` を直接呼ぶ
- 一時的に Hook を外して手動実行（推奨されない）

## 4 つのルール

### 1. 並列で `uv run` を走らせる場合は worktree 分離

並列タスクごとに独立した worktree を切り、それぞれが独自の `.venv` を持つ構成にする。配置先は `/tmp/worktrees/` 配下（[git-workflow.md](git-workflow.md) 参照）。

```bash
# 正しい: 並列ジョブごとに worktree
git worktree add /tmp/worktrees/job-a -b feat/job-a
git worktree add /tmp/worktrees/job-b -b feat/job-b
# それぞれの worktree 内で uv sync && uv run pytest を実行

# 禁止: 同一 .venv を並列で叩く
uv run pytest tests/unit/ &
uv run pytest tests/integration/ &
wait
```

### 2. `uv run --active` フラグは原則使わない

`--active` は VIRTUAL_ENV を尊重するが、`pyproject.toml` の Python 制約と不一致な場合に **venv 再作成のトリガー** になる。Hook で自動ブロック済み。

```bash
# 禁止
uv run --active pytest

# 正しい: uv-managed venv（自動同期、並列セーフ）
uv run pytest
```

### 3. `uv sync` / `uv lock` は直列実行

これらのコマンドは `.venv` および `uv.lock` を書き換えるため、並列実行で競合する。Bash ツールの並列呼び出しでも逐次に並べる。

```bash
# 禁止
uv sync &
uv sync --dev &
wait

# 正しい
uv sync && uv sync --dev
```

### 4. Python バージョンは `.python-version` で固定

現在 `.python-version` は `3.13`。VIRTUAL_ENV を手動で activate するシェルでは `python --version` がこの値と一致するか確認する。

```bash
# 確認
cat .python-version          # 3.13 が出るはず
python --version              # 3.13.x が出るはず
.venv/bin/python --version    # 3.13.x が出るはず
```

`.python-version` を変更する場合は影響範囲が広いため PR レビュー必須。

## 復旧手順

### 兆候

以下のエラーが出たら `.venv` 破損を疑う:

```
failed to remove directory '.venv/lib': Directory not empty
failed to rename file from .../*.tmp* to ...: No such file or directory (os error 2)
Removed virtual environment at: /workspaces/LoRAIro/.venv
Creating virtual environment at: /workspaces/LoRAIro/.venv
```

### 復旧コマンド

```bash
make venv-rebuild
```

または手動:

```bash
cd /workspaces/LoRAIro
rm -rf .venv
uv sync --dev
```

注意点:
- tensorflow など重い依存の再ダウンロードが発生する（数分〜十数分）
- worktree 内の `.venv` が壊れた場合は当該 worktree 内で同様に実行
- 復旧中は他の `uv` コマンドを走らせない

## 判断フロー

並列タスクをディスパッチする前のチェックリスト:

1. このタスクは `uv` を内部で呼び出すか? → No なら気にしなくて良い
2. 並列で走らせる別タスクも `uv` を呼ぶか? → No なら気にしなくて良い
3. 同じ `.venv` を共有しているか? → No（worktree 分離済み）なら OK
4. 上記 3 すべて Yes → **直列に並べ替える、または worktree を切る**
