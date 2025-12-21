#!/usr/bin/env python3
"""
Claude Code Hooks - Post-Tool-Use Hook for Plan Mode

Plan Mode終了時に.claude/plans/の計画をSerena Memoryに自動同期

機能:
- ExitPlanMode検知時に最新のplanファイルを.serena/memories/に同期
- ファイル名: plan_{topic}_{YYYY_MM_DD}.md
- Metadata追加（created, source, original_file）
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logging() -> Path:
    """ログ設定"""
    log_dir = Path("/workspaces/LoRAIro/.claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hook_post_plan_mode.log"


def log_debug(log_file: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def sanitize_topic(topic: str) -> str:
    """トピック名をファイル名用にサニタイズ"""
    # ハイフンをアンダースコアに置換
    sanitized = topic.replace("-", "_")
    # 英数字とアンダースコア以外を除去
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "", sanitized)
    return sanitized.lower()


def find_latest_plan_file(plans_dir: Path, log_file: Path) -> Path | None:
    """最新のplanファイルを検索"""
    if not plans_dir.exists():
        log_debug(log_file, f"Plans directory does not exist: {plans_dir}")
        return None

    # .mdファイルを検索
    plan_files = list(plans_dir.glob("*.md"))

    if not plan_files:
        log_debug(log_file, "No plan files found")
        return None

    # 最新のファイルを取得（更新時刻順）
    latest_file = max(plan_files, key=lambda f: f.stat().st_mtime)
    log_debug(log_file, f"Latest plan file: {latest_file}")

    return latest_file


def extract_topic_from_plan(plan_file: Path, log_file: Path) -> str:
    """planファイルからトピックを抽出"""
    # ファイル名から抽出（例: "moonlit-munching-yeti.md" → "moonlit-munching-yeti"）
    topic = plan_file.stem
    log_debug(log_file, f"Extracted topic from filename: {topic}")

    return topic


def sync_plan_to_serena(plan_file: Path, log_file: Path) -> tuple[bool, str]:
    """Plan Modeの計画をSerena Memoryに同期"""
    try:
        # トピック抽出
        topic_raw = extract_topic_from_plan(plan_file, log_file)
        topic = sanitize_topic(topic_raw)

        # Plan内容読み込み
        with plan_file.open("r", encoding="utf-8") as f:
            plan_content = f.read()

        log_debug(log_file, f"Read plan content ({len(plan_content)} chars)")

        # Memory file名生成
        today = datetime.now().strftime("%Y_%m_%d")
        memory_filename = f"plan_{topic}_{today}.md"
        memory_path = Path("/workspaces/LoRAIro/.serena/memories") / memory_filename

        # Metadata追加
        metadata = f"""# Plan: {topic_raw}

**Created**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Source**: plan_mode
**Original File**: {plan_file.name}
**Status**: planning

---

"""

        # Memory file書き込み
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        with memory_path.open("w", encoding="utf-8") as f:
            f.write(metadata + plan_content)

        log_debug(log_file, f"Successfully synced plan to: {memory_path}")

        return True, f"✅ Plan synced to Serena Memory: {memory_filename}"

    except Exception as e:
        log_debug(log_file, f"Error syncing plan: {e}")
        return False, f"⚠️ Failed to sync plan: {e}"


def main() -> None:
    """メイン処理"""
    log_file = setup_logging()
    log_debug(log_file, "=== Post-Plan-Mode Hook Started ===")

    try:
        # 標準入力からhookデータを読み取り
        input_data: dict[str, Any] = json.load(sys.stdin)
        log_debug(log_file, "Hook input data received")

        # Tool名を確認
        tool_name = input_data.get("tool_name", "")
        log_debug(log_file, f"Tool name: {tool_name}")

        # ExitPlanModeでない場合はスキップ
        if tool_name != "ExitPlanMode":
            log_debug(log_file, f"Not ExitPlanMode (got: {tool_name}), skipping")
            sys.exit(0)

        # Plans directorを検索
        plans_dir = Path("/home/vscode/.claude/plans")
        plan_file = find_latest_plan_file(plans_dir, log_file)

        if not plan_file:
            log_debug(log_file, "No plan file found, exiting")
            sys.exit(0)

        # Serena Memoryに同期
        success, message = sync_plan_to_serena(plan_file, log_file)

        # 結果メッセージ出力（Claude Codeのユーザーに表示される）
        print(message)

        log_debug(log_file, f"Hook completed: {'success' if success else 'failed'}")
        sys.exit(0)

    except json.JSONDecodeError as e:
        log_debug(log_file, f"JSON decode error: {e}")
        sys.exit(0)
    except Exception as e:
        log_debug(log_file, f"Unexpected error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
