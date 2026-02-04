"""lorairo_output バグ修正: pHash検証付きDBパス修正スクリプト

バグ概要:
    2025-08-28以降、FileSystemManager.initialize_from_dataset_selection() が
    プロジェクトディレクトリではなく selected_dir.parent / "lorairo_output" に
    画像を保存していた。ファイルは手動移動済みの前提でDBパスのみ修正する。

検証方法:
    1. バグパス(Windows絶対パス)から image_dataset/ 以降の相対パスを抽出
    2. プロジェクトルート内にそのファイルが存在するか確認
    3. ファイルのpHashとDB記録のpHashが一致するか検証
    4. 一致した場合のみパスを更新

使い方:
    # dry-run（検証のみ、DB変更なし）
    uv run python scripts/fix_lorairo_output_paths.py --dry-run

    # 実行
    uv run python scripts/fix_lorairo_output_paths.py
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# プロジェクトルートをsys.pathに追加してlorairoモジュールを使えるようにする
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lorairo.utils.tools import calculate_phash  # noqa: E402


def find_project_root() -> Path:
    """lorairo_data 配下のプロジェクトディレクトリを自動検出"""
    lorairo_data = REPO_ROOT / "lorairo_data"
    if not lorairo_data.exists():
        print(f"ERROR: {lorairo_data} が見つかりません")
        sys.exit(1)

    project_dirs = [
        d for d in lorairo_data.iterdir() if d.is_dir() and (d / "image_database.db").exists()
    ]

    if len(project_dirs) == 0:
        print("ERROR: image_database.db を含むプロジェクトディレクトリが見つかりません")
        sys.exit(1)
    elif len(project_dirs) == 1:
        return project_dirs[0]
    else:
        print("複数のプロジェクトディレクトリが見つかりました:")
        for i, d in enumerate(project_dirs):
            print(f"  [{i}] {d.name}")
        choice = input("対象を選択してください: ")
        return project_dirs[int(choice)]


def extract_relative_path(absolute_path: str) -> str | None:
    """Windows絶対パスから image_dataset/ 以降の相対パスを抽出

    Args:
        absolute_path: DB内のバグパス

    Returns:
        相対パス (Unix形式) または None
    """
    idx = absolute_path.find("image_dataset")
    if idx < 0:
        return None
    return absolute_path[idx:].replace("\\", "/")


def fix_images_table(
    conn: sqlite3.Connection,
    project_root: Path,
    dry_run: bool,
) -> dict[str, int]:
    """images テーブルのパス修正（pHash検証付き）"""
    cur = conn.cursor()
    stats = {"total": 0, "verified": 0, "file_missing": 0, "phash_mismatch": 0, "no_relative": 0}

    cur.execute("""
        SELECT id, stored_image_path, phash FROM images
        WHERE stored_image_path NOT LIKE 'image_dataset/%'
    """)
    rows = cur.fetchall()
    stats["total"] = len(rows)

    print(f"  対象レコード数: {stats['total']}")

    for image_id, old_path, db_phash in rows:
        relative = extract_relative_path(old_path)
        if relative is None:
            stats["no_relative"] += 1
            print(f"  WARN: image_dataset が見つからない id={image_id}: {old_path}")
            continue

        actual_file = project_root / relative
        if not actual_file.exists():
            stats["file_missing"] += 1
            if stats["file_missing"] <= 10:
                print(f"  MISSING: id={image_id} {relative}")
            continue

        # pHash検証
        try:
            file_phash = calculate_phash(actual_file)
        except (ValueError, FileNotFoundError) as e:
            stats["phash_mismatch"] += 1
            print(f"  PHASH_ERR: id={image_id} {relative} - {e}")
            continue

        if file_phash != db_phash:
            stats["phash_mismatch"] += 1
            print(f"  MISMATCH: id={image_id} DB={db_phash} FILE={file_phash} {relative}")
            continue

        # 検証OK: パスを更新
        stats["verified"] += 1
        if not dry_run:
            cur.execute("UPDATE images SET stored_image_path = ? WHERE id = ?", (relative, image_id))

    return stats


def fix_processed_images_table(
    conn: sqlite3.Connection,
    project_root: Path,
    dry_run: bool,
) -> dict[str, int]:
    """processed_images テーブルのパス修正（ファイル存在確認のみ、サムネイルにpHashは不要）"""
    cur = conn.cursor()
    stats = {"total": 0, "verified": 0, "file_missing": 0, "no_relative": 0}

    cur.execute("""
        SELECT id, stored_image_path FROM processed_images
        WHERE stored_image_path NOT LIKE 'image_dataset/%'
    """)
    rows = cur.fetchall()
    stats["total"] = len(rows)

    print(f"  対象レコード数: {stats['total']}")

    for proc_id, old_path in rows:
        relative = extract_relative_path(old_path)
        if relative is None:
            stats["no_relative"] += 1
            continue

        actual_file = project_root / relative
        if not actual_file.exists():
            stats["file_missing"] += 1
            if stats["file_missing"] <= 10:
                print(f"  MISSING: proc_id={proc_id} {relative}")
            continue

        stats["verified"] += 1
        if not dry_run:
            cur.execute(
                "UPDATE processed_images SET stored_image_path = ? WHERE id = ?",
                (relative, proc_id),
            )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="pHash検証付きDBパス修正")
    parser.add_argument("--dry-run", action="store_true", help="検証のみ、DB変更なし")
    args = parser.parse_args()

    print("=" * 60)
    print("lorairo_output バグ修正: pHash検証付きDBパス修正")
    print("=" * 60)

    if args.dry_run:
        print("[DRY-RUN] 実際のDB変更は行いません\n")

    project_root = find_project_root()
    db_path = project_root / "image_database.db"
    print(f"プロジェクト: {project_root}")
    print(f"DB: {db_path}\n")

    # DBバックアップ
    if not args.dry_run:
        backup_path = db_path.with_suffix(".db.bak_before_path_fix")
        if not backup_path.exists():
            shutil.copy2(db_path, backup_path)
            print(f"バックアップ作成: {backup_path}\n")
        else:
            print(f"バックアップ既存: {backup_path}\n")

    conn = sqlite3.connect(str(db_path))

    # images テーブル修正
    print("--- images テーブル (pHash検証) ---")
    img_stats = fix_images_table(conn, project_root, args.dry_run)
    print(f"\n  検証OK: {img_stats['verified']}")
    print(f"  ファイル不在: {img_stats['file_missing']}")
    print(f"  pHash不一致: {img_stats['phash_mismatch']}")
    print(f"  パス解析失敗: {img_stats['no_relative']}")

    # processed_images テーブル修正
    print("\n--- processed_images テーブル (ファイル存在確認) ---")
    proc_stats = fix_processed_images_table(conn, project_root, args.dry_run)
    print(f"\n  検証OK: {proc_stats['verified']}")
    print(f"  ファイル不在: {proc_stats['file_missing']}")
    print(f"  パス解析失敗: {proc_stats['no_relative']}")

    if not args.dry_run:
        conn.commit()
        print("\nDB変更をコミットしました")
    conn.close()

    # サマリー
    print("\n" + "=" * 60)
    total_ok = img_stats["verified"] + proc_stats["verified"]
    total_issues = (
        img_stats["file_missing"] + img_stats["phash_mismatch"] + proc_stats["file_missing"]
    )
    print(f"修正対象: images={img_stats['total']}, processed={proc_stats['total']}")
    print(f"検証OK: {total_ok}")
    if total_issues > 0:
        print(f"問題あり: {total_issues} (ファイル不在/pHash不一致)")

    if args.dry_run:
        print("\n[DRY-RUN] 実行するには --dry-run を外してください")
    print("=" * 60)


if __name__ == "__main__":
    main()
