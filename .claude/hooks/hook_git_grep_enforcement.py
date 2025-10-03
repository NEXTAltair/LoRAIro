#!/usr/bin/env python3
"""
Claude Code Hooks - Git Grep Enforcement (PreToolUse Hook)

grep/rg コマンドを git grep --function-context に強制変換する hook。
元の hook_git_grep_enforcement.sh の機能を Python で再実装。
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
    return log_dir / "hook_git_grep_enforcement_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def main() -> None:
    """メイン処理"""
    log_file = setup_logging()
    log_debug(log_file, "=== Git Grep Enforcement Hook Started ===")

    try:
        # 標準入力からhookデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Hook input data received")

        # コマンド抽出
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            log_debug(log_file, "No command found, allowing")
            print(json.dumps({"decision": "allow"}))
            sys.exit(0)

        log_debug(log_file, f"Extracted command: {command}")

        # grep系コマンド以外はスキップ
        if not re.match(r"^(grep|rg|git\s+grep)", command):
            log_debug(log_file, "SKIPPING: Not a grep-related command")
            print(json.dumps({"decision": "allow"}))
            sys.exit(0)

        log_debug(log_file, "PROCESSING: grep-related command detected")

        # grep コマンドをブロック
        if re.match(r"^grep\s+", command):
            log_debug(log_file, "BLOCKING: grep command detected")
            response = {
                "decision": "block",
                "reason": "🚫 grep の代わりに git grep --function-context を使ってください。\n\nより良い検索結果のため、関数コンテキスト付きの git grep を使用してください。"
            }
            print(json.dumps(response, ensure_ascii=False, indent=2))
            sys.exit(2)

        # rg (ripgrep) コマンドをブロック
        if re.match(r"^rg\s+", command):
            log_debug(log_file, "BLOCKING: rg command detected")
            response = {
                "decision": "block",
                "reason": "🚫 rg の代わりに git grep --function-context を使ってください。\n\nGit管理ファイルの一貫性のある検索のため、git grep を使用してください。"
            }
            print(json.dumps(response, ensure_ascii=False, indent=2))
            sys.exit(2)

        # git grep でフラグなしをブロック
        if re.match(r"^git\s+grep\s+", command):
            has_context = bool(re.search(r"(--function-context|--show-function|-W|-p)", command))
            if not has_context:
                log_debug(log_file, "BLOCKING: git grep without context flags")
                response = {
                    "decision": "block",
                    "reason": "🚫 git grep では --function-context または --show-function フラグを使ってください。\n\n関数コンテキスト付きでより読みやすい検索結果を得るため、以下のように実行してください:\ngit grep --function-context <pattern> [path]"
                }
                print(json.dumps(response, ensure_ascii=False, indent=2))
                sys.exit(2)

        log_debug(log_file, "ALLOWING: Command passed all checks")
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)

    except Exception as e:
        log_debug(log_file, f"Error: {e}")
        print(json.dumps({"decision": "allow"}))
        sys.exit(0)


if __name__ == "__main__":
    main()