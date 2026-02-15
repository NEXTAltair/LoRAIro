"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationLogicに委譲
"""

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from image_annotator_lib import PHashAnnotationResults

from lorairo.annotations.annotation_logic import AnnotationLogic
from lorairo.utils.log import logger

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.database.schema import AnnotationsDict


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
        super().__init__()

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
        merged_results: PHashAnnotationResults = {}
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

            db_save_success, db_save_skip, image_summaries = self._save_results_to_database(
                merged_results
            )

            # モデル統計とpHash→ファイル名マッピングを構築
            model_statistics = self._build_model_statistics(merged_results)
            phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(
                set(merged_results.keys())
            )
            phash_to_filename = self._build_phash_to_filename_map(phash_to_image_id)

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
            raise

    def _save_results_to_database(
        self, results: PHashAnnotationResults
    ) -> tuple[int, int, list[ImageResultSummary]]:
        """アノテーション結果をDBに保存

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Returns:
            (DB保存成功件数, スキップ件数, 画像ごとの結果概要リスト) のタプル。

        Note:
            ライブラリが返したpHashをfind_image_ids_by_phashesで一括DB照会。
            タグIDもbatch_resolve_tag_ids()で一括解決しN+1を回避。
            保存失敗時は個別にログを記録し、処理を継続する。
        """
        # 事前一括取得: pHash → image_id（N+1回避）
        phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(set(results.keys()))

        # pHash → ファイル名マッピング構築（結果概要用）
        phash_to_filename = self._build_phash_to_filename_map(phash_to_image_id)

        # 事前一括取得: モデル名・タグ文字列を収集
        all_model_names, all_raw_tags = self._collect_model_names_and_tags(results)
        models_cache = self.db_manager.repository.get_models_by_names(all_model_names)

        # 事前一括取得: タグID一括解決（N+1回避）
        tag_id_cache = self._resolve_tag_ids_batch(all_raw_tags)

        success_count = 0
        skip_count = 0
        image_summaries: list[ImageResultSummary] = []

        for phash, annotations in results.items():
            try:
                image_id = phash_to_image_id.get(phash)
                if image_id is None:
                    logger.warning(
                        f"pHash {phash[:8]}... に対応する画像がDBに見つかりません。スキップします。"
                    )
                    skip_count += 1
                    continue

                # 変換（キャッシュ済みモデルを使用）
                annotations_dict = self._convert_to_annotations_dict(annotations, models_cache)

                if not annotations_dict or not any(annotations_dict.values()):
                    logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
                    skip_count += 1
                    continue

                # DB保存（annotation_worker経路: 存在チェックスキップ + タグIDキャッシュ使用）
                self.db_manager.repository.save_annotations(
                    image_id,
                    annotations_dict,
                    skip_existence_check=True,
                    tag_id_cache=tag_id_cache if tag_id_cache else None,
                )
                success_count += 1

                # 画像ごとの結果概要を収集
                image_summaries.append(
                    self._build_image_summary(phash, phash_to_filename, annotations_dict)
                )

                logger.debug(f"画像ID {image_id} のアノテーション保存成功")

            except Exception as e:
                logger.error(f"保存失敗 phash={phash[:8]}...: {e}", exc_info=True)

        logger.info(f"DB保存完了: {success_count}/{len(results)}件成功")
        return success_count, skip_count, image_summaries

    def _build_phash_to_filename_map(self, phash_to_image_id: dict[str, int | None]) -> dict[str, str]:
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
        annotations_dict: "AnnotationsDict",
    ) -> ImageResultSummary:
        """AnnotationsDictから画像結果概要を構築する。

        Args:
            phash: 画像のpHash。
            phash_to_filename: pHash → ファイル名のマッピング。
            annotations_dict: DB保存用アノテーション辞書。

        Returns:
            画像ごとの結果概要。
        """
        file_name = phash_to_filename.get(phash, phash[:12] + "...")
        tag_count = len(annotations_dict.get("tags", []))
        has_caption = len(annotations_dict.get("captions", [])) > 0
        scores = annotations_dict.get("scores", [])
        score = scores[0]["score"] if scores else None
        return ImageResultSummary(
            file_name=file_name,
            tag_count=tag_count,
            has_caption=has_caption,
            score=score,
        )

    @staticmethod
    def _collect_model_names_and_tags(
        results: PHashAnnotationResults,
    ) -> tuple[set[str], set[str]]:
        """全結果からユニークなモデル名とタグ文字列を収集する。

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Returns:
            (モデル名セット, タグ文字列セット) のタプル。
        """
        all_model_names: set[str] = set()
        all_raw_tags: set[str] = set()
        for annotations in results.values():
            for model_name, unified_result in annotations.items():
                error = (
                    unified_result.get("error")
                    if isinstance(unified_result, dict)
                    else unified_result.error
                )
                if error:
                    continue
                all_model_names.add(model_name)
                # タグ文字列を収集（バッチ解決用）
                tags = (
                    unified_result.get("tags") if isinstance(unified_result, dict) else unified_result.tags
                )
                if tags:
                    all_raw_tags.update(tags)
        return all_model_names, all_raw_tags

    def _resolve_tag_ids_batch(self, all_raw_tags: set[str]) -> dict[str, int | None]:
        """タグ文字列を正規化し、外部タグDBのtag_idを一括解決する。

        TagCleaner.clean_format() + strip で正規化後、
        batch_resolve_tag_ids()で一括検索する。

        Args:
            all_raw_tags: 生のタグ文字列セット。

        Returns:
            正規化済みタグ文字列→tag_idのキャッシュ辞書。タグがない場合は空辞書。
        """
        if not all_raw_tags:
            return {}

        normalized_tags: set[str] = set()
        for raw_tag in all_raw_tags:
            normalized = TagCleaner.clean_format(raw_tag).strip()
            if normalized:
                normalized_tags.add(normalized)

        if not normalized_tags:
            return {}

        return self.db_manager.repository.batch_resolve_tag_ids(normalized_tags)

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

    # FIXME: Issue #6参照 - ライブラリ側でUnifiedAnnotationResult統一後に削除可能
    @staticmethod
    def _extract_scores_from_formatted_output(formatted_output: Any) -> dict[str, float] | None:
        """formatted_outputからスコア辞書を抽出する。

        Pipeline/CLIPモデルはUnifiedAnnotationResultの`scores`フィールドではなく
        `formatted_output`にスコアデータを格納する旧形式のため、ここで変換する。

        Args:
            formatted_output: AnnotationResult dictのformatted_outputフィールド値。
                UnifiedAnnotationResult, dict, float/int, またはNone。

        Returns:
            スコア辞書(name->value)。抽出できない場合はNone。
        """
        if formatted_output is None:
            return None

        # CLIP系: formatted_outputがUnifiedAnnotationResult → .scoresをそのまま使用
        if hasattr(formatted_output, "scores") and isinstance(
            getattr(formatted_output, "scores", None), dict
        ):
            return formatted_output.scores

        # Pipeline系(AestheticShadow): dict with "hq" key → aesthetic score
        if isinstance(formatted_output, dict) and "hq" in formatted_output:
            hq_value = formatted_output.get("hq")
            if isinstance(hq_value, (int, float)):
                return {"aesthetic": float(hq_value)}

        # Pipeline系(CafePredictor等): 単一float/int → aesthetic score
        if isinstance(formatted_output, (int, float)):
            return {"aesthetic": float(formatted_output)}

        return None

    def _append_scores(
        self, scores: dict[str, Any] | None, model_id: int, result: "AnnotationsDict"
    ) -> None:
        """スコア結果をAnnotationsDictに追加する。

        Args:
            scores: スコア辞書(name->value)。
            model_id: モデルID。
            result: 追加先のAnnotationsDict。
        """
        if not scores:
            return
        for _score_name, score_value in scores.items():
            result["scores"].append(
                {"model_id": model_id, "score": float(score_value), "is_edited_manually": False}
            )

    def _append_tags(self, tags: list[str] | None, model_id: int, result: "AnnotationsDict") -> None:
        """タグ結果をAnnotationsDictに追加する。

        Args:
            tags: タグ文字列リスト。
            model_id: モデルID。
            result: 追加先のAnnotationsDict。
        """
        if not tags:
            return
        for tag_content in tags:
            result["tags"].append(
                {
                    "model_id": model_id,
                    "tag": tag_content,
                    "existing": False,
                    "is_edited_manually": False,
                    "confidence_score": None,
                    "tag_id": None,
                }
            )

    def _append_captions(
        self, captions: list[str] | None, model_id: int, result: "AnnotationsDict"
    ) -> None:
        """キャプション結果をAnnotationsDictに追加する。

        Args:
            captions: キャプション文字列リスト。
            model_id: モデルID。
            result: 追加先のAnnotationsDict。
        """
        if not captions:
            return
        for caption_content in captions:
            result["captions"].append(
                {
                    "model_id": model_id,
                    "caption": caption_content,
                    "existing": False,
                    "is_edited_manually": False,
                }
            )

    def _append_ratings(self, ratings: Any, model_id: int, result: "AnnotationsDict") -> None:
        """レーティング結果をAnnotationsDictに追加する。

        Args:
            ratings: レーティング値。
            model_id: モデルID。
            result: 追加先のAnnotationsDict。
        """
        if not ratings:
            return
        rating_value = str(ratings)
        result["ratings"].append(
            {
                "model_id": model_id,
                "raw_rating_value": rating_value,
                "normalized_rating": rating_value,
                "confidence_score": None,
            }
        )

    def _convert_to_annotations_dict(
        self, annotations: dict[str, Any], models_cache: dict[str, Any]
    ) -> "AnnotationsDict":
        """PHashAnnotationResults -> AnnotationsDictへ変換

        Args:
            annotations: model_name -> UnifiedResult マッピング
            models_cache: model_name -> Model の事前取得キャッシュ

        Returns:
            AnnotationsDict: DB保存用の型付き辞書

        Note:
            - TypedDictは db_repository.py からimport
            - model_id解決はmodels_cacheから取得(N+1回避)
            - 正しいキー名: "tag", "caption", "raw_rating_value", "normalized_rating"
        """
        from lorairo.database.db_repository import AnnotationsDict

        result: AnnotationsDict = {
            "scores": [],
            "tags": [],
            "captions": [],
            "ratings": [],
        }

        for model_name, unified_result in annotations.items():
            if self._extract_field(unified_result, "error"):
                logger.warning(f"モデル {model_name} エラーをスキップ")
                continue

            model = models_cache.get(model_name)
            if not model:
                logger.warning(f"モデル '{model_name}' がDB未登録")
                continue

            # スコア抽出: scores フィールド優先、なければ formatted_output からフォールバック (Issue #6)
            scores = self._extract_field(unified_result, "scores")
            if scores is None:
                scores = self._extract_scores_from_formatted_output(
                    self._extract_field(unified_result, "formatted_output")
                )
            self._append_scores(scores, model.id, result)
            self._append_tags(self._extract_field(unified_result, "tags"), model.id, result)
            self._append_captions(self._extract_field(unified_result, "captions"), model.id, result)
            self._append_ratings(self._extract_field(unified_result, "ratings"), model.id, result)

        return result

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
        from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter

        # モデルメタデータを取得
        adapter = AnnotatorLibraryAdapter(self.annotation_logic.annotator_adapter.config_service)
        try:
            model_metadata_list = adapter.get_available_models_with_metadata()
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
