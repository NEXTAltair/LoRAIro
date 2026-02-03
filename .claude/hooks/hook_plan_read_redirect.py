#!/usr/bin/env python3
"""Claude Code Hooks - Plan Read Redirect (PreToolUse Hook)

.claude/plans/ への Read アクセスをブロックし、
Serena Memory (mcp__serena__read_memory) へリダイレクトする。

背景:
- Plan Mode で作成された計画は PostToolUse hook で .serena/memories/plan_* に同期される
- 外部ツール（Codex等）で計画が添削・更新された場合、Serena Memory側が最新版となる
- .claude/plans/ は古い版のままなので、常にSerena Memoryを参照すべき
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logging() -> Path:
    """ログ設定"""
    log_dir = Path("/workspaces/LoRAIro/.claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hook_plan_read_redirect.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def find_matching_serena_memory(plan_filename: str, log_file: Path) -> str | None:
    """planファイル名に対応するSerena Memoryを検索する。

    Args:
        plan_filename: planファイルのstem (例: "composed-discovering-ullman")
        log_file: ログファイル

    Returns:
        対応するSerena memoryファイル名、見つからない場合はNone
    """
    memories_dir = Path("/workspaces/LoRAIro/.serena/memories")
    if not memories_dir.exists():
        return None

    # ハイフンをアンダースコアに変換して検索
    sanitized = plan_filename.replace("-", "_").lower()
    pattern = f"plan_{sanitized}_*.md"

    matches = sorted(memories_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        memory_name = matches[0].stem
        log_debug(log_file, f"Found matching memory: {memory_name}")
        return memory_name

    log_debug(log_file, f"No matching memory for pattern: {pattern}")
    return None


def main() -> None:
    """メイン処理"""
    log_file = setup_logging()
    log_debug(log_file, "=== Plan Read Redirect Hook Started ===")

    try:
        input_data: dict[str, Any] = json.load(sys.stdin)

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Read ツール以外はスキップ
        if tool_name != "Read":
            sys.exit(0)

        file_path = tool_input.get("file_path", "")
        log_debug(log_file, f"Read target: {file_path}")

        # .claude/plans/ へのアクセスかチェック
        if ".claude/plans/" not in file_path and "/.claude/plans/" not in file_path:
            sys.exit(0)

        log_debug(log_file, "BLOCKING: .claude/plans/ read detected")

        # planファイル名を抽出
        plan_path = Path(file_path)
        plan_stem = plan_path.stem

        # 対応するSerena Memoryを検索
        memory_name = find_matching_serena_memory(plan_stem, log_file)

        if memory_name:
            reason = (
                f"🔄 .claude/plans/ は古い版の可能性があります。\n"
                f"Serena Memoryの最新版を使用してください:\n\n"
                f"  mcp__serena__read_memory('{memory_name}')\n\n"
                f"計画は外部で添削・更新されている可能性があるため、"
                f"常にSerena Memory側を正とします。"
            )
        else:
            reason = (
                "🔄 .claude/plans/ は古い版の可能性があります。\n"
                "Serena Memoryの最新版を使用してください:\n\n"
                "  mcp__serena__list_memories() で plan_ prefix のメモリを確認\n"
                "  mcp__serena__read_memory('plan_...') で最新版を取得\n\n"
                "計画は外部で添削・更新されている可能性があるため、"
                "常にSerena Memory側を正とします。"
            )

        response = {"decision": "block", "reason": reason}
        print(json.dumps(response, ensure_ascii=False, indent=2))
        sys.exit(2)

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}")
        sys.exit(0)
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
