"""Enhanced Annotation Worker - Phase 2統合版

EnhancedAnnotationServiceとWorkerManagerの統合
- ServiceContainer経由のDI対応
- 既存WorkerBaseとの完全互換性
- バッチ処理対応
- 進捗レポート統合
"""

from pathlib import Path
from typing import Any

from PIL.Image import Image

from ...services.enhanced_annotation_service import EnhancedAnnotationService
from ...utils.log import logger
from .base import LoRAIroWorkerBase


class EnhancedAnnotationWorker(LoRAIroWorkerBase):
    """拡張アノテーションワーカー

    Phase 2: EnhancedAnnotationService統合版
    既存AnnotationWorkerの機能を包含し、新機能を追加

    主要機能:
    - ServiceContainer経由のサービス利用
    - 単発・バッチアノテーション対応
    - 進捗レポート統合
    - 既存WorkerBaseとの完全互換性
    """

    def __init__(
        self,
        images: list[Image] | None = None,
        image_paths: list[str] | None = None,
        phash_list: list[str] | None = None,
        models: list[str] | None = None,
        batch_size: int = 100,
        operation_mode: str = "single",  # "single" or "batch"
    ):
        """EnhancedAnnotationWorker初期化

        Args:
            images: アノテーション対象画像リスト（単発モード用）
            image_paths: 画像パスリスト（バッチモード用）
            phash_list: pHashリスト（単発モード用）
            models: 使用モデル名リスト
            batch_size: バッチサイズ（バッチモード用）
            operation_mode: 動作モード（"single" or "batch"）
        """
        super().__init__()

        # 動作モード設定
        self.operation_mode = operation_mode
        self.batch_size = batch_size

        # 単発モード用パラメータ
        self.images = images or []
        self.phash_list = phash_list or []

        # バッチモード用パラメータ
        self.image_paths = image_paths or []

        # 共通パラメータ
        self.models = models or []

        # EnhancedAnnotationService初期化
        self.annotation_service = EnhancedAnnotationService()

        logger.info(
            f"EnhancedAnnotationWorker初期化 - Mode: {operation_mode}, "
            f"Images: {len(self.images) if images else len(self.image_paths)}, "
            f"Models: {len(self.models)}"
        )

    def execute(self) -> Any:
        """アノテーション処理実行

        動作モードに応じて単発またはバッチ処理を実行

        Returns:
            Any: アノテーション結果
        """
        logger.info(f"Enhanced アノテーション開始 - Mode: {self.operation_mode}")

        try:
            if self.operation_mode == "single":
                return self._execute_single_annotation()
            elif self.operation_mode == "batch":
                return self._execute_batch_annotation()
            else:
                raise ValueError(f"不正な動作モード: {self.operation_mode}")

        except Exception as e:
            logger.error(f"Enhanced アノテーション処理エラー: {e}", exc_info=True)
            raise

    def _execute_single_annotation(self) -> Any:
        """単発アノテーション処理実行

        Returns:
            Any: アノテーション結果
        """
        # 入力検証
        if not self.images:
            raise ValueError("単発モードで画像が指定されていません")
        if not self.models:
            raise ValueError("モデルが選択されていません")

        # 前処理進捗
        self._report_progress(10, "Enhanced AIアノテーション処理を開始...", total_count=len(self.images))

        # キャンセルチェック
        self._check_cancellation()

        # メイン処理進捗
        self._report_progress(
            30,
            f"Enhanced AIモデル実行中: {', '.join(self.models)}",
            processed_count=0,
            total_count=len(self.images),
        )

        # EnhancedAnnotationService経由でアノテーション実行
        results = self.annotation_service.annotator_lib_adapter.call_annotate(
            images=self.images, models=self.models, phash_list=self.phash_list
        )

        # 完了進捗
        self._report_progress(
            100,
            "Enhanced アノテーション処理が完了しました",
            processed_count=len(self.images),
            total_count=len(self.images),
        )

        logger.info(f"Enhanced 単発アノテーション完了: {len(results)}件の結果")
        return results

    def _execute_batch_annotation(self) -> Any:
        """バッチアノテーション処理実行

        Returns:
            Any: バッチアノテーション結果
        """
        # 入力検証
        if not self.image_paths:
            raise ValueError("バッチモードで画像パスが指定されていません")
        if not self.models:
            raise ValueError("モデルが選択されていません")

        # 前処理進捗
        self._report_progress(
            5, "Enhanced バッチアノテーション処理を開始...", total_count=len(self.image_paths)
        )

        # キャンセルチェック
        self._check_cancellation()

        # バッチ処理準備進捗
        self._report_progress(
            10,
            f"Enhanced バッチ処理準備中: {len(self.image_paths)}画像, {len(self.models)}モデル",
            processed_count=0,
            total_count=len(self.image_paths),
        )

        # パスをPathオブジェクトに変換
        path_objects = [Path(path) for path in self.image_paths]

        # 中間進捗
        self._report_progress(
            20,
            "Enhanced バッチアノテーション実行中...",
            processed_count=0,
            total_count=len(self.image_paths),
        )

        # EnhancedAnnotationService経由でバッチアノテーション実行
        batch_result = self.annotation_service.batch_processor.execute_batch_annotation(
            image_paths=path_objects, models=self.models, batch_size=self.batch_size
        )

        # 完了進捗
        self._report_progress(
            100,
            f"Enhanced バッチアノテーション完了: {batch_result.summary}",
            processed_count=batch_result.processed_images,
            total_count=batch_result.total_images,
        )

        logger.info(f"Enhanced バッチアノテーション完了: {batch_result.summary}")
        return batch_result

    def get_worker_info(self) -> dict[str, Any]:
        """ワーカー情報取得

        Returns:
            dict[str, Any]: ワーカー情報
        """
        return {
            "worker_type": "EnhancedAnnotationWorker",
            "operation_mode": self.operation_mode,
            "batch_size": self.batch_size,
            "image_count": len(self.images) if self.images else len(self.image_paths),
            "model_count": len(self.models),
            "models": self.models,
            "phase": "Phase 2 (ServiceContainer Integration)",
        }


class ModelSyncWorker(LoRAIroWorkerBase):
    """モデル同期専用ワーカー

    ModelSyncServiceを使用したライブラリモデル同期を
    非同期で実行するワーカー
    """

    def __init__(self):
        """ModelSyncWorker初期化"""
        super().__init__()

        # EnhancedAnnotationService経由でModelSyncService取得
        self.annotation_service = EnhancedAnnotationService()

        logger.info("ModelSyncWorker初期化完了")

    def execute(self) -> Any:
        """モデル同期処理実行

        Returns:
            Any: ModelSyncResult
        """
        logger.info("モデル同期ワーカー開始")

        try:
            # 前処理進捗
            self._report_progress(10, "ライブラリモデル同期を開始...")

            # キャンセルチェック
            self._check_cancellation()

            # メイン処理進捗
            self._report_progress(50, "image-annotator-libからモデル情報を取得中...")

            # モデル同期実行
            sync_result = self.annotation_service.model_sync_service.sync_available_models()

            # 完了進捗
            self._report_progress(100, f"モデル同期完了: {sync_result.summary}")

            logger.info(f"モデル同期ワーカー完了: {sync_result.summary}")
            return sync_result

        except Exception as e:
            logger.error(f"モデル同期ワーカーエラー: {e}", exc_info=True)
            raise

    def get_worker_info(self) -> dict[str, Any]:
        """ワーカー情報取得

        Returns:
            dict[str, Any]: ワーカー情報
        """
        return {
            "worker_type": "ModelSyncWorker",
            "operation": "model_sync",
            "phase": "Phase 2 (ServiceContainer Integration)",
        }
