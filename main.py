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

                    # 画像処理に必要な情報を取得
                    image_data = db.get_image_from_db(image_id)
                    db_original_image_path = image_data['db_path']

                    # レターボックス､ピラーボックスの除去
                    cropped_img = image_processor.auto_crop_image(db_original_image_path)
                    w = cropped_img.width
                    h = cropped_img.height

                    # 長辺がtarget_resolution未満は無視
                    if max(w, h) < config['image_processing']['target_resolution']:
                        logger.info(f"Image {file_path} は小さい画像なので無視 \n 自動アップスケールはそのうち実装する  \n width: {w} \n height: {h}") # TODO: 自動アップスケールの実装
                        continue
                    processed_img = image_processor.process_image(
                        cropped_img,
                        image_data['has_alpha'],
                        image_data['mode'],
                        )
                    # 処理済み画像を保存とDBへの登録用の情報取得
                    processed_info = image_processor.save_processed_and_return_metadata(processed_img, db_original_image_path)

                    # 処理済み画像情報をDBに登録
                    processed_id = db.add_processed_image(image_id, processed_info)
# ----ここまで動いた-------
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