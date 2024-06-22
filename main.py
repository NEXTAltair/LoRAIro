from PIL import Image
from pathlib import Path
from module.config import get_config
from module.log import setup_logger, get_logger
from module.db import ImageDatabase
from ImageEditor import ImageProcessor, get_image_info
from caption_tags import process_image as generate_caption_tags
import traceback

# 注: この変数は使用されていないため、削除するか設定から読み込むように変更することを推奨します
# IMG_EXTRNSIONDS = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp']

def main():
    # 設定ファイル読み込み
    config = get_config('processing.toml')

    # ロギング開始
    log_level = config.get('log', {}).get('level', 'INFO')
    log_file = config.get('log', {}).get('file', 'app.log')
    setup_logger(log_level=log_level, log_file=log_file)
    logger = get_logger(__name__)

    logger.info("Starting Image Database Management System")

    # ImageProcessorの初期化
    image_processor = ImageProcessor(config)

    # データベースの初期化
    db = ImageDatabase(config['directories'].get('database', 'image_database.sqlite'))

    try:
        db.connect()
        db.create_tables()

        # 画像処理とデータベース更新のメインループ
        dataset_dir = Path(config['directories']['dataset'])
        for file_path in dataset_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in config['image_extensions']:
                logger.info(f"Processing image: {file_path}")

                try:
                    # オリジナル画像の情報を取得してDBに保存
                    original_info = get_image_info(file_path)
                    image_id = db.add_image(
                        width=original_info['width'],
                        height=original_info['height'],
                        format=original_info['format'],
                        mode=original_info['mode'],
                        color_profile=str(original_info['color_profile']),
                        has_alpha=original_info['has_alpha'],
                        file_path=str(file_path)
                    )

                    # 画像処理
                    with Image.open(file_path) as img:
                        # 注: 以下の3行は ImageProcessor クラス内のメソッドにまとめることを推奨します
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