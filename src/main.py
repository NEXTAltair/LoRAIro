from module.config import get_config
from typing import Dict, Any, Tuple, Optional, List
from PIL import Image
from abc import ABC, abstractmethod
from module.log import setup_logger, get_logger
from module.db import initialize_database
from module.file_sys import FileSystemManager
from ImageEditor import ImageProcessingManager
from caption_tags import ImageAnalyzer
import traceback
from pathlib import Path
import logging

class MainControllBase(ABC):
    """ 画像処理のメインコントローラーの基底クラス

    Args:
        ABC (ABC): 抽象基底クラス
    """
    def __init__(self, config: Dict[str, Any], file_system_manager, image_database_manager, image_processing_manager, image_analyzer):
        """コンストラクタ

        """
        self.config = config
        self.file_system_manager = file_system_manager
        self.image_database_manager = image_database_manager
        self.image_processing_manager = image_processing_manager
        self.image_analyzer = image_analyzer
        self.logger = self._setup_logger()

    def _setup_logger(self):
        return logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def execute(self):
        pass

    def _save_original_image(self, image_file: Path) -> Path:
        return self.file_system_manager.save_original_image(image_file)

    def _save_metadata(self, db_stored_original_path: Path, metadata: Dict[str, Any]) -> Tuple[int, str]:
        return self.image_database_manager.save_original_metadata(db_stored_original_path, metadata)

    def _process_image(self, db_stored_original_path: Path, has_alpha: bool, mode: str) ->  Optional[Image.Image]:
        return self.image_processing_manager.process_image(db_stored_original_path, has_alpha, mode)

    def _save_processed_image(self, processed_image: Any, original_path: Path) -> Path:
        return self.file_system_manager.save_processed_image(processed_image, original_path)

    def _save_processed_metadata(self, image_id: int, processed_path: Path, metadata: Dict[str, Any]):
        self.image_database_manager.save_processed_metadata(image_id, processed_path, metadata)

    def _save_annotations(self, image_id: int, annotations: Dict[str, Any]):
        self.image_database_manager.save_annotations(image_id, annotations)

class RealtimeControll(MainControllBase):
    def execute(self):
        self.logger.info("リアルタイム処理を開始")
        dataset_path = Path(self.config['directories']['dataset'])
        image_files = self.file_system_manager.get_image_files(dataset_path)

        for image_file in image_files:
            try:
                self._process_single_image(image_file)
            except Exception as e:
                self.logger.error(f"画像処理中にエラーが発生しました: {image_file}, エラー: {str(e)}")

        self.logger.info("リアルタイム処理が完了しました")

    def _process_single_image(self, image_file: Path):
        self.logger.info(f"画像の処理を開始: {image_file}")

        db_stored_original_path = self._save_original_image(image_file)
        original_metadata = self.file_system_manager.get_image_info(image_file)
        image_id, _ = self._save_metadata(db_stored_original_path, original_metadata)

        existing_annotations = self.image_analyzer.get_existing_annotations(image_file)
        if existing_annotations:
            self._save_annotations(image_id, existing_annotations)

        processed_image = self._process_image(db_stored_original_path,
                                              original_metadata['has_alpha'],
                                              original_metadata['mode'])
        processed_path = self._save_processed_image(processed_image, image_file)

        processed_metadata = self.file_system_manager.get_image_info(processed_path)
        self._save_processed_metadata(image_id, processed_path, processed_metadata)

        analyzed_data = self.image_analyzer.analyze_image(processed_path)
        if analyzed_data:
            self._save_annotations(image_id, analyzed_data)

        self.logger.info(f"画像の処理が完了しました: {image_file}")

class BatchControll(MainControllBase):
    def execute(self):
        self.logger.info("バッチ処理を開始します")
        dataset_path = Path(self.config['directories']['dataset'])
        image_files = self.file_system_manager.get_image_files(dataset_path)

        batch_request_data = []
        for image_file in image_files:
            try:
                batch_request_data.append(self._prepare_batch_request(image_file))
            except Exception as e:
                self.logger.error(f"バッチリクエスト準備中にエラーが発生しました: {image_file}, エラー: {str(e)}")

        self._save_batch_request(batch_request_data)
        self._start_batch_processing()
        self.logger.info("バッチ処理の準備が完了しました")

    def _prepare_batch_request(self, image_file: Path) -> Dict[str, Any]:
        self.logger.info(f"バッチリクエストの準備: {image_file}")

        db_stored_original_path = self._save_original_image(image_file)
        original_metadata = self.file_system_manager.get_image_info(image_file)
        image_id, _ = self._save_metadata(db_stored_original_path, original_metadata)

        processed_image = self._process_image(db_stored_original_path,
                                              original_metadata['has_alpha'],
                                              original_metadata['mode'])
        processed_path = self._save_processed_image(processed_image, image_file)

        return self.image_analyzer.create_batch_request(processed_image, processed_path)

    def _save_batch_request(self, batch_request_data: List[Dict[str, Any]]):
        batch_request_dir = self.file_system_manager.batch_request_dir
        batch_request_file = self.image_analyzer.save_batch_request(batch_request_dir, batch_request_data)
        self.logger.info(f"バッチリクエストが保存されました: {batch_request_file}")

    def _start_batch_processing(self):
        if self.config['generation']['start_batch']:
            upload_file_id = self.image_analyzer.start_batch_processing()
            self.logger.info(f"バッチ処理が開始されました ファイルID: {upload_file_id}")


def start_processing(config_path: str = 'processing.toml'):
    try:
        # 設定ファイルの読み込み
        config = get_config(config_path)

        # ロギングの設定
        setup_logger(config['log'])
        logger = get_logger(__name__)
        logger.info("プログラムの開始")

        # ファイルシステムマネージャーの初期化
        file_system_manager = FileSystemManager()
        dataset_dir = Path(config['directories']['dataset'])
        output_dir = Path(config['directories']['output'])
        target_resolution = config['image_processing']['target_resolution']
        image_extensions = config['image_extensions']
        file_system_manager.initialize(dataset_dir, output_dir, target_resolution, image_extensions)

        # データベースの初期化
        database_name = config['image_database']
        db_path = file_system_manager.get_db_path(database_name)
        models = config['models']
        image_database_manager = initialize_database(db_path, models)
        connection_status = image_database_manager.db_manager.connect()
        if not connection_status:
            logger.error("データベースへの接続に失敗しました。")
            return

        # 画像処理マネージャーの初期化
        preferred_resolutions = config['preferred_resolutions']

        image_processing_manager = ImageProcessingManager(file_system_manager)
        image_processing_manager.initialize(target_resolution, preferred_resolutions)

        # 画像アナライザーの初期化
        image_analyzer = ImageAnalyzer(models)
        prompt = config['prompts']['main']
        additional_prompt = config['prompts']['additional']
        apikey = config['api']['openai_api_key']
        model = config['api']['openai_model']
        image_analyzer.initialize(prompt, additional_prompt, apikey, model, models)

        # 処理モードの選択
        if config['generation']['batch_jsonl']:
            controll = BatchControll(config, file_system_manager, image_database_manager, image_processing_manager, image_analyzer)
        elif config['generation']['single_image']:
            controll = RealtimeControll(config, file_system_manager, image_database_manager, image_processing_manager, image_analyzer)
        else:
            raise ValueError("処理モードが不正です。")

        # 処理の実行
        controll.execute()

        logger.info("すべての処理が完了しました")

    except FileNotFoundError as e:
        logger.error(f"ファイルが見つかりません: {e}")
        logger.debug(traceback.format_exc())
    except PermissionError as e:
        logger.error(f"ファイルへのアクセス権限がありません: {e}")
        logger.debug(traceback.format_exc())
    except ValueError as e:
        logger.error(f"設定値が不正です: {e}")
        logger.debug(traceback.format_exc())
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # リソースのクリーンアップ
        if 'image_database_manager' in locals():
            image_database_manager.db_manager.close()
        logger.info("プログラムを終了します")

if __name__ == "__main__":
    start_processing()