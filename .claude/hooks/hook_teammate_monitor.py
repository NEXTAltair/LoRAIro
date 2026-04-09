#!/usr/bin/env python3
"""
Claude Code Hooks - Teammate Monitor (TeammateIdle/TaskCreated/TaskCompleted)

Agent Teams のチームメート活動を監視する統合フック。
3つのイベントを1ファイルで処理し、hook_event_name フィールドでルーティングする。

イベント:
- TeammateIdle: チームメートがアイドル状態になる前に成果物を確認
- TaskCreated: タスク作成時に必要情報（タイトル等）を検証
- TaskCompleted: タスク完了時に変更ファイルのruff品質チェックを実行
"""

import json
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
        log_file = LOG_DIR / "hook_teammate_monitor_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def load_rules() -> dict[str, Any] | None:
    """ルールファイル読み込み"""
    rules_file = Path(__file__).parent / "rules" / "hook_teammate_rules.json"
    try:
        if not rules_file.exists():
            return None
        with rules_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def get_changed_python_files() -> list[str]:
    """git diff で変更された .py ファイルのリストを取得する"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py") and f]
        return files
    except (subprocess.TimeoutExpired, OSError):
        return []


def handle_task_completed(data: dict[str, Any], rules: dict[str, Any]) -> None:
    """TaskCompleted: 変更ファイルの ruff 品質チェック"""
    task_subject = data.get("task_subject", "")
    teammate_name = data.get("teammate_name", "unknown")

    log_debug(f"TaskCompleted: teammate={teammate_name}, task={task_subject}")

    task_config = rules.get("task_completed", {})
    if not task_config.get("run_ruff", True):
        log_debug("ruff チェック無効（ルール設定）")
        return

    # 変更された .py ファイルを特定
    changed_files = get_changed_python_files()
    if not changed_files:
        log_debug("変更された .py ファイルなし、ruff スキップ")
        return

    log_debug(f"ruff チェック対象: {changed_files}")

    # 変更ファイルのみ ruff check
    try:
        result = subprocess.run(
            ["uv", "run", "ruff", "check", *changed_files],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            violations = result.stdout.strip() or result.stderr.strip()
            log_debug(f"ruff 違反検出: {violations[:200]}")

            if task_config.get("ruff_block_on_error", False):
                # 差し戻し
                print(f"ruff 品質チェック失敗:\n{violations}", file=sys.stderr)
                sys.exit(2)
            else:
                # 警告のみ（ブロックしない）
                log_debug("ruff 違反あり（警告のみ、ブロックなし）")
        else:
            log_debug("ruff チェック通過")
    except subprocess.TimeoutExpired:
        log_debug("ruff タイムアウト")
    except OSError as e:
        log_debug(f"ruff 実行エラー: {e}")


def handle_task_created(data: dict[str, Any], rules: dict[str, Any]) -> None:
    """TaskCreated: タスク情報の検証"""
    task_subject = data.get("task_subject", "")
    teammate_name = data.get("teammate_name", "unknown")

    log_debug(f"TaskCreated: teammate={teammate_name}, subject={task_subject!r}")

    task_config = rules.get("task_created", {})
    min_length = task_config.get("min_subject_length", 5)

    if not task_subject or len(task_subject.strip()) < min_length:
        msg = f"タスク名が短すぎます（最低{min_length}文字）: {task_subject!r}"
        log_debug(f"TaskCreated ブロック: {msg}")
        print(msg, file=sys.stderr)
        sys.exit(2)

    log_debug("TaskCreated 検証通過")


def handle_teammate_idle(data: dict[str, Any], rules: dict[str, Any]) -> None:
    """TeammateIdle: 成果物の存在確認"""
    teammate_name = data.get("teammate_name", "unknown")

    log_debug(f"TeammateIdle: teammate={teammate_name}")

    idle_config = rules.get("teammate_idle", {})
    if not idle_config.get("require_changes", True):
        log_debug("成果物チェック無効（ルール設定）")
        return

    changed_files = get_changed_python_files()
    if not changed_files:
        msg = f"チームメート '{teammate_name}' の成果物（変更ファイル）が見つかりません。作業が完了しているか確認してください。"
        log_debug(f"TeammateIdle ブロック: {msg}")
        print(msg, file=sys.stderr)
        sys.exit(2)

    log_debug(f"TeammateIdle 通過: {len(changed_files)}件の変更あり")


def main() -> None:
    """メイン処理: イベント種別を判定してルーティング"""
    log_debug("=== Teammate Monitor Hook ===")

    # テスト実行時（stdin なし）は早期終了
    if sys.stdin.isatty():
        log_debug("テストモード（stdin なし）")
        sys.exit(0)

    try:
        data: dict[str, Any] = json.load(sys.stdin)
        event = data.get("hook_event_name", "")
        log_debug(f"イベント受信: {event}")

        rules = load_rules()
        if not rules:
            log_debug("ルールファイル読み込み失敗、デフォルト動作")
            sys.exit(0)

        handlers = {
            "TaskCompleted": handle_task_completed,
            "TaskCreated": handle_task_created,
            "TeammateIdle": handle_teammate_idle,
        }

        handler = handlers.get(event)
        if handler:
            handler(data, rules)
        else:
            log_debug(f"未知のイベント: {event}")

    except json.JSONDecodeError as e:
        log_debug(f"JSON 解析エラー: {e}")
    except Exception as e:
        log_debug(f"予期しないエラー: {e}")

    sys.exit(0)


if __name__ == "__main__":
    main()
