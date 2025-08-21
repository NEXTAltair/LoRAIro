# src/lorairo/services/worker_service.py

import time
from pathlib import Path
from typing import Any

from PIL.Image import Image
from PySide6.QtCore import QObject, QSize, Signal

from ...database.db_manager import ImageDatabaseManager
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..workers.annotation_worker import AnnotationWorker, ModelSyncWorker
from ..workers.database_worker import DatabaseRegistrationWorker, SearchWorker, ThumbnailWorker
from ..workers.manager import WorkerManager
from ..workers.search import SearchResult


class WorkerService(QObject):
    """
    ワーカーサービス - 高レベルAPI提供。
    各種ワーカーの統一的な管理とGUI層への簡潔なインターフェースを提供。
    """

    # === 統一的なシグナル ===
    batch_registration_started = Signal(str)  # worker_id
    batch_registration_finished = Signal(object)  # DatabaseRegistrationResult
    batch_registration_error = Signal(str)  # error_message

    annotation_started = Signal(str)  # worker_id
    annotation_finished = Signal(object)  # PHashAnnotationResults
    annotation_error = Signal(str)  # error_message

    enhanced_annotation_started = Signal(str)  # worker_id
    enhanced_annotation_finished = Signal(object)  # Enhanced annotation results
    enhanced_annotation_error = Signal(str)  # error_message

    model_sync_started = Signal(str)  # worker_id
    model_sync_finished = Signal(object)  # ModelSyncResult
    model_sync_error = Signal(str)  # error_message

    search_started = Signal(str)  # worker_id
    search_finished = Signal(object)  # SearchResult
    search_error = Signal(str)  # error_message

    thumbnail_started = Signal(str)  # worker_id
    thumbnail_finished = Signal(object)  # ThumbnailLoadResult
    thumbnail_error = Signal(str)  # error_message

    # === 進捗シグナル ===
    worker_progress_updated = Signal(str, object)  # worker_id, WorkerProgress
    worker_batch_progress = Signal(str, int, int, str)  # worker_id, current, total, filename

    # === 全体管理シグナル ===
    active_worker_count_changed = Signal(int)
    all_workers_finished = Signal()

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        fsm: FileSystemManager,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.db_manager = db_manager
        self.fsm = fsm
        self.worker_manager = WorkerManager(self)

        # シングルトンワーカー管理
        self.current_search_worker_id: str | None = None
        self.current_registration_worker_id: str | None = None
        self.current_annotation_worker_id: str | None = None
        self.current_thumbnail_worker_id: str | None = None

        # ワーカーマネージャーのシグナル接続
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_finished.connect(self._on_worker_finished)
        self.worker_manager.worker_error.connect(self._on_worker_error)
        self.worker_manager.active_worker_count_changed.connect(self.active_worker_count_changed)
        self.worker_manager.all_workers_finished.connect(self.all_workers_finished)

        logger.debug("WorkerService initialized")

    # === Database Registration ===

    def start_batch_registration(self, directory: Path) -> str:
        """
        バッチ登録開始

        Args:
            directory: 登録対象ディレクトリ

        Returns:
            str: ワーカーID
        """
        worker = DatabaseRegistrationWorker(directory, self.db_manager, self.fsm)
        worker_id = f"batch_reg_{int(time.time())}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )
        worker.batch_progress.connect(
            lambda current, total, filename: self.worker_batch_progress.emit(
                worker_id, current, total, filename
            )
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"バッチ登録開始: {directory} (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_batch_registration(self, worker_id: str) -> bool:
        """バッチ登録キャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === Annotation ===

    def start_annotation(self, images: list[Image], phash_list: list[str], models: list[str]) -> str:
        """
        アノテーション開始

        Args:
            images: アノテーション対象画像
            phash_list: pHashリスト
            models: 使用モデルリスト

        Returns:
            str: ワーカーID
        """
        worker = AnnotationWorker(images, phash_list, models)
        worker_id = f"annotation_{int(time.time())}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"アノテーション開始: {len(images)}件 (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_annotation(self, worker_id: str) -> bool:
        """アノテーションキャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === Enhanced Annotation (Phase 2) ===

    def start_enhanced_single_annotation(
        self, images: list[Image], phash_list: list[str], models: list[str]
    ) -> str:
        """Enhanced単発アノテーション開始

        Args:
            images: アノテーション対象画像リスト
            phash_list: pHashリスト
            models: 使用モデル名リスト

        Returns:
            str: ワーカーID
        """
        worker = AnnotationWorker(
            images=images, phash_list=phash_list, models=models, operation_mode="single"
        )
        worker_id = f"enhanced_annotation_{int(time.time())}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(
                f"Enhanced単発アノテーション開始: {len(images)}画像, {len(models)}モデル (ID: {worker_id})"
            )
            return worker_id
        else:
            raise RuntimeError(f"Enhanced Annotationワーカー開始失敗: {worker_id}")

    def start_enhanced_batch_annotation(
        self, image_paths: list[str], models: list[str], batch_size: int = 100
    ) -> str:
        """Enhancedバッチアノテーション開始

        Args:
            image_paths: 画像パスリスト
            models: 使用モデル名リスト
            batch_size: バッチサイズ

        Returns:
            str: ワーカーID
        """
        worker = AnnotationWorker(
            image_paths=image_paths, models=models, batch_size=batch_size, operation_mode="batch"
        )
        worker_id = f"enhanced_batch_{int(time.time())}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(
                f"Enhancedバッチアノテーション開始: {len(image_paths)}画像, {len(models)}モデル (ID: {worker_id})"
            )
            return worker_id
        else:
            raise RuntimeError(f"Enhanced Batch Annotationワーカー開始失敗: {worker_id}")

    def start_model_sync(self) -> str:
        """モデル同期開始

        Returns:
            str: ワーカーID
        """
        worker = ModelSyncWorker()
        worker_id = f"model_sync_{int(time.time())}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"モデル同期開始 (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"Model Syncワーカー開始失敗: {worker_id}")

    def cancel_enhanced_annotation(self, worker_id: str) -> bool:
        """Enhanced Annotationキャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === Search ===

    def start_search(self, filter_conditions: dict[str, Any]) -> str:
        """
        検索開始（既存の検索は自動キャンセル）

        Args:
            filter_conditions: フィルター条件

        Returns:
            str: ワーカーID
        """
        # 既存の検索をキャンセル
        if self.current_search_worker_id:
            logger.info(f"既存の検索をキャンセル: {self.current_search_worker_id}")
            self.worker_manager.cancel_worker(self.current_search_worker_id)
            self.current_search_worker_id = None

        worker = SearchWorker(self.db_manager, filter_conditions)
        worker_id = f"search_{int(time.time())}"
        self.current_search_worker_id = worker_id

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"検索開始: {filter_conditions} (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_search(self, worker_id: str) -> bool:
        """検索キャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === Thumbnail Loading ===

    def start_thumbnail_loading(self, search_result: "SearchResult", thumbnail_size: QSize) -> str:
        """
        サムネイル読み込み開始（既存の読み込みは自動キャンセル）

        Args:
            search_result: 検索結果オブジェクト
            thumbnail_size: サムネイルサイズ

        Returns:
            str: ワーカーID
        """
        # 既存のサムネイル読み込みをキャンセル
        if self.current_thumbnail_worker_id:
            logger.info(f"既存のサムネイル読み込みをキャンセル: {self.current_thumbnail_worker_id}")
            self.worker_manager.cancel_worker(self.current_thumbnail_worker_id)
            self.current_thumbnail_worker_id = None

        worker = ThumbnailWorker(search_result, thumbnail_size, self.db_manager)
        worker_id = f"thumbnail_{int(time.time())}"
        self.current_thumbnail_worker_id = worker_id

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"サムネイル読み込み開始: {len(search_result.image_metadata)}件 (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_thumbnail_loading(self, worker_id: str) -> bool:
        """サムネイル読み込みキャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === General Worker Management ===

    def cancel_all_workers(self) -> None:
        """全ワーカーキャンセル"""
        self.worker_manager.cancel_all_workers()

    def get_active_worker_count(self) -> int:
        """アクティブワーカー数取得"""
        return self.worker_manager.get_active_worker_count()

    def get_active_worker_ids(self) -> list[str]:
        """アクティブワーカーIDリスト取得"""
        return self.worker_manager.get_active_worker_ids()

    def is_worker_active(self, worker_id: str) -> bool:
        """ワーカーアクティブ状態確認"""
        return self.worker_manager.is_worker_active(worker_id)

    def wait_for_all_workers(self, timeout_ms: int = 30000) -> bool:
        """全ワーカー完了待機"""
        return self.worker_manager.wait_for_all_workers(timeout_ms)

    # === Private Event Handlers ===

    def _on_worker_started(self, worker_id: str) -> None:
        """ワーカー開始イベントハンドラー"""
        if worker_id.startswith("batch_reg"):
            self.batch_registration_started.emit(worker_id)
        elif worker_id.startswith("annotation"):
            self.annotation_started.emit(worker_id)
        elif worker_id.startswith("enhanced_annotation") or worker_id.startswith("enhanced_batch"):
            self.enhanced_annotation_started.emit(worker_id)
        elif worker_id.startswith("model_sync"):
            self.model_sync_started.emit(worker_id)
        elif worker_id.startswith("search"):
            self.search_started.emit(worker_id)
        elif worker_id.startswith("thumbnail"):
            self.thumbnail_started.emit(worker_id)

    def _on_worker_finished(self, worker_id: str, result) -> None:
        """ワーカー完了イベントハンドラー"""
        if worker_id.startswith("batch_reg"):
            self.current_registration_worker_id = None
            self.batch_registration_finished.emit(result)
        elif worker_id.startswith("annotation"):
            self.current_annotation_worker_id = None
            self.annotation_finished.emit(result)
        elif worker_id.startswith("enhanced_annotation") or worker_id.startswith("enhanced_batch"):
            self.enhanced_annotation_finished.emit(result)
        elif worker_id.startswith("model_sync"):
            self.model_sync_finished.emit(result)
        elif worker_id.startswith("search"):
            self.current_search_worker_id = None
            self.search_finished.emit(result)
        elif worker_id.startswith("thumbnail"):
            self.current_thumbnail_worker_id = None
            self.thumbnail_finished.emit(result)

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーイベントハンドラー"""
        if worker_id.startswith("batch_reg"):
            self.current_registration_worker_id = None
            self.batch_registration_error.emit(error)
        elif worker_id.startswith("annotation"):
            self.current_annotation_worker_id = None
            self.annotation_error.emit(error)
        elif worker_id.startswith("enhanced_annotation") or worker_id.startswith("enhanced_batch"):
            self.enhanced_annotation_error.emit(error)
        elif worker_id.startswith("model_sync"):
            self.model_sync_error.emit(error)
        elif worker_id.startswith("search"):
            self.current_search_worker_id = None
            self.search_error.emit(error)
        elif worker_id.startswith("thumbnail"):
            self.current_thumbnail_worker_id = None
            self.thumbnail_error.emit(error)

    # === Utility Methods ===

    def get_service_summary(self) -> dict[str, Any]:
        """サービス状態サマリー取得"""
        return {
            "service_name": "WorkerService",
            "active_workers": self.get_active_worker_count(),
            "worker_details": self.worker_manager.get_worker_summary(),
        }
