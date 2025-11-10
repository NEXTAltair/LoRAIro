"""Annotation Worker - Phase 2統合版

AnnotationServiceとWorkerManagerの統合
- ServiceContainer経由のDI対応
- 既存WorkerBaseとの完全互換性
- バッチ処理対応
- 進捗レポート統合
"""

from typing import TYPE_CHECKING, Any

from image_annotator_lib import PHashAnnotationResults
from PIL.Image import Image

from ...services.annotation_service import AnnotationService
from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...services.model_sync_service import ModelSyncResult


class AnnotationWorker(LoRAIroWorkerBase[PHashAnnotationResults]):
    """拡張アノテーションワーカー

    Phase 2: AnnotationService統合版
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
        api_keys: dict[str, str] | None = None,
    ):
        """AnnotationWorker初期化

        Args:
            images: アノテーション対象画像リスト（単発モード用）
            image_paths: 画像パスリスト（バッチモード用）
            phash_list: pHashリスト（単発モード用）
            models: 使用モデル名リスト
            batch_size: バッチサイズ（バッチモード用）
            operation_mode: 動作モード（"single" or "batch"）
            api_keys: APIキー辞書（プロバイダー名 → APIキー）
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
        self.api_keys = api_keys or {}

        # AnnotationService初期化
        self.annotation_service = AnnotationService()

        logger.info(
            f"AnnotationWorker初期化 - Mode: {operation_mode}, "
            f"Images: {len(self.images) if images else len(self.image_paths)}, "
            f"Models: {len(self.models)}"
        )

    def execute(self) -> PHashAnnotationResults:
        """アノテーション処理実行

        動作モードに応じて単発またはバッチ処理を実行

        Returns:
            PHashAnnotationResults: アノテーション結果
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

    def _execute_single_annotation(self) -> PHashAnnotationResults:
        """単発アノテーション処理実行（モデルループ + キャンセル対応）

        Returns:
            PHashAnnotationResults: アノテーション結果
        """
        from image_annotator_lib import annotate

        # 入力検証
        if not self.images:
            raise ValueError("単発モードで画像が指定されていません")
        if not self.models:
            raise ValueError("モデルが選択されていません")

        # 前処理進捗
        self._report_progress(10, "AIアノテーション処理を開始...", total_count=len(self.images))

        # キャンセルチェック
        self._check_cancellation()

        # 結果を統合するための辞書
        merged_results: PHashAnnotationResults = {}

        # モデル単位で処理（モデル間キャンセル対応）
        total_models = len(self.models)
        for model_idx, model_name in enumerate(self.models):
            # モデル間キャンセルチェック
            self._check_cancellation()

            # 進捗報告
            progress = 10 + int((model_idx / total_models) * 80)  # 10-90%
            self._report_progress(
                progress,
                f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                processed_count=model_idx,
                total_count=total_models,
            )

            # 単一モデルでアノテーション実行
            try:
                model_results = annotate(
                    images_list=self.images,
                    model_name_list=[model_name],
                    phash_list=self.phash_list,
                    api_keys=self.api_keys,
                )

                # 結果をマージ
                for phash, annotations in model_results.items():
                    if phash not in merged_results:
                        merged_results[phash] = {}
                    merged_results[phash].update(annotations)

                logger.debug(f"モデル {model_name} 完了: {len(model_results)}件の結果")

            except Exception as e:
                logger.error(f"モデル {model_name} でエラー: {e}", exc_info=True)
                # エラーでも次のモデルに進む（部分的成功を許容）

        # 完了進捗
        self._report_progress(
            100,
            "アノテーション処理が完了しました",
            processed_count=len(self.images),
            total_count=len(self.images),
        )

        logger.info(f"単発アノテーション完了: {len(merged_results)}件の結果")
        return merged_results

    def _execute_batch_annotation(self) -> PHashAnnotationResults:
        """バッチアノテーション処理実行（モデルループ + キャンセル対応）

        Returns:
            PHashAnnotationResults: バッチアノテーション結果
        """
        from image_annotator_lib import annotate
        from PIL import Image as PILImage

        # 入力検証
        if not self.image_paths:
            raise ValueError("バッチモードで画像パスが指定されていません")
        if not self.models:
            raise ValueError("モデルが選択されていません")

        # 前処理進捗
        self._report_progress(5, "バッチアノテーション処理を開始...", total_count=len(self.image_paths))

        # キャンセルチェック
        self._check_cancellation()

        # 画像読み込み
        self._report_progress(10, "画像を読み込み中...", total_count=len(self.image_paths))
        images = []
        for image_path in self.image_paths:
            try:
                img = PILImage.open(image_path)
                images.append(img)
            except Exception as e:
                logger.error(f"画像読み込みエラー: {image_path}, {e}")

        if not images:
            raise RuntimeError("読み込める画像がありませんでした")

        # 結果を統合するための辞書
        merged_results: PHashAnnotationResults = {}

        # モデル単位で処理（モデル間キャンセル対応）
        total_models = len(self.models)
        for model_idx, model_name in enumerate(self.models):
            # モデル間キャンセルチェック
            self._check_cancellation()

            # 進捗報告
            progress = 10 + int((model_idx / total_models) * 80)  # 10-90%
            self._report_progress(
                progress,
                f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                processed_count=model_idx,
                total_count=total_models,
            )

            # 単一モデルでアノテーション実行
            try:
                model_results = annotate(
                    images_list=images, model_name_list=[model_name], api_keys=self.api_keys
                )

                # 結果をマージ
                for phash, annotations in model_results.items():
                    if phash not in merged_results:
                        merged_results[phash] = {}
                    merged_results[phash].update(annotations)

                logger.debug(f"モデル {model_name} 完了: {len(model_results)}件の結果")

            except Exception as e:
                logger.error(f"モデル {model_name} でエラー: {e}", exc_info=True)
                # エラーでも次のモデルに進む（部分的成功を許容）

        # 完了進捗
        self._report_progress(
            100, "バッチアノテーション完了", processed_count=len(images), total_count=len(images)
        )

        logger.info(f"バッチアノテーション完了: {len(merged_results)}件の結果")
        return merged_results

    def get_worker_info(self) -> dict[str, Any]:
        """ワーカー情報取得

        Returns:
            dict[str, Any]: ワーカー情報
        """
        return {
            "worker_type": "AnnotationWorker",
            "operation_mode": self.operation_mode,
            "batch_size": self.batch_size,
            "image_count": len(self.images) if self.images else len(self.image_paths),
            "model_count": len(self.models),
            "models": self.models,
            "phase": "Phase 2 (ServiceContainer Integration)",
        }


class ModelSyncWorker(LoRAIroWorkerBase["ModelSyncResult"]):
    """モデル同期専用ワーカー

    ModelSyncServiceを使用したライブラリモデル同期を
    非同期で実行するワーカー
    """

    def __init__(self) -> None:
        """ModelSyncWorker初期化"""
        super().__init__()

        # AnnotationService経由でModelSyncService取得
        self.annotation_service = AnnotationService()

        logger.info("ModelSyncWorker初期化完了")

    def execute(self) -> "ModelSyncResult":
        """モデル同期処理実行

        Returns:
            ModelSyncResult: ModelSyncResult
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
            # AnnotationServiceの抽象APIを使用
            self.annotation_service.sync_available_models()

            # 結果確認（AnnotationServiceにはsync_available_modelsの結果を返すメソッドが必要）
            # 現在は仮の結果オブジェクトを作成
            from ...services.model_sync_service import ModelSyncResult

            sync_result = ModelSyncResult(
                total_library_models=0, new_models_registered=0, existing_models_updated=0, errors=[]
            )

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
