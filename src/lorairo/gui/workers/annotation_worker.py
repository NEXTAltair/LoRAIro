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
from lorairo.services.model_registry_protocol import (
    ModelInfo,
    ModelRegistryServiceProtocol,
    selection_includes_webapi_model,
)
from lorairo.utils.log import logger

from .base import CancellationError, LoRAIroWorkerBase

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
    rating: str | None = None


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
    - QObject + QThreadベースの非同期実行
    - 進捗レポート（Signal経由）
    - キャンセル対応
    - AnnotationLogic呼び出し
    """

    _OPERATION_TYPE = "annotation"
    _LEGACY_SENTINEL_PREFIX = "__legacy_"
    _LEGACY_SENTINEL_SUFFIX = "__"

    @staticmethod
    def _is_legacy_sentinel_model_id(model_name: str) -> bool:
        if not (
            model_name.startswith(AnnotationWorker._LEGACY_SENTINEL_PREFIX)
            and model_name.endswith(AnnotationWorker._LEGACY_SENTINEL_SUFFIX)
        ):
            return False
        body = model_name[
            len(AnnotationWorker._LEGACY_SENTINEL_PREFIX) : -len(AnnotationWorker._LEGACY_SENTINEL_SUFFIX)
        ]
        return body.isdecimal()

    def __init__(
        self,
        annotation_logic: AnnotationLogic,
        image_paths: list[str],
        litellm_model_ids: list[str],
        db_manager: "ImageDatabaseManager",
        model_registry: ModelRegistryServiceProtocol,
    ):
        """AnnotationWorker初期化

        Issue #245 / ADR 0023 Phase 1.11: 使用モデルは `Model.litellm_model_id`
        (registry key SSoT) で受け取る。同 `Model.name` 異 `provider` 行の混在
        (migration 経由 OpenRouter vs 新規 sync 直接版) に対しても確実に
        registry lookup hit するように設計されている。

        Args:
            annotation_logic: アノテーション業務ロジック
            image_paths: 画像パスリスト
            litellm_model_ids: 使用モデルの `litellm_model_id` リスト
            db_manager: データベースマネージャ（必須: DB保存・エラー記録用）
            model_registry: モデルレジストリ (provider/capabilities 取得用、Issue #225)
        """
        super().__init__(db_manager=db_manager)

        self.annotation_logic = annotation_logic
        self.image_paths = image_paths
        self.litellm_model_ids = [
            model_id for model_id in litellm_model_ids if not self._is_legacy_sentinel_model_id(model_id)
        ]
        dropped = len(litellm_model_ids) - len(self.litellm_model_ids)
        if dropped:
            logger.info(f"AnnotationWorker初期化: legacy sentinel を除外しました: {dropped}件")
        self.db_manager = db_manager
        self.model_registry = model_registry

        logger.info(
            f"AnnotationWorker初期化 - Images: {len(self.image_paths)}, "
            f"Models: {len(self.litellm_model_ids)}"
        )
        logger.debug(f"  選択モデル (litellm_model_ids): {self.litellm_model_ids}")
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
        total_models = len(self.litellm_model_ids)

        logger.debug(f"モデル順次実行開始: {total_models}モデル = {self.litellm_model_ids}")

        for model_idx, litellm_model_id in enumerate(self.litellm_model_ids):
            self._check_cancellation()

            progress = 10 + int((model_idx / total_models) * 70)
            self._report_progress(
                progress,
                f"AIモデル実行中: {litellm_model_id} ({model_idx + 1}/{total_models})",
                processed_count=model_idx,
                total_count=total_models,
            )

            try:
                logger.debug(
                    f"モデル実行開始: {litellm_model_id} ({model_idx + 1}/{total_models}), "
                    f"対象画像数={len(self.image_paths)}"
                )

                model_results = self.annotation_logic.execute_annotation(
                    image_paths=self.image_paths,
                    litellm_model_ids=[litellm_model_id],
                    phash_list=None,
                )

                for phash, annotations in model_results.items():
                    if phash not in merged_results:
                        merged_results[phash] = {}
                    merged_results[phash].update(annotations)

                logger.debug(
                    f"モデル実行完了: {litellm_model_id}, 結果={len(model_results)}件, "
                    f"マージ後合計={len(merged_results)}件"
                )

            except CancellationError:
                logger.info(f"モデル {litellm_model_id} のアノテーション処理がキャンセルされました")
                raise

            except Exception as e:
                logger.error(f"モデル {litellm_model_id} でエラー: {e}", exc_info=True)
                self._save_error_records(e, self.image_paths, model_name=litellm_model_id)
                # エラー詳細を収集（全画像に対するモデルレベルエラー）
                # NOTE: ModelErrorDetail.model_name はサマリー表示用ラベルとして
                # litellm_model_id 値をそのまま入れる (登録 ID と一致するため
                # ユーザーが models list の結果と照合可能)。
                for image_path in self.image_paths:
                    model_errors.append(
                        ModelErrorDetail(
                            model_name=litellm_model_id,
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
        logger.info(
            f"アノテーション処理開始 - {len(self.image_paths)}画像, {len(self.litellm_model_ids)}モデル"
        )

        try:
            # Phase 0: refusal 送信前 filter (5%)
            # ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): refusal filter
            # は WebAPI モデル選択時のみ適用、Worker 内で async 実行 (GUI freeze
            # 回避)。バッチ resolve で N+1 クエリも解消。filter 後の件数を以後の
            # progress total_count として使う。
            self._report_progress(
                5,
                "refusal filter を適用中...",
                total_count=len(self.image_paths),
            )
            self._check_cancellation()
            self._apply_refusal_prefilter()

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
                models_used=list(self.litellm_model_ids),
                db_save_success=db_save_success,
                db_save_skip=db_save_skip,
                model_errors=model_errors,
                image_summaries=image_summaries,
                model_statistics=model_statistics,
                phash_to_filename=phash_to_filename,
                total_processing_time_sec=0.0,
            )

        except CancellationError:
            logger.info("アノテーション処理がキャンセルされました")
            raise

        except Exception as e:
            logger.error(f"アノテーション処理エラー: {e}", exc_info=True)
            self._save_error_records(e, self.image_paths, model_name=None)
            self._error_already_recorded = True
            raise

    def _apply_refusal_prefilter(self) -> None:
        """refusal を持つ画像を `self.image_paths` から除外する (Worker 内実行版)。

        ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): GUI スレッド上で
        N+1 クエリを発行しないよう、Worker 内で実行する設計に変更。filter は
        WebAPI モデル選択時のみ適用し、registry lookup 失敗時は filter skip して
        annotation を続行する (graceful degradation)。

        副作用: `self.image_paths` を filter 結果で in-place 置換する。
        """
        try:
            should_filter = selection_includes_webapi_model(self.litellm_model_ids, self.model_registry)
        except Exception as exc:
            logger.warning(
                f"Model registry lookup failed; refusal prefilter を skip して annotation 続行: {exc}",
                exc_info=True,
            )
            should_filter = False

        if not should_filter:
            logger.debug(
                "refusal filter スキップ (WebAPI 不在 or registry lookup 失敗): "
                f"litellm_model_ids={self.litellm_model_ids}"
            )
            return

        save_service = AnnotationSaveService(self.db_manager.repository)
        original_count = len(self.image_paths)
        try:
            self.image_paths = save_service.filter_refused_image_paths(self.image_paths)
        except Exception as exc:
            logger.warning(
                f"refusal filter 実行失敗; filter skip して annotation 続行: {exc}",
                exc_info=True,
            )
            return

        excluded = original_count - len(self.image_paths)
        if excluded > 0:
            logger.info(
                f"refusal filter 適用: {original_count}件 → {len(self.image_paths)}件 "
                f"(refusal 除外: {excluded}件)"
            )

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
        path_to_image_id = self.db_manager.repository.get_image_ids_by_filepaths(self.image_paths)
        image_id_to_path: dict[int, str] = {
            image_id: image_path
            for image_path, image_id in path_to_image_id.items()
            if image_id is not None
        }

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
        rating: str | None = None
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
            if rating is None:
                raw_ratings = (
                    unified_result.get("ratings")
                    if isinstance(unified_result, dict)
                    else getattr(unified_result, "ratings", None)
                )
                rating = AnnotationWorker._format_rating_summary(raw_ratings)
        return ImageResultSummary(
            file_name=file_name,
            tag_count=tag_count,
            has_caption=has_caption,
            score=score,
            rating=rating,
        )

    @staticmethod
    def _format_rating_summary(ratings: Any) -> str | None:
        """ratings から完了ダイアログ用の代表表示を作る。"""
        prediction = AnnotationWorker._select_rating_prediction(ratings)
        if prediction is None:
            return None
        if isinstance(prediction, str):
            return prediction

        raw_label = AnnotationWorker._extract_rating_attr(prediction, "raw_label")
        if not raw_label:
            return None

        source_scheme = AnnotationWorker._extract_rating_attr(prediction, "source_scheme")
        confidence = AnnotationWorker._extract_rating_attr(prediction, "confidence_score")
        if source_scheme and confidence is not None:
            return f"{raw_label} ({source_scheme}, {float(confidence):.2f})"
        if source_scheme:
            return f"{raw_label} ({source_scheme})"
        if confidence is not None:
            return f"{raw_label} ({float(confidence):.2f})"
        return str(raw_label)

    @staticmethod
    def _select_rating_prediction(ratings: Any) -> Any | None:
        """str / list / structured rating から代表表示対象を取り出す。

        structured rating は保存処理と同じく confidence 最大を代表にする。
        confidence 欠損は最下位扱いで、同値の場合は先頭を維持する。
        """
        if not ratings:
            return None
        if isinstance(ratings, str):
            return ratings
        candidates = ratings if isinstance(ratings, list) else [ratings]
        if candidates and all(isinstance(candidate, str) for candidate in candidates):
            return candidates[0]
        predictions = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict) or hasattr(candidate, "raw_label")
        ]
        if not predictions:
            return None
        return max(predictions, key=AnnotationWorker._rating_confidence_sort_key)

    @staticmethod
    def _rating_confidence_sort_key(prediction: Any) -> float:
        """confidence_score の sort key。None は最下位扱い。"""
        score = AnnotationWorker._extract_rating_attr(prediction, "confidence_score")
        return -1.0 if score is None else float(score)

    @staticmethod
    def _extract_rating_attr(prediction: Any, name: str) -> Any:
        """RatingPrediction / dict の両方から属性を読む。"""
        if isinstance(prediction, dict):
            return prediction.get(name)
        return getattr(prediction, name, None)

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
        ModelRegistry からprovider情報とcapabilitiesを取得する (Issue #225)。

        Issue #245 / ADR 0023 Phase 1.11: `results` のモデルキーは
        `AnnotatorInfo.name` (= `litellm_model_id` for WebAPI / bare 名 for ローカル ML)
        となるため、`info_map` のキーも `litellm_model_id` (fallback: `info.name`) に
        揃え、registry key SSoT に統一する。

        Args:
            results: PHashAnnotationResults (phash → litellm_model_id → UnifiedResult)

        Returns:
            litellm_model_id → ModelStatistics のマッピング。

        Note:
            - メタデータは ModelRegistryServiceProtocol.get_available_models() から取得
            - プロバイダーと capabilities は ModelInfo の属性
            - 取得失敗時は provider=None, capabilities=[] にフォールバック
        """
        try:
            model_info_list = self.model_registry.get_available_models()
            # registry key (= litellm_model_id with bare-name fallback) でマップ
            info_map: dict[str, ModelInfo] = {
                (info.litellm_model_id or info.name): info for info in model_info_list
            }
        except Exception as e:
            logger.warning(f"モデルメタデータ取得エラー: {e}")
            info_map = {}

        # モデル別統計を集計
        model_stats: dict[str, ModelStatistics] = {}

        for annotations in results.values():
            for model_name, unified_result in annotations.items():
                if self._is_legacy_sentinel_model_id(model_name):
                    continue
                if model_name not in model_stats:
                    info = info_map.get(model_name)
                    provider_name = info.provider if info else None
                    capabilities = list(info.capabilities) if info else []

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
