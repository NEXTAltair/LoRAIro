import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Dict
import sys
import yaml

def load_config(config_path: str = 'logging_config.yaml') -> Dict[str, Any]:
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading config file: {e}")
        return {}

def setup_logger(log_level: str = 'INFO', log_file: str = 'app.log', config_path: str = 'logging_config.yaml'):
    config = load_config(config_path)
    logging.info(f"Loaded config: {config}")  # 設定内容をログ出

    log_level = config.get('log_level', log_level).upper()
    log_file = config.get('log_file', log_file)

    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # ルートロガーの設定
    logging.basicConfig(level=numeric_level)
    root_logger = logging.getLogger()

    # すべてのロガーのログレベルを設定 # ← 追加
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)

    # 既存のハンドラを削除
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # ログのフォーマット設定
    formatter = logging.Formatter(config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # コンソールハンドラの設定
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ファイルハンドラの設定
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.get('max_bytes', 10*1024*1024),
        backupCount=config.get('backup_count', 5)
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    root_logger.log(numeric_level, f"Logging initialized. Level: {log_level}, File: {log_file}")

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    return logger