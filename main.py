from PIL import Image
from pathlib import Path
from module.config import get_config
from module.log import setup_logger, get_logger
from module.db import ImageDatabase
from ImageEditor import ImageProcessor, get_image_info
from caption_tags import process_image as generate_caption_tags
import traceback

def main():
    # 設定ファイル読み込み
    config = get_config('processing.toml')

    # ロギング開始
    log_level = config.get('log', {}).get('level', 'INFO')
    log_file = config.get('log', {}).get('file', 'app.log')
    setup_logger(log_level=log_level, log_file=log_file)
    logger = get_logger(__name__)

    # ImageProcessorの初期化
    image_processor = ImageProcessor(config, logger)

    # データベースの初期化
    output_dir = Path(config['directories']['output'])
    db_path = output_dir  / "image_dataset" / "image_database.db"
    db = ImageDatabase(db_path)

    try:
        db.connect()

        # 画像処理とデータベース更新のメインループ
        dataset_dir = Path(config['directories']['dataset'])
        for file_path in dataset_dir.rglob('*'):
            # ファイルが画像かどうかを確認
            if file_path.is_file() and file_path.suffix.lower() in config['image_extensions']:
                logger.info(f"Processing image: {file_path}")

                try:
                    # 画像の編集とDBへ登録するための情報取得
                    original_path, original_info = image_processor.save_original_and_return_metadata(file_path)
                    # 編集前の画像情報をDBに登録
                    image_id, uuid = db.add_image(original_path, original_info)

                    # 既存タグ､キャプションをtxtファイルから取得してDBに登録
                    # タグファイルの処理
                    tag_file = file_path.with_suffix('.txt')
                    if tag_file.exists():
                        with open(tag_file, 'r', encoding='utf-8') as f:
                            tags = f.read().strip()
                            db.add_text(image_id=image_id, model_id=None, text=tags, type='tag', existing=True)
                    # キャプションファイルの処理
                    caption_file = file_path.with_suffix('.caption')
                    if caption_file.exists():
                        with open(caption_file, 'r', encoding='utf-8') as f:
                            caption = f.read().strip()
                            db.add_text(image_id=image_id, model_id=None, text=caption, type='cap', existing=True)

# ----ここまで動いた----
                    # 画像処理
                    with Image.open(file_path) as img:
                        processed_img = image_processor.process_image(img)

                    # 処理後の画像情報をDBに更新
                    db.update_image(image_id, processed_img.width, processed_img.height, processed_img.format)

                    # 処理済み画像の保存
                    output_path = image_processor.save_processed_image(processed_img, file_path)

                    # キャプションとタグの生成
                    captions, tags = generate_caption_tags(processed_img, config['generation'])

                    # タグとキャプションをDBに保存
                    db.add_annotations(image_id, captions, tags)

                    logger.info(f"Successfully processed and saved: {output_path}")

                except Exception as e:
                    logger.error(f"Error processing image {file_path}: {str(e)}")
                    logger.debug(traceback.format_exc())  # スタックトレースをログに追加

            logger.info("All images processed successfully")
    except Exception as e:
        logger.error(f"An error occurred during processing: {str(e)}")
        logger.debug(traceback.format_exc())  # スタックトレースをログに追加
    finally:
        db.close()

    logger.info("Image Processing and Database Management System finished")

if __name__ == "__main__":
    main()