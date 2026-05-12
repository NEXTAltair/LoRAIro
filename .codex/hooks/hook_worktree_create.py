#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (PostToolUse Hook)

ワークツリー作成後に uv sync --dev を自動実行する。
新しいワークツリーで依存関係が即座に使えるようにする。
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

        result = subprocess.run(
            ["uv", "sync", "--dev"],
            cwd=path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(json.dumps({
                "systemMessage": f"⚠️ uv sync --dev 失敗:\n{result.stderr[-500:]}",
                "continue": True,
            }, ensure_ascii=False))

    except (json.JSONDecodeError, OSError):
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
