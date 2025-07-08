#!/usr/bin/env python3
"""
既存データベースのパスを新しいプロジェクト構造に合わせて修正するスクリプト

変更内容:
- Windows区切り文字 (\) → Unix区切り文字 (/)
- output/image_dataset → image_dataset (outputプレフィックス除去)

使用方法:
    UV_PROJECT_ENVIRONMENT=.venv_linux uv run python scripts/migrate_database_paths.py <db_path>
"""

import sqlite3
import sys
from pathlib import Path


def normalize_legacy_path(old_path: str) -> str:
    """パスを新しい構造に正規化
    
    Args:
        old_path: 旧形式パス (例: "output\\image_dataset\\original_images\\...")
        
    Returns:
        str: 新形式パス (例: "image_dataset/original_images/...")
    """
    # Windows区切り文字を正規化
    path = old_path.replace('\\', '/')
    
    # output/image_dataset → image_dataset に変換
    if path.startswith('output/image_dataset/'):
        return path[7:]  # "output/" を除去 (7文字)
    elif path.startswith('output\\image_dataset\\'):
        # 万が一まだWindows形式が残っている場合
        path = path.replace('\\', '/')
        return path[7:]
    
    # 既に正しい形式の場合はそのまま
    return path


def migrate_database_paths(db_path: str):
    """データベースのパスを移行"""
    
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ データベースファイルが見つかりません: {db_path}")
        return False
    
    print(f"📦 データベースパス移行開始: {db_path}")
    
    # バックアップ作成
    backup_path = db_file.with_suffix('.db.backup')
    import shutil
    shutil.copy2(db_file, backup_path)
    print(f"💾 バックアップ作成: {backup_path}")
    
    # データベース接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Images テーブルのパス更新
        print("🔄 Images テーブルのパス更新中...")
        cursor.execute("SELECT id, original_image_path, stored_image_path FROM images")
        images = cursor.fetchall()
        
        updated_images = 0
        for image_id, original_path, stored_path in images:
            new_original = normalize_legacy_path(original_path)
            new_stored = normalize_legacy_path(stored_path)
            
            # パスが変更された場合のみ更新
            if new_original != original_path or new_stored != stored_path:
                cursor.execute("""
                    UPDATE images 
                    SET original_image_path = ?, stored_image_path = ?
                    WHERE id = ?
                """, (new_original, new_stored, image_id))
                updated_images += 1
        
        print(f"   Images: {updated_images}/{len(images)} レコードを更新")
        
        # ProcessedImages テーブルのパス更新
        print("🔄 ProcessedImages テーブルのパス更新中...")
        cursor.execute("SELECT id, stored_image_path FROM processed_images")
        processed = cursor.fetchall()
        
        updated_processed = 0
        for proc_id, stored_path in processed:
            new_stored = normalize_legacy_path(stored_path)
            
            # パスが変更された場合のみ更新
            if new_stored != stored_path:
                cursor.execute("""
                    UPDATE processed_images 
                    SET stored_image_path = ?
                    WHERE id = ?
                """, (new_stored, proc_id))
                updated_processed += 1
        
        print(f"   ProcessedImages: {updated_processed}/{len(processed)} レコードを更新")
        
        # 変更をコミット
        conn.commit()
        print("✅ パス移行が完了しました")
        
        # 検証: 更新後のサンプル表示
        print("\n📊 移行結果の検証:")
        cursor.execute("SELECT stored_image_path FROM images LIMIT 3")
        sample_paths = cursor.fetchall()
        for path, in sample_paths:
            print(f"  Images: {path}")
            
        cursor.execute("SELECT stored_image_path FROM processed_images LIMIT 3")
        sample_paths = cursor.fetchall()
        for path, in sample_paths:
            print(f"  Processed: {path}")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ エラーが発生しました: {e}")
        print(f"💾 バックアップから復元してください: {backup_path}")
        return False
    finally:
        conn.close()


def main():
    if len(sys.argv) != 2:
        print("使用方法: python scripts/migrate_database_paths.py <database_path>")
        print("例: python scripts/migrate_database_paths.py lorairo_data/main_dataset_20250707_001/image_database.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    success = migrate_database_paths(db_path)
    
    if success:
        print("\n🎉 データベースパス移行が成功しました！")
        print("💡 バックアップファイルは手動で削除してください")
    else:
        print("\n💥 移行が失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()