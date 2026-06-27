"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationRunnerに委譲
"""

import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from image_annotator_lib import PHashAnnotationResults
from PySide6.QtCore import Signal

from lorairo.annotation.annotation_runner import AnnotationRunner
from lorairo.services.annotation_save_service import AnnotationSaveService
from lorairo.services.job_ledger_service import (
    StageModelInput,
    StageProgress,
    build_stage_progress,
)
from lorairo.services.model_registry_protocol import (
    ModelInfo,
    ModelRegistryServiceProtocol,
    selection_includes_webapi_model,
)
from lorairo.services.moderation_preflight_service import (
    MODERATION_LITELLM_MODEL_ID,
    ModerationPreflightService,
    build_annotation_runner_runner,
)
from lorairo.utils.log import logger

from .base import CancellationError, LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.gui.widgets.run_settings_dialog import RunOptions


@dataclass
class ModelErrorDetail:
    """モデルエラー詳細情報"""

    model_name: str
    image_path: str
    error_message: str
    error_type: str = "model_error"


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


class _CancellationCheckingModelList(list[str]):
    """モデル iteration の各要素直前に Worker cancellation を確認する list。"""

    def __init__(self, models: list[str], check_cancellation: Callable[[], None]) -> None:
        super().__init__(models)
        self._check_cancellation = check_cancellation

    def __iter__(self) -> Iterator[str]:
        for model in super().__iter__():
            self._check_cancellation()
            yield model


class AnnotationWorker(LoRAIroWorkerBase["AnnotationExecutionResult"]):
    """アノテーションワーカー

    GUI Layer: Qt非同期処理と進捗管理
    ビジネスロジックはAnnotationRunnerに委譲

    主要機能:
    - QObject + QThreadベースの非同期実行
    - 進捗レポート（Signal経由）
    - キャンセル対応
    - AnnotationRunner呼び出し
    """

    # Issue #805: DS JobsScreen のステージ別 progress 用。list[StageProgress] を運ぶ。
    stage_progress_updated = Signal(object)

    _OPERATION_TYPE = "annotation"
    _ERROR_TYPE_L2 = "lib_call_exception"
    _ERROR_TYPE_L3 = "fatal"
    _ERROR_TYPE_INTEGRITY = "integrity_violation"

    def __init__(
        self,
        annotation_runner: AnnotationRunner,
        image_paths: list[str],
        litellm_model_ids: list[str],
        db_manager: "ImageDatabaseManager",
        model_registry: ModelRegistryServiceProtocol,
        run_options: "RunOptions | None" = None,
    ):
        """AnnotationWorker初期化

        Issue #245 / ADR 0023 Phase 1.11: 使用モデルは `Model.litellm_model_id`
        (registry key SSoT) で受け取る。同 `Model.name` 異 `provider` 行の混在
        (migration 経由 OpenRouter vs 新規 sync 直接版) に対しても確実に
        registry lookup hit するように設計されている。

        Args:
            annotation_runner: アノテーション業務ロジック
            image_paths: 画像パスリスト
            litellm_model_ids: 使用モデルの `litellm_model_id` リスト
            db_manager: データベースマネージャ（必須: DB保存・エラー記録用）
            model_registry: モデルレジストリ (provider/capabilities 取得用、Issue #225)
            run_options: 実行詳細設定 (Issue #803)。``dry_run`` 時は推論・送信・DB保存を
                行わず件数のみ算出する。``rating_gate=False`` 時は X/XXX rating +
                moderation preflight をスキップする (過去 refusal の再送を防ぐ refusal
                filter は rating ゲートと独立して維持)。``None`` の場合は従来挙動
                (dry_run=False / rating_gate=True)。
        """
        super().__init__(db_manager=db_manager)

        self.annotation_runner = annotation_runner
        self.image_paths = image_paths
        self.litellm_model_ids = list(litellm_model_ids)
        self.db_manager = db_manager
        self.model_registry = model_registry
        # Issue #803: run_options 未指定時は従来挙動 (dry_run=False / rating_gate=True)。
        self._dry_run = run_options.dry_run if run_options is not None else False
        self._rating_gate = run_options.rating_gate if run_options is not None else True
        self._path_to_phash: dict[str, str | None] = {}
        self._phash_to_input_path: dict[str, str] = {}
        self._phash_to_input_filename: dict[str, str] = {}
        self._path_to_image_id: dict[str, int] = {}

        logger.info(
            f"AnnotationWorker初期化 - Images: {len(self.image_paths)}, "
            f"Models: {len(self.litellm_model_ids)}"
        )
        logger.debug(f"  選択モデル (litellm_model_ids): {self.litellm_model_ids}")
        logger.debug(f"  対象画像パス: {self.image_paths[:5]}{'...' if len(self.image_paths) > 5 else ''}")

    def _save_error_records(
        self,
        error: Exception,
        image_paths: list[str],
        model_name: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """エラーレコードを各画像パスに対して保存する。

        image_idが取得できない場合もNoneのまま保存する(file_pathでトレース可能)。
        二次エラーが発生した場合はログのみで継続する。

        Args:
            error: 発生した例外。
            image_paths: エラー対象の画像パスリスト。
            model_name: エラー発生モデル名(全体エラーの場合はNone)。
            error_type: ADR 0033 予約分類。省略時は例外型名を使う。
        """
        # 例外オブジェクトから直接トレースバックを取得(except外でも確実に動作)
        stack_trace = "".join(traceback.format_exception(error))

        for image_path in image_paths:
            try:
                image_id = self._path_to_image_id.get(image_path)
                if image_id is None:
                    logger.warning(f"image_id取得失敗(file_pathで記録): {image_path}")
                self.db_manager.save_error_record(
                    operation_type="annotation",
                    error_type=error_type or type(error).__name__,
                    error_message=str(error),
                    image_id=image_id,
                    stack_trace=stack_trace,
                    file_path=image_path,
                    model_name=model_name,
                )
            except Exception as save_error:
                logger.error(f"エラーレコード保存失敗: {image_path}, {save_error}")

    def _refresh_input_phash_cache(self) -> None:
        """現在の `image_paths` に対応する DB 登録済み pHash を一括取得する。"""
        try:
            path_to_phash = self.db_manager.image_repo.get_phashes_by_filepaths(self.image_paths)
        except Exception as exc:
            logger.warning(
                f"pHash 一括取得に失敗しました。lib 側自動計算に委任します: {exc}", exc_info=True
            )
            path_to_phash = {}
        self._path_to_phash = path_to_phash if isinstance(path_to_phash, dict) else {}

        self._phash_to_input_path = {
            phash: image_path for image_path, phash in self._path_to_phash.items() if phash is not None
        }
        self._phash_to_input_filename = {
            phash: Path(image_path).name for phash, image_path in self._phash_to_input_path.items()
        }

        phashes = {p for p in self._path_to_phash.values() if p is not None}
        phash_to_id = self.db_manager.image_repo.find_image_ids_by_phashes(phashes) if phashes else {}
        self._path_to_image_id = {
            path: phash_to_id[phash]
            for path, phash in self._path_to_phash.items()
            if phash is not None and phash in phash_to_id
        }

    def _build_phash_list_for_current_paths(self) -> list[str] | None:
        """lib に渡す pHash list を input path 順に構築する。

        未登録画像が混ざる場合は alignment を壊さないため None を返し、lib 側計算へ
        フォールバックする。
        """
        if not self.image_paths:
            return []
        if not self._path_to_phash:
            return None
        phash_list = [self._path_to_phash.get(image_path) for image_path in self.image_paths]
        if any(phash is None for phash in phash_list):
            return None
        return [str(phash) for phash in phash_list]

    def _collect_valid_model_results(
        self,
        model_results: PHashAnnotationResults,
        expected_model_ids: set[str],
        model_errors: list[ModelErrorDetail],
    ) -> PHashAnnotationResults:
        """選択外 model_id を integrity violation として除外した結果を返す。"""
        valid_results: PHashAnnotationResults = PHashAnnotationResults()
        for phash, annotations in model_results.items():
            valid_annotations: dict[str, Any] = {}
            for model_name, unified_result in annotations.items():
                if model_name not in expected_model_ids:
                    self._record_integrity_violation(phash, model_name, unified_result, model_errors)
                    continue
                valid_annotations[model_name] = unified_result
            if valid_annotations:
                valid_results[phash] = valid_annotations
        return valid_results

    def _record_integrity_violation(
        self,
        phash: str,
        model_name: str,
        unified_result: Any,
        model_errors: list[ModelErrorDetail],
    ) -> None:
        """選択外 model_id が結果に混入したことを error_records と summary に記録する。"""
        message = f"Annotation result contains unexpected model_id: {model_name}"
        image_path = self._phash_to_input_path.get(phash)
        image_label = Path(image_path).name if image_path else phash[:12] + "..."
        model_errors.append(
            ModelErrorDetail(
                model_name=model_name,
                image_path=image_label,
                error_message=message,
                error_type=self._ERROR_TYPE_INTEGRITY,
            )
        )

        try:
            image_id = None
            if image_path is not None:
                image_id = self.db_manager.get_image_id_by_filepath(image_path)
            self.db_manager.save_error_record(
                operation_type="annotation",
                error_type=self._ERROR_TYPE_INTEGRITY,
                error_message=message,
                image_id=image_id,
                stack_trace=f"phash={phash}, result={unified_result!r}",
                file_path=image_path or image_label,
                model_name=model_name,
            )
        except Exception as save_error:
            logger.error(f"integrity_violation 保存失敗: phash={phash}, model={model_name}, {save_error}")

    def _collect_l1_model_errors(
        self,
        model_results: PHashAnnotationResults,
        model_errors: list[ModelErrorDetail],
    ) -> None:
        """lib `result.error` を DB 保存せず summary 用 model_errors に集約する。"""
        for phash, annotations in model_results.items():
            image_label = self._phash_to_input_filename.get(phash, phash[:12] + "...")
            for model_name, unified_result in annotations.items():
                error = self._extract_field(unified_result, "error")
                if not error:
                    continue
                model_errors.append(
                    ModelErrorDetail(
                        model_name=model_name,
                        image_path=image_label,
                        error_message=str(error),
                        error_type="result_error",
                    )
                )

    def _merge_annotation_results(
        self,
        destination: PHashAnnotationResults,
        source: PHashAnnotationResults,
    ) -> None:
        """pHash -> model result の辞書を destination にマージする。"""
        for phash, annotations in source.items():
            if phash not in destination:
                destination[phash] = {}
            destination[phash].update(annotations)

    def _build_stage_model_inputs(self) -> list[StageModelInput]:
        """選択モデルを registry 解決して StageModelInput 列に変換する (Issue #805)。

        registry に無い litellm_model_id は capability 不明扱い (ANNOTATE ステージ) に
        縮退する。registry 取得失敗時は空リストを返し、ステージ表示を諦める
        (進捗本体は別途報告されるため annotation は継続)。

        Returns:
            選択順の StageModelInput リスト。
        """
        try:
            model_info_list = self.model_registry.get_available_models()
        except Exception as exc:
            logger.warning(f"ステージ進捗用モデル情報の取得に失敗: {exc}")
            return []
        info_map = {(info.litellm_model_id or info.name): info for info in model_info_list}
        inputs: list[StageModelInput] = []
        for model_id in self.litellm_model_ids:
            info = info_map.get(model_id)
            # key は一意な litellm_model_id を使う (同一 info.name へ解決する別ルートを
            # 取り違えないため、Codex P2)。表示名 model_name は重複し得る。
            if info is None:
                inputs.append(StageModelInput(model_id, model_id, "", [], False))
            else:
                inputs.append(
                    StageModelInput(
                        model_id, info.name, info.provider, list(info.capabilities), info.requires_api_key
                    )
                )
        return inputs

    def _emit_stage_progress(
        self,
        stage_inputs: list[StageModelInput],
        *,
        processed_count: int,
        finished: bool = False,
        completed_keys: set[str] | None = None,
        errored_keys: set[str] | None = None,
    ) -> None:
        """ステージ別進捗を構築して signal で通知する (Issue #805)。"""
        if not stage_inputs:
            return
        stages: list[StageProgress] = build_stage_progress(
            stage_inputs,
            processed_count=processed_count,
            total_count=len(self.image_paths),
            finished=finished,
            completed_keys=completed_keys,
            errored_keys=errored_keys,
        )
        self.stage_progress_updated.emit(stages)

    @staticmethod
    def _stage_errored_model_keys(results: PHashAnnotationResults) -> set[str]:
        """result.error を持つモデルキー集合を返す (Issue #805 / Codex P2)。

        例外を投げない L1 エラー (provider/model の result_error) を持つモデルを
        ステージ表示で失敗扱いにするために使う。結果のモデルキーは registry key
        SSoT (= litellm_model_id) であり ``StageModelInput.key`` と一致する。

        Args:
            results: phash → model_key → UnifiedResult のマッピング。

        Returns:
            error フィールドが立っているモデルキーの集合。
        """
        errored: set[str] = set()
        for annotations in results.values():
            for model_key, unified_result in annotations.items():
                if AnnotationWorker._extract_field(unified_result, "error"):
                    errored.add(model_key)
        return errored

    def _run_annotation(self) -> tuple[PHashAnnotationResults, list[ModelErrorDetail]]:
        """選択モデルを一括渡ししてアノテーションを実行する。

        Returns:
            (マージされたアノテーション結果, モデルエラー詳細リスト) のタプル。
        """
        merged_results: PHashAnnotationResults = PHashAnnotationResults()
        model_errors: list[ModelErrorDetail] = []
        total_models = len(self.litellm_model_ids)
        phash_list = self._build_phash_list_for_current_paths()

        if total_models == 0:
            logger.debug("選択モデルなし: アノテーション実行をスキップ")
            return merged_results, model_errors

        logger.debug(f"モデル一括実行開始: {total_models}モデル = {self.litellm_model_ids}")

        stage_inputs = self._build_stage_model_inputs()
        self._report_progress(
            5,
            f"AIモデル一括実行中: {total_models}モデル",
            processed_count=0,
            total_count=len(self.image_paths),
        )
        # 実行開始時点のステージ別進捗 (全モデル 0 件処理済み) を通知する。
        self._emit_stage_progress(stage_inputs, processed_count=0)

        try:
            self._check_cancellation()
            bulk_results = self.annotation_runner.execute_annotation(
                image_paths=self.image_paths,
                litellm_model_ids=_CancellationCheckingModelList(
                    self.litellm_model_ids,
                    self._check_cancellation,
                ),
                phash_list=phash_list,
            )
            valid_results = self._collect_valid_model_results(
                bulk_results,
                set(self.litellm_model_ids),
                model_errors,
            )
            self._collect_l1_model_errors(valid_results, model_errors)
            self._merge_annotation_results(merged_results, valid_results)

            self._report_progress(
                90,
                f"AIモデル一括実行完了: {total_models}モデル",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
            # 一括実行完了: result.error を持つモデル (例外を投げない L1 エラー) は
            # 失敗ステージとして通知し、それ以外を完了 (100% / ok) にする。
            # finished=True で一律 ok にすると result_error のモデルが成功表示になり、
            # サマリーと矛盾する (Codex P2)。
            errored_keys = self._stage_errored_model_keys(valid_results)
            completed_keys = {key for key in self.litellm_model_ids if key not in errored_keys}
            self._emit_stage_progress(
                stage_inputs,
                processed_count=len(self.image_paths),
                completed_keys=completed_keys,
                errored_keys=errored_keys,
            )
            logger.debug(f"モデル一括実行完了: 結果={len(bulk_results)}件")
            return merged_results, model_errors

        except CancellationError:
            logger.info("モデル一括アノテーション処理がキャンセルされました")
            raise
        except Exception as bulk_error:
            logger.warning(
                f"モデル一括実行に失敗したためモデル単位 fallback に切り替えます: {bulk_error}",
                exc_info=True,
            )
            return self._run_annotation_per_model_fallback(phash_list)

    def _run_annotation_per_model_fallback(
        self,
        phash_list: list[str] | None,
    ) -> tuple[PHashAnnotationResults, list[ModelErrorDetail]]:
        """一括呼び出し失敗時の互換 fallback としてモデル単位で実行する。"""
        merged_results: PHashAnnotationResults = PHashAnnotationResults()
        model_errors: list[ModelErrorDetail] = []
        total_models = len(self.litellm_model_ids)

        logger.debug(f"モデル単位 fallback 実行開始: {total_models}モデル = {self.litellm_model_ids}")

        # Issue #805: per-model 完了/失敗を一意キー (litellm_model_id) で追跡する。
        # 未起動モデルを 100% と誤表示しないよう、ステージ進捗の率は
        # processed_count=0 (未完了は 0%) で出し、完了は completed_keys 経由で 100%
        # にする (Codex P2: fallback で未起動モデルが false 100% になる回帰の回避)。
        stage_inputs = self._build_stage_model_inputs()
        completed_keys: set[str] = set()
        errored_keys: set[str] = set()

        for model_idx, litellm_model_id in enumerate(self.litellm_model_ids):
            self._check_cancellation()

            processed_steps = model_idx * len(self.image_paths)
            total_steps = max(total_models * len(self.image_paths), 1)
            progress = 5 + int((processed_steps / total_steps) * 85)
            self._report_progress(
                progress,
                f"AIモデル実行中: {litellm_model_id} ({model_idx + 1}/{total_models})",
                processed_count=min(processed_steps, len(self.image_paths)),
                total_count=len(self.image_paths),
            )
            self._emit_stage_progress(
                stage_inputs,
                processed_count=0,
                completed_keys=completed_keys,
                errored_keys=errored_keys,
            )

            try:
                logger.debug(
                    f"モデル実行開始: {litellm_model_id} ({model_idx + 1}/{total_models}), "
                    f"対象画像数={len(self.image_paths)}"
                )

                model_results = self.annotation_runner.execute_annotation(
                    image_paths=self.image_paths,
                    litellm_model_ids=[litellm_model_id],
                    phash_list=phash_list,
                )

                valid_model_results = self._collect_valid_model_results(
                    model_results,
                    {litellm_model_id},
                    model_errors,
                )
                self._collect_l1_model_errors(valid_model_results, model_errors)

                self._merge_annotation_results(merged_results, valid_model_results)

                completed_keys.add(litellm_model_id)

                logger.debug(
                    f"モデル実行完了: {litellm_model_id}, 結果={len(model_results)}件, "
                    f"マージ後合計={len(merged_results)}件"
                )

            except CancellationError:
                logger.info(f"モデル {litellm_model_id} のアノテーション処理がキャンセルされました")
                raise

            except Exception as e:
                errored_keys.add(litellm_model_id)
                logger.error(f"モデル {litellm_model_id} でエラー: {e}", exc_info=True)
                self._save_error_records(
                    e,
                    self.image_paths,
                    model_name=litellm_model_id,
                    error_type=self._ERROR_TYPE_L2,
                )
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
                            error_type=self._ERROR_TYPE_L2,
                        )
                    )
                # エラーでも次のモデルに進む(部分的成功を許容)

            completed_steps = (model_idx + 1) * len(self.image_paths)
            self._report_progress(
                5 + int((completed_steps / max(total_models * len(self.image_paths), 1)) * 85),
                f"AIモデル実行完了: {litellm_model_id} ({model_idx + 1}/{total_models})",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
            # このモデルの完了/失敗を反映したステージ別進捗を通知する。
            # 未起動モデルは completed_keys に無いため 0% のまま (false 100% を出さない)。
            self._emit_stage_progress(
                stage_inputs,
                processed_count=0,
                completed_keys=completed_keys,
                errored_keys=errored_keys,
            )

        logger.debug(f"モデル単位 fallback 実行完了: 最終結果={len(merged_results)}件")
        return merged_results, model_errors

    def execute(self) -> AnnotationExecutionResult:
        """アノテーション処理実行

        AnnotationRunner経由でビジネスロジックを実行し、
        進捗管理とキャンセル処理を担当する。

        Returns:
            AnnotationExecutionResult: サマリー付きアノテーション結果

        Raises:
            Exception: アノテーション実行エラー
        """
        logger.info(
            f"アノテーション処理開始 - {len(self.image_paths)}画像, {len(self.litellm_model_ids)}モデル"
        )

        # Issue #803 (Codex P1): dry-run は実推論・送信・DB保存を一切行わず件数のみ算出する。
        # RunSettings 契約は「実際に推論せずジョブ件数・推定コストだけを検証する」であり、
        # 有料 WebAPI 呼び出しや preflight 副作用を発生させてはならない。最終保存だけの
        # スキップでは不十分なため、推論前にここで短絡する。
        if self._dry_run:
            logger.info(
                "dry-run: 推論・送信・DB保存をスキップし件数のみ算出 "
                f"({len(self.image_paths)}画像 × {len(self.litellm_model_ids)}モデル)"
            )
            return AnnotationExecutionResult(
                results=PHashAnnotationResults(),
                total_images=len(self.image_paths),
                models_used=list(self.litellm_model_ids),
            )

        try:
            # Phase 0: refusal 送信前 filter (5%)
            # ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): refusal filter
            # は WebAPI モデル選択時のみ適用、Worker 内で async 実行 (GUI freeze
            # 回避)。バッチ resolve で N+1 クエリも解消。filter 後の件数を以後の
            # progress total_count として使う。
            self._refresh_input_phash_cache()

            self._report_progress(
                5,
                "refusal filter を適用中...",
                total_count=len(self.image_paths),
            )
            self._check_cancellation()
            preflight_errors = self._apply_refusal_prefilter()

            # Phase 1: アノテーション実行(5-90%)
            self._report_progress(5, "アノテーション処理を開始...", total_count=len(self.image_paths))
            self._check_cancellation()

            merged_results, model_errors = self._run_annotation()
            model_errors = preflight_errors + model_errors

            # Phase 2: DB保存(90-95%)
            self._report_progress(
                90,
                "結果をDBに保存中...",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
            self._check_cancellation()

            db_save_success, db_save_skip, image_summaries, phash_to_filename = (
                self._save_results_to_database(merged_results)
            )

            # Phase 3: 統計集計(95-100%)
            self._report_progress(
                95,
                "統計を集計中...",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
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
            self._save_error_records(e, self.image_paths, model_name=None, error_type=self._ERROR_TYPE_L3)
            self._error_already_recorded = True
            raise

    def _apply_refusal_prefilter(self) -> list[ModelErrorDetail]:
        """refusal を持つ画像を `self.image_paths` から除外する (Worker 内実行版)。

        ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): GUI スレッド上で
        N+1 クエリを発行しないよう、Worker 内で実行する設計に変更。filter は
        WebAPI モデル選択時のみ適用し、registry lookup 失敗時は filter skip して
        annotation を続行する (graceful degradation)。
        WebAPI モデル選択時は refusal + rating prefilter を順次適用する。

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
            return []

        save_service = AnnotationSaveService(
            annotation_repo=self.db_manager.annotation_repo,
            image_repo=self.db_manager.image_repo,
            model_repo=self.db_manager.model_repo,
            error_record_repo=self.db_manager.error_record_repo,
        )
        original_count = len(self.image_paths)
        try:
            # refusal filter は rating ゲートと独立 (Issue #803 Codex P2)。過去に provider が
            # 拒否した画像 (SAFETY_REFUSAL / EMPTY_ANNOTATION) の再送・API 浪費を防ぐため、
            # rating ゲートの ON/OFF に関わらず常に適用する。
            filtered_image_paths = save_service.filter_refused_image_paths(self.image_paths)

            # Issue #803: rating ゲート無効時は X/XXX rating + moderation preflight のみスキップ。
            if not self._rating_gate:
                self.image_paths = filtered_image_paths
                excluded = original_count - len(self.image_paths)
                if excluded > 0:
                    logger.info(
                        f"prefilter 適用 (rating ゲート無効): {original_count}件 → "
                        f"{len(self.image_paths)}件 (refusal 除外のみ: {excluded}件)"
                    )
                else:
                    logger.debug(
                        "rating ゲート無効 (run_options.rating_gate=False): "
                        "rating/moderation preflight をスキップ"
                    )
                return []

            rating_filtered_paths = save_service.filter_excluded_by_rating(filtered_image_paths)
            preflight_service = ModerationPreflightService(
                image_repo=self.db_manager.image_repo,
                model_repo=self.db_manager.model_repo,
                error_record_repo=self.db_manager.error_record_repo,
                annotation_save_service=save_service,
                config_service=self.db_manager.config_service,
                moderation_runner=build_annotation_runner_runner(self.annotation_runner.execute_annotation),
            )
            preflight_result = preflight_service.apply(rating_filtered_paths)
            self.image_paths = preflight_result.allowed_paths
        except Exception as exc:
            logger.warning(
                f"refusal filter 実行失敗; filter skip して annotation 続行: {exc}",
                exc_info=True,
            )
            return []

        excluded = original_count - len(self.image_paths)
        if excluded > 0:
            logger.info(
                f"prefilter 適用: {original_count}件 → {len(self.image_paths)}件 "
                f"(refusal + rating 除外: {excluded}件)"
            )
        return [
            ModelErrorDetail(
                model_name=MODERATION_LITELLM_MODEL_ID,
                image_path=Path(skip.image_path).name,
                error_message=skip.message,
                error_type=skip.reason,
            )
            for skip in preflight_result.skipped
        ]

    def _save_results_to_database(
        self, results: PHashAnnotationResults
    ) -> tuple[int, int, list[ImageResultSummary], dict[str, str]]:
        """アノテーション結果をDBに保存

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Returns:
            (DB保存成功件数, スキップ件数, 画像ごとの結果概要リスト, phash→ファイル名マップ) のタプル。
        """
        # #633: 保存対象をこのバッチで実際に処理した image_id 集合に限定する
        # (同一 pHash の未選択別版へ結果を書き込み汚染しないため)。
        allowed_image_ids = self._resolve_batch_image_ids()

        save_result = AnnotationSaveService(
            annotation_repo=self.db_manager.annotation_repo,
            image_repo=self.db_manager.image_repo,
            model_repo=self.db_manager.model_repo,
            error_record_repo=self.db_manager.error_record_repo,
        ).save_annotation_results(results, allowed_image_ids=allowed_image_ids)

        # GUIサマリー用: phash→ファイル名マップを構築 (#633: 別版で複数 image_id になり得る)
        phash_to_image_ids = self.db_manager.image_repo.find_image_ids_by_phashes_multi(set(results.keys()))
        phash_to_filename = self._build_phash_to_filename_map(phash_to_image_ids)

        # 画像ごとの結果概要（DB登録済みのもののみ）。サマリーは pHash 単位 1 行のため、
        # 別版で複数 image_id があっても代表ファイル名 1 件を表示する。
        image_summaries: list[ImageResultSummary] = [
            self._build_image_summary(phash, phash_to_filename, annotations)
            for phash, annotations in results.items()
            if phash_to_image_ids.get(phash)
        ]

        logger.info(f"DB保存完了: {save_result.success_count}/{save_result.total_count}件成功")
        return save_result.success_count, save_result.skip_count, image_summaries, phash_to_filename

    def _resolve_batch_image_ids(self) -> set[int] | None:
        """このバッチの image_paths を DB 上の image_id 集合に解決する (#633)。

        annotation 保存の fan-out をバッチ内画像へ限定するために使う。解決に失敗した
        場合は None を返し、save 側は pHash ごと先頭 1 件のみ保存する安全側挙動になる。

        Returns:
            バッチに対応する image_id 集合。解決不能時は None。
        """
        try:
            path_to_image_id = self.db_manager.image_repo.get_image_ids_by_filepaths(self.image_paths)
        except Exception as exc:
            logger.warning(f"バッチ image_id 解決に失敗、fan-out を先頭 1 件に縮退: {exc}")
            return None
        if not isinstance(path_to_image_id, dict):
            return None
        image_ids = {image_id for image_id in path_to_image_id.values() if image_id is not None}
        return image_ids or None

    def _build_phash_to_filename_map(self, phash_to_image_ids: dict[str, list[int]]) -> dict[str, str]:
        """pHashからファイル名へのマッピングを構築する。

        image_pathsリストとDB上のimage_idマッピングから、
        phash → ファイル名の逆引きマップを作る。サマリーは pHash 単位 1 行のため、
        別版で複数 image_id がある場合は最初に一致した image_id のファイル名を代表に採る (#633)。

        Args:
            phash_to_image_ids: pHash → image_id 昇順リスト のマッピング。

        Returns:
            pHash → ファイル名のマッピング。
        """
        # image_id → file_path マッピングを構築
        path_to_image_id = self.db_manager.image_repo.get_image_ids_by_filepaths(self.image_paths)
        if not isinstance(path_to_image_id, dict):
            path_to_image_id = {}
        image_id_to_path: dict[int, str] = {
            image_id: image_path
            for image_path, image_id in path_to_image_id.items()
            if image_id is not None
        }

        # phash → filename マッピング
        result: dict[str, str] = {}
        for phash, image_ids in phash_to_image_ids.items():
            # この pHash に紐づく image_id のうち、対象 image_paths に含まれる代表を採用
            matched_name: str | None = None
            for image_id in image_ids:
                if image_id in image_id_to_path:
                    matched_name = Path(image_id_to_path[image_id]).name
                    break
            result[phash] = matched_name if matched_name is not None else phash[:12] + "..."
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
