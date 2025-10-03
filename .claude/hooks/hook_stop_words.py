#!/usr/bin/env python3
"""
Claude Code Hooks - Stop Words Checker (PostToolUse Hook)

ツール実行結果（stdout）のNGワードチェックを行うPostToolUse hook。
元の hook_stop_words.sh の機能を Python で再実装。
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
    return log_dir / "hook_stop_words_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def load_ng_word_rules(rules_file: Path, log_file: Path) -> dict[str, Any] | None:
    """NGワードルールファイル読み込み"""
    try:
        if not rules_file.exists():
            log_debug(log_file, f"Rules file not found: {rules_file}")
            return None

        with rules_file.open("r", encoding="utf-8") as f:
            rules = json.load(f)
            log_debug(log_file, f"Loaded {len(rules)} rule categories")
            return rules
    except (OSError, json.JSONDecodeError) as e:
        log_debug(log_file, f"Error loading rules file: {e}")
        return None


def check_ng_words(
    stdout: str, rules: dict[str, Any], log_file: Path
) -> tuple[bool, list[str]]:
    """NGワード検出"""
    violations = []

    for rule_name, rule_config in rules.items():
        if not isinstance(rule_config, dict):
            continue

        keywords = rule_config.get("keywords", [])
        rule_message = rule_config.get("message", f"Rule violation: {rule_name}")

        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword:
                continue

            # 大文字小文字を区別しない検索
            if re.search(re.escape(keyword), stdout, re.IGNORECASE):
                violation_detail = (
                    f"🚫 [{rule_name}] キーワード「{keyword}」検出\n   → {rule_message}"
                )
                violations.append(violation_detail)
                log_debug(log_file, f"VIOLATION - Rule: {rule_name}, Keyword: {keyword}")
                break  # 同一ルール内では最初の違反のみ

    return len(violations) > 0, violations


def main() -> None:
    """メイン処理"""
    log_file = setup_logging()
    log_debug(log_file, "=== Stop Words Checker Started ===")

    try:
        # 標準入力からhookデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, "Hook input data received")

        # NGワードルールファイル読み込み
        rules_file = Path(__file__).parent / "rules" / "hook_stop_words_rules.json"
        rules = load_ng_word_rules(rules_file, log_file)

        if not rules:
            log_debug(log_file, "No rules loaded, allowing operation")
            sys.exit(0)

        # tool_response.stdout を取得
        tool_response = input_data.get("tool_response", {})
        stdout = tool_response.get("stdout", "")

        if not stdout:
            log_debug(log_file, "No stdout to check")
            sys.exit(0)

        log_debug(log_file, f"Checking stdout ({len(stdout)} bytes)")

        # NGワード検出
        has_violations, violations = check_ng_words(stdout, rules, log_file)

        if has_violations:
            log_debug(log_file, f"WARNING: {len(violations)} violations detected")

            # 違反内容をログにのみ記録（ユーザーには表示しない）
            violations_text = "\n".join(violations)
            log_debug(log_file, f"Violations:\n{violations_text}")

            # 処理は続行（ユーザー向け表示なし）
            sys.exit(0)
        else:
            log_debug(log_file, "No violations detected")
            sys.exit(0)

    except Exception as e:
        log_debug(log_file, f"Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()