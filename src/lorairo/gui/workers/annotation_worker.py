"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationLogicに委譲
"""

import traceback
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


class AnnotationWorker(LoRAIroWorkerBase[PHashAnnotationResults]):
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

    def execute(self) -> PHashAnnotationResults:
        """アノテーション処理実行

        AnnotationLogic経由でビジネスロジックを実行し、
        進捗管理とキャンセル処理を担当する。

        Returns:
            PHashAnnotationResults: アノテーション結果

        Raises:
            Exception: アノテーション実行エラー
        """
        logger.info(f"アノテーション処理開始 - {len(self.image_paths)}画像, {len(self.models)}モデル")

        try:
            # Phase 1: アノテーション実行（10-80%）
            self._report_progress(10, "アノテーション処理を開始...", total_count=len(self.image_paths))
            self._check_cancellation()

            # モデル単位で処理（進捗・キャンセル対応）
            merged_results: PHashAnnotationResults = {}
            total_models = len(self.models)

            for model_idx, model_name in enumerate(self.models):
                # モデル間キャンセルチェック
                self._check_cancellation()

                # 進捗報告
                progress = 10 + int((model_idx / total_models) * 70)  # 10-80%
                self._report_progress(
                    progress,
                    f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                    processed_count=model_idx,
                    total_count=total_models,
                )

                # AnnotationLogic経由でアノテーション実行
                try:
                    model_results = self.annotation_logic.execute_annotation(
                        image_paths=self.image_paths,
                        model_names=[model_name],
                        phash_list=None,
                    )

                    # 結果をマージ
                    for phash, annotations in model_results.items():
                        if phash not in merged_results:
                            merged_results[phash] = {}
                        merged_results[phash].update(annotations)

                    logger.debug(f"モデル {model_name} 完了: {len(model_results)}件の結果")

                except Exception as e:
                    logger.error(f"モデル {model_name} でエラー: {e}", exc_info=True)

                    # エラーレコード保存（二次エラー対策付き）
                    for image_path in self.image_paths:
                        try:
                            # 画像パスから image_id を取得
                            image_id = self.db_manager.get_image_id_by_filepath(image_path)

                            # エラーレコード保存
                            self.db_manager.save_error_record(
                                operation_type="annotation",
                                error_type=type(e).__name__,
                                error_message=str(e),
                                image_id=image_id,
                                stack_trace=traceback.format_exc(),
                                file_path=image_path,
                                model_name=model_name,
                            )
                        except Exception as save_error:
                            logger.error(
                                f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}"
                            )

                    # エラーでも次のモデルに進む（部分的成功を許容）

            # Phase 2: DB保存（85%）
            self._report_progress(
                85,
                "結果をDBに保存中...",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )
            self._check_cancellation()

            self._save_results_to_database(merged_results)

            # 完了進捗
            self._report_progress(
                100,
                "アノテーション処理が完了しました",
                processed_count=len(self.image_paths),
                total_count=len(self.image_paths),
            )

            logger.info(f"アノテーション処理完了: {len(merged_results)}件の結果")
            return merged_results

        except Exception as e:
            logger.error(f"アノテーション処理エラー: {e}", exc_info=True)

            # エラーレコード保存（二次エラー対策付き）
            for image_path in self.image_paths:
                try:
                    # 画像パスから image_id を取得
                    image_id = self.db_manager.get_image_id_by_filepath(image_path)

                    # エラーレコード保存
                    self.db_manager.save_error_record(
                        operation_type="annotation",
                        error_type=type(e).__name__,
                        error_message=str(e),
                        image_id=image_id,
                        stack_trace=traceback.format_exc(),
                        file_path=image_path,
                        model_name=None,  # 全体エラーのためモデル特定不可
                    )
                except Exception as save_error:
                    logger.error(f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}")

            raise

    def _save_results_to_database(self, results: PHashAnnotationResults) -> None:
        """アノテーション結果をDBに保存

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Note:
            ライブラリが返したpHashをfind_image_ids_by_phashesで一括DB照会。
            タグIDもbatch_resolve_tag_ids()で一括解決しN+1を回避。
            保存失敗時は個別にログを記録し、処理を継続する。
        """
        # 事前一括取得: pHash → image_id（N+1回避）
        phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(set(results.keys()))

        # 事前一括取得: モデル名・タグ文字列を収集
        all_model_names, all_raw_tags = self._collect_model_names_and_tags(results)
        models_cache = self.db_manager.repository.get_models_by_names(all_model_names)

        # 事前一括取得: タグID一括解決（N+1回避）
        tag_id_cache = self._resolve_tag_ids_batch(all_raw_tags)

        success_count = 0
        for phash, annotations in results.items():
            try:
                image_id = phash_to_image_id.get(phash)
                if image_id is None:
                    logger.warning(
                        f"pHash {phash[:8]}... に対応する画像がDBに見つかりません。スキップします。"
                    )
                    continue

                # 変換（キャッシュ済みモデルを使用）
                annotations_dict = self._convert_to_annotations_dict(annotations, models_cache)

                if not annotations_dict or not any(annotations_dict.values()):
                    logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
                    continue

                # DB保存（annotation_worker経路: 存在チェックスキップ + タグIDキャッシュ使用）
                self.db_manager.repository.save_annotations(
                    image_id,
                    annotations_dict,
                    skip_existence_check=True,
                    tag_id_cache=tag_id_cache if tag_id_cache else None,
                )
                success_count += 1

                logger.info(f"画像ID {image_id} のアノテーション保存成功")

            except Exception as e:
                logger.error(f"保存失敗 phash={phash[:8]}...: {e}", exc_info=True)

        logger.info(f"DB保存完了: {success_count}/{len(results)}件成功")

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

    def _convert_to_annotations_dict(
        self, annotations: dict[str, Any], models_cache: dict[str, Any]
    ) -> "AnnotationsDict":
        """PHashAnnotationResults→AnnotationsDictへ変換

        Args:
            annotations: model_name → UnifiedResult マッピング
            models_cache: model_name → Model の事前取得キャッシュ

        Returns:
            AnnotationsDict: DB保存用の型付き辞書

        Note:
            - TypedDictは db_repository.py からimport
            - model_id解決はmodels_cacheから取得（N+1回避）
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
            # 辞書アクセス（image-annotator-libから返される値は辞書またはPydanticモデル）
            error = (
                unified_result.get("error") if isinstance(unified_result, dict) else unified_result.error
            )
            if error:
                logger.warning(f"モデル {model_name} エラーをスキップ")
                continue

            # キャッシュからモデル取得（DBクエリ不要）
            model = models_cache.get(model_name)
            if not model:
                logger.warning(f"モデル '{model_name}' がDB未登録")
                continue

            # 結果の取得（辞書またはPydanticモデル対応）
            scores = (
                unified_result.get("scores") if isinstance(unified_result, dict) else unified_result.scores
            )
            tags = unified_result.get("tags") if isinstance(unified_result, dict) else unified_result.tags
            captions = (
                unified_result.get("captions")
                if isinstance(unified_result, dict)
                else unified_result.captions
            )
            ratings = (
                unified_result.get("ratings")
                if isinstance(unified_result, dict)
                else unified_result.ratings
            )

            # Scores
            if scores:
                for _score_name, score_value in scores.items():
                    result["scores"].append(
                        {
                            "model_id": model.id,
                            "score": float(score_value),
                            "is_edited_manually": False,
                        }
                    )

            # Tags (正しいキー: "tag")
            if tags:
                for tag_content in tags:
                    result["tags"].append(
                        {
                            "model_id": model.id,
                            "tag": tag_content,  # ← schema.py準拠
                            "existing": False,
                            "is_edited_manually": False,
                            "confidence_score": None,
                            "tag_id": None,
                        }
                    )

            # Captions (正しいキー: "caption")
            if captions:
                for caption_content in captions:
                    result["captions"].append(
                        {
                            "model_id": model.id,
                            "caption": caption_content,  # ← schema.py準拠
                            "existing": False,
                            "is_edited_manually": False,
                        }
                    )

            # Ratings (正しいキー: "raw_rating_value", "normalized_rating")
            if ratings:
                rating_value = str(ratings)
                result["ratings"].append(
                    {
                        "model_id": model.id,
                        "raw_rating_value": rating_value,  # ← schema.py準拠
                        "normalized_rating": rating_value,  # ← schema.py準拠
                        "confidence_score": None,
                    }
                )

        return result
