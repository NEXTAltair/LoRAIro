#!/usr/bin/env python3
"""SessionStart Hook - セッション開始時のコンテキスト復元.

セッション開始時に以下の情報を表示:
- 最新のSerena Memories (plan_*.md)
- 現在のプロジェクト状況
- 推奨される初期アクション
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def get_recent_memories(memories_dir: Path, limit: int = 3) -> list[Path]:
    """最新のplan_*.mdメモリファイルを取得する."""
    if not memories_dir.exists():
        return []

    plan_files = list(memories_dir.glob("plan_*.md"))
    return sorted(plan_files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def get_git_branch() -> str | None:
    """現在のgitブランチ名を取得する."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def main() -> None:
    """メイン処理."""
    project_root = Path("/workspaces/LoRAIro")
    memories_dir = project_root / ".serena" / "memories"

    # ヘッダー
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Session started at {timestamp}")
    print()

    # Git ブランチ情報
    branch = get_git_branch()
    if branch:
        print(f"Current branch: {branch}")
        print()

    # 最新のSerena Memories
    recent_memories = get_recent_memories(memories_dir)
    if recent_memories:
        print("Recent Serena Memories:")
        for memory in recent_memories:
            mtime = datetime.fromtimestamp(memory.stat().st_mtime)
            print(f"  - {memory.name} ({mtime.strftime('%m/%d %H:%M')})")
        print()

    # プロジェクト状況ファイルの確認
    status_file = memories_dir / "current-project-status"
    if status_file.exists():
        print("Tip: Read 'current-project-status' for project context")
        print("  mcp__serena__read_memory('current-project-status')")
        print()

    # 推奨アクション
    print("Recommended actions:")
    print("  - /check-existing [feature] - Check for existing solutions")
    print("  - /planning [task] - Plan implementation strategy")
    print("  - /verify - Run quality checks")

    sys.exit(0)


if __name__ == "__main__":
    main()
