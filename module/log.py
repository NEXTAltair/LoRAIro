import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger(log_level: str = 'INFO', log_file: str = 'app.log'):
    """
    ロガーの設定を行う

    Args:
        log_level (str): ログレベル（'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'）
        log_file (str): ログファイルのパス
    """
    # ログレベルの設定
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # ルートロガーの設定
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # ログのフォーマット設定
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # コンソールハンドラの設定
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイルハンドラの設定
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"Logging initialized. Level: {log_level}, File: {log_file}")

def get_logger(name: str) -> logging.Logger:
    """
    名前付きロガーを取得する

    Args:
        name (str): ロガーの名前

    Returns:
        logging.Logger: 設定済みのロガーインスタンス
    """
    return logging.getLogger(name)