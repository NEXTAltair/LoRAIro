#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Commands (PreToolUse Hook)

LoRAIroプロジェクト用コマンド制御・変換システム。

機能:
- uv run変換（python → uv run python など）
- ブロックコマンド検出（git安全系、pip等）
- grep系コマンド制御（Grepツール推奨、git grepはコンテキストフラグ必須）
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("/workspaces/LoRAIro/.claude/logs")


def log_debug(message: str) -> None:
    """デバッグログ出力"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "hook_pre_commands_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def load_rules() -> dict[str, Any] | None:
    """ルールファイル読み込み"""
    rules_file = Path(__file__).parent / "rules" / "hook_pre_commands_rules.json"
    try:
        if not rules_file.exists():
            return None
        with rules_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def apply_uv_transform(command: str, rules: dict[str, Any]) -> str | None:
    """uv run変換: python → uv run python など"""
    for rule in rules.get("uv_transforms", []):
        pattern = rule.get("pattern", "")
        sed_expr = rule.get("transform", "")
        if re.search(pattern, command):
            # sed式をPythonで処理: s/^pattern/replacement/
            match = re.match(r"s/\^?([^/]+)/([^/]+)/", sed_expr)
            if match:
                search, replace = match.group(1), match.group(2)
                converted = re.sub(f"^{re.escape(search)}", replace, command)
                if converted != command:
                    log_debug(f"UV transform: {command} → {converted}")
                    return converted
    return None


def check_blocked(command: str, rules: dict[str, Any]) -> str | None:
    """ブロックコマンドチェック"""
    for rule in rules.get("blocked_commands", []):
        pattern = rule.get("pattern", "")
        if re.search(pattern, command):
            reason = rule.get("reason", "Blocked")
            suggestion = rule.get("suggestion", "")
            return f"🚫 {reason}\n→ {suggestion}"
    return None


def check_grep_command(command: str) -> str | None:
    """grep系コマンドの制御。

    - rg/grep → Grepツール使用を推奨してブロック
    - git grep（コンテキストフラグなし） → --function-context 追加を推奨してブロック
    - git grep（コンテキストフラグあり） → 許可

    Returns:
        ブロックする場合はエラーメッセージ、許可する場合はNone
    """
    # rg (ripgrep) コマンド → Grepツール推奨
    if re.match(r"^rg\s", command):
        log_debug(f"BLOCKING: rg command detected: {command}")
        return "🔍 rg の代わりに Claude Code の Grep ツールを使用してください。\nGrep ツールはripgrepベースで高速かつ権限管理されています。"

    # bare grep コマンド → Grepツール推奨
    if re.match(r"^grep\s", command):
        log_debug(f"BLOCKING: grep command detected: {command}")
        return "🔍 grep の代わりに Claude Code の Grep ツールを使用してください。\nGrep ツールはripgrepベースで高速かつ権限管理されています。"

    # git grep（コンテキストフラグなし） → --function-context 推奨
    if re.match(r"^git\s+grep\s", command):
        has_context = bool(re.search(r"(--function-context|--show-function|-W|-p)", command))
        if not has_context:
            log_debug(f"BLOCKING: git grep without context flags: {command}")
            return (
                "🔍 git grep では --function-context または --show-function フラグを使用してください。\n"
                "→ git grep --function-context <pattern> [path]"
            )

    return None


def main() -> None:
    """メイン処理"""
    log_debug("=== Pre-Commands Hook ===")

    try:
        input_data: dict[str, Any] = json.load(sys.stdin)
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            sys.exit(0)

        log_debug(f"Command: {command}")
        rules = load_rules()
        if not rules:
            sys.exit(0)

        # grep系コマンド制御
        grep_msg = check_grep_command(command)
        if grep_msg:
            print(json.dumps({"decision": "block", "reason": grep_msg}, ensure_ascii=False))
            sys.exit(2)

        # ブロックチェック
        block_msg = check_blocked(command, rules)
        if block_msg:
            print(json.dumps({"decision": "block", "reason": block_msg}, ensure_ascii=False))
            sys.exit(2)

        # uv run変換
        uv_cmd = apply_uv_transform(command, rules)
        if uv_cmd:
            print(json.dumps({
                "decision": "block",
                "reason": f"🔄 uv run変換: {uv_cmd}\n元: {command}"
            }, ensure_ascii=False))
            sys.exit(2)

        sys.exit(0)

    except Exception as e:
        log_debug(f"Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
