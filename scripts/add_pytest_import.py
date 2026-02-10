#!/usr/bin/env python3
"""
テストファイルに import pytest を自動追加するスクリプト。

@pytest.mark が使用されているテストファイルで、
import pytest がない場合に追加します。

使用方法:
    python scripts/add_pytest_import.py --dir tests/
"""

import argparse
import re
from pathlib import Path


def add_pytest_import_to_file(file_path: Path) -> bool:
    """
    テストファイルに import pytest を追加。

    Args:
        file_path: テストファイルのパス

    Returns:
        変更があったかどうか
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # @pytest.mark が使用されているか確認
    if not re.search(r"@pytest\.mark\.", content):
        return False

    # import pytest が既にあるか確認
    if re.search(r"^\s*import pytest", content, re.MULTILINE):
        return False

    # ファイルの最初のインポートセクションを找す
    lines = content.split("\n")
    import_insert_line = None
    last_import_line = 0

    for i, line in enumerate(lines):
        if re.match(r"^(from|import)\s+", line) and not line.startswith("#"):
            last_import_line = i

    if last_import_line > 0:
        # 既存のインポート最後の後に追加
        insert_line = last_import_line + 1
    else:
        # インポートセクションがない場合は、モジュール説明の後に追加
        insert_line = 0
        for i, line in enumerate(lines):
            if line and not line.startswith('"""') and not line.startswith("'''"):
                if i > 0 and (lines[i - 1].endswith('"""') or lines[i - 1].endswith("'''")):
                    insert_line = i
                    break

    lines.insert(insert_line, "import pytest")
    new_content = "\n".join(lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def main() -> None:
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="テストファイルに import pytest を自動追加"
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

    print(f"📝 import pytest 追加対象")
    print(f"📁 ディレクトリ: {target_dir}")
    print(f"📊 対象ファイル数: {len(test_files)}")
    print("-" * 60)

    modified_count = 0
    for test_file in test_files:
        if args.dry_run:
            if re.search(r"@pytest\.mark\.", open(test_file).read()):
                print(f"[DRY-RUN] {test_file.relative_to(target_dir.parent.parent)}")
        else:
            if add_pytest_import_to_file(test_file):
                print(f"✅ {test_file.relative_to(target_dir.parent.parent)}")
                modified_count += 1

    print("-" * 60)
    if args.dry_run:
        print(f"[DRY-RUN] 変更対象のファイルが表示されました")
    else:
        print(f"✨ 完了: {modified_count} ファイルに import pytest を追加")


if __name__ == "__main__":
    main()
