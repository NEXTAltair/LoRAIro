#!/usr/bin/env python3
"""
Claude Code Hooks - Assistant Response NG Word Checker

AssistantのレスポンスメッセージをPreToolUseで事前チェックし、
NGワード検出時にブロックする高精度検出システム。

特徴:
- LoRAIroプロジェクト品質方針に準拠した厳格なNGワードチェック
- 6カテゴリルール完全対応（推測・代替案・改善提案・追加作業・推奨・MCP統合環境）
- Claude Code 2025年新仕様対応（hookSpecificOutput形式）
- 詳細デバッグログによる動作状況監視

使用方法:
- matcher: "*" でAssistant応答時に自動実行
- NGワード検出時は即座にブロックし、適切なガイダンスを表示
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logging() -> Path:
    """ログ設定とディレクトリ作成"""
    log_dir = Path("/workspaces/LoRAIro/.claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hook_assistant_response_checker_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        with log_file.open("a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass  # ログエラーは無視


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


def check_ng_words(message: str, rules: dict[str, Any], log_file: Path) -> tuple[bool, list[str]]:
    """NGワード検出メイン処理

    Args:
        message: チェック対象のメッセージ
        rules: NGワードルール辞書
        log_file: ログファイル

    Returns:
        (違反検出フラグ, 違反詳細リスト)
    """
    violations = []

    for rule_name, rule_config in rules.items():
        if not isinstance(rule_config, dict):
            continue

        keywords = rule_config.get("keywords", [])
        rule_message = rule_config.get("message", f"Rule violation: {rule_name}")

        log_debug(log_file, f"Checking rule '{rule_name}' with {len(keywords)} keywords")

        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword:
                continue

            # 大文字小文字を区別しない検索
            if re.search(re.escape(keyword), message, re.IGNORECASE):
                violation_detail = f"🚫 [{rule_name}] キーワード「{keyword}」検出\n   → {rule_message}"
                violations.append(violation_detail)

                log_debug(log_file, f"VIOLATION DETECTED - Rule: {rule_name}, Keyword: {keyword}")

                # 同一ルール内では最初の違反のみ記録
                break

    return len(violations) > 0, violations


def extract_assistant_message(input_data: dict[str, Any], log_file: Path) -> str | None:
    """入力データからAssistant応答メッセージを抽出

    Claude Code のPreToolUse hookでは、様々な形式でデータが渡される可能性がある。
    複数の可能性を試して、Assistant応答メッセージを抽出する。
    """

    # 可能性1: tool_input内にメッセージが含まれる場合
    tool_input = input_data.get("tool_input", {})
    if isinstance(tool_input, dict):
        # Write/Edit ツールの content
        if "content" in tool_input:
            content = tool_input["content"]
            if isinstance(content, str) and content.strip():
                log_debug(log_file, "Found assistant message in tool_input.content")
                return content

        # その他のツール入力フィールド
        for field in ["message", "text", "response", "output"]:
            if field in tool_input:
                value = tool_input[field]
                if isinstance(value, str) and value.strip():
                    log_debug(log_file, f"Found assistant message in tool_input.{field}")
                    return value

    # 可能性2: assistant_response フィールド（カスタム拡張）
    if "assistant_response" in input_data:
        response = input_data["assistant_response"]
        if isinstance(response, str) and response.strip():
            log_debug(log_file, "Found assistant message in assistant_response")
            return response

    # 可能性3: その他のトップレベルフィールド
    for field in ["message", "content", "text", "response"]:
        if field in input_data:
            value = input_data[field]
            if isinstance(value, str) and value.strip():
                log_debug(log_file, f"Found assistant message in {field}")
                return value

    log_debug(log_file, "No assistant message found in input data")
    return None


def generate_block_response(violations: list[str]) -> dict[str, Any]:
    """ブロック応答生成（Claude Code 2025年新仕様対応）"""

    violations_text = "\n".join(violations)

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"""🚫 NGワード規則違反が検出されました:

{violations_text}

LoRAIroプロジェクトでは以下が必要です:
• 推測や憶測ではなく、具体的な調査・確認を実行
• 代替案提示ではなく、指示されたことの正確な実行
• 勝手な改善ではなく、厳密に指示したことのみ実行
• 追加作業は禁止、指示されたタスクのみに集中
• 推奨ではなく確実な実装、人間の意思決定を尊重
• MCP統合環境（Serena+Cipher）の適切な使い分け実行

Context7ライブラリ検索やテスト実行による確実な検証を優先してください。""",
        }
    }


def main() -> None:
    """メイン処理: Assistant応答NGワードチェック"""

    log_file = setup_logging()
    log_debug(log_file, "=== Assistant Response NG Word Checker Started ===")

    try:
        # 標準入力からClaude Codeのフックデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Input data received: {json.dumps(input_data, indent=2)}")

        # NGワードルールファイル読み込み
        rules_file = Path(__file__).parent / "rules" / "hook_stop_words_rules.json"
        rules = load_ng_word_rules(rules_file, log_file)

        if not rules:
            log_debug(log_file, "No rules loaded, allowing operation")
            sys.exit(0)

        # Assistant応答メッセージ抽出
        message = extract_assistant_message(input_data, log_file)

        if not message:
            log_debug(log_file, "No assistant message to check, allowing operation")
            sys.exit(0)

        log_debug(log_file, f"Checking message length: {len(message)} characters")

        # NGワード検出実行
        has_violations, violations = check_ng_words(message, rules, log_file)

        if has_violations:
            log_debug(log_file, f"BLOCKING: {len(violations)} violations detected")

            # ブロック応答を生成・出力
            block_response = generate_block_response(violations)
            print(json.dumps(block_response, ensure_ascii=False, indent=2))

            sys.exit(2)  # Block operation (deny permission)
        else:
            log_debug(log_file, "No violations detected, allowing operation")

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, allowing operation")
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, allowing operation")

    # 正常終了（操作を許可）
    log_debug(log_file, "Operation allowed")
    sys.exit(0)


if __name__ == "__main__":
    main()
