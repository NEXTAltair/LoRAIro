import sys
import locale

# システムのデフォルトエンコーディングをUTF-8に設定
if sys.platform.startswith('win'):
    # Windowsの場合
    import ctypes
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
else:
    # Unix系の場合
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

import logging
from logging.handlers import RotatingFileHandler
from typing import Dict
import io

def setup_logger(config: Dict[str, str]) -> None:
    log_level = config['level'].upper()
    log_file = config['file']

    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 既存のハンドラを削除
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # ログのフォーマット設定
    formatter = logging.Formatter(config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # コンソールハンドラの設定
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.stream = io.TextIOWrapper(console_handler.stream.buffer, encoding='utf-8')
    root_logger.addHandler(console_handler)

    # ファイルハンドラの設定
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.get('max_bytes', 10*1024*1024),
        backupCount=config.get('backup_count', 5),
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # デバッグ情報の出力
    print(f"Debug: StreamHandler's stream: {console_handler.stream}", file=sys.stderr)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)