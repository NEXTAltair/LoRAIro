#!/usr/bin/env python3
"""
Claude Code Hooks - Grep Tool Blocker

Claude CodeのGrepツール使用を完全ブロックし、
git grep --function-context の使用を推奨する専用スクリプト。

使用方法:
- matcher: "Grep" でGrepツールの使用時に呼び出される
- 常にブロックし、適切な代替案を提示
"""

import json
import sys


def main() -> None:
    """Grepツールを完全にブロックし、git grepの使用を推奨"""

    # Claude CodeのGrepツール使用を完全ブロック
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "🔍 Use 'git grep --function-context <pattern> [path]' instead of Grep tool for better code search with function context and git-tracked files only",
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
