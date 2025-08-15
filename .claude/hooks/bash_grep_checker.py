#!/usr/bin/env python3
"""
Claude Code Hooks - Bash Grep Checker

Bash内でのgrep系コマンド使用を監視・制御するスクリプト。

監視対象:
- rg (ripgrep) → git grep --function-context を推奨
- git grep (フラグなし) → --function-context または --show-function フラグを強制

除外対象:
- grep コマンド → permissions deny で既に処理済み
- その他のBashコマンド → 処理をスキップ

使用方法:
- matcher: "Bash" でBashコマンド実行時に呼び出される
- grep系コマンドのみを対象に条件チェックを実行
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logging() -> Path:
    """ログ設定"""
    log_dir = Path("/workspaces/LoRAIro/.claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "bash_grep_checker_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        with log_file.open("a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass  # ログエラーは無視


def main() -> None:
    """Bash内grep系コマンドの監視・制御"""

    log_file = setup_logging()
    log_debug(log_file, "=== Bash Grep Checker Started ===")

    try:
        # 標準入力からClaude Codeのフックデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Input data received: {input_data}")

        # ツール名チェック
        tool_name: str = input_data.get("tool_name", "")
        if tool_name != "Bash":
            log_debug(log_file, f"Not a Bash tool: {tool_name}, skipping")
            sys.exit(0)

        # コマンド抽出
        command: str = input_data.get("tool_input", {}).get("command", "")
        if not command:
            log_debug(log_file, "No command found, skipping")
            sys.exit(0)

        log_debug(log_file, f"Command to check: {command}")

        # rg (ripgrep) コマンドブロック
        if re.match(r"^rg\s", command):
            log_debug(log_file, "BLOCKING: rg command detected")
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "🔍 Use 'git grep --function-context <pattern> [path]' instead of ripgrep for consistent git-tracked file search with better context",
                }
            }
            print(json.dumps(output))
            sys.exit(2)  # Block command (deny permission)

        # git grep フラグチェック
        if re.match(r"^git\s+grep\s", command):
            log_debug(log_file, "git grep command detected, checking flags")

            # 必須フラグの存在確認
            if not re.search(r"(--function-context|--show-function|-W|-p)", command):
                log_debug(log_file, "BLOCKING: git grep without required context flags")
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "🔍 Add context flag to git grep for better code readability:\n\n• git grep --function-context <pattern> [path]\n• git grep --show-function <pattern> [path]\n\nThese flags show surrounding function context, making search results much more useful for code understanding.",
                    }
                }
                print(json.dumps(output))
                sys.exit(2)  # Block command (deny permission)
            else:
                log_debug(log_file, "ALLOWING: git grep with context flags")

        # その他のコマンドは処理をスキップ
        log_debug(log_file, "No grep-related issues found, allowing command")

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, skipping")
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, allowing command")

    # 正常終了(コマンドを許可)
    sys.exit(0)


if __name__ == "__main__":
    main()
