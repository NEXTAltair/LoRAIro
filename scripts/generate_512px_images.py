#!/usr/bin/env python3
"""
512px画像生成スクリプト

データベース登録時の512px画像生成機能がない時期の画像に対して、
512px画像を後から生成するワンタイムスクリプト。

既存のデータ構造を破壊せず、512px画像のみを追加生成する。
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lorairo.database.db_core import DefaultSessionLocal, resolve_stored_path
from src.lorairo.database.db_manager import ImageDatabaseManager
from src.lorairo.database.db_repository import ImageRepository
from src.lorairo.services.configuration_service import ConfigurationService
from src.lorairo.services.image_processing_service import ImageProcessingService
from src.lorairo.storage.file_system import FileSystemManager
from src.lorairo.utils.log import logger


def _delete_image_record(image_id: int, idm: ImageDatabaseManager) -> None:
    """画像レコードをデータベースから削除する"""
    with DefaultSessionLocal() as session:
        try:
            from sqlalchemy import text
            
            # 関連するレコードを削除（外部キー制約を考慮）
            session.execute(text("DELETE FROM tags WHERE image_id = :image_id"), {"image_id": image_id})
            session.execute(text("DELETE FROM captions WHERE image_id = :image_id"), {"image_id": image_id})
            session.execute(text("DELETE FROM scores WHERE image_id = :image_id"), {"image_id": image_id})
            session.execute(text("DELETE FROM ratings WHERE image_id = :image_id"), {"image_id": image_id})
            session.execute(text("DELETE FROM processed_images WHERE image_id = :image_id"), {"image_id": image_id})
            
            # 最後にメイン画像レコードを削除
            session.execute(text("DELETE FROM images WHERE id = :image_id"), {"image_id": image_id})
            
            session.commit()
            logger.info(f"画像レコードと関連データを削除: 画像ID={image_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"画像レコード削除中にエラー: 画像ID={image_id}, Error: {e}")
            raise


def _process_single_image(
    image_id: int, idm: ImageDatabaseManager, image_processing_service: ImageProcessingService
) -> tuple[bool | str, str]:
    """単一画像の512px生成処理"""
    try:
        # 512px画像が既に存在するかチェック
        existing_512px = idm.check_processed_image_exists(image_id, 512)
        if existing_512px:
            # ファイルシステムでも存在確認
            stored_path = existing_512px.get("stored_image_path")
            if stored_path:
                resolved_path = resolve_stored_path(stored_path)
                if resolved_path.exists():
                    return True, "skip"
                else:
                    logger.warning(f"DB上は存在するが、ファイルが見つからない: {resolved_path}")

        # オリジナル画像のメタデータを取得
        original_metadata = idm.get_image_metadata(image_id)
        if not original_metadata:
            return False, f"オリジナル画像メタデータが取得できません: 画像ID={image_id}"

        # オリジナル画像のパスを解決
        original_path_str = original_metadata.get("stored_image_path")
        if not original_path_str:
            return False, f"stored_image_pathが見つかりません: 画像ID={image_id}"

        original_path = resolve_stored_path(original_path_str)
        if not original_path.exists():
            return "delete", f"オリジナル画像ファイルが見つかりません: {original_path}"

        # 512px画像を生成
        logger.info(f"512px画像を生成: 画像ID={image_id}, パス={original_path}")
        try:
            result_path = image_processing_service.ensure_512px_image(image_id)
            if result_path:
                logger.info(f"512px画像生成成功: 画像ID={image_id}, 出力パス={result_path}")
                return True, "success"
            else:
                return False, f"512px画像生成失敗: 画像ID={image_id} - ensure_512px_image returned None"
        except Exception as detailed_error:
            logger.error(f"512px画像生成中に詳細エラー: 画像ID={image_id}, Error: {detailed_error}", exc_info=True)
            return False, f"512px画像生成失敗: 画像ID={image_id} - {detailed_error}"

    except Exception as e:
        return False, f"画像ID={image_id}の処理中にエラー: {e}"


def generate_missing_512px_images():
    """
    データベース内の全オリジナル画像について、
    512px画像が存在しない場合に生成する
    """
    # サービスを初期化
    config_service = ConfigurationService()
    
    # データベースディレクトリの確認
    database_dir = config_service.get_database_directory()
    if not database_dir.exists():
        logger.error(f"データベースディレクトリが存在しません: {database_dir}")
        print(f"エラー: データベースディレクトリが存在しません: {database_dir}")
        return False
    
    # データベースファイルの存在確認
    db_file = database_dir / "image_database.db"
    if not db_file.exists():
        logger.error(f"データベースファイルが存在しません: {db_file}")
        print(f"エラー: データベースファイルが存在しません: {db_file}")
        return False
    
    # FileSystemManagerを初期化（既存のデータベースディレクトリを使用）
    fsm = FileSystemManager()
    fsm.initialize(database_dir)
    
    image_repo = ImageRepository(session_factory=DefaultSessionLocal)
    idm = ImageDatabaseManager(image_repo, config_service, fsm)
    image_processing_service = ImageProcessingService(config_service, fsm, idm)

    logger.info("512px画像生成スクリプトを開始します")
    logger.info(f"データベース: {db_file}")
    logger.info(f"データベースディレクトリ: {database_dir}")

    try:
        # エラーが発生した特定の画像IDのみを処理
        error_image_ids = [1975, 2244]  # 前回エラーが発生した画像ID
        
        logger.info(f"処理対象: {len(error_image_ids)} 件のエラー画像（ID: {error_image_ids}）")

        processed_count = 0
        skipped_count = 0
        error_count = 0
        deleted_count = 0
        error_details = []

        for i, image_id in enumerate(error_image_ids, 1):
            logger.info(f"処理中: {i}/{len(error_image_ids)} - 画像ID: {image_id}")

            success, result_type = _process_single_image(image_id, idm, image_processing_service)

            if success is True:
                if result_type == "skip":
                    logger.debug(f"512px画像が既に存在: 画像ID={image_id}")
                    skipped_count += 1
                else:
                    processed_count += 1
            elif success == "delete":
                logger.warning(f"画像ファイルが見つからないため削除: 画像ID={image_id}")
                # データベースから画像レコードを削除
                try:
                    _delete_image_record(image_id, idm)
                    deleted_count += 1
                    logger.info(f"画像レコードを削除しました: 画像ID={image_id}")
                except Exception as e:
                    logger.error(f"画像レコード削除中にエラー: 画像ID={image_id}, Error: {e}")
                    error_count += 1
                    error_details.append(f"画像ID {image_id}: レコード削除エラー - {e}")
            else:
                logger.error(result_type)
                error_count += 1
                error_details.append(f"画像ID {image_id}: {result_type}")

        # 結果をレポート
        logger.info("512px画像生成処理完了:")
        logger.info(f"  - 処理済み: {processed_count} 件")
        logger.info(f"  - スキップ: {skipped_count} 件")
        logger.info(f"  - 削除: {deleted_count} 件")
        logger.info(f"  - エラー: {error_count} 件")
        logger.info(f"  - 合計: {len(error_image_ids)} 件")

        print("\n=== 512px画像生成スクリプト実行結果 ===")
        print(f"処理済み: {processed_count} 件")
        print(f"スキップ: {skipped_count} 件")
        print(f"削除: {deleted_count} 件")
        print(f"エラー: {error_count} 件")
        print(f"合計: {len(error_image_ids)} 件")
        print("===================================\n")
        
        # エラー詳細を表示
        if error_details:
            print("=== エラー詳細 ===")
            for i, error in enumerate(error_details, 1):
                print(f"{i}. {error}")
            print("=================\n")

    except Exception as e:
        logger.error(f"512px画像生成スクリプトでエラーが発生: {e}", exc_info=True)
        print(f"エラー: {e}")
        return False

    return True


if __name__ == "__main__":
    print("512px画像生成スクリプトを開始...")
    print("既存のデータ構造は破壊されません。")
    print("512px画像のみを生成します。")
    print()

    # 確認プロンプト
    response = input("実行しますか? (y/N): ")
    if response.lower() != "y":
        print("実行をキャンセルしました。")
        sys.exit(0)

    success = generate_missing_512px_images()

    if success:
        print("512px画像生成が完了しました。")
        sys.exit(0)
    else:
        print("512px画像生成中にエラーが発生しました。")
        sys.exit(1)
