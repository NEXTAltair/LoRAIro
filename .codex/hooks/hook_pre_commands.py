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
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("/workspaces/LoRAIro/.claude/logs")
WORKTREE_ROOT = Path("/tmp/worktrees")
SHARED_UV_ENV_NAME = "UV_PROJECT_ENVIRONMENT"
SHARED_UV_ENV_VALUE = "/workspaces/LoRAIro/.venv"
SHARED_UV_ENV = f"{SHARED_UV_ENV_NAME}={SHARED_UV_ENV_VALUE}"


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


def _is_under_worktree(path: str | Path) -> bool:
    """パスが /tmp/worktrees 配下かどうかを判定する。"""
    try:
        return Path(path).expanduser().resolve().is_relative_to(WORKTREE_ROOT)
    except (OSError, RuntimeError):
        return str(path).startswith(f"{WORKTREE_ROOT}/")


def _command_cd_worktree(command: str) -> bool:
    """command 内の `cd /tmp/worktrees/...` を検出する。"""
    try:
        parts = shlex.split(command)
    except ValueError:
        return bool(re.search(r"\bcd\s+/tmp/worktrees(?:/|\b)", command))

    for index, part in enumerate(parts[:-1]):
        if part == "cd" and _is_under_worktree(parts[index + 1]):
            return True
    return False


def _runs_in_worktree(command: str, input_data: dict[str, Any]) -> bool:
    """Bash 実行コンテキストが worktree 配下かどうかを推定する。"""
    tool_input = input_data.get("tool_input", {})
    for key in ("cwd", "workdir", "working_dir"):
        value = tool_input.get(key) or input_data.get(key)
        if value and _is_under_worktree(value):
            return True

    return _command_cd_worktree(command) or _is_under_worktree(os.getcwd())


def _has_uv_invocation(command: str) -> bool:
    """uv 実行を検出する。env prefix や cd 後の実行も対象にする。"""
    return bool(re.search(r"(^|[\s;&|])(?:env\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*uv(?:\s|$)", command))


def _has_shared_uv_environment(command: str) -> bool:
    """共有 venv の UV_PROJECT_ENVIRONMENT 指定を検出する。"""
    pattern = rf"(^|[\s;&|])(?:env\s+)?{re.escape(SHARED_UV_ENV)}(?:\s|$)"
    return bool(re.search(pattern, command)) or os.environ.get(SHARED_UV_ENV_NAME) == SHARED_UV_ENV_VALUE


def _is_bare_uv_command(command: str) -> bool:
    """`uv` 単体は help 表示のみで venv を作らないため許可する。"""
    stripped = command.strip()
    if stripped == "uv":
        return True

    try:
        parts = shlex.split(stripped)
    except ValueError:
        return False

    if parts == ["uv"]:
        return True

    for separator in ("&&", ";"):
        if separator in parts:
            uv_index = parts.index(separator) + 1
            return parts[uv_index:] == ["uv"]
    return False


def check_worktree_uv_environment(command: str, input_data: dict[str, Any]) -> str | None:
    """worktree 内の uv は共有 .venv を明示させ、worktree .venv 作成を防ぐ。"""
    if not _has_uv_invocation(command):
        return None
    if not _runs_in_worktree(command, input_data):
        return None
    if _has_shared_uv_environment(command):
        return None
    if _is_bare_uv_command(command):
        return None

    log_debug(f"BLOCKING: uv without shared env in worktree: {command}")
    return (
        "🚫 worktree 内で uv を実行する場合は共有 venv を明示してください。\n"
        f"→ `{SHARED_UV_ENV} uv ...` を使用してください。\n"
        "→ venv を作らない確認目的だけなら `uv` 単体は許可されています。"
    )


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

        # worktree 内 uv 実行制御
        worktree_uv_msg = check_worktree_uv_environment(command, input_data)
        if worktree_uv_msg:
            print(json.dumps({"decision": "block", "reason": worktree_uv_msg}, ensure_ascii=False))
            sys.exit(2)

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
