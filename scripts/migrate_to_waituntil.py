#!/usr/bin/env python3
"""
qtbot.wait() から qtbot.waitUntil() への移行スクリプト。

このスクリプトは、固定時間待機 qtbot.wait() を条件待機 qtbot.waitUntil() に
段階的に移行するための支援機能を提供します。

使用方法:
    python scripts/migrate_to_waituntil.py --dir tests/ --analyze
    python scripts/migrate_to_waituntil.py --dir tests/ --suggest
"""

import argparse
import re
from pathlib import Path
from typing import NamedTuple


class WaitUsage(NamedTuple):
    """wait() 使用情報"""

    file: str
    line_no: int
    code_snippet: str
    wait_duration: int


def find_wait_usages(test_dir: Path) -> list[WaitUsage]:
    """
    qtbot.wait() の使用箇所を探索。

    Args:
        test_dir: テストディレクトリ

    Returns:
        WaitUsage のリスト
    """
    usages = []
    test_files = test_dir.rglob("test_*.py")

    for test_file in test_files:
        with open(test_file, encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if "qtbot.wait(" in line:
                # wait() の引数を抽出
                match = re.search(r"qtbot\.wait\((\d+)\)", line)
                if match:
                    duration = int(match.group(1))
                    usages.append(
                        WaitUsage(
                            file=str(test_file.relative_to(test_dir.parent.parent)),
                            line_no=i + 1,
                            code_snippet=line.strip(),
                            wait_duration=duration,
                        )
                    )

    return usages


def suggest_replacements(usages: list[WaitUsage]) -> None:
    """
    wait() 使用箇所に対する waitUntil() 移行提案を出力。

    Args:
        usages: WaitUsage のリスト
    """
    print("📋 qtbot.wait() → qtbot.waitUntil() 移行提案\n")
    print("=" * 80)

    for usage in sorted(usages, key=lambda x: (x.file, x.line_no)):
        print(f"\n📍 {usage.file}:{usage.line_no}")
        print(f"   現在: {usage.code_snippet}")
        print(f"   ⏱️  待機時間: {usage.wait_duration}ms")

        # コンテキストに応じた提案
        if "wait(50)" in usage.code_snippet:
            print(f"   提案1: qtbot.waitUntil(lambda: widget.isEnabled(), timeout={usage.wait_duration})")
            print(f"   提案2: qtbot.waitUntil(lambda: not widget.isHidden(), timeout={usage.wait_duration})")
        elif "wait(100)" in usage.code_snippet:
            print(f"   提案: qtbot.waitSignal(widget.completed, timeout={usage.wait_duration})")
            print(f"        または")
            print(f"        qtbot.waitUntil(lambda: widget.isVisible(), timeout={usage.wait_duration})")
        else:
            print(f"   提案: UI 更新完了をスグナルで待機")
            print(f"        qtbot.waitSignal(..., timeout={usage.wait_duration})")
            print(f"        または")
            print(f"        qtbot.waitUntil(lambda: condition, timeout={usage.wait_duration})")

    print("\n" + "=" * 80)
    print(f"\n✅ 合計 {len(usages)} 箇所の wait() が見つかりました\n")


def analyze_wait_distribution(usages: list[WaitUsage]) -> None:
    """
    wait() 使用の分布を分析。

    Args:
        usages: WaitUsage のリスト
    """
    print("📊 qtbot.wait() 使用分析\n")
    print("=" * 80)

    # ファイルごとの使用回数
    file_counts = {}
    for usage in usages:
        file_counts[usage.file] = file_counts.get(usage.file, 0) + 1

    print("\n📁 ファイルごとの wait() 使用回数:")
    for file, count in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"   {count:2d}回: {file}")

    # 待機時間の分布
    durations = {}
    for usage in usages:
        key = f"{usage.wait_duration}ms"
        durations[key] = durations.get(key, 0) + 1

    print("\n⏱️  待機時間の分布:")
    for duration, count in sorted(durations.items(), key=lambda x: -x[1]):
        print(f"   {count:2d}回: {duration}")

    # 改善効果の推定
    total_wait_time = sum(u.wait_duration for u in usages)
    improvement = total_wait_time * 0.5  # 50% 削減を想定
    print(f"\n🚀 改善効果:")
    print(f"   現在の無駄な待機時間: 合計 {total_wait_time}ms")
    print(f"   waitUntil 導入後: 推定 {improvement}ms 削減")
    print(f"   テスト実行時間削減: 推定 1-2秒/テストスイート\n")

    print("=" * 80)


def main() -> None:
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="qtbot.wait() → qtbot.waitUntil() 移行支援ツール"
    )
    parser.add_argument(
        "--dir", required=True, help="テストディレクトリ", type=Path
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="wait() 使用を分析",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="移行提案を表示",
    )

    args = parser.parse_args()

    if not args.dir.exists():
        print(f"❌ ディレクトリが見つかりません: {args.dir}")
        return

    # デフォルトは分析+提案の両方
    do_analyze = args.analyze or not (args.suggest)
    do_suggest = args.suggest or not (args.analyze)

    print(f"🔍 テストディレクトリをスキャン: {args.dir}\n")
    usages = find_wait_usages(args.dir)

    if not usages:
        print("✅ qtbot.wait() の使用が見つかりません\n")
        return

    if do_analyze:
        analyze_wait_distribution(usages)

    if do_suggest:
        suggest_replacements(usages)


if __name__ == "__main__":
    main()
