# src/lorairo/services/worker_service.py

import uuid
from pathlib import Path
from typing import Any

from PIL.Image import Image
from PySide6.QtCore import QObject, QSize, Signal

from ...annotations.annotation_logic import AnnotationLogic
from ...annotations.annotator_adapter import AnnotatorLibraryAdapter
from ...database.db_manager import ImageDatabaseManager
from ...services.configuration_service import ConfigurationService
from ...services.search_models import SearchConditions
from ...services.service_container import get_service_container
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..workers.annotation_worker import AnnotationWorker
from ..workers.database_worker import (
    DatabaseRegistrationWorker,
    SearchResult,
    SearchWorker,
    ThumbnailWorker,
)
from ..workers.manager import WorkerManager
from ..workers.modern_progress_manager import ModernProgressManager, create_worker_id


class WorkerService(QObject):
    """
    Workerサービス - 高レベルAPI提供。
    各種ワーカーの統一的な管理とGUI層への簡潔なインターフェースを提供。
    """

    # === 統一的なシグナル ===
    batch_registration_started = Signal(str)  # worker_id
    batch_registration_finished = Signal(object)  # DatabaseRegistrationResult
    batch_registration_error = Signal(str)  # error_message

    enhanced_annotation_started = Signal(str)  # worker_id
    enhanced_annotation_finished = Signal(object)  # Enhanced annotation results
    enhanced_annotation_error = Signal(str)  # error_message

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

        # モダンプログレス管理
        self.progress_manager = ModernProgressManager(parent)
        self.progress_manager.cancellation_requested.connect(self._on_progress_cancellation_requested)

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

        # プログレス更新シグナル接続
        self.worker_progress_updated.connect(self._on_progress_updated)
        self.worker_batch_progress.connect(self._on_batch_progress_updated)

        # AnnotationLogic 遅延初期化（依存関係: AnnotatorAdapter, ConfigService, DBManager）
        self._annotation_logic: AnnotationLogic | None = None

        logger.debug("WorkerService initialized")

    @property
    def annotation_logic(self) -> AnnotationLogic:
        """AnnotationLogic 取得（遅延初期化）

        Returns:
            AnnotationLogic: アノテーションビジネスロジック
        """
        if self._annotation_logic is None:
            # ServiceContainer 経由で AnnotatorAdapter 取得
            container = get_service_container()
            annotator_adapter = container.annotator_library

            # AnnotationLogic インスタンス化（annotator_adapterのみ）
            self._annotation_logic = AnnotationLogic(
                annotator_adapter=annotator_adapter,
            )
            logger.debug("AnnotationLogic initialized in WorkerService")

        return self._annotation_logic

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
    # 注: 旧APIメソッド（start_annotation, start_enhanced_single_annotation）は削除済み
    # 新API: start_enhanced_batch_annotation() を使用してください

    def start_enhanced_batch_annotation(
        self,
        image_paths: list[str],
        models: list[str],
    ) -> str:
        """バッチアノテーション開始（新API）

        Args:
            image_paths: 画像パスリスト
            models: 使用モデル名リスト

        Returns:
            str: ワーカーID
        """
        logger.debug(f"バッチアノテーション準備: models={models}, 画像数={len(image_paths)}")

        worker = AnnotationWorker(
            annotation_logic=self.annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=self.db_manager,
        )
        worker_id = f"annotation_{uuid.uuid4().hex[:8]}"

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(
                f"バッチアノテーション開始: {len(image_paths)}画像, {len(models)}モデル (ID: {worker_id})"
            )
            logger.debug(f"  ワーカーID={worker_id}, モデル=[{', '.join(models)}]")
            return worker_id
        else:
            raise RuntimeError(f"アノテーションワーカー開始失敗: {worker_id}")

    def cancel_annotation(self, worker_id: str) -> bool:
        """アノテーションキャンセル"""
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
            self.current_thumbnail_worker_id = worker_id
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

    def start_thumbnail_page_load(
        self,
        search_result: SearchResult,
        thumbnail_size: QSize,
        image_ids: list[int],
        page_num: int,
        request_id: str,
        cancel_previous: bool = True,
    ) -> str:
        """
        ページ単位のサムネイル読み込み開始。

        Args:
            search_result: 検索結果オブジェクト
            thumbnail_size: サムネイルサイズ
            image_ids: 読み込み対象の画像IDリスト
            page_num: 対象ページ番号
            request_id: リクエスト識別子
            cancel_previous: 既存サムネイルワーカーをキャンセルするか

        Returns:
            ワーカーID
        """
        if not isinstance(search_result, SearchResult):
            raise TypeError(f"Expected SearchResult, got {type(search_result)}")

        if not image_ids:
            raise ValueError("image_ids is empty")

        if not isinstance(thumbnail_size, QSize) or thumbnail_size.isEmpty():
            logger.warning(f"Invalid thumbnail_size: {thumbnail_size}, using default QSize(128, 128)")
            thumbnail_size = QSize(128, 128)

        if cancel_previous and self.current_thumbnail_worker_id:
            logger.debug(f"既存のサムネイル読み込みをキャンセル: {self.current_thumbnail_worker_id}")
            self.worker_manager.cancel_worker(self.current_thumbnail_worker_id)
            self.current_thumbnail_worker_id = None

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=thumbnail_size,
            db_manager=self.db_manager,
            image_id_filter=image_ids,
            request_id=request_id,
            page_num=page_num,
        )
        worker_id = f"thumbnail_{uuid.uuid4().hex[:8]}"

        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            self.current_thumbnail_worker_id = worker_id
            logger.info(
                f"ページサムネイル読み込み開始: page={page_num}, count={len(image_ids)}, "
                f"request_id={request_id}, cancel_previous={cancel_previous} (ID: {worker_id})"
            )
            return worker_id

        raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

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

    def _on_progress_updated(self, worker_id: str, progress: "WorkerProgress") -> None:
        """プログレス更新処理 - ModernProgressManagerに転送"""
        self.progress_manager.update_worker_progress(worker_id, progress)

    def _on_batch_progress_updated(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """バッチプログレス更新処理 - ModernProgressManagerに転送"""
        self.progress_manager.update_batch_progress(worker_id, current, total, filename)

    def _on_progress_cancellation_requested(self, worker_id: str) -> None:
        """プログレスダイアログからのキャンセル要求処理"""
        logger.info(f"プログレスダイアログからキャンセル要求: {worker_id}")

        # 該当ワーカーをキャンセル
        success = self.worker_manager.cancel_worker(worker_id)
        if success:
            logger.info(f"ワーカーキャンセル実行: {worker_id}")
        else:
            logger.warning(f"ワーカーキャンセル失敗: {worker_id}")

    # === プライベートメソッド ===

    def _on_worker_started(self, worker_id: str) -> None:
        """ワーカー開始ハンドラ - プログレスダイアログ自動開始"""
        operation_name = "不明な操作"

        if worker_id.startswith("batch_reg_"):
            operation_name = "データベース登録"
            self.batch_registration_started.emit(worker_id)
        elif worker_id.startswith("annotation_"):
            operation_name = "アノテーション処理"
            self.enhanced_annotation_started.emit(worker_id)
        elif worker_id.startswith("search_"):
            operation_name = "検索処理"
            self.search_started.emit(worker_id)
        elif worker_id.startswith("thumbnail_"):
            operation_name = "サムネイル読み込み"
            self.thumbnail_started.emit(worker_id)

        # サムネイル先読みはバックグラウンド処理のためプログレスダイアログ不要
        if not worker_id.startswith("thumbnail_"):
            self.progress_manager.start_worker_progress(
                worker_id, operation_name, f"{operation_name}を開始しています...", parent=self.parent()
            )

        logger.info(f"ワーカー開始: {operation_name} (ID: {worker_id})")

    def _on_worker_finished(self, worker_id: str, result: Any) -> None:
        """ワーカー完了ハンドラ - プログレスダイアログ終了処理"""
        # サムネイルワーカーはプログレスダイアログを使用しないためスキップ
        if not worker_id.startswith("thumbnail_"):
            self.progress_manager.finish_worker_progress(worker_id, success=True)

        if worker_id.startswith("batch_reg_"):
            self.batch_registration_finished.emit(result)
            if self.current_registration_worker_id == worker_id:
                self.current_registration_worker_id = None
        elif worker_id.startswith("annotation_"):
            self.enhanced_annotation_finished.emit(result)
            if self.current_annotation_worker_id == worker_id:
                self.current_annotation_worker_id = None
        elif worker_id.startswith("search_"):
            self.search_finished.emit(result)
            if self.current_search_worker_id == worker_id:
                self.current_search_worker_id = None
        elif worker_id.startswith("thumbnail_"):
            self.thumbnail_finished.emit(result)
            if self.current_thumbnail_worker_id == worker_id:
                self.current_thumbnail_worker_id = None

        logger.info(f"ワーカー完了: {worker_id}")

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーハンドラ - プログレスダイアログエラー処理"""
        logger.error(f"ワーカーエラー {worker_id}: {error}")

        # サムネイルワーカーはプログレスダイアログを使用しないためスキップ
        if not worker_id.startswith("thumbnail_"):
            self.progress_manager.finish_worker_progress(worker_id, success=False)

        if worker_id.startswith("batch_reg_"):
            self.batch_registration_error.emit(error)
            if self.current_registration_worker_id == worker_id:
                self.current_registration_worker_id = None
        elif worker_id.startswith("annotation_"):
            self.enhanced_annotation_error.emit(error)
            if self.current_annotation_worker_id == worker_id:
                self.current_annotation_worker_id = None
        elif worker_id.startswith("search_"):
            self.search_error.emit(error)
            if self.current_search_worker_id == worker_id:
                self.current_search_worker_id = None
        elif worker_id.startswith("thumbnail_"):
            self.thumbnail_error.emit(error)
            if self.current_thumbnail_worker_id == worker_id:
                self.current_thumbnail_worker_id = None

        logger.info(f"ワーカーエラーとプログレス終了: {worker_id}")
