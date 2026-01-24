#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Commands (PreToolUse Hook)

LoRAIroプロジェクト用コマンド制御・変換システム。

機能:
- Makefile変換（pytest → make test など）
- uv run変換（python → uv run python など）
- ブロックコマンド検出
"""

import json
import re
import subprocess
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


def apply_makefile_transform(command: str, rules: dict[str, Any]) -> str | None:
    """Makefile変換: pytest → make test など"""
    for rule in rules.get("makefile_transforms", []):
        pattern = rule.get("pattern", "")
        target = rule.get("transform", "")
        if re.search(pattern, command):
            log_debug(f"Makefile transform: {command} → {target}")
            return target
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


def call_external_script(script_name: str, hook_data: str) -> int:
    """外部スクリプト呼び出し"""
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        return 0
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            input=hook_data, capture_output=True, text=True, timeout=30
        )
        if result.stdout:
            print(result.stdout, end="")
        return result.returncode
    except Exception:
        return 0


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

        # rg/git grep → 外部スクリプト
        if re.match(r"^rg\s", command):
            sys.exit(call_external_script("read_mcp_memorys.py", json.dumps(input_data)))
        if re.match(r"^git\s+grep", command):
            sys.exit(call_external_script("bash_grep_checker.py", json.dumps(input_data)))

        # ブロックチェック
        block_msg = check_blocked(command, rules)
        if block_msg:
            print(json.dumps({"decision": "block", "reason": block_msg}, ensure_ascii=False))
            sys.exit(2)

        # Makefile変換
        make_cmd = apply_makefile_transform(command, rules)
        if make_cmd:
            print(json.dumps({
                "decision": "block",
                "reason": f"🔄 Makefile使用: {make_cmd}\n元: {command}"
            }, ensure_ascii=False))
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
