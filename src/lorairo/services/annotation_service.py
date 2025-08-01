# src/lorairo/services/annotation_service.py
from typing import Any

from image_annotator_lib import PHashAnnotationResults, annotate, list_available_annotators
from PIL.Image import Image
from PySide6.QtCore import QObject, Signal

from lorairo.utils.log import logger

# 新ワーカーシステムを使用


# --- Annotation Function (Compatible with progress.Worker) ---
def run_annotation_task(
    images: list[Image],
    phash_list: list[str],
    models: list[str],
    progress_callback: Any = None,
    status_callback: Any = None,
    is_canceled: Any = None,
) -> PHashAnnotationResults:
    """
    AIアノテーションライブラリを呼び出す関数。
    progress.Workerの動的コールバック注入方式に対応。

    Args:
        images: アノテーション対象の PIL Image オブジェクトのリスト
        phash_list: 画像の pHash 値のリスト
        models: 使用する AI モデル名のリスト
        progress_callback: 進捗コールバック (progress.Workerから自動注入)
        status_callback: ステータスコールバック (progress.Workerから自動注入)
        is_canceled: キャンセル状態確認関数 (progress.Workerから自動注入)

    Returns:
        アノテーション結果 (PHashAnnotationResults)

    Raises:
        AiAnnotatorError: アノテーションライブラリ呼び出しでエラーが発生した場合
        ValueError: 入力データに問題がある場合など
        Exception: その他の予期しないエラー
    """
    logger.info("アノテーション処理タスクを開始します。")

    if status_callback:
        status_callback("AIアノテーション処理を開始...")

    # キャンセルチェック
    if is_canceled and is_canceled():
        logger.info("アノテーション処理がキャンセルされました。")
        raise RuntimeError("アノテーション処理がキャンセルされました。")

    # 進捗表示（開始）
    if progress_callback:
        progress_callback(10)  # 10% 開始

    try:
        # Call the image-annotator-lib directly
        if status_callback:
            status_callback(f"AIモデル実行中: {', '.join(models)}")

        results = annotate(images, models, phash_list)

        # 進捗表示（完了）
        if progress_callback:
            progress_callback(100)  # 100% 完了

        if status_callback:
            status_callback("アノテーション処理が完了しました。")

        logger.info("アノテーション処理タスクが正常に完了しました。")
        return results

    except Exception as e:
        logger.error(f"アノテーション処理中にエラーが発生: {e}")
        if status_callback:
            status_callback(f"エラー: {e}")
        raise


# --- Annotation Service ---
class AnnotationService(QObject):
    """
    AIアノテーション処理を実行し、UIに進捗・結果を通知するサービス。
    progress.Workerを利用して非同期で処理を行う。
    """

    # --- シグナル定義 ---
    # 完了通知 (結果オブジェクト)
    annotationFinished = Signal(object)
    # エラー通知
    annotationError = Signal(str)
    # 利用可能なモデルリスト取得完了
    availableAnnotatorsFetched = Signal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._annotation_result: object = None

    # --- Public Methods ---
    def start_annotation(self, images: list[Image], phash_list: list[str], models: list[str]) -> None:
        """
        アノテーション処理を非同期で開始する。
        注意: このメソッドは非推奨です。代わりにWorkerServiceを直接使用してください。

        Args:
            images: アノテーション対象の PIL Image オブジェクトのリスト。
            phash_list: 画像の pHash 値のリスト。
            models: 使用する AI モデル名のリスト。
        """
        # Input validation
        if not images:
            logger.warning("AnnotationService: 画像リストが空のため、アノテーションを開始しません。")
            self.annotationError.emit("入力画像がありません。")
            return
        if not phash_list or len(images) != len(phash_list):
            logger.error(
                "AnnotationService: 画像リストとpHashリストの数が一致しないか、pHashリストが空です。"
            )
            self.annotationError.emit("画像とpHashの数が一致しません。")
            return
        if not models:
            logger.warning("AnnotationService: モデルリストが空のため、アノテーションを開始しません。")
            self.annotationError.emit("モデルが選択されていません。")
            return

        logger.info(
            f"AnnotationService: アノテーション処理を開始します。Images: {len(images)}, Models: {models}"
        )

        # 非推奨メソッドの警告
        logger.warning(
            "AnnotationService.start_annotation() は非推奨です。WorkerServiceを直接使用してください。"
        )
        self.annotationError.emit("アノテーション機能は現在WorkerServiceに移行されています。")

    def fetch_available_annotators(self) -> None:
        """利用可能なアノテーターのモデル名リストを取得する (同期処理)"""
        # NOTE: Consider making this asynchronous using a worker if it ever becomes slow.
        logger.info("AnnotationService: 利用可能なアノテーターモデル名リストを取得します。")
        try:
            # Call image-annotator-lib directly
            models = list_available_annotators()
            self.availableAnnotatorsFetched.emit(models)
        except Exception as e:
            logger.error(f"利用可能なアノテーターモデル名リストの取得に失敗しました: {e}")
            self.availableAnnotatorsFetched.emit([])
            # Consider emitting a specific error signal

    def cancel_annotation(self) -> None:
        """現在実行中のアノテーション処理のキャンセルを試みる"""
        logger.info("AnnotationService: アノテーション機能はWorkerServiceに移行されました。")
