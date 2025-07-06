# src/lorairo/services/annotation_service.py 作成


from image_annotator_lib import PHashAnnotationResults, annotate, list_available_annotators
from PIL.Image import Image
from PySide6.QtCore import QObject, QThread, Signal

from lorairo.services.base_worker import BaseWorker
from lorairo.utils.log import logger


# --- Annotation Worker (Inherits from BaseWorker) ---
class AnnotationWorker(BaseWorker):
    """
    AnnotationServiceのためのワーカースレッド。
    BaseWorkerを継承し、AIアノテーションの具体的な処理を `run_task` に実装する。

    Args:
        images: アノテーション対象の PIL Image オブジェクトのリスト。
        phash_list: 画像の pHash 値のリスト。
        models: 使用する AI モデル名のリスト。
    """

    # finished and progress signals are inherited from BaseWorker

    def __init__(self, images: list[Image], phash_list: list[str], models: list[str]) -> None:
        # No parent needed here, will be handled by moveToThread
        super().__init__()
        self._images = images
        self._phash_list = phash_list
        self._models = models
        # _is_cancelled is handled by BaseWorker

    def run_task(self) -> object:
        """
        AIアノテーションライブラリを呼び出す具体的なタスク。

        Returns:
            アノテーション結果 (PHashAnnotationResults)。

        Raises:
            AiAnnotatorError: アノテーションライブラリ呼び出しでエラーが発生した場合。
            ValueError: 入力データに問題がある場合など。
            Exception: その他の予期しないエラー。
        """
        logger.info("AnnotationWorker: アノテーション処理タスクを開始します。")
        # Cancellation check before starting is handled by BaseWorker.run()
        # Error handling (try...except) is primarily handled by BaseWorker.run()

        # Call the image-annotator-lib directly
        # This might raise exceptions like ValueError, etc.
        results = annotate(self._images, self._models, self._phash_list)

        # No need to emit finished signal here, BaseWorker.run() handles it.
        # No need for final cancellation check, BaseWorker.run() handles it.
        logger.info("AnnotationWorker: アノテーション処理タスクが正常に完了しました。")
        return results

    # cancel() method is inherited from BaseWorker.
    # Override it if specific cancellation logic for call_annotate_library is needed.


# --- Annotation Service ---
class AnnotationService(QObject):
    """
    AIアノテーション処理を実行し、UIに進捗・結果を通知するサービス。
    BaseWorkerとQThreadを利用して非同期で処理を行う。
    """

    # --- シグナル定義 ---
    # 完了通知 (成功時は結果オブジェクト、エラー時はException)
    annotationFinished = Signal(object)
    # 利用可能なモデルリスト取得完了
    availableAnnotatorsFetched = Signal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: AnnotationWorker | None = None

    # --- Public Methods ---
    def start_annotation(self, images: list[Image], phash_list: list[str], models: list[str]) -> None:
        """
        アノテーション処理を非同期で開始する。

        Args:
            images: アノテーション対象の PIL Image オブジェクトのリスト。
            phash_list: 画像の pHash 値のリスト。
            models: 使用する AI モデル名のリスト。
        """
        if self._thread is not None and self._thread.isRunning():
            logger.warning("アノテーション処理が既に実行中です。")
            # Consider emitting an error signal or returning a status
            # self.annotationFinished.emit(RuntimeError("Annotation already in progress"))
            return

        # Input validation
        if not images:
            logger.warning("AnnotationService: 画像リストが空のため、アノテーションを開始しません。")
            self.annotationFinished.emit(ValueError("入力画像がありません。"))
            return
        if not phash_list or len(images) != len(phash_list):
            logger.error(
                "AnnotationService: 画像リストとpHashリストの数が一致しないか、pHashリストが空です。"
            )
            self.annotationFinished.emit(ValueError("画像とpHashの数が一致しません。"))
            return
        if not models:
            logger.warning("AnnotationService: モデルリストが空のため、アノテーションを開始しません。")
            self.annotationFinished.emit(ValueError("モデルが選択されていません。"))
            return

        logger.info(
            f"AnnotationService: アノテーション処理を開始します。Images: {len(images)}, Models: {models}"
        )

        # Create thread and worker
        self._thread = QThread()
        # Pass necessary data to worker constructor, no parent
        self._worker = AnnotationWorker(images, phash_list, models)
        self._worker.moveToThread(self._thread)

        # Connect signals
        # BaseWorker's run method is the entry point
        self._thread.started.connect(self._worker.run)
        # Connect BaseWorker's finished signal to the handler
        self._worker.finished.connect(self._handle_finished)
        # Connect BaseWorker's progress signal if needed
        # self._worker.progress.connect(self.progressUpdated)

        # Cleanup connections
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._reset_thread_worker)

        # Start the thread
        self._thread.start()

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
        if self._worker is not None and self._thread is not None and self._thread.isRunning():
            logger.info("AnnotationService: アノテーション処理のキャンセルを要求します。")
            # Call BaseWorker's cancel method
            self._worker.cancel()
        else:
            logger.info("AnnotationService: キャンセル対象のアノテーション処理はありません。")

    # --- Private Slots ---
    def _handle_finished(self, result: object) -> None:
        """ワーカースレッド完了時の処理 (BaseWorker.finishedシグナルから呼び出される)"""
        logger.info(f"AnnotationService: ワーカー処理が完了しました。Result type: {type(result)}")
        # Forward the result (success object or exception) from the worker
        self.annotationFinished.emit(result)

    def _reset_thread_worker(self) -> None:
        """スレッドとワーカーの参照をリセット"""
        logger.debug("AnnotationService: スレッドとワーカーの参照をリセットします。")
        self._thread = None
        self._worker = None
