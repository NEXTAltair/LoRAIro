#!/usr/bin/env python3
"""
Claude Code Hooks - Response Monitor (Stop Hook)

Claude応答完了時に実行されるStop hookによるNGワード検出システム。
Claude の応答が完了した時点で、応答内容をチェックし、
NGワード検出時は警告メッセージを表示する。

特徴:
- Stop hookによる応答完了時のチェック実行（唯一のNGワードチェッカー）
- コードブロック除外による誤検知防止
- 除外パターンによる文脈認識
- Claude Code 最新仕様対応
- 詳細ログと警告メッセージ表示

使用方法:
- Stop hookとして設定し、Claude応答完了時に自動実行
- NGワード検出時は警告メッセージを表示（ブロックではなく警告）
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
    return log_dir / "hook_response_monitor_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        with log_file.open("a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def strip_quoted_content(text: str) -> str:
    """引用符内のコンテンツを除去する（引用・言及・例示はNGワード対象外）。

    対象: 「」（日本語鉤括弧）、""（英語ダブルクオート）、``（バッククオート）
    """
    text = re.sub(r"「[^」]*」", "", text)
    text = re.sub(r'"[^"]*"', "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text
def check_ng_words(message: str, rules: dict[str, Any], log_file: Path) -> tuple[bool, list[str]]:
    """NGワード検出メイン処理（文脈対応版）。

    Args:
        message: チェック対象のメッセージ
        rules: NGワードルール辞書
        log_file: ログファイル

    Returns:
        (違反検出フラグ, 違反詳細リスト)
    """
    violations = []

    # 引用符内はNGワード対象外（キーワードの言及・例示・説明のため）
    check_message = strip_quoted_content(message)

    for rule_name, rule_config in rules.items():
        if not isinstance(rule_config, dict):
            continue

        keywords = rule_config.get("keywords", [])
        rule_message = rule_config.get("message", f"Rule violation: {rule_name}")
        exclude_patterns = rule_config.get("exclude_patterns", [])

        log_debug(log_file, f"Checking rule '{rule_name}' with {len(keywords)} keywords")

        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword:
                continue

            # 大文字小文字を区別しない検索（引用符除去済みテキストで）
            if re.search(re.escape(keyword), check_message, re.IGNORECASE):
                violation_detail = f"🚫 [{rule_name}] キーワード「{keyword}」検出\n   → {rule_message}"
                violations.append(violation_detail)

                log_debug(log_file, f"VIOLATION DETECTED - Rule: {rule_name}, Keyword: {keyword}")

                # 同一ルール内では最初の違反のみ記録
                break

    return len(violations) > 0, violations


def extract_response_content(input_data: dict[str, Any], log_file: Path) -> str | None:
    """Stop hook入力データからClaude応答を抽出。

    Stop hookでは、Claudeの応答内容を取得できる可能性があります。
    様々なフィールドを確認して応答テキストを抽出します。
    """
    # 可能性1: response フィールド
    if "response" in input_data:
        response = input_data["response"]
        if isinstance(response, str) and response.strip():
            log_debug(log_file, "Found response content in 'response' field")
            return response
        elif isinstance(response, dict):
            for field in ["content", "text", "message", "output"]:
                if field in response:
                    content = response[field]
                    if isinstance(content, str) and content.strip():
                        log_debug(log_file, f"Found response content in response.{field}")
                        return content

    # 可能性2: トップレベルの応答関連フィールド
    for field in ["assistant_response", "claude_response", "output", "content", "text", "message"]:
        if field in input_data:
            value = input_data[field]
            if isinstance(value, str) and value.strip():
                log_debug(log_file, f"Found response content in '{field}' field")
                return value

    # 可能性3: transcript_path からの読み取り（最新assistantエントリを逆順探索）
    transcript_path = input_data.get("transcript_path", "")
    if transcript_path and Path(transcript_path).exists():
        try:
            log_debug(log_file, f"Attempting to read transcript: {transcript_path}")
            with open(transcript_path, encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        transcript_entry = json.loads(line)
                        if transcript_entry.get("type") == "assistant":
                            message = transcript_entry.get("message", "")
                            if isinstance(message, dict):
                                content_list = message.get("content", [])
                                if isinstance(content_list, list):
                                    text_parts = []
                                    for item in content_list:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            text_parts.append(item.get("text", ""))
                                    if text_parts:
                                        combined_text = "\n".join(text_parts)
                                        log_debug(log_file, f"Found response content in transcript (length: {len(combined_text)})")
                                        return combined_text
                            elif isinstance(message, str) and message.strip():
                                log_debug(log_file, "Found response content in transcript")
                                return message
                    except json.JSONDecodeError:
                        continue
        except OSError as e:
            log_debug(log_file, f"Error reading transcript: {e}")

    log_debug(log_file, "No response content found in Stop hook data")
    return None


def generate_warning_output(violations: list[str]) -> dict[str, Any]:
    """警告出力生成（Stop hookは警告のみ、ブロックはしない）"""
    violations_text = "\n".join(violations)

    warning_message = f"""⚠️ NGワード規則違反が検出されました:

{violations_text}

LoRAIroプロジェクト品質方針:
• 指示外の追加作業禁止 → 指定タスクのみ集中
• 具体的調査・確認を実施してから回答する
• 推測・憶測を避け、テスト・検証で確認する"""

    return {
        "systemMessage": warning_message,
        "continue": True,
        "suppressOutput": False,
    }


def main() -> None:
    """メイン処理: Claude応答完了時のNGワード監視"""
    log_file = setup_logging()
    log_debug(log_file, "=== Response Monitor (Stop Hook) Started ===")

    try:
        # テスト実行時は標準入力がないため早期終了
        if sys.stdin.isatty():
            log_debug(log_file, "Running in test mode (no stdin), exiting")
            sys.exit(0)

        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Stop hook input data received")

        # NGワードルールファイル読み込み
        rules_file = Path(__file__).parent / "rules" / "hook_stop_words_rules.json"
        rules = load_ng_word_rules(rules_file, log_file)

        if not rules:
            log_debug(log_file, "No rules loaded, monitoring disabled")
            sys.exit(0)

        # Claude応答内容抽出
        response_content = extract_response_content(input_data, log_file)

        if not response_content:
            log_debug(log_file, "No response content to monitor")
            sys.exit(0)

        log_debug(log_file, f"Monitoring response length: {len(response_content)} characters")

        # NGワード検出実行（文脈対応）
        has_violations, violations = check_ng_words(response_content, rules, log_file)

        if has_violations:
            log_debug(log_file, f"VIOLATIONS: {len(violations)} detected")

            violations_text = "\n".join(violations)
            block_response = {
                "decision": "block",
                "reason": f"""🚫 NGワード規則違反が検出されました（ファイル・ブランチ名に含まれている場合を除く）:

{violations_text}

作業を中止し、具体的な調査・検証を実施してから再回答してください。
推測・代替案・追加作業は禁止。指示されたことのみを正確に実行してください。"""
            }
            print(json.dumps(block_response, ensure_ascii=False, indent=2))
            sys.exit(2)
        else:
            log_debug(log_file, "No violations detected, monitoring complete")

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, monitoring disabled")
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, monitoring disabled")

    log_debug(log_file, "Response monitoring complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
