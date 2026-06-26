#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (PostToolUse Hook)

ワークツリー作成後に submodule (local_packages/*) を init するだけにする。

重要: ここで `uv sync` は実行しない。
  共有 venv (/workspaces/LoRAIro/.venv, named volume) は main checkout から
  既に sync 済みで、ワークツリーはこれを共有する。ワークツリーの cwd で
  `uv sync` を走らせると uv が workspace member (local_packages/*) の editable
  install をワークツリー側のパスへ貼り替え、共有 venv の editable ピンが
  壊れる (main checkout と他の全ワークツリーのローカルパッケージ import が
  同時に狂う)。詳細は .claude/rules/git-workflow.md / testing.md 参照。

代わりに submodule を init する。ワークツリーは submodule が未 checkout だと
conftest が image_annotator_lib を MagicMock fallback して無関係テストが偽陽性に
なるため、ソースだけ materialize しておく (共有 venv には一切触れない)。
"""

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        data: dict = json.load(sys.stdin)

        # ワークツリーパスを取得
        worktree_path = data.get("tool_input", {}).get("path", "")
        if not worktree_path:
            sys.exit(0)

        path = Path(worktree_path)
        if not path.exists():
            sys.exit(0)

        # submodule のソースのみ init する (共有 venv は触らない)
        result = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(json.dumps({
                "systemMessage": f"⚠️ git submodule update --init 失敗:\n{result.stderr[-500:]}",
                "continue": True,
            }, ensure_ascii=False))

    except (json.JSONDecodeError, OSError):
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
