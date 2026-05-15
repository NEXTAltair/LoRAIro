#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-PR Submodule Check (PreToolUse Hook for `gh pr create`)

`gh pr create` 実行時に submodule 変更を含む PR を検知し、CI-equivalent test
の実行確認を要求する gate。

検知条件:
- command が `gh pr create` を含む
- `git diff --name-only origin/main...HEAD` が `local_packages/*` を含む

通過条件 (いずれか):
- command 文字列に `CI-EQUIV-TESTED` marker を含む (テスト実行ログを兼ねる)
- submodule 変更を含まない PR (普通の PR)
- git diff が失敗 (detached HEAD 等) → graceful degrade で allow

詳細:
- 影響を受ける package と対応する CI filter は rules JSON で管理
- `.claude/rules/testing.md` の "CI-equivalent filter で local 検証する" セクション参照

実装背景: iam-lib #62 (lazy torch refactor) → LoRAIro #260 で CI 失敗を未然に防げな
かった見落としの再発防止。`-m unit` 等の短縮 filter のみで local 検証完了とみなした
ことが原因。
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("/workspaces/LoRAIro/.claude/logs")
PROJECT_DIR = Path("/workspaces/LoRAIro")


def log_debug(message: str) -> None:
    """デバッグログ出力"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "hook_pre_pr_submodule_check_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def load_rules() -> dict[str, Any] | None:
    """ルールファイル読み込み"""
    rules_file = Path(__file__).parent / "rules" / "hook_pre_pr_submodule_check_rules.json"
    try:
        if not rules_file.exists():
            return None
        with rules_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def is_gh_pr_create(command: str) -> bool:
    """command が `gh pr create` を呼び出しているか判定"""
    return bool(re.search(r"\bgh\s+pr\s+create\b", command))


def get_submodule_changes() -> list[str]:
    """現 branch と origin/main の差分から local_packages/* の変更パスを返す"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log_debug(f"git diff failed: {result.stderr[:200]}")
            return []
        changed = result.stdout.strip().split("\n")
        # local_packages/<pkg>/ 配下の変更のみ抽出
        return [f for f in changed if f.startswith("local_packages/") and "/" in f[len("local_packages/") :]]
    except (subprocess.TimeoutExpired, OSError) as e:
        log_debug(f"git diff exception: {e}")
        return []


def identify_affected_packages(changes: list[str], packages: dict[str, Any]) -> set[str]:
    """変更パスから影響を受ける package path を特定"""
    affected: set[str] = set()
    for path in changes:
        for pkg_path in packages:
            if path.startswith(pkg_path):
                affected.add(pkg_path)
    return affected


def build_reminder(affected: set[str], packages: dict[str, Any], bypass_marker: str) -> str:
    """block 時の reminder メッセージを構築"""
    lines = [
        "🚫 submodule 変更を含む PR を作成しようとしていますが、",
        "    CI-equivalent test の実行確認 (marker) が command に含まれていません。",
        "",
        "影響を受ける package と CI-equivalent コマンド:",
    ]
    for pkg_path in sorted(affected):
        pkg_config = packages[pkg_path]
        lines.append(f"  - {pkg_path}")
        lines.append(f"    cd {pkg_config['working_directory']}")
        lines.append(f"    uv run pytest {pkg_config['ci_filter']}")
    lines.extend(
        [
            "",
            f"テスト pass を確認後、command 内に '{bypass_marker}' marker を含めて再実行してください。",
            "例:",
            "",
            f"  # {bypass_marker}: ran `uv run pytest ...` -> N passed",
            '  gh pr create --title "..." --body "..."',
            "",
            "詳細: .claude/rules/testing.md の 'CI-equivalent filter で local 検証する' セクション参照",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    log_debug("=== Pre-PR Submodule Check Hook ===")

    try:
        input_data: dict[str, Any] = json.load(sys.stdin)
        command = input_data.get("tool_input", {}).get("command", "")
        if not command or not is_gh_pr_create(command):
            sys.exit(0)

        log_debug(f"gh pr create detected: {command[:200]}")

        rules = load_rules() or {}
        bypass_marker = rules.get("bypass_marker", "CI-EQUIV-TESTED")
        packages = rules.get("packages", {})

        changes = get_submodule_changes()
        if not changes:
            log_debug("no submodule changes (or git diff failed), allow")
            sys.exit(0)

        affected = identify_affected_packages(changes, packages)
        if not affected:
            log_debug(f"changes outside known packages: {changes}")
            sys.exit(0)

        if bypass_marker in command:
            log_debug(f"bypass marker '{bypass_marker}' detected, allow")
            sys.exit(0)

        reminder = build_reminder(affected, packages, bypass_marker)
        log_debug(f"BLOCKING: affected packages={sorted(affected)}")
        print(json.dumps({"decision": "block", "reason": reminder}, ensure_ascii=False))
        sys.exit(2)

    except Exception as e:
        log_debug(f"Error: {e}")
        # 失敗時は allow (gracefully degrade — block over-fire を避ける)
        sys.exit(0)


if __name__ == "__main__":
    main()
