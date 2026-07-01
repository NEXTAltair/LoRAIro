#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (provider hook)

Agent tool の `isolation: "worktree"` 起動時に harness が呼ぶ **provider**。
worktree を作成し、そのパスを stdout に echo して返す (契約: 失敗時は非ゼロ exit)。

harness が渡す payload (tool_input.path は無い — このフックが作成する側):
  {session_id, transcript_path, cwd, hook_event_name: "WorktreeCreate", name}

重要: ここで `uv sync` は実行しない。
  共有 venv (/workspaces/LoRAIro/.venv, named volume) は main checkout から既に
  sync 済みで、worktree はこれを共有する。worktree の cwd で `uv sync` を走らせると
  uv が workspace member (local_packages/*) の editable install を worktree 側の
  パスへ貼り替え、共有 venv の editable ピンが壊れる (main checkout と他の全 worktree
  のローカルパッケージ import が同時に狂う) 上に venv 容量も肥大する。
  詳細は .claude/rules/git-workflow.md / testing.md 参照。

代わりに submodule のソースだけ init する。worktree は submodule が未 checkout だと
conftest が image_annotator_lib を MagicMock fallback して無関係テストが偽陽性に
なるため、ソースだけ materialize しておく (共有 venv には一切触れない)。

worktree は detached HEAD で作る。実装 agent は中で `feat/issue-NNN` 等の
専用ブランチを切る (git-workflow.md のブランチ命名規約に従う)。
"""

import json
import subprocess
import sys
from pathlib import Path

# isolation worktree の配置先: リポジトリ内 .agents/worktree/ (git-workflow.md の
# ワークツリー配置ルール。重い .venv は共有 named volume を使うため source のみの
# worktree の bind mount I/O は実用範囲。.gitignore で追跡対象外)。
WORKTREE_SUBDIR = ".agents/worktree"


def _sanitize(name: str) -> str:
    """agent 名を path 安全なディレクトリ名へ正規化する。"""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name) or "agent"


def main() -> None:
    if sys.stdin.isatty():
        sys.exit(0)

    try:
        data: dict = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"WorktreeCreate hook: payload 解析失敗: {e}")
        sys.exit(1)

    repo = data.get("cwd") or "/workspaces/LoRAIro"
    worktree_base = Path(repo) / WORKTREE_SUBDIR
    worktree_path = worktree_base / _sanitize(data.get("name") or "agent")

    try:
        worktree_base.mkdir(parents=True, exist_ok=True)

        # 既存 worktree は再利用 (セッション再開耐性)。無ければ detached で作成。
        if not (worktree_path / ".git").exists():
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), "HEAD"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                sys.stderr.write(f"git worktree add 失敗: {result.stderr[-500:]}")
                sys.exit(1)

        # submodule のソースのみ init する (共有 venv は触らない)。
        # 失敗しても worktree 自体は使えるので致命扱いにしない (warning のみ)。
        sub = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if sub.returncode != 0:
            sys.stderr.write(f"⚠️ git submodule update --init 失敗: {sub.stderr[-300:]}")

    except OSError as e:
        sys.stderr.write(f"WorktreeCreate hook: worktree 作成失敗: {e}")
        sys.exit(1)

    # 契約: 作成した worktree のパスを stdout に echo する。
    print(str(worktree_path))
    sys.exit(0)


if __name__ == "__main__":
    main()
