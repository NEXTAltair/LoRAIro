# src/lorairo/services/annotation_service.py

from image_annotator_lib import PHashAnnotationResults, annotate, list_available_annotators
from PIL.Image import Image
from PySide6.QtCore import QObject, QThread, Signal

from lorairo.utils.log import logger

from ..gui.window.progress import Controller, Worker


# --- Annotation Function (Compatible with progress.Worker) ---
def run_annotation_task(
    images: list[Image],
    phash_list: list[str],
    models: list[str],
    progress_callback=None,
    status_callback=None,
    is_canceled=None,
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
        self._controller: Controller | None = None
        self._annotation_result: object = None

    # --- Public Methods ---
    def start_annotation(self, images: list[Image], phash_list: list[str], models: list[str]) -> None:
        """
        アノテーション処理を非同期で開始する。

        Args:
            images: アノテーション対象の PIL Image オブジェクトのリスト。
            phash_list: 画像の pHash 値のリスト。
            models: 使用する AI モデル名のリスト。
        """
        if self._controller is not None:
            logger.warning("アノテーション処理が既に実行中です。")
            self.annotationError.emit("アノテーション処理が既に実行中です。")
            return

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

        # Create controller with progress widget
        self._controller = Controller()

        # Connect signals
        self._controller.worker = None  # Will be created in start_process

        # Use a wrapper function to capture the result
        def annotation_wrapper():
            try:
                result = run_annotation_task(images, phash_list, models)
                self._annotation_result = result
                return result
            except Exception as e:
                logger.error(f"アノテーション処理エラー: {e}")
                self._annotation_result = None
                raise

        # Start the process using progress.Worker system
        self._controller.start_process(annotation_wrapper)

        # Connect completion signal after worker is created
        if self._controller.worker:
            self._controller.worker.finished.connect(self._handle_annotation_finished)
            self._controller.worker.error_occurred.connect(self._handle_annotation_error)

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
        if self._controller is not None and self._controller.worker is not None:
            logger.info("AnnotationService: アノテーション処理のキャンセルを要求します。")
            # Call progress.Worker's cancel method
            self._controller.worker.cancel()
        else:
            logger.info("AnnotationService: キャンセル対象のアノテーション処理はありません。")

    # --- Private Slots ---
    def _handle_annotation_finished(self) -> None:
        """ワーカー処理完了時の処理"""
        logger.info("AnnotationService: アノテーション処理が完了しました。")

        # 結果を送信
        if self._annotation_result is not None:
            self.annotationFinished.emit(self._annotation_result)

        # リソースをクリーンアップ
        self._reset_controller()

    def _handle_annotation_error(self, error_message: str) -> None:
        """ワーカーエラー時の処理"""
        logger.error(f"AnnotationService: アノテーション処理エラー - {error_message}")
        self.annotationError.emit(error_message)

        # リソースをクリーンアップ
        self._reset_controller()

    def _reset_controller(self) -> None:
        """コントローラーの参照をリセット"""
        logger.debug("AnnotationService: コントローラーの参照をリセットします。")
        self._controller = None
        self._annotation_result = None
