"""
アプリケーション全体のロギングを設定するためのユーティリティモジュール。

loguru ライブラリを使用して、コンソールとファイルへのログ出力を設定します。
設定ファイルに基づいて、デフォルトのログレベルとモジュールごとのログレベルを
動的に設定できます。

主な機能:
- initialize_logging: アプリケーション起動時にロガーを初期化します。
- LEVEL_NAME_TO_NO: 標準ログレベル名と数値のマッピングを提供します。
"""

import logging
import sys
from functools import partial  # functools.partial をインポート
from typing import TYPE_CHECKING, Any

from loguru import logger as _logger

logger = _logger  # Explicitly re-export for mypy

# TYPE_CHECKING ブロックを追加して Record を条件付きでインポート
if TYPE_CHECKING:
    from loguru import Record

# ログフォーマットを定義 (コード内で固定)
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}"

# 標準ログレベル名から数値へのマッピング
LEVEL_NAME_TO_NO: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.FATAL,  # FATAL は CRITICAL のエイリアス
    "ERROR": logging.ERROR,
    "WARN": logging.WARNING,  # WARN は WARNING のエイリアス
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def _parse_log_levels(log_config: dict[str, Any], level_map: dict[str, int]) -> tuple[int, dict[str, int]]:
    """ログ設定辞書からデフォルトレベルとモジュール別レベルを解析し、数値に変換します。

    Args:
        log_config: ログ設定を含む辞書。
        level_map: ログレベル名 (大文字) から数値へのマッピング辞書。

    Returns:
        デフォルトのログレベル数値と、モジュールプレフィックスからログレベル数値への
        マッピング辞書のタプル。
    """
    module_levels_config = log_config.get("levels", {})
    default_level_name = log_config.get("level", "INFO").upper()

    # デフォルトレベルの数値を取得 (無効な場合は INFO)
    default_level_no = level_map.get(default_level_name, logging.INFO)
    if default_level_name not in level_map:
        # logger はまだ初期化されていない可能性があるため、標準エラー出力に警告を表示
        print(
            f"Warning: Invalid default log level '{default_level_name}' in config. Using 'INFO'.",
            file=sys.stderr,
        )

    # モジュール別レベルの数値を取得
    module_level_nos: dict[str, int] = {}
    for prefix, level_name in module_levels_config.items():
        level_name_upper = str(level_name).upper()  # 設定値が文字列でない可能性を考慮
        level_no = level_map.get(level_name_upper)
        if level_no is not None:
            module_level_nos[prefix] = level_no
        else:
            # logger はまだ初期化されていない可能性があるため、標準エラー出力に警告を表示
            print(
                f"Warning: Invalid log level '{level_name}' for module prefix '{prefix}' in config. Ignoring.",
                file=sys.stderr,
            )

    return default_level_no, module_level_nos


def _level_filter(record: "Record", default_level_no: int, module_level_nos: dict[str, int]) -> bool:
    """レコードのモジュール名に基づいてログレベルを判定するフィルタ関数本体。"""
    module_name = record["name"]
    record_level_no = record["level"].no

    should_pass = False  # フィルタ結果の初期値

    # module_name が None でない場合のみプレフィックスチェックを行う
    if module_name:
        # モジュール固有のレベル設定を確認 (事前計算した数値を使用)
        # 最も長く一致するプレフィックスの設定を優先する (例: a.b.c は a.b より優先)
        longest_match_prefix = None
        for prefix in module_level_nos:
            if module_name.startswith(prefix):
                if longest_match_prefix is None or len(prefix) > len(longest_match_prefix):
                    longest_match_prefix = prefix

        if longest_match_prefix is not None:
            # 一致する最も長いプレフィックスのレベル設定を適用
            target_level_no = module_level_nos[longest_match_prefix]
            should_pass = record_level_no >= target_level_no
        else:
            # モジュール固有の設定がない場合は、デフォルトレベルを適用
            should_pass = record_level_no >= default_level_no
    else:
        # モジュール名がない場合はデフォルトレベルを適用
        should_pass = record_level_no >= default_level_no

    return should_pass


def initialize_logging(log_config: dict[str, Any]) -> None:
    """Loguruのロガーを設定します。

    アプリケーション起動時に一度だけ呼び出す想定です。
    既存のLoguruハンドラはすべて削除され、設定に基づいて新しいハンドラ
    (コンソールおよびオプションでファイル) が追加されます。

    Args:
        log_config: ログ設定を含む辞書。以下のキーを想定:
            - level (str): デフォルトのログレベル名 (例: "INFO", "DEBUG")。
            - levels (dict[str, str]): モジュールプレフィックスごとのログレベル名。
            - file_path (str, optional): ログファイルパス。
            - rotation (str, optional): ログローテーション設定 (例: "25 MB")。
    """
    # --- 設定値の取得と数値レベルへの変換 ---
    default_level_no, module_level_nos = _parse_log_levels(log_config, LEVEL_NAME_TO_NO)
    file_path = log_config.get("file_path")
    rotation = log_config.get("rotation", "25 MB")

    # --- Loguru 設定 ---
    logger.remove()  # 既存のハンドラをすべて削除

    # --- レベルフィルタ関数の準備 ---
    # 解析済みのレベル設定をキャプチャしたフィルタ関数を作成
    # partial を使って default_level_no と module_level_nos を固定する
    filter_func = partial(
        _level_filter, default_level_no=default_level_no, module_level_nos=module_level_nos
    )

    # --- シンクの追加 ---
    # コンソールシンク (stderr)
    logger.add(
        sys.stderr,
        level=0,  # フィルタでレベル制御するため、シンク自体のレベルは最低(0)に設定
        filter=filter_func,  # 作成したフィルタ関数を適用
        format=LOG_FORMAT,
        colorize=True,  # コンソール出力に色を付ける
        backtrace=True,  # 例外発生時のトレースバックを強化
        diagnose=True,  # 例外発生時に変数情報を表示
    )

    # ファイルシンク (設定があれば)
    if file_path:
        try:
            logger.add(
                file_path,
                level=0,  # フィルタでレベル制御するため、シンク自体のレベルは最低(0)に設定
                filter=filter_func,  # 作成したフィルタ関数を適用
                format=LOG_FORMAT,
                rotation=rotation,  # ログローテーション設定
                retention=5,  # 保持するローテーション済みログファイルの数
                encoding="utf-8",
                backtrace=True,  # 例外発生時のトレースバックを強化
                diagnose=True,  # 例外発生時に変数情報を表示
            )
            logger.info(f"Logging to file: {file_path}")
        except Exception as e:
            # ファイルログ設定失敗時はエラーログを出力して続行 (コンソールには出力される)
            logger.error(f"Failed to configure file logging to '{file_path}': {e}")
            logger.error("File logging disabled.")

    logger.success("Logger initialized.")


# --- 使用方法 ---
# アプリケーションのエントリポイントで一度だけ initialize_logging を呼び出す
# 例:
# from lorairo.utils import config, log
# try:
#     app_config = config.get_config()
#     log_settings = app_config.get('logging', {})
#     log.initialize_logging(log_settings)
# except Exception as e:
#     # 設定読み込みやログ初期化失敗時のフォールバック
#     print(f"Failed to initialize configuration or logging: {e}", file=sys.stderr)
#     sys.exit(1)
#
# # 各モジュールでは以下のように logger をインポートして使用
# from lorairo.utils.log import logger
# logger.info("This is an info message.")
