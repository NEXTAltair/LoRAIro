# src/lorairo/services/worker_service.py

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL.Image import Image
from PySide6.QtCore import QObject, QSize, Signal

from ...annotations.annotation_logic import AnnotationLogic
from ...annotations.annotator_adapter import AnnotatorLibraryAdapter
from ...database.db_manager import ImageDatabaseManager
from ...services.configuration_service import ConfigurationService
from ...services.job_ledger_service import JobLedgerService, JobStatus
from ...services.model_registry_protocol import local_ml_model_names
from ...services.search_models import SearchConditions
from ...services.service_container import get_service_container
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..workers.annotation_worker import AnnotationWorker
from ..workers.base import LoRAIroWorkerBase, WorkerProgress
from ..workers.manager import WorkerManager
from ..workers.model_install_worker import ModelInstallWorker
from ..workers.registration_worker import DatabaseRegistrationWorker
from ..workers.search_worker import SearchResult, SearchWorker
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent
from ..workers.thumbnail_worker import ThumbnailWorker
from .operation_events import OperationContext, OperationOutcome, OperationType, WorkerOperationEvent

if TYPE_CHECKING:
    from ..widgets.run_settings_dialog import RunOptions

# ADR 0066 §3: Jobs 台帳に載せる operation (Pipeline/Operation レベル) とその表示タイトル。
# 検索/サムネイル等の UI 応答系 worker は載せない (firehose 化を防ぐ)。
_JOB_LEDGER_TITLES: dict[OperationType, str] = {
    OperationType.BATCH_REGISTRATION: "データベース登録",
    OperationType.BATCH_IMPORT: "バッチインポート",
    OperationType.ANNOTATION: "アノテーション処理",
    OperationType.MODEL_INSTALL: "モデルインストール",  # Issue #754 (ADR 0066 §5)
}


@dataclass(frozen=True)
class _QueuedGpuJob:
    """GPU 直列キューで起動待機中のジョブ (ADR 0066 §6)。

    Issue #754: アノテーションに加えて model_install ジョブも GPU 直列スロットを
    使う (インストール完了 → 推論実行の順序を構造的に保証するため)。
    """

    worker_id: str
    worker: LoRAIroWorkerBase[Any]  # Any使用: ジョブ種別ごとに Worker の結果型が異なる


class WorkerService(QObject):
    """
    Workerサービス - 高レベルAPI提供。
    各種ワーカーの統一的な管理とGUI層への簡潔なインターフェースを提供。
    """

    # === 統一的なシグナル ===
    batch_registration_started = Signal(str)  # worker_id
    batch_registration_finished = Signal(object)  # DatabaseRegistrationResult
    batch_registration_error = Signal(str)  # error_message
    batch_registration_canceled = Signal(str)  # worker_id

    enhanced_annotation_started = Signal(str)  # worker_id
    enhanced_annotation_finished = Signal(object)  # Enhanced annotation results
    enhanced_annotation_error = Signal(str)  # error_message
    enhanced_annotation_canceled = Signal(str)  # worker_id

    search_started = Signal(str)  # worker_id
    search_finished = Signal(object)  # SearchResult
    search_error = Signal(str)  # error_message
    search_canceled = Signal(str)  # worker_id

    thumbnail_started = Signal(str)  # worker_id
    thumbnail_finished = Signal(object)  # ThumbnailLoadResult
    thumbnail_error = Signal(str)  # error_message
    thumbnail_canceled = Signal(str)  # worker_id

    batch_import_started = Signal(str)  # worker_id
    batch_import_finished = Signal(object)  # BatchImportResult
    batch_import_error = Signal(str)  # error_message
    batch_import_canceled = Signal(str)  # worker_id

    model_install_started = Signal(str)  # worker_id (Issue #754)
    model_install_finished = Signal(object)  # ModelInstallResult
    model_install_error = Signal(str)  # error_message
    model_install_canceled = Signal(str)  # worker_id

    # === 進捗シグナル ===
    worker_progress_updated = Signal(str, object)  # worker_id, WorkerProgress
    worker_batch_progress = Signal(str, int, int, str)  # worker_id, current, total, filename
    worker_terminal = Signal(object)  # WorkerTerminalEvent
    operation_event = Signal(object)  # WorkerOperationEvent
    job_ledger_changed = Signal()  # ADR 0066: 同期ジョブ台帳の変更通知

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

        # ADR 0066: 同期ジョブの in-memory 台帳 (進捗ポップアップ廃止後の lifecycle ビュー)
        self.job_ledger = JobLedgerService()

        # シングルトンワーカー管理
        self.current_search_worker_id: str | None = None
        self.current_registration_worker_id: str | None = None
        self.current_annotation_worker_id: str | None = None
        self.current_thumbnail_worker_id: str | None = None
        self.current_batch_import_worker_id: str | None = None
        self._worker_operations: dict[str, OperationContext] = {}
        self._operation_sequence = 0
        self._search_generation = 0
        self._thumbnail_generation = 0

        # ADR 0066 §6: ローカル GPU 推論ジョブの直列キュー (VRAM 競合防止、同時 1 件)
        self._gpu_active_worker_id: str | None = None
        self._gpu_queue: list[_QueuedGpuJob] = []
        # Issue #754: install ジョブ -> 後続アノテーションジョブの連結
        # (install 失敗/キャンセル時に後続を取り消すための対応表)
        self._install_chained_annotation: dict[str, str] = {}

        # ワーカーマネージャーのシグナル接続
        self.worker_manager.worker_started.connect(self._on_worker_started)
        self.worker_manager.worker_terminal.connect(self._on_worker_terminal)
        self.worker_manager.active_worker_count_changed.connect(self.active_worker_count_changed)
        self.worker_manager.all_workers_finished.connect(self.all_workers_finished)

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
        self._register_operation(worker_id, OperationType.BATCH_REGISTRATION)

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
            self.current_registration_worker_id = worker_id
            logger.info(f"バッチ登録開始: {directory} (ID: {worker_id})")
            return worker_id
        else:
            self._worker_operations.pop(worker_id, None)
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
        litellm_model_ids: list[str],
        run_options: "RunOptions | None" = None,
    ) -> str:
        """バッチアノテーション開始（新API）

        Issue #245 / ADR 0023 Phase 1.11: モデル指定は `Model.litellm_model_id`
        (registry key SSoT) で受け取る。

        ADR 0066 §6: 選択モデルにローカル ML (provider 空/"local") が含まれる
        ジョブは GPU 直列キューで同時 1 件に制御する。先行 GPU ジョブの実行中は
        queued 状態で台帳に載せ、前ジョブの終端で自動起動する。API 系のみの
        ジョブは従来通り並列実行する。

        Args:
            image_paths: 画像パスリスト
            litellm_model_ids: 使用モデルの `litellm_model_id` リスト
            run_options: 実行詳細設定 (Issue #803)。``dry_run`` / ``rating_gate`` を
                AnnotationWorker に伝搬する。``None`` の場合は従来挙動。

        Returns:
            str: ワーカーID
        """
        # ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): refusal 送信前
        # filter は AnnotationWorker.execute() 冒頭で実行する。GUI スレッド上
        # で N+1 DB クエリを避け (大量画像選択時の UI freeze 防止)、Worker 内で
        # async / 進捗シグナル経由で実行する。filter ロジック自体は Worker
        # 内 `_apply_refusal_prefilter()` 参照。
        logger.debug(
            f"バッチアノテーション準備: litellm_model_ids={litellm_model_ids}, 画像数={len(image_paths)}"
        )

        model_registry = get_service_container().model_registry
        worker = AnnotationWorker(
            annotation_logic=self.annotation_logic,
            image_paths=image_paths,
            litellm_model_ids=litellm_model_ids,
            db_manager=self.db_manager,
            model_registry=model_registry,
            run_options=run_options,
        )
        worker_id = f"annotation_{uuid.uuid4().hex[:8]}"
        self._register_operation(worker_id, OperationType.ANNOTATION)

        # 進捗シグナル接続
        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        # ADR 0066 §6: GPU ジョブ判定とキュー投入
        local_models = local_ml_model_names(litellm_model_ids, model_registry)
        requires_gpu = bool(local_models)

        # Issue #754: 未インストールのローカル ML モデルがあれば model_install ジョブを
        # 前段に連結する (install 実行中/待機中、後続アノテーションは queued で待機)
        missing_models = self._detect_missing_local_models(local_models)
        if missing_models:
            install_worker_id = self._start_model_install(missing_models)
            if install_worker_id is not None:
                self._install_chained_annotation[install_worker_id] = worker_id
                self._enqueue_gpu_annotation(worker_id, worker, len(image_paths), len(litellm_model_ids))
                return worker_id

        if requires_gpu and self._gpu_active_worker_id is not None:
            self._enqueue_gpu_annotation(worker_id, worker, len(image_paths), len(litellm_model_ids))
            return worker_id

        if requires_gpu:
            # start_worker 中に即終端しても terminal handler が解放できるよう先に確定する
            self._gpu_active_worker_id = worker_id

        if self.worker_manager.start_worker(worker_id, worker):
            self.current_annotation_worker_id = worker_id
            logger.info(
                f"バッチアノテーション開始: {len(image_paths)}画像 (filter 前), "
                f"{len(litellm_model_ids)}モデル (ID: {worker_id}, GPU直列={requires_gpu})"
            )
            logger.debug("  refusal filter は Worker 内で実行 (Codex P2 対応)")
            logger.debug(f"  ワーカーID={worker_id}, litellm_model_ids=[{', '.join(litellm_model_ids)}]")
            return worker_id
        else:
            self._worker_operations.pop(worker_id, None)
            if self._gpu_active_worker_id == worker_id:
                self._gpu_active_worker_id = None
            raise RuntimeError(f"アノテーションワーカー開始失敗: {worker_id}")

    def cancel_annotation(self, worker_id: str) -> bool:
        """アノテーションキャンセル

        queued (GPU 直列キュー待機中) のジョブは実行前に即時取り消す (ADR 0066 §6)。
        """
        if self._cancel_queued_gpu_job(worker_id):
            return True
        return self.worker_manager.cancel_worker(worker_id)

    # === Model Install (Issue #754, ADR 0066 §5) ===

    def _detect_missing_local_models(self, local_model_names: list[str]) -> list[str]:
        """選択中のローカル ML モデルから未インストールのものを検出する。

        Args:
            local_model_names: 選択されたローカル ML モデル名リスト。

        Returns:
            未インストールのモデル名リスト (空ならインストール不要)。
        """
        if not local_model_names:
            return []
        adapter = get_service_container().annotator_library
        missing = adapter.get_missing_local_models(local_model_names)
        if missing:
            logger.info(f"未インストールのローカルMLモデルを検出: {missing}")
        return missing

    def _start_model_install(self, model_names: list[str]) -> str | None:
        """model_install ワーカーを GPU 直列スロットで起動 (または待機投入) する。

        インストールと GPU 推論を同一直列スロットで扱うことで
        「install 完了 → 推論実行」の順序を構造的に保証する (Issue #754)。

        Args:
            model_names: インストール対象のモデル名リスト。

        Returns:
            起動/投入した install ワーカーID。起動失敗時は None
            (呼び出し元は install なしの従来フロー = 暗黙ダウンロードに縮退)。
        """
        adapter = get_service_container().annotator_library
        worker = ModelInstallWorker(adapter, model_names, db_manager=self.db_manager)
        worker_id = f"model_install_{uuid.uuid4().hex[:8]}"
        self._register_operation(worker_id, OperationType.MODEL_INSTALL)

        worker.progress_updated.connect(
            lambda progress: self._on_model_install_progress(worker_id, progress)
        )

        if self._gpu_active_worker_id is not None:
            self._enqueue_gpu_job(worker_id, worker, OperationType.MODEL_INSTALL)
            logger.info(
                f"モデルインストールをGPU直列キューに投入: {model_names} (ID: {worker_id}, "
                f"実行中: {self._gpu_active_worker_id})"
            )
            return worker_id

        self._gpu_active_worker_id = worker_id
        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"モデルインストール開始: {len(model_names)}件 {model_names} (ID: {worker_id})")
            return worker_id

        # 起動失敗: install なしの従来フロー (推論中の暗黙ダウンロード) に縮退する
        logger.error(f"モデルインストールワーカー開始失敗: {worker_id} — 暗黙ダウンロードに縮退")
        self._worker_operations.pop(worker_id, None)
        if self._gpu_active_worker_id == worker_id:
            self._gpu_active_worker_id = None
        return None

    def _on_model_install_progress(self, worker_id: str, progress: WorkerProgress) -> None:
        """install ワーカーの DL 進捗を Jobs 台帳のサマリー列へ反映する (Issue #754)。"""
        self.worker_progress_updated.emit(worker_id, progress)
        if self.job_ledger.update(worker_id, summary=progress.status_message) is not None:
            self.job_ledger_changed.emit()

    def _handle_install_chain_terminal(self, event: WorkerTerminalEvent) -> None:
        """install ジョブの終端時に連結アノテーションの扱いを確定する (Issue #754)。

        install が成功すれば連結を解除して GPU キューの自動起動に任せる。
        失敗/キャンセル時は後続アノテーションを取り消す (未インストールのまま
        推論に入って暗黙ダウンロードでフリーズする状況を防ぐ)。
        """
        if not event.worker_id.startswith("model_install_"):
            return
        if event.outcome is WorkerOutcome.SUCCEEDED:
            self._install_chained_annotation.pop(event.worker_id, None)
            return
        self._cancel_chained_annotation(event.worker_id)

    def _cancel_chained_annotation(self, install_worker_id: str) -> None:
        """install 未完了時に連結された後続アノテーションを取り消す。"""
        chained_id = self._install_chained_annotation.pop(install_worker_id, None)
        if chained_id is None:
            return
        if self._cancel_queued_gpu_job(chained_id, reason=CancelReason.PIPELINE_CANCEL):
            logger.info(f"モデルインストール未完了のため後続アノテーションを取り消し: {chained_id}")

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
        # 既存の検索を破棄(新検索による置換。ユーザーキャンセルではない)
        if self.current_search_worker_id:
            logger.debug(f"前回検索を破棄(新検索で置換): {self.current_search_worker_id}")
            self.worker_manager.cancel_worker(
                self.current_search_worker_id,
                reason=CancelReason.SEARCH_REPLACED,
            )
            self.current_search_worker_id = None

        worker = SearchWorker(self.db_manager, search_conditions)
        worker_id = f"search_{uuid.uuid4().hex[:8]}"
        self._search_generation += 1
        self._register_operation(worker_id, OperationType.SEARCH, generation=self._search_generation)
        previous_search_worker_id = self.current_search_worker_id
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
            self._worker_operations.pop(worker_id, None)
            if self.current_search_worker_id == worker_id:
                self.current_search_worker_id = previous_search_worker_id
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_search(
        self,
        worker_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
    ) -> bool:
        """検索キャンセル"""
        return self._cancel_worker(worker_id, reason)

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
        self._thumbnail_generation += 1
        self._register_operation(worker_id, OperationType.THUMBNAIL, generation=self._thumbnail_generation)
        previous_thumbnail_worker_id = self.current_thumbnail_worker_id
        self.current_thumbnail_worker_id = worker_id

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
            self._worker_operations.pop(worker_id, None)
            if self.current_thumbnail_worker_id == worker_id:
                self.current_thumbnail_worker_id = previous_thumbnail_worker_id
            raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_thumbnail_load(
        self,
        worker_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
    ) -> bool:
        """サムネイル読み込みキャンセル"""
        return self._cancel_worker(worker_id, reason)

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
            self.worker_manager.cancel_worker(
                self.current_thumbnail_worker_id,
                reason=CancelReason.THUMBNAIL_REPLACED,
            )
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
        self._thumbnail_generation += 1
        self._register_operation(
            worker_id,
            OperationType.THUMBNAIL,
            request_id=request_id,
            generation=self._thumbnail_generation,
        )
        previous_thumbnail_worker_id = self.current_thumbnail_worker_id
        self.current_thumbnail_worker_id = worker_id

        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )

        if self.worker_manager.start_worker(worker_id, worker):
            logger.debug(
                f"ページサムネイル読み込み開始: page={page_num}, count={len(image_ids)}, "
                f"request_id={request_id}, cancel_previous={cancel_previous} (ID: {worker_id})"
            )
            return worker_id

        self._worker_operations.pop(worker_id, None)
        if self.current_thumbnail_worker_id == worker_id:
            self.current_thumbnail_worker_id = previous_thumbnail_worker_id
        raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def start_batch_import(
        self,
        jsonl_files: list[Path],
        *,
        dry_run: bool = False,
        model_name_override: str | None = None,
    ) -> str:
        """バッチインポートワーカーを開始する。

        Args:
            jsonl_files: インポート対象のJSONLファイルリスト。
            dry_run: Trueの場合、DB書き込みを行わない。
            model_name_override: モデル名上書き。

        Returns:
            ワーカーID。
        """
        from ..workers.batch_import_worker import BatchImportWorker

        container = get_service_container()
        repository = container.db_manager.image_repo

        worker = BatchImportWorker(
            repository,
            jsonl_files,
            dry_run=dry_run,
            model_name_override=model_name_override,
            db_manager=self.db_manager,
        )
        worker_id = f"batch_import_{uuid.uuid4().hex[:8]}"
        self._register_operation(worker_id, OperationType.BATCH_IMPORT)

        worker.progress_updated.connect(
            lambda progress: self.worker_progress_updated.emit(worker_id, progress)
        )
        worker.batch_progress.connect(
            lambda current, total, filename: self.worker_batch_progress.emit(
                worker_id, current, total, filename
            )
        )

        mode = "DRY-RUN" if dry_run else "LIVE"
        if self.worker_manager.start_worker(worker_id, worker):
            logger.info(f"バッチインポート開始: {len(jsonl_files)}ファイル ({mode}) (ID: {worker_id})")
            self.current_batch_import_worker_id = worker_id
            return worker_id

        self._worker_operations.pop(worker_id, None)
        raise RuntimeError(f"ワーカー開始失敗: {worker_id}")

    def cancel_batch_import(self, worker_id: str) -> None:
        """バッチインポートワーカーをキャンセルする。

        Args:
            worker_id: キャンセル対象のワーカーID。
        """
        self.worker_manager.cancel_worker(worker_id)

    # === 全般管理 ===

    def cancel_all_workers(self) -> None:
        """全ワーカーキャンセル (GPU 直列キューの待機ジョブも含めて取り消す)"""
        # 実行中ジョブの終端で次の待機ジョブが自動起動しないよう、先にキューを空にする
        for queued_job in list(self._gpu_queue):
            self._cancel_queued_gpu_job(queued_job.worker_id, reason=CancelReason.SHUTDOWN)
        self.worker_manager.cancel_all_workers(reason=CancelReason.SHUTDOWN)

    def get_active_worker_count(self) -> int:
        """アクティブワーカー数取得"""
        return self.worker_manager.get_active_worker_count()

    def get_worker_status(self, worker_id: str) -> str | None:
        """指定ワーカーのステータス取得"""
        if self.worker_manager.is_worker_active(worker_id):
            return "active"
        return None

    def cancel_job(self, worker_id: str) -> bool:
        """Jobs タブの行アクションからのジョブキャンセル (ADR 0066 §4)。

        進捗ポップアップ廃止に伴い、同期ジョブのキャンセル操作は
        Jobs タブの行ボタンへ移設された。queued (GPU 直列キュー待機中) の
        ジョブは実行前に即時 canceled として終端する (ADR 0066 §6)。

        Args:
            worker_id: キャンセル対象のワーカーID (= 台帳 job_id)。

        Returns:
            キャンセル要求を発行できたかどうか。
        """
        if self._cancel_queued_gpu_job(worker_id):
            return True
        return self.worker_manager.cancel_worker(worker_id)

    # === プライベートメソッド ===

    def _on_worker_started(self, worker_id: str) -> None:
        """ワーカー開始ハンドラ - 互換 started シグナルと operation/台帳イベント発行"""
        operation_name = "不明な操作"

        if worker_id.startswith("batch_reg_"):
            operation_name = "データベース登録"
            self.batch_registration_started.emit(worker_id)
        elif worker_id.startswith("batch_import_"):
            operation_name = "バッチインポート"
            self.batch_import_started.emit(worker_id)
        elif worker_id.startswith("annotation_"):
            operation_name = "アノテーション処理"
            self.enhanced_annotation_started.emit(worker_id)
        elif worker_id.startswith("model_install_"):
            operation_name = "モデルインストール"
            self.model_install_started.emit(worker_id)
        elif worker_id.startswith("search_"):
            operation_name = "検索処理"
            self.search_started.emit(worker_id)
        elif worker_id.startswith("thumbnail_"):
            operation_name = "サムネイル読み込み"
            self.thumbnail_started.emit(worker_id)

        self._emit_operation_started(worker_id)
        # ライフサイクルINFOはこの1層に集約。search/thumbnailは高頻度なのでDEBUGに落とす。
        log_lifecycle = (
            logger.info
            if self._resolve_worker_type(worker_id)
            in ("batch_reg", "batch_import", "annotation", "model_install")
            else logger.debug
        )
        log_lifecycle(f"ワーカー開始: {operation_name} (ID: {worker_id})")

    def _resolve_worker_type(self, worker_id: str) -> str:
        """worker_idプレフィックスからワーカー種別を返すヘルパー。"""
        for prefix in (
            "batch_reg_",
            "batch_import_",
            "annotation_",
            "model_install_",
            "search_",
            "thumbnail_",
        ):
            if worker_id.startswith(prefix):
                return prefix.rstrip("_")
        return "unknown"

    def _on_worker_finished(self, worker_id: str, result: Any) -> None:
        """ワーカー完了ハンドラ - 互換シグナルとcurrent idの更新のみ行う"""
        worker_type = self._resolve_worker_type(worker_id)
        finished_dispatch: dict[str, tuple[Any, str | None]] = {
            "batch_reg": (self.batch_registration_finished, "current_registration_worker_id"),
            "batch_import": (self.batch_import_finished, "current_batch_import_worker_id"),
            "annotation": (self.enhanced_annotation_finished, "current_annotation_worker_id"),
            "model_install": (self.model_install_finished, None),
            "search": (self.search_finished, "current_search_worker_id"),
            "thumbnail": (self.thumbnail_finished, "current_thumbnail_worker_id"),
        }
        if worker_type in finished_dispatch:
            signal, attr = finished_dispatch[worker_type]
            signal.emit(result)
            if attr and getattr(self, attr) == worker_id:
                setattr(self, attr, None)

        # ライフサイクルINFOはこの1層に集約。search/thumbnailは高頻度なのでDEBUGに落とす。
        log_lifecycle = (
            logger.info if worker_type in ("batch_reg", "batch_import", "annotation") else logger.debug
        )
        log_lifecycle(f"ワーカー完了: {worker_id}")

    def _on_worker_error(self, worker_id: str, error: str) -> None:
        """ワーカーエラーハンドラ - 互換エラーシグナルとcurrent idの更新のみ行う"""
        logger.error(f"ワーカーエラー {worker_id}: {error}")

        worker_type = self._resolve_worker_type(worker_id)
        error_dispatch: dict[str, tuple[Any, str | None]] = {
            "batch_reg": (self.batch_registration_error, "current_registration_worker_id"),
            "batch_import": (self.batch_import_error, "current_batch_import_worker_id"),
            "annotation": (self.enhanced_annotation_error, "current_annotation_worker_id"),
            "model_install": (self.model_install_error, None),
            "search": (self.search_error, "current_search_worker_id"),
            "thumbnail": (self.thumbnail_error, "current_thumbnail_worker_id"),
        }
        if worker_type in error_dispatch:
            signal, attr = error_dispatch[worker_type]
            signal.emit(error)
            if attr and getattr(self, attr) == worker_id:
                setattr(self, attr, None)

        logger.info(f"ワーカーエラー処理完了: {worker_id}")

    def _on_worker_canceled(self, worker_id: str) -> None:
        """ワーカーキャンセルハンドラ - エラー扱いせずプログレスを終了"""
        self._on_worker_canceled_event(
            WorkerTerminalEvent(
                worker_id=worker_id,
                worker_type=self._resolve_worker_type(worker_id),
                outcome=WorkerOutcome.CANCELED,
                cancel_reason=CancelReason.USER_REQUESTED,
            )
        )

    def _on_worker_terminal(self, event: WorkerTerminalEvent) -> None:
        """Unified worker terminal event dispatcher."""
        self.worker_terminal.emit(event)
        self._emit_operation_terminal(event)

        if event.outcome is WorkerOutcome.SUCCEEDED:
            self._on_worker_finished(event.worker_id, event.result)
        elif event.outcome is WorkerOutcome.FAILED:
            if self._is_replacement_terminal(event):
                self._clear_current_worker_id(event.worker_id)
                self._release_gpu_slot_if_active(event)
                return
            self._on_worker_error(event.worker_id, event.error or "")
        elif event.outcome is WorkerOutcome.CANCELED:
            self._on_worker_canceled_event(event)
        else:
            self._on_worker_abnormal_terminal(event)

        # Issue #754: install ジョブの非成功終端で連結アノテーションを先に取り消す
        # (slot 解放より前に行い、取り消し対象が自動起動しないようにする)
        self._handle_install_chain_terminal(event)
        # ADR 0066 §6: アクティブな GPU ジョブの終端で次の待機ジョブを自動起動
        self._release_gpu_slot_if_active(event)

    def _on_worker_canceled_event(self, event: WorkerTerminalEvent) -> None:
        """ワーカーキャンセルハンドラ - エラー扱いせずプログレスを終了"""
        worker_id = event.worker_id
        logger.info(
            f"ワーカーキャンセル完了: {worker_id}"
            f" (reason={event.cancel_reason.value if event.cancel_reason else 'unknown'})"
        )

        worker_type = self._resolve_worker_type(worker_id)
        canceled_dispatch: dict[str, tuple[Any, str | None]] = {
            "batch_reg": (self.batch_registration_canceled, "current_registration_worker_id"),
            "batch_import": (self.batch_import_canceled, "current_batch_import_worker_id"),
            "annotation": (self.enhanced_annotation_canceled, "current_annotation_worker_id"),
            "model_install": (self.model_install_canceled, None),
            "search": (self.search_canceled, "current_search_worker_id"),
            "thumbnail": (self.thumbnail_canceled, "current_thumbnail_worker_id"),
        }
        if worker_type in canceled_dispatch:
            signal, attr = canceled_dispatch[worker_type]
            if self._should_emit_compat_canceled(event):
                signal.emit(worker_id)
            if attr and getattr(self, attr) == worker_id:
                setattr(self, attr, None)

    def _on_worker_abnormal_terminal(self, event: WorkerTerminalEvent) -> None:
        """Handle timeout/terminate outcomes as abnormal terminals, not normal cancellation."""
        message = event.error or f"ワーカー異常終了: {event.outcome.value}"
        logger.warning(
            f"ワーカー異常終了: {event.worker_id}, outcome={event.outcome.value}, "
            f"reason={event.cancel_reason.value if event.cancel_reason else 'unknown'}, message={message}"
        )
        if self._is_replacement_terminal(event):
            self._clear_current_worker_id(event.worker_id)
            return

        self._on_worker_error(event.worker_id, message)

    def _should_emit_compat_canceled(self, event: WorkerTerminalEvent) -> bool:
        """Suppress normal UI cancellation signals for replacement-only cancellation."""
        return event.cancel_reason not in {
            CancelReason.SEARCH_REPLACED,
            CancelReason.THUMBNAIL_REPLACED,
            CancelReason.PREFETCH_REPLACED,
        }

    def _is_replacement_terminal(self, event: WorkerTerminalEvent) -> bool:
        return event.cancel_reason in {
            CancelReason.SEARCH_REPLACED,
            CancelReason.THUMBNAIL_REPLACED,
            CancelReason.PREFETCH_REPLACED,
        }

    def _clear_current_worker_id(self, worker_id: str) -> None:
        worker_type = self._resolve_worker_type(worker_id)
        attr_by_type = {
            "batch_reg": "current_registration_worker_id",
            "batch_import": "current_batch_import_worker_id",
            "annotation": "current_annotation_worker_id",
            "search": "current_search_worker_id",
            "thumbnail": "current_thumbnail_worker_id",
        }
        attr = attr_by_type.get(worker_type)
        if attr and getattr(self, attr) == worker_id:
            setattr(self, attr, None)

    def _register_operation(
        self,
        worker_id: str,
        operation_type: OperationType,
        *,
        request_id: str | None = None,
        generation: int | None = None,
    ) -> OperationContext:
        self._operation_sequence += 1
        context = OperationContext(
            operation_id=f"{operation_type.value}_{self._operation_sequence}",
            operation_type=operation_type,
            worker_id=worker_id,
            request_id=request_id,
            generation=generation,
        )
        self._worker_operations[worker_id] = context
        return context

    def _emit_operation_started(self, worker_id: str) -> None:
        context = self._operation_context_for_worker(worker_id)
        self._record_job_ledger_started(context)
        self.operation_event.emit(
            WorkerOperationEvent(
                operation_id=context.operation_id,
                operation_type=context.operation_type,
                worker_id=worker_id,
                outcome=OperationOutcome.STARTED,
                is_current=self._is_current_operation(context),
                request_id=context.request_id,
                generation=context.generation,
            )
        )

    def _emit_operation_terminal(self, event: WorkerTerminalEvent) -> None:
        context = self._operation_context_for_worker(event.worker_id)
        outcome = self._operation_outcome_for_terminal(event)
        self._record_job_ledger_terminal(context, outcome, event)
        is_current = (
            False if outcome is OperationOutcome.SUPERSEDED else self._is_current_operation(context)
        )
        self.operation_event.emit(
            WorkerOperationEvent(
                operation_id=context.operation_id,
                operation_type=context.operation_type,
                worker_id=event.worker_id,
                outcome=outcome,
                is_current=is_current,
                request_id=context.request_id,
                generation=context.generation,
                result=event.result,
                error=event.error,
                cancel_reason=event.cancel_reason,
                worker_terminal=event,
            )
        )
        self._worker_operations.pop(event.worker_id, None)

    def _record_job_ledger_started(self, context: OperationContext) -> None:
        """Pipeline/Operation レベルのジョブを台帳に記録する (ADR 0066 §3)。"""
        title = _JOB_LEDGER_TITLES.get(context.operation_type)
        if title is None:
            return
        entry = self.job_ledger.register(context.worker_id, context.operation_type.value, title)
        if entry.status is JobStatus.QUEUED:
            # ADR 0066 §6: GPU 直列キューからの起動 (queued -> running)
            self.job_ledger.update(context.worker_id, status=JobStatus.RUNNING)
        self.job_ledger_changed.emit()

    # === GPU 直列キュー (ADR 0066 §6) ===

    def _enqueue_gpu_job(
        self,
        worker_id: str,
        worker: LoRAIroWorkerBase[Any],  # Any使用: ジョブ種別ごとに Worker の結果型が異なる
        operation_type: OperationType,
    ) -> None:
        """GPU 直列キューにジョブを queued で投入し台帳に載せる (ADR 0066 §6)。

        Args:
            worker_id: 待機させるワーカーID。
            worker: 構築済みの Worker (起動は前ジョブ終端まで保留)。
            operation_type: 台帳表示に使う operation 種別。
        """
        self._gpu_queue.append(_QueuedGpuJob(worker_id=worker_id, worker=worker))
        self.job_ledger.register(
            worker_id,
            operation_type.value,
            _JOB_LEDGER_TITLES[operation_type],
            status=JobStatus.QUEUED,
        )
        self.job_ledger_changed.emit()

    def _enqueue_gpu_annotation(
        self,
        worker_id: str,
        worker: AnnotationWorker,
        image_count: int,
        model_count: int,
    ) -> None:
        """先行 GPU ジョブの実行中に投入されたアノテーションを queued で待機させる。

        Args:
            worker_id: 待機させるワーカーID。
            worker: 構築済みの AnnotationWorker (起動は前ジョブ終端まで保留)。
            image_count: 対象画像数 (ログ用)。
            model_count: 選択モデル数 (ログ用)。
        """
        self._enqueue_gpu_job(worker_id, worker, OperationType.ANNOTATION)
        logger.info(
            f"GPU直列キューで待機: {image_count}画像, {model_count}モデル (ID: {worker_id}, "
            f"実行中: {self._gpu_active_worker_id}, 待機数: {len(self._gpu_queue)})"
        )

    def _release_gpu_slot_if_active(self, event: WorkerTerminalEvent) -> None:
        """アクティブな GPU ジョブの終端で slot を解放し、次の待機ジョブを起動する。

        UNRESPONSIVE は worker が停止確認できていない状態のため slot を保持する
        (VRAM が解放された保証がない以上、次ジョブを起動すると競合し得る)。
        """
        if event.worker_id != self._gpu_active_worker_id:
            return
        if event.outcome is WorkerOutcome.UNRESPONSIVE:
            logger.warning(
                f"GPUジョブが応答不能のため直列キューを保留: {event.worker_id} "
                f"(待機数: {len(self._gpu_queue)})"
            )
            return
        self._gpu_active_worker_id = None
        self._start_next_queued_gpu_job()

    def _start_next_queued_gpu_job(self) -> None:
        """GPU 直列キューの先頭ジョブを起動する。起動失敗時は次の待機ジョブを試す。"""
        while self._gpu_queue:
            queued_job = self._gpu_queue.pop(0)
            worker_type = self._resolve_worker_type(queued_job.worker_id)
            self._gpu_active_worker_id = queued_job.worker_id
            if self.worker_manager.start_worker(queued_job.worker_id, queued_job.worker):
                if worker_type == "annotation":
                    self.current_annotation_worker_id = queued_job.worker_id
                logger.info(
                    f"GPU直列キューからジョブ起動: {queued_job.worker_id} "
                    f"(残り待機数: {len(self._gpu_queue)})"
                )
                return
            # 起動失敗: 台帳と operation を失敗で確定し、次の待機ジョブへ進む
            logger.error(f"GPU直列キューのジョブ起動失敗: {queued_job.worker_id}")
            if self._gpu_active_worker_id == queued_job.worker_id:
                self._gpu_active_worker_id = None
            self._worker_operations.pop(queued_job.worker_id, None)
            if (
                self.job_ledger.finish(queued_job.worker_id, JobStatus.FAILED, "ワーカー開始失敗")
                is not None
            ):
                self.job_ledger_changed.emit()
            if worker_type == "model_install":
                # Issue #754: install を起動できなかった場合は連結アノテーションも取り消す
                self._cancel_chained_annotation(queued_job.worker_id)
                self.model_install_error.emit(f"モデルインストールワーカー開始失敗: {queued_job.worker_id}")
            else:
                self.enhanced_annotation_error.emit(
                    f"アノテーションワーカー開始失敗: {queued_job.worker_id}"
                )

    def _cancel_queued_gpu_job(
        self,
        worker_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
    ) -> bool:
        """queued (起動前) の GPU ジョブを即時 canceled として終端する (ADR 0066 §6)。

        Args:
            worker_id: 取り消す待機中ジョブのワーカーID。
            reason: キャンセル理由。

        Returns:
            キューから取り消せた場合 True。待機中でなければ False。
        """
        for index, queued_job in enumerate(self._gpu_queue):
            if queued_job.worker_id != worker_id:
                continue
            self._gpu_queue.pop(index)
            queued_job.worker.deleteLater()
            logger.info(f"GPU直列キューの待機ジョブを取り消し: {worker_id} (理由: {reason.value})")
            # 起動前のため manager を介さず synthetic terminal で終端を確定する
            self._on_worker_terminal(
                WorkerTerminalEvent(
                    worker_id=worker_id,
                    worker_type=self._resolve_worker_type(worker_id),
                    outcome=WorkerOutcome.CANCELED,
                    cancel_reason=reason,
                )
            )
            return True
        return False

    def _record_job_ledger_terminal(
        self,
        context: OperationContext,
        outcome: OperationOutcome,
        event: WorkerTerminalEvent,
    ) -> None:
        """ジョブの終端結果を台帳に確定する (ADR 0066 §3)。"""
        if context.operation_type not in _JOB_LEDGER_TITLES:
            return
        status, summary = self._ledger_status_for_outcome(outcome, event)
        if self.job_ledger.finish(event.worker_id, status, summary) is not None:
            self.job_ledger_changed.emit()

    @staticmethod
    def _ledger_status_for_outcome(
        outcome: OperationOutcome,
        event: WorkerTerminalEvent,
    ) -> tuple[JobStatus, str]:
        """Operation outcome を台帳の終端状態とサマリーへ変換する。"""
        if outcome is OperationOutcome.SUCCEEDED:
            return JobStatus.FINISHED, ""
        if outcome in {OperationOutcome.CANCELED, OperationOutcome.SUPERSEDED}:
            reason = event.cancel_reason.value if event.cancel_reason else "unknown"
            return JobStatus.CANCELED, f"キャンセル ({reason})"
        return JobStatus.FAILED, event.error or f"異常終了: {outcome.value}"

    def _operation_context_for_worker(self, worker_id: str) -> OperationContext:
        context = self._worker_operations.get(worker_id)
        if context is not None:
            return context
        operation_type = self._operation_type_from_worker_type(self._resolve_worker_type(worker_id))
        return OperationContext(
            operation_id=worker_id,
            operation_type=operation_type,
            worker_id=worker_id,
        )

    def _operation_outcome_for_terminal(self, event: WorkerTerminalEvent) -> OperationOutcome:
        if self._is_replacement_terminal(event):
            return OperationOutcome.SUPERSEDED
        if event.outcome is WorkerOutcome.SUCCEEDED:
            return OperationOutcome.SUCCEEDED
        if event.outcome is WorkerOutcome.CANCELED:
            return OperationOutcome.CANCELED
        if event.outcome is WorkerOutcome.UNRESPONSIVE:
            return OperationOutcome.UNRESPONSIVE
        if event.outcome in {WorkerOutcome.CANCEL_TIMEOUT, WorkerOutcome.TERMINATED}:
            return OperationOutcome.TERMINATED
        return OperationOutcome.FAILED

    def _is_current_operation(self, context: OperationContext) -> bool:
        current_attr_by_type = {
            OperationType.BATCH_REGISTRATION: "current_registration_worker_id",
            OperationType.BATCH_IMPORT: "current_batch_import_worker_id",
            OperationType.ANNOTATION: "current_annotation_worker_id",
            OperationType.SEARCH: "current_search_worker_id",
            OperationType.THUMBNAIL: "current_thumbnail_worker_id",
        }
        attr = current_attr_by_type.get(context.operation_type)
        if attr is None or getattr(self, attr) != context.worker_id:
            return False
        if context.operation_type is OperationType.SEARCH and context.generation != self._search_generation:
            return False
        if (
            context.operation_type is OperationType.THUMBNAIL
            and context.generation != self._thumbnail_generation
        ):
            return False
        return True

    def _operation_type_from_worker_type(self, worker_type: str) -> OperationType:
        return {
            "batch_reg": OperationType.BATCH_REGISTRATION,
            "batch_import": OperationType.BATCH_IMPORT,
            "annotation": OperationType.ANNOTATION,
            "model_install": OperationType.MODEL_INSTALL,
            "search": OperationType.SEARCH,
            "thumbnail": OperationType.THUMBNAIL,
        }.get(worker_type, OperationType.UNKNOWN)

    def _cancel_worker(self, worker_id: str, reason: CancelReason) -> bool:
        if reason is CancelReason.USER_REQUESTED:
            return self.worker_manager.cancel_worker(worker_id)
        return self.worker_manager.cancel_worker(worker_id, reason=reason)
