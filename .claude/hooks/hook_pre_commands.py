#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Commands (PreToolUse Hook)

LoRAIroプロジェクト用コマンド制御・変換システム。
元の hook_pre_commands.sh の機能を Python で再実装。

機能:
- LoRAIro環境コマンド変換（pytest → uv run pytest など）
- rg コマンド検出 → read_mcp_memorys.py 呼び出し
- git grep フラグチェック → bash_grep_checker.py 呼び出し
- ドキュメント優先推奨メッセージ
- ブロックコマンド検出とブロック
- 自動フォーマット実行（git add/commit時）
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logging() -> Path:
    """ログ設定"""
    log_dir = Path("/workspaces/LoRAIro/.claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hook_pre_commands_debug.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def load_rules(rules_file: Path, log_file: Path) -> dict[str, Any] | None:
    """ルールファイル読み込み"""
    try:
        if not rules_file.exists():
            log_debug(log_file, f"Rules file not found: {rules_file}")
            return None

        with rules_file.open("r", encoding="utf-8") as f:
            rules = json.load(f)
            log_debug(log_file, f"Loaded rules file with {len(rules)} sections")
            return rules
    except (OSError, json.JSONDecodeError) as e:
        log_debug(log_file, f"Error loading rules file: {e}")
        return None


def transform_lorairo_command(command: str, rules: dict[str, Any], log_file: Path) -> str:
    """LoRAIro環境コマンド変換"""
    transforms = rules.get("lorairo_environment_transforms", [])

    for transform in transforms:
        pattern = transform.get("pattern", "")
        transform_sed = transform.get("transform", "")
        description = transform.get("description", "")

        if re.search(pattern, command):
            log_debug(log_file, f"Pattern matched: {pattern}")
            log_debug(log_file, f"Description: {description}")

            # sedコマンドをPythonで実装
            # s/^pytest/uv run pytest/ → ^pytest を uv run pytest に置換
            match = re.match(r"s/\^?([^/]+)/([^/]+)/", transform_sed)
            if match:
                search_pattern = match.group(1)
                replacement = match.group(2)

                # 先頭マッチ（^ があるかどうか）
                if transform_sed.startswith("s/^"):
                    converted = re.sub(f"^{re.escape(search_pattern)}", replacement, command)
                else:
                    converted = command.replace(search_pattern, replacement)

                if converted != command:
                    log_debug(log_file, f"Command transformed: {command} -> {converted}")
                    return converted

    return command


def check_documentation_first(
    command: str, rules: dict[str, Any], log_file: Path
) -> list[str]:
    """ドキュメント優先推奨チェック"""
    recommendations = []
    doc_rules = rules.get("documentation_first_commands", [])

    for rule in doc_rules:
        pattern = rule.get("pattern", "")
        reason = rule.get("reason", "")
        suggestion = rule.get("suggestion", "")

        if re.search(pattern, command):
            msg = f"📚 ドキュメント優先推奨:\n理由: {reason}\n提案: {suggestion}\n"
            recommendations.append(msg)
            log_debug(log_file, f"Documentation first recommendation: {pattern}")

    return recommendations


def check_library_investigation(
    command: str, rules: dict[str, Any], log_file: Path
) -> list[str]:
    """ライブラリ調査提案チェック"""
    suggestions = []
    lib_rules = rules.get("library_investigation_suggestions", [])

    for rule in lib_rules:
        pattern = rule.get("pattern", "")
        reason = rule.get("reason", "")
        suggestion = rule.get("suggestion", "")

        if re.search(pattern, command):
            msg = f"🔬 ライブラリ調査推奨:\n理由: {reason}\n提案: {suggestion}\n"
            suggestions.append(msg)
            log_debug(log_file, f"Library investigation suggestion: {pattern}")

    return suggestions


def check_blocked_commands(
    command: str, rules: dict[str, Any], log_file: Path
) -> tuple[bool, str]:
    """ブロックコマンドチェック"""
    blocked_rules = rules.get("blocked_commands", [])

    for rule in blocked_rules:
        pattern = rule.get("pattern", "")
        reason = rule.get("reason", "")
        suggestion = rule.get("suggestion", "")

        if re.search(pattern, command):
            log_debug(log_file, f"BLOCKING: Command matched pattern: {pattern}")
            block_reason = f"🚫 コマンドがブロックされました:\n理由: {reason}\n代替案: {suggestion}"
            return True, block_reason

    return False, ""


def execute_auto_format(
    command: str, rules: dict[str, Any], log_file: Path
) -> list[str]:
    """自動フォーマット実行"""
    messages = []
    format_rules = rules.get("auto_format_commands", [])

    for rule in format_rules:
        pattern = rule.get("pattern", "")
        pre_hook = rule.get("pre_hook", "")
        description = rule.get("description", "")

        if re.search(pattern, command):
            log_debug(log_file, f"Auto-format triggered: {pattern}")
            messages.append(f"🛠️ 自動フォーマット実行: {description}")

            # $FILES 置換（git add の場合）
            actual_hook = pre_hook
            if command.startswith("git add"):
                # git add 後のファイルリストを抽出（.pyファイルのみ）
                files_part = command.replace("git add ", "").strip()
                py_files = [f for f in files_part.split() if f.endswith(".py")]

                if py_files:
                    files_str = " ".join(py_files)
                    actual_hook = pre_hook.replace("$FILES", files_str)
                    log_debug(log_file, f"Files to format: {files_str}")
                else:
                    log_debug(log_file, "No Python files found, skipping auto-format")
                    continue

            log_debug(log_file, f"Executing: {actual_hook}")
            messages.append(f"実行コマンド: {actual_hook}")

            try:
                result = subprocess.run(
                    actual_hook,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    messages.append("✅ 自動フォーマット完了")
                    log_debug(log_file, "Auto-format succeeded")
                else:
                    messages.append("⚠️ 自動フォーマット失敗 - 続行します")
                    log_debug(log_file, f"Auto-format failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                messages.append("⚠️ 自動フォーマットタイムアウト - 続行します")
                log_debug(log_file, "Auto-format timeout")
            except Exception as e:
                messages.append(f"⚠️ 自動フォーマットエラー: {e}")
                log_debug(log_file, f"Auto-format error: {e}")

    return messages


def call_external_script(script_name: str, hook_data_json: str, log_file: Path) -> int:
    """外部Pythonスクリプト呼び出し"""
    script_path = Path(__file__).parent / script_name

    if not script_path.exists():
        log_debug(log_file, f"External script not found: {script_path}")
        return 0  # スクリプトがない場合は続行

    try:
        log_debug(log_file, f"Calling external script: {script_name}")
        result = subprocess.run(
            ["python3", str(script_path)],
            input=hook_data_json,
            capture_output=True,
            text=True,
            timeout=30
        )

        log_debug(log_file, f"{script_name} exit code: {result.returncode}")

        # 外部スクリプトの出力をそのまま stdout に出力
        if result.stdout:
            print(result.stdout, end="")

        return result.returncode
    except subprocess.TimeoutExpired:
        log_debug(log_file, f"{script_name} timeout")
        return 0
    except Exception as e:
        log_debug(log_file, f"Error calling {script_name}: {e}")
        return 0


def main() -> None:
    """メイン処理"""
    log_file = setup_logging()
    log_debug(log_file, "=== Pre-Commands Hook Started ===")

    try:
        # 標準入力からhookデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        hook_data_json = json.dumps(input_data)  # 外部スクリプト用
        log_debug(log_file, "Hook input data received")

        # コマンド抽出
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            log_debug(log_file, "No command found, allowing")
            sys.exit(0)

        log_debug(log_file, f"Original command: {command}")

        # ルールファイル読み込み
        rules_file = Path(__file__).parent / "rules" / "hook_pre_commands_rules.json"
        rules = load_rules(rules_file, log_file)

        if not rules:
            log_debug(log_file, "No rules loaded, allowing operation")
            sys.exit(0)

        # === LoRAIro環境コマンド変換 ===
        transformed_command = transform_lorairo_command(command, rules, log_file)

        if transformed_command != command:
            log_debug(log_file, f"Command transformation applied")
            response = {
                "decision": "block",
                "reason": f"🔄 LoRAIro環境コマンドに自動変換: {transformed_command}\n\n元コマンド: {command}\n変換後: {transformed_command}"
            }
            print(json.dumps(response, ensure_ascii=False, indent=2))
            sys.exit(2)

        # === rg/git grep 特別処理 ===

        # rg コマンド → read_mcp_memorys.py 呼び出し
        if re.match(r"^rg\s", command):
            log_debug(log_file, "RG command detected, calling read_mcp_memorys.py")
            exit_code = call_external_script("read_mcp_memorys.py", hook_data_json, log_file)
            sys.exit(exit_code)

        # git grep コマンド → bash_grep_checker.py 呼び出し
        if re.match(r"^git\s+grep", command):
            log_debug(log_file, "Git grep command detected, calling bash_grep_checker.py")
            exit_code = call_external_script("bash_grep_checker.py", hook_data_json, log_file)
            sys.exit(exit_code)

        # === ルールベースチェック ===

        log_debug(log_file, f"🔍 Command check: {command}")

        # 1. ドキュメント優先推奨
        doc_recommendations = check_documentation_first(command, rules, log_file)
        for msg in doc_recommendations:
            print(msg)

        # 1.5. ライブラリ調査提案
        lib_suggestions = check_library_investigation(command, rules, log_file)
        for msg in lib_suggestions:
            print(msg)

        # 2. ブロックコマンドチェック
        is_blocked, block_reason = check_blocked_commands(command, rules, log_file)
        if is_blocked:
            response = {
                "decision": "block",
                "reason": block_reason
            }
            print(json.dumps(response, ensure_ascii=False, indent=2))
            sys.exit(2)

        # 3. 自動フォーマット実行
        format_messages = execute_auto_format(command, rules, log_file)
        for msg in format_messages:
            print(msg)

        log_debug(log_file, "Command allowed")
        sys.exit(0)

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, allowing operation")
        sys.exit(0)
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, allowing operation")
        sys.exit(0)


if __name__ == "__main__":
    main()