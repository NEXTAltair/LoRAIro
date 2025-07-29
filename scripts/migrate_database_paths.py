#!/usr/bin/env python3
"""
データベースパス修正マイグレーションスクリプト

不整合なパスレコードを削除ではなく修正により救済し、
絶対パスを相対パスに正規化してクロスプラットフォーム対応を実現。

Usage:
    python scripts/migrate_database_paths.py [database_path]

Example:
    python scripts/migrate_database_paths.py lorairo_data/main_dataset_20250707_001/image_database.db
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from lorairo.utils.log import logger


class DatabasePathMigrator:
    """データベースパス修正マイグレーター"""

    def __init__(self, db_path: Path, project_root: Path | None = None):
        self.db_path = Path(db_path)
        self.project_root = project_root or self.db_path.parent
        self.backup_path = None
        self.migration_report = {
            "simple_fixes": 0,
            "file_based_fixes": 0,
            "estimated_fixes": 0,
            "unable_to_fix": 0,
            "deleted_records": 0,
            "details": [],
        }

    def migrate(self) -> dict:
        """メインマイグレーション処理"""
        logger.info(f"データベースパス修正マイグレーション開始: {self.db_path}")

        try:
            # 1. バックアップ作成
            self._create_backup()

            # 2. 段階的修正実行
            self._stage1_simple_path_fixes()
            self._stage2_file_existence_fixes()
            self._stage3_estimated_path_fixes()
            self._stage4_cleanup_unfixable()

            # 3. 検証・レポート
            self._validate_results()
            self._generate_report()

            logger.success("マイグレーション完了")
            return self.migration_report

        except Exception as e:
            logger.error(f"マイグレーション失敗: {e}")
            self._restore_backup()
            raise

    def _create_backup(self):
        """データベースバックアップ作成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.db_path.parent / f"{self.db_path.stem}_backup_{timestamp}.db"

        shutil.copy2(self.db_path, self.backup_path)
        logger.info(f"バックアップ作成: {self.backup_path}")

    def _restore_backup(self):
        """バックアップからリストア"""
        if self.backup_path and self.backup_path.exists():
            shutil.copy2(self.backup_path, self.db_path)
            logger.info(f"バックアップからリストア: {self.backup_path}")

    def _stage1_simple_path_fixes(self):
        """Stage 1: 簡単なパス修正"""
        logger.info("Stage 1: 簡単なパス修正を実行")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 修正パターン定義
            fixes = [
                # 絶対パス → 相対パス (Linux)
                (f"/workspaces/LoRAIro/lorairo_data/{self.db_path.parent.name}/", ""),
                (f"lorairo_data/{self.db_path.parent.name}/", ""),
                # 絶対パス → 相対パス (Windows)
                (f"C:/LoRAIro/lorairo_data/{self.db_path.parent.name}/", ""),
                (f"C:\\LoRAIro\\lorairo_data\\{self.db_path.parent.name}\\", ""),
                # 一時ディレクトリパス除去
                ("/tmp/", ""),
                # パス区切り統一
                ("\\", "/"),
                # 重複パス除去
                ("image_dataset/image_dataset/", "image_dataset/"),
                ("original_images/original_images/", "original_images/"),
            ]

            for old_pattern, new_pattern in fixes:
                # processed_images テーブル
                cursor.execute(
                    """
                    UPDATE processed_images
                    SET stored_image_path = REPLACE(stored_image_path, ?, ?)
                    WHERE stored_image_path LIKE ?
                """,
                    (old_pattern, new_pattern, f"%{old_pattern}%"),
                )

                processed_count = cursor.rowcount

                # images テーブル
                cursor.execute(
                    """
                    UPDATE images
                    SET stored_image_path = REPLACE(stored_image_path, ?, ?)
                    WHERE stored_image_path LIKE ?
                """,
                    (old_pattern, new_pattern, f"%{old_pattern}%"),
                )

                images_count = cursor.rowcount

                if processed_count + images_count > 0:
                    self.migration_report["simple_fixes"] += processed_count + images_count
                    self.migration_report["details"].append(
                        f"パターン修正: '{old_pattern}' → '{new_pattern}' "
                        f"(processed: {processed_count}, images: {images_count})"
                    )
                    logger.info(
                        f"修正: '{old_pattern}' → '{new_pattern}' (計 {processed_count + images_count} 件)"
                    )

            conn.commit()

    def _stage2_file_existence_fixes(self):
        """Stage 2: ファイル存在ベース修正"""
        logger.info("Stage 2: ファイル存在ベース修正を実行")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 不整合レコードを取得
            cursor.execute("""
                SELECT id, image_id, stored_image_path
                FROM processed_images
                WHERE stored_image_path LIKE '%/512/%'
                ORDER BY id
            """)

            records = cursor.fetchall()
            logger.info(f"512px画像レコード {len(records)} 件を検査")

            # 実際の512pxファイル一覧を作成
            actual_files = {}
            image_dataset_512 = self.project_root / "image_dataset" / "512"
            if image_dataset_512.exists():
                for file_path in image_dataset_512.glob("**/*.webp"):
                    rel_path = file_path.relative_to(self.project_root)
                    actual_files[file_path.name] = str(rel_path)

            logger.info(f"実際のファイル {len(actual_files)} 件を発見")

            fixed_count = 0
            for record_id, image_id, stored_path in records:
                current_path = self.project_root / stored_path

                # 現在のパスで存在チェック
                if current_path.exists():
                    continue  # 正常なので何もしない

                # ファイル名でマッチング試行
                filename = Path(stored_path).name
                if filename in actual_files:
                    correct_path = actual_files[filename]

                    cursor.execute(
                        """
                        UPDATE processed_images
                        SET stored_image_path = ?
                        WHERE id = ?
                    """,
                        (correct_path, record_id),
                    )

                    fixed_count += 1
                    self.migration_report["details"].append(
                        f"ファイル名マッチ修正: ID {record_id}, {stored_path} → {correct_path}"
                    )
                    logger.debug(f"ファイル名マッチ修正: {stored_path} → {correct_path}")

            self.migration_report["file_based_fixes"] = fixed_count
            logger.info(f"ファイル名マッチングで {fixed_count} 件修正")
            conn.commit()

    def _stage3_estimated_path_fixes(self):
        """Stage 3: パス推定による修正"""
        logger.info("Stage 3: パス推定による修正を実行")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 残りの不整合レコードを取得
            cursor.execute("""
                SELECT p.id, p.image_id, p.stored_image_path, i.stored_image_path as original_path
                FROM processed_images p
                JOIN images i ON p.image_id = i.id
                WHERE p.stored_image_path LIKE '%/512/%'
            """)

            records = cursor.fetchall()
            fixed_count = 0

            for record_id, image_id, stored_path, original_path in records:
                current_path = self.project_root / stored_path

                # 既に存在する場合はスキップ
                if current_path.exists():
                    continue

                # 元画像パスから推定
                estimated_paths = self._generate_candidate_paths(stored_path, original_path)

                for candidate in estimated_paths:
                    if (self.project_root / candidate).exists():
                        cursor.execute(
                            """
                            UPDATE processed_images
                            SET stored_image_path = ?
                            WHERE id = ?
                        """,
                            (candidate, record_id),
                        )

                        fixed_count += 1
                        self.migration_report["details"].append(
                            f"推定パス修正: ID {record_id}, {stored_path} → {candidate}"
                        )
                        logger.debug(f"推定パス修正: {stored_path} → {candidate}")
                        break

            self.migration_report["estimated_fixes"] = fixed_count
            logger.info(f"パス推定で {fixed_count} 件修正")
            conn.commit()

    def _generate_candidate_paths(self, stored_path: str, original_path: str) -> list[str]:
        """推定候補パスを生成"""
        candidates = []
        filename = Path(stored_path).name

        try:
            # 元画像パスから日付・ディレクトリ情報を抽出
            original_parts = Path(original_path).parts

            # パターン: image_dataset/original_images/2024/10/13/dir_name/
            if len(original_parts) >= 6 and "original_images" in original_parts:
                original_idx = list(original_parts).index("original_images")
                if len(original_parts) > original_idx + 4:
                    year = original_parts[original_idx + 1]
                    month = original_parts[original_idx + 2]
                    day = original_parts[original_idx + 3]
                    dir_name = original_parts[original_idx + 4]

                    # 推定: image_dataset/512/2024/10/13/dir_name/filename
                    estimated = f"image_dataset/512/{year}/{month}/{day}/{dir_name}/{filename}"
                    candidates.append(estimated)

                    # 推定: image_dataset/512/2024/10/13/filename (ディレクトリなし)
                    estimated_simple = f"image_dataset/512/{year}/{month}/{day}/{filename}"
                    candidates.append(estimated_simple)

        except (IndexError, ValueError):
            pass

        return candidates

    def _stage4_cleanup_unfixable(self):
        """Stage 4: 修正不可レコードのクリーンアップ"""
        logger.info("Stage 4: 修正不可レコードのクリーンアップ")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 修正不可能なレコードを特定
            cursor.execute("""
                SELECT id, image_id, stored_image_path
                FROM processed_images
                WHERE stored_image_path LIKE '%/512/%'
            """)

            unfixable_records = []
            for record_id, image_id, stored_path in cursor.fetchall():
                current_path = self.project_root / stored_path
                if not current_path.exists():
                    unfixable_records.append((record_id, stored_path))

            if unfixable_records:
                logger.warning(f"修正不可能レコード {len(unfixable_records)} 件を削除")

                for record_id, stored_path in unfixable_records:
                    cursor.execute("DELETE FROM processed_images WHERE id = ?", (record_id,))
                    self.migration_report["details"].append(f"削除: ID {record_id}, {stored_path}")

                self.migration_report["deleted_records"] = len(unfixable_records)
                self.migration_report["unable_to_fix"] = len(unfixable_records)
                conn.commit()
            else:
                logger.info("修正不可能レコードなし")

    def _validate_results(self):
        """マイグレーション結果検証"""
        logger.info("マイグレーション結果を検証")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 残存する不整合レコード数
            cursor.execute("""
                SELECT COUNT(*) FROM processed_images
                WHERE stored_image_path LIKE '%/512/%'
            """)
            remaining_512_records = cursor.fetchone()[0]

            # 実際に存在しないファイルの数
            cursor.execute("""
                SELECT stored_image_path FROM processed_images
                WHERE stored_image_path LIKE '%/512/%'
            """)

            missing_files = 0
            for (stored_path,) in cursor.fetchall():
                if not (self.project_root / stored_path).exists():
                    missing_files += 1

            logger.info(f"検証結果: 512px レコード {remaining_512_records} 件, 不整合 {missing_files} 件")

            if missing_files > 0:
                logger.warning(f"まだ {missing_files} 件の不整合が残存しています")
            else:
                logger.success("すべての不整合が解消されました")

    def _generate_report(self):
        """マイグレーションレポート生成"""
        report_path = (
            self.db_path.parent / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("データベースパス修正マイグレーションレポート\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"実行時刻: {datetime.now()}\n")
            f.write(f"対象データベース: {self.db_path}\n")
            f.write(f"プロジェクトルート: {self.project_root}\n\n")

            f.write("修正結果サマリー:\n")
            f.write(f"  簡単なパス修正: {self.migration_report['simple_fixes']} 件\n")
            f.write(f"  ファイル名マッチ修正: {self.migration_report['file_based_fixes']} 件\n")
            f.write(f"  パス推定修正: {self.migration_report['estimated_fixes']} 件\n")
            f.write(f"  削除されたレコード: {self.migration_report['deleted_records']} 件\n\n")

            f.write("修正詳細:\n")
            for detail in self.migration_report["details"]:
                f.write(f"  {detail}\n")

        logger.info(f"マイグレーションレポート作成: {report_path}")


def main():
    """メイン実行関数"""
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        # デフォルトのデータベースパス
        db_path = Path("lorairo_data/main_dataset_20250707_001/image_database.db")

    if not db_path.exists():
        print(f"エラー: データベースファイルが見つかりません: {db_path}")
        sys.exit(1)

    try:
        migrator = DatabasePathMigrator(db_path)
        report = migrator.migrate()

        print("\n" + "=" * 50)
        print("マイグレーション完了!")
        print("=" * 50)
        print(f"簡単なパス修正: {report['simple_fixes']} 件")
        print(f"ファイル名マッチ修正: {report['file_based_fixes']} 件")
        print(f"パス推定修正: {report['estimated_fixes']} 件")
        print(f"削除されたレコード: {report['deleted_records']} 件")
        print(
            f"総修正件数: {sum([report['simple_fixes'], report['file_based_fixes'], report['estimated_fixes']])} 件"
        )

    except Exception as e:
        print(f"エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
