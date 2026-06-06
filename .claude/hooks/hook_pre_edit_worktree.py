#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Edit Worktree Gate (PreToolUse Hook)

LoRAIro 本体のアプリコード (`src/`, `tests/`) を共有 checkout
(/workspaces/LoRAIro) で直接 Edit/Write しようとしたらブロックする。

目的:
- ISSUE 解決・機能開発は「worktree 作成 → そこで実装」を機械的に強制する。
  これまでルール (.claude/rules/git-workflow.md) は guidance のみで、
  Edit/Write を素通りさせていたため「修正してから後付けで worktree を作る」
  という崩れた順序が起きていた。

ブロック対象 (共有 checkout 上):
- /workspaces/LoRAIro/src/**
- /workspaces/LoRAIro/tests/**

ブロックしない (意図的に共有 checkout で作業してよいもの):
- /workspaces/LoRAIro/.agents/worktree/** (worktree 内なら何でも可)
- local_packages/** (submodule は editable install のため in-place 運用が正。
  worktree だと editable 解決が壊れる。memory: project_iam_lib_inplace_not_worktree)
- docs/ / .claude/ / .codex/ / .agents/ / config/ / README / .gitignore 等の
  docs・tooling chore (git-workflow.md の「worktree+PR を要さない例外」)

バイパス:
- 緊急時など main 直編集が必要な場合は環境変数 LORAIRO_ALLOW_MAIN_EDIT=1 を設定。
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path("/workspaces/LoRAIro")
WORKTREE_ROOT = Path("/workspaces/LoRAIro/.agents/worktree")
# 共有 checkout 上でブロックする LoRAIro 本体アプリコードのトップレベル dir
BLOCKED_TOPLEVEL = ("src", "tests")


def _resolve(file_path: str) -> Path | None:
    try:
        return Path(file_path).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _is_blocked(file_path: str) -> bool:
    """共有 checkout 上の LoRAIro 本体 src/ tests/ への編集なら True。"""
    resolved = _resolve(file_path)
    if resolved is None:
        return False

    # worktree 内なら常に許可
    if resolved.is_relative_to(WORKTREE_ROOT):
        return False

    # repo root 配下でなければ対象外
    if not resolved.is_relative_to(REPO_ROOT):
        return False

    rel = resolved.relative_to(REPO_ROOT)
    if not rel.parts:
        return False

    # local_packages/** は submodule in-place 運用なので除外
    if rel.parts[0] == "local_packages":
        return False

    return rel.parts[0] in BLOCKED_TOPLEVEL


def _build_message(file_path: str) -> str:
    resolved = _resolve(file_path)
    rel = resolved.relative_to(REPO_ROOT) if resolved else Path(file_path)
    return (
        "🚫 共有 checkout でのアプリコード編集はブロックされました。\n"
        f"   対象: {rel}\n"
        "→ ISSUE 解決・機能開発は worktree から開始してください "
        "(.claude/rules/git-workflow.md)。\n"
        "   git fetch origin\n"
        "   git worktree add /workspaces/LoRAIro/.agents/worktree/<branch> -b <type>/issue-<n> origin/main\n"
        "   # 以降の Edit/commit/push はこの worktree 内で行う\n"
        "→ docs/.claude 等の chore は対象外。緊急で main 直編集が必要な場合のみ "
        "LORAIRO_ALLOW_MAIN_EDIT=1 を設定。"
    )


def main() -> None:
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        if os.environ.get("LORAIRO_ALLOW_MAIN_EDIT") == "1":
            sys.exit(0)

        input_data: dict = json.load(sys.stdin)
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            sys.exit(0)

        if _is_blocked(file_path):
            reason = _build_message(file_path)
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            print(reason, file=sys.stderr)
            sys.exit(2)

        sys.exit(0)

    except (json.JSONDecodeError, OSError):
        sys.exit(0)


if __name__ == "__main__":
    main()
