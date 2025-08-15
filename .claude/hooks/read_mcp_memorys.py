#!/usr/bin/env python3
"""
Claude Code Hooks - Read MCP Memorys

Readツール使用時にMCPの効率的な使い分けを推奨するスクリプト。
Serena(高速・直接操作)とCipher(複雑な分析・設計)の適切な使い分けを案内。

対象:
- ソースコードファイル (.py)
- 設定ファイル (.toml, .json, .yaml等)
- ドキュメントファイル (.md)

推奨内容:
1. Serena活用 - 構造的理解、シンボル検索、進行中タスク確認
2. Cipher活用 - 設計方針、過去の設計変更結果参照

使用方法:
- matcher: "Read" でReadツール使用時に呼び出される
- ファイル種別に応じた適切なガイダンスを提供
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Any


def setup_logging() -> str:
    """ログ設定"""
    log_dir = "/workspaces/LoRAIro/.claude/logs"
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "read_mcp_memorys_debug.log")


def log_debug(log_file: str, message: str) -> None:
    """デバッグログ出力"""
    try:
        with open(log_file, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def get_file_category(file_path: str) -> str:
    """ファイルカテゴリ判定"""
    if not file_path:
        return "unknown"

    # ソースコードファイル
    code_extensions: set[str] = {".py", ".ui"}
    # 設定ファイル
    config_extensions: set[str] = {".toml", ".json", ".yaml", ".yml", ".ini", ".conf", ".cfg"}
    # ドキュメントファイル
    doc_extensions: set[str] = {".md", ".mdc", ".rst", ".txt"}

    file_ext = os.path.splitext(file_path.lower())[1]

    if file_ext in code_extensions:
        return "code"
    elif file_ext in config_extensions:
        return "config"
    elif file_ext in doc_extensions:
        return "docs"
    else:
        return "other"


def should_provide_guidance(file_path: str, file_category: str) -> bool:
    """ガイダンス提供判定"""
    # 除外パターン
    exclude_patterns: list[str] = [
        r"\.git/",
        r"__pycache__/",
        r"\.pytest_cache/",
        r"node_modules/",
        r"\.venv/",
        r"\.env",
        r"logs/",
        r"\.log$",
    ]

    for pattern in exclude_patterns:
        if re.search(pattern, file_path):
            return False

    # 対象ファイルカテゴリ
    return file_category in {"code", "config", "docs"}


def generate_guidance_message(file_path: str, file_category: str) -> str:
    """ガイダンスメッセージ生成"""

    base_message = f"📋 **{os.path.basename(file_path)} - より効率的なMCP活用:**\n\n"

    if file_category == "code":
        serena_guidance = (
            "🔍 **Serena活用推奨** (高速・構造的理解):\n"
            "• `use serena: get_symbols_overview` - ファイル構造の概要把握\n"
            "• `use serena: find_symbol <名前>` - 特定クラス・関数の詳細\n"
            "• `use serena: find_referencing_symbols` - 依存関係分析\n"
            "• `use serena: read_memory` - 進行中タスクの計画・現在状況確認\n\n"
        )
    elif file_category == "config":
        serena_guidance = (
            "⚙️ **Serena活用推奨** (設定理解):\n"
            "• `use serena: search_for_pattern` - 関連設定パターン検索\n"
            "• `use serena: read_memory` - 設定変更の計画・履歴確認\n\n"
        )
    elif file_category == "docs":
        serena_guidance = (
            "📚 **Serena活用推奨** (ドキュメント理解):\n"
            "• `use serena: search_for_pattern` - 関連ドキュメント検索\n"
            "• `use serena: read_memory` - プロジェクト概要・計画確認\n\n"
        )
    else:
        serena_guidance = ""

    cipher_guidance = (
        "🧠 **Cipher活用推奨** (設計・歴史的理解):\n"
        "• **設計方針が必要な時**: `use cipher: このモジュールの設計思想と全体アーキテクチャでの役割は?`\n"
        "• **過去の変更理由が必要な時**: `use cipher: この部分が現在の実装になった経緯と設計変更の理由は?`\n"
        "• **複合的判断が必要な時**: `use cipher: 複数の情報源を統合した包括的分析`\n\n"
    )

    efficiency_note = (
        "💡 **効率的な開発のために**:\n"
        "• 構造理解・現在状況・タスク進捗 → **Serena** (高速)\n"
        "• 設計思想・変更履歴・複合判断 → **Cipher** (深い分析)\n"
        "• 具体的コード変更 → **Serena** + 通常Read\n"
        "• 複数ファイル横断分析 → **Cipher**"
    )

    return base_message + serena_guidance + cipher_guidance + efficiency_note


def generate_rg_guidance(log_file: str, command: str) -> None:
    """rgコマンド用の段階的検索ガイダンス生成"""

    # コマンドからパターンを抽出
    import shlex

    try:
        cmd_parts = shlex.split(command)
        pattern = cmd_parts[1] if len(cmd_parts) > 1 else "<pattern>"
    except (IndexError, ValueError):
        pattern = "<pattern>"

    guidance_message = f"""🔍 **効率的な段階的検索フロー - {pattern}を探す:**

**第1段階: プロジェクト構造把握**
• `use serena: read_memory` - プロジェクト概要・アーキテクチャ確認
• `use serena: list_memories` - 関連する過去の調査結果確認

**第2段階: 的確なファイル・シンボル特定**
• `use serena: find_symbol {pattern}` - クラス・関数名の場合
• `use serena: search_for_pattern {pattern}` - 一般的なパターン検索
• `use serena: find_file "*{pattern}*"` - ファイル名の場合

**第3段階: 詳細検索（必要に応じて）**
• `git grep --function-context {pattern} <特定ファイル>` - 関数コンテキスト付き検索
• `use serena: find_referencing_symbols` - 依存関係分析

**高度な分析が必要な場合:**
• `use cipher: プロジェクト全体での"{pattern}"の使用状況と設計パターン分析`

💡 **段階的アプローチの利点:**
• MCPメモリーでプロジェクト理解 → 正確なファイル特定 → 効率的検索
• 闇雲な全文検索より高速・構造的で理解しやすい結果"""

    log_debug(log_file, "Providing RG guidance")

    # PreToolUse形式でrgコマンドをブロックし、段階的検索を推奨
    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": guidance_message,
        }
    }

    print(json.dumps(output))
    sys.exit(2)  # Block command (deny permission)


def main() -> None:
    """Readツール使用時のMCPガイダンス提供"""

    log_file = setup_logging()
    log_debug(log_file, "=== Read MCP Memorys Started ===")

    try:
        # 標準入力からClaude Codeのフックデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, f"Input data received: {input_data}")

        # ツール名チェック
        tool_name = input_data.get("tool_name")
        if tool_name not in ["Read", "Bash"]:
            log_debug(log_file, f"Not a Read or Bash tool: {tool_name}, skipping")
            sys.exit(0)

        # ツール別処理分岐
        if tool_name == "Bash":
            # Bashコマンド処理（rgコマンド）
            tool_input = input_data.get("tool_input", {})
            command = tool_input.get("command", "")

            # rgコマンドチェック
            if not command.strip().startswith("rg"):
                log_debug(log_file, f"Not an rg command: {command}, skipping")
                sys.exit(0)

            log_debug(log_file, f"RG command detected: {command}")
            generate_rg_guidance(log_file, command)
            return

        # Readツール処理
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            log_debug(log_file, "No file path found, skipping")
            sys.exit(0)

        log_debug(log_file, f"File path: {file_path}")

        # ファイルカテゴリ判定
        file_category = get_file_category(file_path)
        log_debug(log_file, f"File category: {file_category}")

        # ガイダンス提供判定
        if not should_provide_guidance(file_path, file_category):
            log_debug(log_file, "Guidance not needed for this file, skipping")
            sys.exit(0)

        # ガイダンスメッセージ生成・出力
        guidance_message = generate_guidance_message(file_path, file_category)
        log_debug(log_file, "Providing MCP guidance")

        # PreToolUse形式でガイダンスを提供(ファイル読み取り前)
        output: dict[str, Any] = {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": guidance_message},
            "suppressOutput": False,  # ガイダンスを表示
        }

        print(json.dumps(output))

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}, skipping")
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}, allowing read")

    # 正常終了(Readツールの実行を許可)
    sys.exit(0)


if __name__ == "__main__":
    main()
