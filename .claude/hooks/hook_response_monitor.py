#!/usr/bin/env python3
"""
Claude Code Hooks - Response Monitor (Stop Hook)

Claude応答完了時に実行されるStop hookによるNGワード検出システム。
Claude の応答が完了した時点で、応答内容をチェックし、
NGワード検出時は警告メッセージを表示する。

特徴:
- Stop hookによる応答完了時のチェック実行
- 6カテゴリNGワード規則完全対応
- Claude Code 2025年新仕様対応
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
from typing import An


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
    """NGワード検出メイン処理"""
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


def extract_response_content(input_data: dict[str, Any], log_file: Path) -> str | None:
    """Stop hook入力データからClaude応答を抽出

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
            # response辞書内のテキストフィールドを確認
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

    # 可能性3: transcript_path からの読み取り（最新エントリ）
    transcript_path = input_data.get("transcript_path", "")
    if transcript_path and Path(transcript_path).exists():
        try:
            log_debug(log_file, f"Attempting to read transcript: {transcript_path}")
            with open(transcript_path, encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    # 最新の行（JSON形式）を確認
                    last_line = lines[-1].strip()
                    if last_line:
                        try:
                            transcript_entry = json.loads(last_line)
                            # assistant応答を探す
                            if transcript_entry.get("role") == "assistant":
                                content = transcript_entry.get("content", "")
                                if isinstance(content, str) and content.strip():
                                    log_debug(log_file, "Found response content in transcript")
                                    return content
                        except json.JSONDecodeError:
                            pass
        except (OSError, Exception) as e:
            log_debug(log_file, f"Error reading transcript: {e}")

    log_debug(log_file, "No response content found in Stop hook data")
    return None


def generate_warning_output(violations: list[str]) -> dict[str, Any]:
    """警告出力生成（Stop hookは警告のみ、ブロックはしない）"""

    violations_text = "\n".join(violations)

    warning_message = f"""⚠️ NGワード規則違反が検出されました:

{violations_text}

LoRAIroプロジェクト品質方針:
• 推測・憶測 → 具体的調査・確認実行
• 代替案提示 → 指示内容の正確実行
• 勝手な改善 → 厳密指示範囲での実装
• 追加作業禁止 → 指定タスクのみ集中
• 推奨→確実実装 → 人間意思決定尊重
• MCP適切使い分け → Serena+Cipher統合活用

今後はContext7ライブラリ検索・テスト実行による確実な検証を優先してください。"""

    return {
        "systemMessage": warning_message,
        "continue": True,  # 処理は続行（Stop hookなのでブロック不可）
        "suppressOutput": False,  # 警告メッセージを表示
    }


def main() -> None:
    """メイン処理: Claude応答完了時のNGワード監視"""

    log_file = setup_logging()
    log_debug(log_file, "=== Response Monitor (Stop Hook) Started ===")

    try:
        # 標準入力からClaude Codeのフックデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Stop hook input data: {json.dumps(input_data, indent=2)}")

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

        # NGワード検出実行
        has_violations, violations = check_ng_words(response_content, rules, log_file)

        if has_violations:
            log_debug(log_file, f"WARNING: {len(violations)} violations detected")

            # 警告出力を生成・表示
            warning_output = generate_warning_output(violations)
            print(json.dumps(warning_output, ensure_ascii=False, indent=2))

            # Stop hookでは警告のみ（ブロックなし）
            sys.exit(0)
        else:
            log_debug(log_file, "No violations detected, monitoring complete")

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, monitoring disabled")
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, monitoring disabled")

    # 正常終了
    log_debug(log_file, "Response monitoring complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
