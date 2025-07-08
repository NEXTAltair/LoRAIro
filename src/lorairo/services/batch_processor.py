"""バッチ処理モジュール - progress.Workerシステムとの統合用"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..database.db_manager import ImageDatabaseManager
from ..database.schema import CaptionAnnotationData, TagAnnotationData
from ..services.configuration_service import ConfigurationService
from ..storage.file_system import FileSystemManager
from ..utils.log import logger


def _process_associated_files(image_file: Path, image_id: int, idm: ImageDatabaseManager) -> None:
    """
    画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する

    Args:
        image_file: 画像ファイルのパス
        image_id: データベースの画像ID
        idm: 画像データベースマネージャー
    """
    base_path = image_file.with_suffix("")  # 拡張子を除いたパス

    # .txtファイル（タグ）の処理
    txt_file = base_path.with_suffix(".txt")
    if txt_file.exists():
        try:
            tags_content = txt_file.read_text(encoding="utf-8").strip()
            if tags_content:
                # カンマ区切りのタグを分割
                tag_strings = [tag.strip() for tag in tags_content.split(",") if tag.strip()]
                if tag_strings:
                    # TagAnnotationDataのリストを作成
                    tags_data: list[TagAnnotationData] = []
                    for tag_string in tag_strings:
                        tag_data: TagAnnotationData = {
                            "tag_id": None,  # 新規タグとして追加
                            "model_id": None,  # ファイルからの読み込みなのでモデルなし
                            "tag": tag_string,
                        }
                        tags_data.append(tag_data)

                    idm.save_tags(image_id, tags_data)
                    logger.info(f"タグを追加: {image_file.name} - {len(tag_strings)}個のタグ")
                else:
                    logger.debug(f"タグファイルが空: {txt_file.name}")
        except Exception as e:
            logger.error(f"タグファイル読み込みエラー: {txt_file.name} - {e}")

    # .captionファイル（キャプション）の処理
    caption_file = base_path.with_suffix(".caption")
    if caption_file.exists():
        try:
            caption_content = caption_file.read_text(encoding="utf-8").strip()
            if caption_content:
                # CaptionAnnotationDataを作成
                caption_data: CaptionAnnotationData = {
                    "model_id": None,  # ファイルからの読み込みなのでモデルなし
                    "caption": caption_content,
                    "existing": False,  # 新規キャプション
                }
                idm.save_captions(image_id, [caption_data])
                logger.info(f"キャプションを追加: {image_file.name}")
            else:
                logger.debug(f"キャプションファイルが空: {caption_file.name}")
        except Exception as e:
            logger.error(f"キャプションファイル読み込みエラー: {caption_file.name} - {e}")


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

                # 6. 関連するタグとキャプションファイルの処理
                _process_associated_files(image_file, image_id, idm)

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
