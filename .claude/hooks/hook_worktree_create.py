#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (PostToolUse Hook)

ワークツリー作成後に共有 venv を指定して uv sync --dev を自動実行する。
ワークツリー内に .venv を作らず、新しいワークツリーで依存関係が即座に使えるようにする。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SHARED_UV_ENVIRONMENT = "/workspaces/LoRAIro/.venv"


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

        env = os.environ.copy()
        env["UV_PROJECT_ENVIRONMENT"] = SHARED_UV_ENVIRONMENT

        result = subprocess.run(
            ["uv", "sync", "--dev"],
            cwd=path,
            env=env,
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
