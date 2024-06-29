from pathlib import Path
from module.config import get_config
from module.log import setup_logger, get_logger
from module.db import DatabaseManager
from module.file_sys import FileSystemManager
from ImageEditor import ImageProcessingManager
from caption_tags import ImageAnalyzer
import traceback

def start_processing():
    # 設定ファイル読み込み
    config = get_config('processing.toml')

    # ロギング開始
    setup_logger(config['log'])
    logger = get_logger(__name__)
    logger.info("プログラムの開始")

    try:
        # 各マネージャーの初期化
        file_system_manager = FileSystemManager()
        file_system_manager.initialize(config)

        database_manager = DatabaseManager(config)
        database_manager.initialize()
        connection_status = database_manager.connect()
        if not connection_status:
            logger.error("データベースへの接続に失敗しました。")
            return

        image_processing_manager = ImageProcessingManager(file_system_manager)
        image_processing_manager.initialize(config)

        image_analyzer = ImageAnalyzer()
        image_analyzer.initialize(config)


        # 画像処理のメインループ
        image_files = file_system_manager.get_image_files()
        for image_file in image_files:
            logger.info(f"画像の処理: {image_file}")
            try:
                # 1. 元画像をdatabase用ディレクトリへ保存
                db_stored_original_path = file_system_manager.save_original_image(image_file)

                # 2. 元画像のメタデータを取得してDBへ保存
                original_metadata = file_system_manager.get_image_info(image_file)
                image_id, uuid = database_manager.save_original_metadata(db_stored_original_path , original_metadata)

                # 元画像のタグ､キャプションを取得してDBへ保存
                existing_annotations = image_analyzer.get_existing_annotations(image_file)
                if existing_annotations:
                    database_manager.save_annotations(image_id, existing_annotations)

                # 3. 画像の処理、保存
                processed_image = image_processing_manager.process_image(db_stored_original_path, original_metadata)
                processed_path = file_system_manager.save_processed_image(processed_image, image_file)

                # 4. 処理済み画像のメタデータを取得してDBへ保存
                processed_metadata = file_system_manager.get_image_info(processed_image)
                database_manager.save_processed_metadata(image_id, processed_path, processed_metadata)

                # 5. 処理済み画像のタグ､キャプションを作成、DBへ保存
                tags, caption = image_analyzer.analyze_image(processed_path)
                database_manager.save_annotations(image_id, {'tags': tags, 'captions': [caption]})

                logger.info(f"画像の処理が完了しました: {image_file}")

            except Exception as e:
                logger.error(f"画像の処理中にエラーが発生しました {image_file}: {str(e)}")
                logger.debug(traceback.format_exc())

        logger.info("すべての画像の処理が完了しました")

    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {str(e)}")
        logger.debug(traceback.format_exc())

    finally:
        if 'database_manager' in locals():
            database_manager.disconnect()

    logger.info("画像処理とデータベース管理システムが終了しました")

if __name__ == "__main__":
    start_processing()