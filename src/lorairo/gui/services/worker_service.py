# src/lorairo/services/worker_service.py

import uuid
from pathlib import Path
from typing import Any

from PIL.Image import Image
from PySide6.QtCore import QObject, QSize, Signal

from ...database.db_manager import ImageDatabaseManager
from ...services.search_models import SearchConditions
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..workers.annotation_worker import AnnotationWorker, ModelSyncWorker
from ..workers.database_worker import (
    DatabaseRegistrationWorker,
    SearchResult,
    SearchWorker,
    ThumbnailWorker,
)
from ..workers.manager import WorkerManager


class WorkerService(QObject):
    """
    Workerサービス - 高レベルAPI提供。
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
        return self.start_batch_registration_with_fsm(directory, self.fsm)

    def start_batch_registration_with_fsm(self, directory: Path, fsm: FileSystemManager) -> str:
        """
        バッチ登録開始（FileSystemManager指定版）

        Args:
            directory: 登録対象ディレクトリ
            fsm: 初期化済みFileSystemManager

        Returns:
            str: ワーカーID
        """
        worker = DatabaseRegistrationWorker(directory, self.db_manager, fsm)
        worker_id = f"batch_reg_{uuid.uuid4().hex[:8]}"

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
        worker_id = f"annotation_{uuid.uuid4().hex[:8]}"

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
        worker_id = f"enhanced_annotation_{uuid.uuid4().hex[:8]}"

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
        worker_id = f"enhanced_batch_{uuid.uuid4().hex[:8]}"

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
        worker_id = f"model_sync_{uuid.uuid4().hex[:8]}"

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

    def start_search(self, search_conditions: SearchConditions) -> str:
        """
        検索開始（既存の検索は自動キャンセル）

        Args:
            search_conditions: 検索条件

        Returns:
            str: ワーカーID

        Raises:
            RuntimeError: ワーカー開始失敗の場合
        """
        # 既存の検索をキャンセル
        if self.current_search_worker_id:
            logger.info(f"既存の検索をキャンセル: {self.current_search_worker_id}")
            self.worker_manager.cancel_worker(self.current_search_worker_id)
            self.current_search_worker_id = None

        worker = SearchWorker(self.db_manager, search_conditions)
        worker_id = f"search_{uuid.uuid4().hex[:8]}"
        self.current_search_worker_id = worker_id

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
            logger.info(f"検索開始: {search_conditions} (ID: {worker_id})")
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_search(self, worker_id: str) -> bool:
        """検索キャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === Thumbnail ===

    def start_thumbnail_load(self, search_result: SearchResult, thumbnail_size: QSize) -> str:
        """
        サムネイル読み込み開始

        Args:
            search_result: 検索結果オブジェクト（image_metadataを含む）
            thumbnail_size: サムネイルサイズ（通常128x128）

        Returns:
            str: ワーカーID

        Raises:
            RuntimeError: ワーカー開始失敗の場合
            TypeError: 引数の型が不正な場合
            ValueError: 引数の値が不正な場合
        """
        # 引数バリデーション
        if not isinstance(search_result, SearchResult):
            raise TypeError(f"Expected SearchResult, got {type(search_result)}")

        if not search_result.image_metadata:
            raise ValueError("SearchResult.image_metadata is empty")

        if not isinstance(thumbnail_size, QSize) or thumbnail_size.isEmpty():
            logger.warning(f"Invalid thumbnail_size: {thumbnail_size}, using default QSize(128, 128)")
            thumbnail_size = QSize(128, 128)

        # ThumbnailWorker作成 - 正しいパラメータで初期化
        worker = ThumbnailWorker(search_result, thumbnail_size, self.db_manager)
        worker_id = f"thumbnail_{uuid.uuid4().hex[:8]}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(
                f"サムネイル読み込み開始: {len(search_result.image_metadata)}件, "
                f"サイズ={thumbnail_size.width()}x{thumbnail_size.height()} (ID: {worker_id})"
            )
            return worker_id
        else:
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_thumbnail_load(self, worker_id: str) -> bool:
        """サムネイル読み込みキャンセル"""
        return self.worker_manager.cancel_worker(worker_id)

    # === 全般管理 ===

    def cancel_all_workers(self) -> None:
        """全ワーカーキャンセル"""
        self.worker_manager.cancel_all_workers()

    def get_active_worker_count(self) -> int:
        """アクティブワーカー数取得"""
        return self.worker_manager.active_worker_count()

    def get_worker_status(self, worker_id: str) -> str | None:
        """指定ワーカーのステータス取得"""
        return self.worker_manager.get_worker_status(worker_id)

    # === プライベートメソッド ===

    def _on_worker_started(self, worker_id: str) -> None:
        """ワーカー開始ハンドラ"""
        if worker_id.startswith("batch_reg_"):
            self.batch_registration_started.emit(worker_id)
        elif worker_id.startswith("annotation_"):
            self.annotation_started.emit(worker_id)
        elif worker_id.startswith("enhanced_"):
            self.enhanced_annotation_started.emit(worker_id)
        elif worker_id.startswith("model_sync_"):
            self.model_sync_started.emit(worker_id)
        elif worker_id.startswith("search_"):
            self.search_started.emit(worker_id)
        elif worker_id.startswith("thumbnail_"):
            self.thumbnail_started.emit(worker_id)

    def _on_worker_finished(self, worker_id: str, result: Any) -> None:
        """ワーカー完了ハンドラ"""
        if worker_id.startswith("batch_reg_"):
            self.batch_registration_finished.emit(result)
            if self.current_registration_worker_id == worker_id:
                self.current_registration_worker_id = None
        elif worker_id.startswith("annotation_"):
            self.annotation_finished.emit(result)
            if self.current_annotation_worker_id == worker_id:
                self.current_annotation_worker_id = None
        elif worker_id.startswith("enhanced_"):
            self.enhanced_annotation_finished.emit(result)
        elif worker_id.startswith("model_sync_"):
            self.model_sync_finished.emit(result)
        elif worker_id.startswith("search_"):
            self.search_finished.emit(result)
            if self.current_search_worker_id == worker_id:
                self.current_search_worker_id = None
        elif worker_id.startswith("thumbnail_"):
            self.thumbnail_finished.emit(result)
            if self.current_thumbnail_worker_id == worker_id:
                self.current_thumbnail_worker_id = None

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーハンドラ"""
        logger.error(f"ワーカーエラー {worker_id}: {error}")

        if worker_id.startswith("batch_reg_"):
            self.batch_registration_error.emit(error)
            if self.current_registration_worker_id == worker_id:
                self.current_registration_worker_id = None
        elif worker_id.startswith("annotation_"):
            self.annotation_error.emit(error)
            if self.current_annotation_worker_id == worker_id:
                self.current_annotation_worker_id = None
        elif worker_id.startswith("enhanced_"):
            self.enhanced_annotation_error.emit(error)
        elif worker_id.startswith("model_sync_"):
            self.model_sync_error.emit(error)
        elif worker_id.startswith("search_"):
            self.search_error.emit(error)
            if self.current_search_worker_id == worker_id:
                self.current_search_worker_id = None
        elif worker_id.startswith("thumbnail_"):
            self.thumbnail_error.emit(error)
            if self.current_thumbnail_worker_id == worker_id:
                self.current_thumbnail_worker_id = None
