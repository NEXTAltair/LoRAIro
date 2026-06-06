#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Commands (PreToolUse Hook)

LoRAIroプロジェクト用コマンド制御・変換システム。

機能:
- uv run変換（python → uv run python など）
- ブロックコマンド検出（git安全系、pip等）
- PR draft作成ブロック（agent PR は ready for review で作成）
- grep系コマンド制御（Grepツール推奨、git grepはコンテキストフラグ必須）
"""

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("/workspaces/LoRAIro/.claude/logs")
WORKTREE_ROOT = Path("/workspaces/LoRAIro/.agents/worktree")
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
    """パスが /workspaces/LoRAIro/.agents/worktree 配下かどうかを判定する。"""
    try:
        return Path(path).expanduser().resolve().is_relative_to(WORKTREE_ROOT)
    except (OSError, RuntimeError):
        return str(path).startswith(f"{WORKTREE_ROOT}/")


def _command_cd_worktree(command: str) -> bool:
    """command 内の `cd /workspaces/LoRAIro/.agents/worktree/...` を検出する。"""
    try:
        parts = shlex.split(command)
    except ValueError:
        return bool(re.search(r"\bcd\s+/workspaces/LoRAIro/\.agents/worktree(?:/|\b)", command))

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


def check_draft_pr_create(command: str) -> str | None:
    """agent-created PR が draft のまま放置されるのを防ぐ。"""
    if not re.search(r"\bgh\s+pr\s+create\b", command):
        return None
    if not re.search(r"(^|\s)--draft(?:[=\s]|$)", command):
        return None

    log_debug(f"BLOCKING: draft PR create detected: {command}")
    return (
        "🚫 agent PR を draft で作成しないでください。\n"
        "→ `--draft` を外して ready for review の PR を作成し、"
        "作成直後に agent-pr-maintainer で CI/レビュー監視を開始してください。"
    )


def _default_base_branch() -> str:
    """統合先の base ブランチ (main / master) を検出する。"""
    for base in ("main", "master"):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", base],
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return base
    return "main"


def _branch_is_integrated(branch: str) -> bool:
    """branch が base に統合済み (通常マージ / squash merge) か判定する。

    squash merge はコミットが ancestor にも patch-id 一致にもならないため、
    通常マージ判定だけでは検出できない。以下を fast→network の順で確認する:
      1. merge-base --is-ancestor : 通常マージ / fast-forward
      2. git diff --quiet base..branch : squash 直後 (branch 固有差分なし)
      3. gh で merged PR の存在 : main 進行後の squash merge を確実に検出
    """
    base = _default_base_branch()

    # 1. 通常マージ / fast-forward (branch が base の祖先)
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch, base],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    # 2. squash merge 直後: branch のツリーが base に対して固有差分を持たない
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", base, branch],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    # 3. merged PR が存在すれば統合済み (squash merge を確実に検出)
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "[]"):
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    return False


def check_branch_force_delete(command: str) -> str | None:
    """git branch -D を「統合済みなら許可、未統合のみブロック」する。

    squash merge 運用では merged ブランチの掃除に -D が必須 (-d は祖先判定で拒否される)。
    一律ブロックは摩擦になるため、base へ統合済みか動的に判定する。
    """
    if not re.search(r"git\s+branch\s+(-D|--delete\s+-f)", command):
        return None

    # 複合コマンド (A && git branch -D foo; B / 改行区切り) から該当 git invocation の
    # セグメントだけを切り出す (全体 tokenize による誤抽出・誤ブロックを防ぐ)。
    # セグメントが git コマンドで始まる場合のみ対象とし、commit message や echo 内の
    # 文字列 "git branch -D ..." に誤反応しないようにする。
    segments = re.split(r"&&|\|\||;|\||&|[\r\n]+", command)
    target_seg = None
    for seg in segments:
        stripped = seg.strip()
        # 先頭の VAR=val 環境変数を許容しつつ git コマンドで始まることを要求
        if not re.match(r"^(?:\w+=\S+\s+)*git\b", stripped):
            continue
        if re.search(r"\bbranch\b", stripped) and re.search(r"(-D|--delete\s+-f)", stripped):
            target_seg = stripped
            break
    if target_seg is None:
        return None

    # 削除対象ブランチ名を抽出 (フラグでない引数)
    try:
        tokens = shlex.split(target_seg)
    except ValueError:
        return None
    if "branch" not in tokens:
        return None
    # branch 名を収集: フラグはスキップ、リダイレクト/シェルメタ文字で打ち切る
    # (例: `git branch -D foo 2>&1 | tee log` から ['foo'] のみ抽出)
    branch_args: list[str] = []
    for token in tokens[tokens.index("branch") + 1 :]:
        if token.startswith("-"):
            continue
        if re.search(r"[<>&|$`()]", token):
            break
        branch_args.append(token)
    if not branch_args:
        # 形が読めない場合は判定せず他ルールに委ねる (誤許可を避ける)
        return None

    unmerged = [b for b in branch_args if not _branch_is_integrated(b)]
    if not unmerged:
        log_debug(f"ALLOW branch -D (integrated): {branch_args}")
        return None

    log_debug(f"BLOCKING: branch -D on unmerged branch(es): {unmerged}")
    return (
        f"🚫 git branch -D: base へ未統合の可能性があるブランチを強制削除しようとしています: {unmerged}\n"
        "→ squash merge 済みなら main へ pull 後に再試行 (統合判定が通ります)。\n"
        "→ 本当に破棄してよい場合のみ、ユーザー確認の上で実行してください。"
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


def emit_block(reason: str) -> None:
    """Block the tool call and emit a reason for clients that read stderr."""
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    print(reason, file=sys.stderr)
    sys.exit(2)


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

        # PR draft作成制御
        draft_pr_msg = check_draft_pr_create(command)
        if draft_pr_msg:
            emit_block(draft_pr_msg)

        # worktree 内 uv 実行制御
        worktree_uv_msg = check_worktree_uv_environment(command, input_data)
        if worktree_uv_msg:
            emit_block(worktree_uv_msg)

        # grep系コマンド制御
        grep_msg = check_grep_command(command)
        if grep_msg:
            emit_block(grep_msg)

        # git branch -D 制御 (統合済みなら許可、未統合のみブロック)
        branch_del_msg = check_branch_force_delete(command)
        if branch_del_msg:
            emit_block(branch_del_msg)

        # ブロックチェック
        block_msg = check_blocked(command, rules)
        if block_msg:
            emit_block(block_msg)

        # uv run変換
        uv_cmd = apply_uv_transform(command, rules)
        if uv_cmd:
            emit_block(f"🔄 uv run変換: {uv_cmd}\n元: {command}")

        sys.exit(0)

    except Exception as e:
        log_debug(f"Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
