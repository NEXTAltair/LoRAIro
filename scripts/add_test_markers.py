#!/usr/bin/env python3
"""
テストファイルに pytest マーカーを一括付与するスクリプト。

使用方法:
    python scripts/add_test_markers.py --marker unit --dir tests/unit/
    python scripts/add_test_markers.py --marker integration --dir tests/integration/
    python scripts/add_test_markers.py --marker gui --dir tests/unit/gui/
    python scripts/add_test_markers.py --marker bdd --dir tests/bdd/
"""

import argparse
import re
from pathlib import Path


def add_marker_to_test_file(file_path: Path, marker_name: str) -> bool:
    """
    テストファイルに @pytest.mark.<marker> を付与する。

    既に付与されているテストはスキップ、同一ファイルに新しい関数は付与対象。

    Args:
        file_path: テストファイルのパス
        marker_name: マーカー名 (unit, integration, gui, bdd)

    Returns:
        変更があったかどうか
    """
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    original_content = "".join(lines)
    modified = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # test_ で始まる関数定義を探す（モジュールレベルまたはクラス内）
        if re.match(r"^\s*def test_", line):
            # 既に @pytest.mark.<marker> が付与されているかチェック
            if i > 0 and re.search(rf"@pytest\.mark\.{marker_name}", lines[i - 1]):
                i += 1
                continue

            # マーカーを挿入
            indent = re.match(r"^(\s*)", line).group(1)
            marker_line = f"{indent}@pytest.mark.{marker_name}\n"

            # 既に @pytest が付与されている場合は後に付与
            if i > 0 and "@pytest." in lines[i - 1]:
                # 既存のデコレータの直後に追加
                insert_position = i
                while insert_position > 0 and "@pytest." in lines[insert_position - 1]:
                    insert_position -= 1
                lines.insert(insert_position, marker_line)
                modified = True
                i += 2  # 新しい行を追加したので、インデックスを進める
            else:
                # デコレータがない場合は、関数定義の直前に追加
                lines.insert(i, marker_line)
                modified = True
                i += 2  # 新しい行を追加したので、インデックスを進める
        else:
            i += 1

    if modified:
        new_content = "".join(lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True

    return False


def main() -> None:
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="テストファイルに pytest マーカーを一括付与"
    )
    parser.add_argument(
        "--marker",
        required=True,
        choices=["unit", "integration", "gui", "bdd"],
        help="付与するマーカー名",
    )
    parser.add_argument(
        "--dir", required=True, help="対象ディレクトリ", type=Path
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の変更をせず、変更対象ファイルのみ表示",
    )

    args = parser.parse_args()

    target_dir = args.dir
    if not target_dir.exists():
        print(f"❌ ディレクトリが見つかりません: {target_dir}")
        return

    # テストファイルを収集
    test_files = sorted(target_dir.rglob("test_*.py"))

    if not test_files:
        print(f"❌ テストファイルが見つかりません: {target_dir}")
        return

    print(f"📝 マーカー付与対象: {args.marker}")
    print(f"📁 ディレクトリ: {target_dir}")
    print(f"📊 対象ファイル数: {len(test_files)}")
    print("-" * 60)

    modified_count = 0
    for test_file in test_files:
        if args.dry_run:
            print(f"[DRY-RUN] {test_file.relative_to(target_dir.parent.parent)}")
        else:
            if add_marker_to_test_file(test_file, args.marker):
                print(f"✅ {test_file.relative_to(target_dir.parent.parent)}")
                modified_count += 1
            else:
                print(f"⏭️  {test_file.relative_to(target_dir.parent.parent)}")

    print("-" * 60)
    if args.dry_run:
        print(f"[DRY-RUN] {len(test_files)} ファイルが対象です")
    else:
        print(f"✨ 完了: {modified_count}/{len(test_files)} ファイルを変更")


if __name__ == "__main__":
    main()
