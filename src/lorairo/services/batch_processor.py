"""バッチ処理モジュール - progress.Workerシステムとの統合用"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..database.db_manager import ImageDatabaseManager
from ..services.configuration_service import ConfigurationService
from ..storage.file_system import FileSystemManager
from ..utils.log import logger


def process_directory_batch(
    directory_path: Path,
    config_service: ConfigurationService,
    fsm: FileSystemManager,
    idm: ImageDatabaseManager,
    progress_callback: Callable[[int], None] | None = None,
    batch_progress_callback: Callable[[int, int, str], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
    is_canceled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    ディレクトリ内の画像を効率的にバッチ処理する関数

    progress.Workerの動的コールバック注入方式に完全対応。

    Args:
        directory_path: 処理対象のディレクトリパス
        config_service: 設定サービス
        fsm: ファイルシステムマネージャー
        idm: 画像データベースマネージャー
        progress_callback: 基本進捗コールバック (0-100) - progress.Workerから自動注入
        batch_progress_callback: 詳細進捗コールバック (current, total, filename) - progress.Workerから自動注入
        status_callback: ステータスメッセージコールバック - progress.Workerから自動注入
        is_canceled: キャンセル状態確認関数 - progress.Workerから自動注入

    Returns:
        dict: 処理結果統計
        {
            "processed": int,  # 成功処理数
            "errors": int,     # エラー数
            "skipped": int,    # スキップ数（重複等）
            "total": int       # 総ファイル数
        }
    """
    logger.info(f"バッチ処理開始: {directory_path}")

    if status_callback:
        status_callback("ファイルをスキャン中...")

    # 1. ファイルリスト取得
    try:
        image_files = fsm.get_image_files(directory_path)
        total_files = len(image_files)
        logger.info(f"処理対象ファイル数: {total_files}")

        if total_files == 0:
            logger.warning("処理対象の画像ファイルが見つかりません")
            if status_callback:
                status_callback("処理対象の画像ファイルが見つかりません")
            return {"processed": 0, "errors": 0, "skipped": 0, "total": 0}

    except Exception as e:
        logger.error(f"ファイルスキャンエラー: {e}")
        if status_callback:
            status_callback(f"エラー: ファイルスキャンに失敗 - {e}")
        return {"processed": 0, "errors": 1, "skipped": 0, "total": 0}

    # 2. 処理結果の初期化
    results = {"processed": 0, "errors": 0, "skipped": 0, "total": total_files}

    if status_callback:
        status_callback(f"バッチ処理開始: {total_files}件の画像を処理します")

    # 3. ファイル単位で処理
    for current_index, image_file in enumerate(image_files):
        current_count = current_index + 1

        # キャンセルチェック
        if is_canceled and is_canceled():
            logger.info(f"バッチ処理がキャンセルされました (処理済み: {current_count - 1}/{total_files})")
            if status_callback:
                status_callback("処理がキャンセルされました")
            break

        filename = image_file.name
        logger.debug(f"処理中: {filename} ({current_count}/{total_files})")

        # 詳細進捗更新 (新機能)
        if batch_progress_callback:
            batch_progress_callback(current_count, total_files, filename)

        # 基本進捗更新
        if progress_callback:
            progress_percentage = int((current_count / total_files) * 100)
            progress_callback(progress_percentage)

        # ステータス更新
        if status_callback:
            status_callback(f"処理中: {filename} ({current_count}/{total_files})")

        try:
            # 4. 重複チェック
            existing_id = idm.detect_duplicate_image(image_file)
            if existing_id:
                logger.debug(f"重複画像をスキップ: {filename} (既存ID: {existing_id})")
                results["skipped"] += 1
                continue

            # 5. 新規画像の登録
            registration_result = idm.register_original_image(image_file, fsm)
            if registration_result is not None:
                image_id, metadata = registration_result
                logger.info(f"画像登録成功: {filename} (ID: {image_id})")
                results["processed"] += 1
            else:
                logger.error(f"画像登録失敗: {filename}")
                results["errors"] += 1

        except Exception as e:
            logger.error(f"画像処理エラー: {filename} - {e}")
            results["errors"] += 1
            # 個別エラーでバッチ全体を停止しない
            continue

    # 6. 処理完了
    logger.info(
        f"バッチ処理完了: 処理済み={results['processed']}, エラー={results['errors']}, スキップ={results['skipped']}"
    )

    if status_callback:
        status_callback(
            f"完了: 成功 {results['processed']}件, エラー {results['errors']}件, スキップ {results['skipped']}件"
        )

    return results
