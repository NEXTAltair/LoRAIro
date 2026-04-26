"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationLogicに委譲
"""

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from image_annotator_lib import PHashAnnotationResults

from lorairo.annotations.annotation_logic import AnnotationLogic
from lorairo.services.annotation_save_service import AnnotationSaveService
from lorairo.utils.log import logger

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


@dataclass
class ModelErrorDetail:
    """モデルエラー詳細情報"""

    model_name: str
    image_path: str
    error_message: str


@dataclass
class ImageResultSummary:
    """画像ごとのアノテーション結果概要"""

    file_name: str
    tag_count: int = 0
    has_caption: bool = False
    score: float | None = None


@dataclass
class ModelStatistics:
    """モデル別統計情報"""

    model_name: str
    provider_name: str | None
    capabilities: list[str]
    success_count: int
    error_count: int
    total_tags: int = 0
    total_captions: int = 0
    avg_confidence: float | None = None
    processing_time_sec: float | None = None


@dataclass
class AnnotationExecutionResult:
    """アノテーション実行結果（サマリー付き）

    Workerの実行結果と処理統計を保持する。
    MainWindowでサマリーダイアログ表示に使用する。
    """

    results: PHashAnnotationResults
    total_images: int
    models_used: list[str]
    db_save_success: int = 0
    db_save_skip: int = 0
    model_errors: list[ModelErrorDetail] = field(default_factory=list)
    image_summaries: list[ImageResultSummary] = field(default_factory=list)
    model_statistics: dict[str, ModelStatistics] = field(default_factory=dict)
    phash_to_filename: dict[str, str] = field(default_factory=dict)
    total_processing_time_sec: float = 0.0


class AnnotationWorker(LoRAIroWorkerBase["AnnotationExecutionResult"]):
    """アノテーションワーカー

    GUI Layer: Qt非同期処理と進捗管理
    ビジネスロジックはAnnotationLogicに委譲

    主要機能:
    - Qt QRunnableベースの非同期実行
    - 進捗レポート（Signal経由）
    - キャンセル対応
    - AnnotationLogic呼び出し
    """

    _OPERATION_TYPE = "annotation"

    def __init__(
        self,
        annotation_logic: AnnotationLogic,
        image_paths: list[str],
        models: list[str],
        db_manager: "ImageDatabaseManager",
    ):
        """AnnotationWorker初期化

        Args:
            annotation_logic: アノテーション業務ロジック
            image_paths: 画像パスリスト
            models: 使用モデル名リスト
            db_manager: データベースマネージャ（必須: DB保存・エラー記録用）
        """
        super().__init__(db_manager=db_manager)

        self.annotation_logic = annotation_logic
        self.image_paths = image_paths
        self.models = models
        self.db_manager = db_manager

        logger.info(f"AnnotationWorker初期化 - Images: {len(self.image_paths)}, Models: {len(self.models)}")
        logger.debug(f"  選択モデル: {self.models}")
        logger.debug(f"  対象画像パス: {self.image_paths[:5]}{'...' if len(self.image_paths) > 5 else ''}")

    def _save_error_records(
        self, error: Exception, image_paths: list[str], model_name: str | None = None
    ) -> None:
        """エラーレコードを各画像パスに対して保存する。

        image_idが取得できない場合もNoneのまま保存する(file_pathでトレース可能)。
        二次エラーが発生した場合はログのみで継続する。

        Args:
            error: 発生した例外。
            image_paths: エラー対象の画像パスリスト。
            model_name: エラー発生モデル名(全体エラーの場合はNone)。
        """
        # 例外オブジェクトから直接トレースバックを取得(except外でも確実に動作)
        stack_trace = "".join(traceback.format_exception(error))

        for image_path in image_paths:
            try:
                image_id = self.db_manager.get_image_id_by_filepath(image_path)
                if image_id is None:
                    logger.warning(f"image_id取得失敗(file_pathで記録): {image_path}")
                self.db_manager.save_error_record(
                    operation_type="annotation",
                    error_type=type(error).__name__,
                    error_message=str(error),
                    image_id=image_id,
                    stack_trace=stack_trace,
                    file_path=image_path,
                    model_name=model_name,
                )
            except Exception as save_error:
                logger.error(f"エラーレコード保存失敗: {image_path}, {save_error}")

    def _run_annotation(self) -> tuple[PHashAnnotationResults, list[ModelErrorDetail]]:
        """モデル単位でアノテーションを実行し、結果をマージする。

        Returns:
            (マージされたアノテーション結果, モデルエラー詳細リスト) のタプル。
        """
        merged_results: PHashAnnotationResults = PHashAnnotationResults()
        model_errors: list[ModelErrorDetail] = []
        total_models = len(self.models)

        logger.debug(f"モデル順次実行開始: {total_models}モデル = {self.models}")

        for model_idx, model_name in enumerate(self.models):
            self._check_cancellation()

            progress = 10 + int((model_idx / total_models) * 70)
            self._report_progress(
                progress,
                f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                processed_count=model_idx,
                total_count=total_models,
            )

            try:
                logger.debug(
                    f"モデル実行開始: {model_name} ({model_idx + 1}/{total_models}), "
                    f"対象画像数={len(self.image_paths)}"
                )

                model_results = self.annotation_logic.execute_annotation(
                    image_paths=self.image_paths,
                    model_names=[model_name],
                    phash_list=None,
                )

                for phash, annotations in model_results.items():
                    if phash not in merged_results:
                        merged_results[phash] = {}
                    merged_results[phash].update(annotations)

                logger.debug(
                    f"モデル実行完了: {model_name}, 結果={len(model_results)}件, "
                    f"マージ後合計={len(merged_results)}件"
                )

            except Exception as e:
                logger.error(f"モデル {model_name} でエラー: {e}", exc_info=True)
                self._save_error_records(e, self.image_paths, model_name=model_name)
                # エラー詳細を収集（全画像に対するモデルレベルエラー）
                for image_path in self.image_paths:
                    model_errors.append(
                        ModelErrorDetail(
                            model_name=model_name,
                            image_path=Path(image_path).name,
                            error_message=str(e),
                        )
                    )
                # エラーでも次のモデルに進む(部分的成功を許容)

        logger.debug(f"モデル順次実行完了: 最終結果={len(merged_results)}件")
        return merged_results, model_errors

    def execute(self) -> AnnotationExecutionResult:
        """アノテーション処理実行

        AnnotationLogic経由でビジネスロジックを実行し、
        進捗管理とキャンセル処理を担当する。

        Returns:
            AnnotationExecutionResult: サマリー付きアノテーション結果

        Raises:
            Exception: アノテーション実行エラー
        """
        logger.info(f"アノテーション処理開始 - {len(self.image_paths)}画像, {len(self.models)}モデル")

        try:
            # Phase 1: アノテーション実行(10-80%)
            self._report_progress(10, "アノテーション処理を開始...", total_count=len(self.image_paths))
            self._check_cancellation()

            merged_results, model_errors = self._run_annotation()

            # Phase 2: DB保存(85%)
            self._report_progress(
                85,
                "結果をDBに保存中...",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
            self._check_cancellation()

            db_save_success, db_save_skip, image_summaries, phash_to_filename = (
                self._save_results_to_database(merged_results)
            )

            # モデル統計を構築
            model_statistics = self._build_model_statistics(merged_results)

            self._report_progress(
                100,
                "アノテーション処理が完了しました",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )

            logger.info(f"アノテーション処理完了: {len(merged_results)}件の結果")
            return AnnotationExecutionResult(
                results=merged_results,
                total_images=len(self.image_paths),
                models_used=list(self.models),
                db_save_success=db_save_success,
                db_save_skip=db_save_skip,
                model_errors=model_errors,
                image_summaries=image_summaries,
                model_statistics=model_statistics,
                phash_to_filename=phash_to_filename,
                total_processing_time_sec=0.0,
            )

        except Exception as e:
            logger.error(f"アノテーション処理エラー: {e}", exc_info=True)
            self._save_error_records(e, self.image_paths, model_name=None)
            self._error_already_recorded = True
            raise

    def _save_results_to_database(
        self, results: PHashAnnotationResults
    ) -> tuple[int, int, list[ImageResultSummary], dict[str, str]]:
        """アノテーション結果をDBに保存

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Returns:
            (DB保存成功件数, スキップ件数, 画像ごとの結果概要リスト, phash→ファイル名マップ) のタプル。
        """
        save_result = AnnotationSaveService(self.db_manager.repository).save_annotation_results(results)

        # GUIサマリー用: phash→ファイル名マップを構築
        phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(set(results.keys()))
        phash_to_filename = self._build_phash_to_filename_map(phash_to_image_id)

        # 画像ごとの結果概要（DB登録済みのもののみ）
        image_summaries: list[ImageResultSummary] = [
            self._build_image_summary(phash, phash_to_filename, annotations)
            for phash, annotations in results.items()
            if phash_to_image_id.get(phash) is not None
        ]

        logger.info(f"DB保存完了: {save_result.success_count}/{save_result.total_count}件成功")
        return save_result.success_count, save_result.skip_count, image_summaries, phash_to_filename

    def _build_phash_to_filename_map(self, phash_to_image_id: dict[str, int]) -> dict[str, str]:
        """pHashからファイル名へのマッピングを構築する。

        image_pathsリストとDB上のimage_idマッピングから、
        phash → ファイル名の逆引きマップを作る。

        Args:
            phash_to_image_id: pHash → image_id のマッピング。

        Returns:
            pHash → ファイル名のマッピング。
        """
        # image_id → file_path マッピングを構築
        image_id_to_path: dict[int, str] = {}
        for image_path in self.image_paths:
            image_id = self.db_manager.get_image_id_by_filepath(image_path)
            if image_id is not None:
                image_id_to_path[image_id] = image_path

        # phash → filename マッピング
        result: dict[str, str] = {}
        for phash, image_id in phash_to_image_id.items():
            if image_id is not None and image_id in image_id_to_path:
                result[phash] = Path(image_id_to_path[image_id]).name
            else:
                result[phash] = phash[:12] + "..."
        return result

    @staticmethod
    def _build_image_summary(
        phash: str,
        phash_to_filename: dict[str, str],
        raw_annotations: dict[str, Any],
    ) -> ImageResultSummary:
        """raw annotations から画像結果概要を構築する。

        Args:
            phash: 画像のpHash。
            phash_to_filename: pHash → ファイル名のマッピング。
            raw_annotations: model_name → UnifiedAnnotationResult のマッピング。

        Returns:
            画像ごとの結果概要。
        """
        file_name = phash_to_filename.get(phash, phash[:12] + "...")
        tag_count = 0
        has_caption = False
        score: float | None = None
        for unified_result in raw_annotations.values():
            error = (
                unified_result.get("error")
                if isinstance(unified_result, dict)
                else getattr(unified_result, "error", None)
            )
            if error:
                continue
            tags = (
                unified_result.get("tags")
                if isinstance(unified_result, dict)
                else getattr(unified_result, "tags", None)
            )
            if tags:
                tag_count += len(tags)
            captions = (
                unified_result.get("captions")
                if isinstance(unified_result, dict)
                else getattr(unified_result, "captions", None)
            )
            if captions:
                has_caption = True
            if score is None:
                raw_scores = (
                    unified_result.get("scores")
                    if isinstance(unified_result, dict)
                    else getattr(unified_result, "scores", None)
                )
                if isinstance(raw_scores, dict) and raw_scores:
                    score = float(next(iter(raw_scores.values())))
        return ImageResultSummary(
            file_name=file_name,
            tag_count=tag_count,
            has_caption=has_caption,
            score=score,
        )

    @staticmethod
    def _extract_field(result: Any, field_name: str) -> Any:
        """unified_resultから辞書/Pydanticモデル両対応でフィールドを取得する。

        Args:
            result: 辞書またはPydanticモデルオブジェクト。
            field_name: 取得するフィールド名。

        Returns:
            フィールドの値、またはNone。
        """
        if isinstance(result, dict):
            return result.get(field_name)
        return getattr(result, field_name, None)

    def _build_model_statistics(self, results: PHashAnnotationResults) -> dict[str, ModelStatistics]:
        """モデル別統計情報を構築する。

        resultsからモデル別の成功/エラー件数、タグ数、キャプション数を集計し、
        image-annotator-libのメタデータからprovider情報とcapabilitiesを取得する。

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Returns:
            モデル名 → ModelStatistics のマッピング。

        Note:
            - ライブラリのメタデータは AnnotatorLibraryAdapter.
              get_available_models_with_metadata() から取得
            - プロバイダー情報は メタデータの "provider" フィールド
            - capabilities は メタデータの "capabilities" フィールド
        """
        # モデルメタデータを取得（AnnotationLogic経由でアダプターに委譲）
        try:
            model_metadata_list = self.annotation_logic.get_available_models_with_metadata()
            # モデル名をキーとしたメタデータマップを構築
            metadata_map: dict[str, dict[str, Any]] = {}
            for metadata in model_metadata_list:
                model_name = metadata.get("model_name")
                if model_name:
                    metadata_map[model_name] = metadata
        except Exception as e:
            logger.warning(f"モデルメタデータ取得エラー: {e}")
            metadata_map = {}

        # モデル別統計を集計
        model_stats: dict[str, ModelStatistics] = {}

        for annotations in results.values():
            for model_name, unified_result in annotations.items():
                if model_name not in model_stats:
                    # メタデータから provider と capabilities を取得
                    metadata = metadata_map.get(model_name, {})
                    provider_name = metadata.get("provider")
                    capabilities = metadata.get("capabilities", [])

                    model_stats[model_name] = ModelStatistics(
                        model_name=model_name,
                        provider_name=provider_name,
                        capabilities=capabilities,
                        success_count=0,
                        error_count=0,
                        total_tags=0,
                        total_captions=0,
                        avg_confidence=None,
                        processing_time_sec=None,
                    )

                # エラーチェック
                error = self._extract_field(unified_result, "error")
                if error:
                    model_stats[model_name].error_count += 1
                    continue

                model_stats[model_name].success_count += 1

                # タグ数を集計
                tags = self._extract_field(unified_result, "tags")
                if tags:
                    model_stats[model_name].total_tags += len(tags)

                # キャプション数を集計
                captions = self._extract_field(unified_result, "captions")
                if captions:
                    model_stats[model_name].total_captions += len(captions)

        logger.debug(f"モデル統計構築完了: {len(model_stats)}モデル")
        return model_stats
