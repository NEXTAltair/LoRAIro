"""バッチ処理モジュール - progress.Workerシステムとの統合用"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..database.db_manager import ImageDatabaseManager
from ..database.db_repository import CaptionAnnotationData, TagAnnotationData
from ..services.configuration_service import ConfigurationService
from ..storage.file_system import FileSystemManager
from ..utils.log import logger


def _process_associated_files(image_file: Path, image_id: int, idm: ImageDatabaseManager) -> None:
    """画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する。

    Args:
        image_file: 画像ファイルのパス。
        image_id: データベースの画像ID。
        idm: 画像データベースマネージャー。
    """
    base_path = image_file.with_suffix("")

    _import_tag_file(base_path, image_file.name, image_id, idm)
    _import_caption_file(base_path, image_file.name, image_id, idm)


def _import_tag_file(base_path: Path, filename: str, image_id: int, idm: ImageDatabaseManager) -> None:
    """タグファイル(.txt)を読み込みDBに登録する。

    Args:
        base_path: 拡張子なしのベースパス。
        filename: 表示用ファイル名。
        image_id: データベースの画像ID。
        idm: 画像データベースマネージャー。
    """
    txt_file = base_path.with_suffix(".txt")
    if not txt_file.exists():
        return

    try:
        tags_content = txt_file.read_text(encoding="utf-8").strip()
        if not tags_content:
            logger.debug(f"タグファイルが空: {txt_file.name}")
            return

        tag_strings = [tag.strip() for tag in tags_content.split(",") if tag.strip()]
        if not tag_strings:
            logger.debug(f"タグファイルが空: {txt_file.name}")
            return

        tags_data: list[TagAnnotationData] = [
            {
                "tag_id": None,
                "model_id": None,
                "tag": tag_string,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
            }
            for tag_string in tag_strings
        ]
        idm.save_tags(image_id, tags_data)
        logger.info(f"タグを追加: {filename} - {len(tag_strings)}個のタグ")
    except Exception as e:
        logger.error(f"タグファイル読み込みエラー: {txt_file.name} - {e}")


def _import_caption_file(base_path: Path, filename: str, image_id: int, idm: ImageDatabaseManager) -> None:
    """キャプションファイル(.caption)を読み込みDBに登録する。

    Args:
        base_path: 拡張子なしのベースパス。
        filename: 表示用ファイル名。
        image_id: データベースの画像ID。
        idm: 画像データベースマネージャー。
    """
    caption_file = base_path.with_suffix(".caption")
    if not caption_file.exists():
        return

    try:
        caption_content = caption_file.read_text(encoding="utf-8").strip()
        if not caption_content:
            logger.debug(f"キャプションファイルが空: {caption_file.name}")
            return

        caption_data: CaptionAnnotationData = {
            "model_id": None,
            "caption": caption_content,
            "existing": True,
            "is_edited_manually": False,
        }
        idm.save_captions(image_id, [caption_data])
        logger.info(f"キャプションを追加: {filename}")
    except Exception as e:
        logger.error(f"キャプションファイル読み込みエラー: {caption_file.name} - {e}")


def _scan_image_files(
    directory_path: Path,
    fsm: FileSystemManager,
    status_callback: Callable[[str], None] | None,
) -> tuple[list[Path], dict[str, Any]] | None:
    """ディレクトリから画像ファイルリストを取得する。

    Args:
        directory_path: 処理対象のディレクトリパス。
        fsm: ファイルシステムマネージャー。
        status_callback: ステータスメッセージコールバック。

    Returns:
        (画像ファイルリスト, 空結果dict)のタプル。エラー時はNone。
    """
    if status_callback:
        status_callback("ファイルをスキャン中...")

    try:
        image_files = fsm.get_image_files(directory_path)
        total_files = len(image_files)
        logger.info(f"処理対象ファイル数: {total_files}")

        if total_files == 0:
            logger.warning("処理対象の画像ファイルが見つかりません")
            if status_callback:
                status_callback("処理対象の画像ファイルが見つかりません")
            return [], {"processed": 0, "errors": 0, "skipped": 0, "total": 0}

        return image_files, {"processed": 0, "errors": 0, "skipped": 0, "total": total_files}
    except Exception as e:
        logger.error(f"ファイルスキャンエラー: {e}")
        if status_callback:
            status_callback(f"エラー: ファイルスキャンに失敗 - {e}")
        return None


def _process_single_image(
    image_file: Path,
    idm: ImageDatabaseManager,
    fsm: FileSystemManager,
    results: dict[str, Any],
) -> None:
    """単一画像ファイルの重複チェック・登録・関連ファイル処理を行う。

    Args:
        image_file: 処理対象の画像ファイル。
        idm: 画像データベースマネージャー。
        fsm: ファイルシステムマネージャー。
        results: 処理結果カウンターdict（直接更新される）。
    """
    filename = image_file.name

    # 重複チェック
    existing_id = idm.detect_duplicate_image(image_file)
    if existing_id:
        logger.debug(f"重複画像をスキップ: {filename} (既存ID: {existing_id})")
        _process_associated_files(image_file, existing_id, idm)
        results["skipped"] += 1
        return

    # 新規画像の登録
    registration_result = idm.register_original_image(image_file, fsm)
    if registration_result is not None:
        image_id, _metadata = registration_result
        logger.info(f"画像登録成功: {filename} (ID: {image_id})")
        _process_associated_files(image_file, image_id, idm)
        results["processed"] += 1
    else:
        logger.error(f"画像登録失敗: {filename}")
        results["errors"] += 1


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
    """ディレクトリ内の画像を効率的にバッチ処理する関数。

    progress.Workerの動的コールバック注入方式に完全対応。

    Args:
        directory_path: 処理対象のディレクトリパス。
        config_service: 設定サービス。
        fsm: ファイルシステムマネージャー。
        idm: 画像データベースマネージャー。
        progress_callback: 基本進捗コールバック (0-100)。
        batch_progress_callback: 詳細進捗コールバック (current, total, filename)。
        status_callback: ステータスメッセージコールバック。
        is_canceled: キャンセル状態確認関数。

    Returns:
        処理結果統計dict (processed, errors, skipped, total)。
    """
    logger.info(f"バッチ処理開始: {directory_path}")

    scan_result = _scan_image_files(directory_path, fsm, status_callback)
    if scan_result is None:
        return {"processed": 0, "errors": 1, "skipped": 0, "total": 0}

    image_files, results = scan_result
    total_files = results["total"]
    if total_files == 0:
        return results

    if status_callback:
        status_callback(f"バッチ処理開始: {total_files}件の画像を処理します")

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

        # 進捗更新
        if batch_progress_callback:
            batch_progress_callback(current_count, total_files, filename)
        if progress_callback:
            progress_callback(int((current_count / total_files) * 100))
        if status_callback:
            status_callback(f"処理中: {filename} ({current_count}/{total_files})")

        try:
            _process_single_image(image_file, idm, fsm, results)
        except Exception as e:
            logger.error(f"画像処理エラー: {filename} - {e}")
            results["errors"] += 1

    # 処理完了
    logger.info(
        f"バッチ処理完了: 処理済み={results['processed']}, エラー={results['errors']}, スキップ={results['skipped']}"
    )
    if status_callback:
        status_callback(
            f"完了: 成功 {results['processed']}件, エラー {results['errors']}件, スキップ {results['skipped']}件"
        )

    return results
