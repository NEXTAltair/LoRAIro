"""Enhanced Annotation Service - Phase 2統合版

既存AnnotationServiceの機能を拡張し、Phase 1コンポーネントと統合
- ServiceContainer経由でのDI対応
- ModelSyncServiceによる動的モデル管理
- BatchProcessorでの大規模処理対応
- 既存WorkerServiceとの互換性維持
"""

from typing import Any

from PIL.Image import Image
from PySide6.QtCore import QObject, Signal

from ..utils.log import logger
from .service_container import get_service_container


class EnhancedAnnotationService(QObject):
    """拡張アノテーションサービス

    Phase 2: ServiceContainer統合版
    既存AnnotationServiceの機能を包含しつつ、新機能を追加

    主要機能:
    - 動的モデル同期（ModelSyncService連携）
    - バッチアノテーション処理（BatchProcessor連携）
    - 外部APIキー統合管理（ConfigurationService連携）
    - 既存WorkerServiceとの完全互換性
    """

    # シグナル定義
    annotationFinished = Signal(object)  # アノテーション完了（結果オブジェクト）
    annotationError = Signal(str)  # アノテーションエラー
    availableAnnotatorsFetched = Signal(list)  # 利用可能モデル取得完了
    modelSyncCompleted = Signal(object)  # モデル同期完了（ModelSyncResult）
    batchProcessingStarted = Signal(int)  # バッチ処理開始（総画像数）
    batchProcessingProgress = Signal(int, int)  # バッチ処理進捗（処理済み数, 総数）
    batchProcessingFinished = Signal(object)  # バッチ処理完了（BatchAnnotationResult）

    def __init__(self, parent: QObject | None = None) -> None:
        """EnhancedAnnotationService初期化

        Args:
            parent: Qt親オブジェクト
        """
        super().__init__(parent)

        # ServiceContainer経由でサービス取得
        self.container = get_service_container()

        # 結果保持
        self._last_annotation_result: Any = None
        self._last_batch_result: Any = None

        logger.info("EnhancedAnnotationService初期化完了")

    def sync_available_models(self) -> None:
        """利用可能モデルの同期実行

        ModelSyncServiceを使用してimage-annotator-libから
        最新のモデル情報を取得・DB同期
        """
        logger.info("モデル同期処理を開始します")

        try:
            sync_result = self.container.model_sync_service.sync_available_models()

            if sync_result.success:
                logger.info(f"モデル同期完了: {sync_result.summary}")
                self.modelSyncCompleted.emit(sync_result)
            else:
                error_msg = f"モデル同期エラー: {', '.join(sync_result.errors)}"
                logger.error(error_msg)
                self.annotationError.emit(error_msg)

        except Exception as e:
            error_msg = f"モデル同期処理中に予期しないエラー: {e}"
            logger.error(error_msg, exc_info=True)
            self.annotationError.emit(error_msg)

    def get_available_models(self) -> list[dict[str, Any]]:
        """利用可能モデル一覧取得

        Returns:
            list[dict[str, Any]]: モデルメタデータリスト
        """
        try:
            models = self.container.annotator_lib_adapter.get_available_models_with_metadata()
            logger.debug(f"利用可能モデル取得: {len(models)}件")
            return models

        except Exception as e:
            logger.error(f"利用可能モデル取得エラー: {e}", exc_info=True)
            return []

    def fetch_available_annotators(self) -> None:
        """利用可能アノテーター取得（既存互換性メソッド）

        既存AnnotationServiceとの互換性のため、
        モデル名のみのリストをシグナルで通知
        """
        logger.info("利用可能アノテーター取得を開始します")

        try:
            models = self.get_available_models()
            model_names = [model["name"] for model in models]

            logger.info(f"利用可能アノテーター取得完了: {len(model_names)}件")
            self.availableAnnotatorsFetched.emit(model_names)

        except Exception as e:
            error_msg = f"利用可能アノテーター取得エラー: {e}"
            logger.error(error_msg, exc_info=True)
            self.annotationError.emit(error_msg)
            self.availableAnnotatorsFetched.emit([])

    def start_single_annotation(
        self, images: list[Image], phash_list: list[str], models: list[str]
    ) -> None:
        """単発アノテーション処理開始

        少数画像に対する即座アノテーション処理
        WorkerServiceとの統合は Phase 2-3で実装

        Args:
            images: アノテーション対象画像リスト
            phash_list: pHashリスト
            models: 使用モデル名リスト
        """
        logger.info(f"単発アノテーション開始: {len(images)}画像, {len(models)}モデル")

        # 入力検証
        if not self._validate_annotation_input(images, phash_list, models):
            return

        try:
            # アノテーション実行
            results = self.container.annotator_lib_adapter.call_annotate(
                images=images, models=models, phash_list=phash_list
            )

            # 結果保存・通知
            self._last_annotation_result = results
            logger.info(f"単発アノテーション完了: {len(results)}件の結果")
            self.annotationFinished.emit(results)

        except Exception as e:
            error_msg = f"単発アノテーション処理エラー: {e}"
            logger.error(error_msg, exc_info=True)
            self.annotationError.emit(error_msg)

    def start_batch_annotation(
        self, image_paths: list[str], models: list[str], batch_size: int = 100
    ) -> None:
        """バッチアノテーション処理開始

        大規模画像セットに対するバッチアノテーション処理
        BatchProcessor使用

        Args:
            image_paths: 画像パスリスト
            models: 使用モデル名リスト
            batch_size: バッチサイズ（デフォルト: 100）
        """
        logger.info(f"バッチアノテーション開始: {len(image_paths)}画像, {len(models)}モデル")

        # 入力検証
        if not image_paths:
            self.annotationError.emit("画像パスが指定されていません")
            return
        if not models:
            self.annotationError.emit("モデルが選択されていません")
            return

        try:
            # バッチ処理開始通知
            self.batchProcessingStarted.emit(len(image_paths))

            # パスをPathオブジェクトに変換
            from pathlib import Path

            path_objects = [Path(path) for path in image_paths]

            # バッチアノテーション実行
            batch_result = self.container.batch_processor.execute_batch_annotation(
                image_paths=path_objects, models=models, batch_size=batch_size
            )

            # 結果保存・通知
            self._last_batch_result = batch_result
            logger.info(f"バッチアノテーション完了: {batch_result.summary}")
            self.batchProcessingFinished.emit(batch_result)

        except Exception as e:
            error_msg = f"バッチアノテーション処理エラー: {e}"
            logger.error(error_msg, exc_info=True)
            self.annotationError.emit(error_msg)

    def get_library_models_summary(self) -> dict[str, Any]:
        """ライブラリモデルサマリー情報取得

        Returns:
            dict[str, Any]: ライブラリモデルサマリー
        """
        try:
            return self.container.model_sync_service.get_library_models_summary()
        except Exception as e:
            logger.error(f"ライブラリモデルサマリー取得エラー: {e}", exc_info=True)
            return {}

    def get_last_annotation_result(self) -> Any:
        """最後のアノテーション結果取得

        Returns:
            Any: 最後のアノテーション結果（None if no results）
        """
        return self._last_annotation_result

    def get_last_batch_result(self) -> Any:
        """最後のバッチ処理結果取得

        Returns:
            Any: 最後のバッチ処理結果（None if no results）
        """
        return self._last_batch_result

    def cancel_annotation(self) -> None:
        """アノテーション処理キャンセル

        Note: Phase 2-3でWorkerService統合時に実装予定
        """
        logger.info("アノテーション処理キャンセル要求（Phase 2-3で実装予定）")
        # TODO: Phase 2-3でWorker統合時に実装

    def _validate_annotation_input(
        self, images: list[Image], phash_list: list[str], models: list[str]
    ) -> bool:
        """アノテーション入力検証

        Args:
            images: 画像リスト
            phash_list: pHashリスト
            models: モデルリスト

        Returns:
            bool: 検証結果
        """
        if not images:
            self.annotationError.emit("入力画像がありません")
            return False

        if not models:
            self.annotationError.emit("モデルが選択されていません")
            return False

        if phash_list and len(images) != len(phash_list):
            self.annotationError.emit("画像とpHashの数が一致しません")
            return False

        return True

    def get_service_status(self) -> dict[str, Any]:
        """サービス状況取得

        Returns:
            dict[str, Any]: サービス状況情報
        """
        return {
            "service_name": "EnhancedAnnotationService",
            "phase": "Phase 2 (ServiceContainer Integration)",
            "container_summary": self.container.get_service_summary(),
            "last_results": {
                "has_annotation_result": self._last_annotation_result is not None,
                "has_batch_result": self._last_batch_result is not None,
            },
        }
