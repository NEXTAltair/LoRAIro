"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationLogicに委譲
"""

import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        db_manager: "ImageDatabaseManager | None" = None,
    ):
        """AnnotationWorker初期化

        Args:
            annotation_logic: アノテーション業務ロジック
            image_paths: 画像パスリスト
            models: 使用モデル名リスト
            db_manager: データベースマネージャ（エラー記録用、Optional）
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
            # Phase 1: pHashマッピング構築
            self._report_progress(5, "pHash計算中...", total_count=len(self.image_paths))
            self._check_cancellation()

            phash_mapping, valid_image_paths = self._build_phash_mapping()
            phash_list = list(phash_mapping.keys())

            if not phash_list:
                raise ValueError("pHash計算に失敗しました - 処理を中止します")

            # 有効画像数のログ
            valid_count = len(valid_image_paths)
            if valid_count < len(self.image_paths):
                logger.warning(
                    f"一部画像をスキップ: {len(self.image_paths) - valid_count}件失敗, "
                    f"{valid_count}件で処理継続"
                )

            # Phase 2: アノテーション実行
            self._report_progress(10, "アノテーション処理を開始...", total_count=valid_count)
            self._check_cancellation()

            # モデル単位で処理（進捗・キャンセル対応）
            merged_results: PHashAnnotationResults = {}
            total_models = len(self.models)

            for model_idx, model_name in enumerate(self.models):
                # モデル間キャンセルチェック
                self._check_cancellation()

                # 進捗報告
                progress = 10 + int((model_idx / total_models) * 70)  # 10-80% (changed from 10-90%)
                self._report_progress(
                    progress,
                    f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                    processed_count=model_idx,
                    total_count=total_models,
                )

                # AnnotationLogic経由でアノテーション実行（有効画像のみ）
                try:
                    model_results = self.annotation_logic.execute_annotation(
                        image_paths=valid_image_paths,  # FIXED: 有効画像のみ渡す
                        model_names=[model_name],
                        phash_list=phash_list,  # NEW: 事前計算したpHash listを渡す
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
                    # バッチ処理のため、各画像に対してエラーレコードを作成
                    # 注: 全画像（self.image_paths）を対象とする
                    #     - pHash計算失敗画像も含む（完全なエラー記録のため）
                    #     - 実際の処理対象はvalid_image_pathsだが、エラー記録は包括的に行う
                    if self.db_manager:
                        for image_path in self.image_paths:
                            try:
                                # 画像パスから image_id を取得
                                image_id = self.db_manager.get_image_id_by_filepath(image_path)

                                # エラーレコード保存
                                self.db_manager.save_error_record(
                                    operation_type="annotation",
                                    error_type=type(e).__name__,
                                    error_message=str(e),
                                    image_id=image_id,  # 画像IDを指定
                                    stack_trace=traceback.format_exc(),
                                    file_path=image_path,
                                    model_name=model_name,
                                )
                            except Exception as save_error:
                                logger.error(
                                    f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}"
                                )

                    # エラーでも次のモデルに進む（部分的成功を許容）

            # Phase 3: DB保存
            self._report_progress(
                85, "結果をDBに保存中...", processed_count=valid_count, total_count=valid_count
            )
            self._check_cancellation()

            self._save_results_to_database(merged_results, phash_mapping)

            # 完了進捗
            self._report_progress(
                100,
                "アノテーション処理が完了しました",
                processed_count=valid_count,
                total_count=valid_count,
            )

            logger.info(f"アノテーション処理完了: {len(merged_results)}件の結果")
            return merged_results

        except Exception as e:
            logger.error(f"アノテーション処理エラー: {e}", exc_info=True)

            # エラーレコード保存（二次エラー対策付き）
            # 全体エラーでも各画像に対してエラーレコードを作成
            # 注: 全画像（self.image_paths）を対象とする
            #     - pHash計算失敗画像も含む（完全なエラー記録のため）
            #     - 実際の処理対象はvalid_image_pathsだが、エラー記録は包括的に行う
            if self.db_manager:
                for image_path in self.image_paths:
                    try:
                        # 画像パスから image_id を取得
                        image_id = self.db_manager.get_image_id_by_filepath(image_path)

                        # エラーレコード保存
                        self.db_manager.save_error_record(
                            operation_type="annotation",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            image_id=image_id,  # 画像IDを指定
                            stack_trace=traceback.format_exc(),
                            file_path=image_path,
                            model_name=None,  # 全体エラーのためモデル特定不可
                        )
                    except Exception as save_error:
                        logger.error(f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}")

            raise

    def _build_phash_mapping(self) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """pHash→画像メタデータマッピングを構築

        LoRAIroのcalculate_phash()を使用してpHashを事前計算し、
        DB値との整合性を保証する。

        Returns:
            tuple[dict, list]: (phash_mapping, valid_image_paths)
                - phash_mapping: {phash: {image_id, image_path}}
                - valid_image_paths: 処理成功した画像パスのリスト

        Note:
            pHash計算失敗またはimage_id取得失敗の画像はスキップされ、
            valid_image_pathsには含まれません。
        """
        from lorairo.utils.tools import calculate_phash

        phash_mapping = {}
        valid_image_paths = []
        failed_count = 0

        for image_path in self.image_paths:
            try:
                path_obj = Path(image_path)
                phash_value = calculate_phash(path_obj)
                image_id = self.db_manager.get_image_id_by_filepath(image_path)

                # image_id検証（Noneの場合はスキップ）
                if image_id is None:
                    failed_count += 1
                    logger.error(f"image_id取得失敗: {image_path} - DBに未登録の可能性")
                    continue

                phash_mapping[phash_value] = {"image_id": image_id, "image_path": image_path}
                valid_image_paths.append(image_path)

                logger.debug(f"pHash計算成功: {path_obj.name} → {phash_value[:8]}...")

            except Exception as e:
                failed_count += 1
                logger.error(f"pHash計算失敗: {image_path}, {e}")

        if failed_count > 0:
            logger.warning(f"pHash計算失敗: {failed_count}/{len(self.image_paths)}件")

        logger.info(f"pHashマッピング構築完了: {len(phash_mapping)}件（有効画像: {len(valid_image_paths)}件）")
        return phash_mapping, valid_image_paths

    def _save_results_to_database(
        self, results: PHashAnnotationResults, phash_mapping: dict[str, dict[str, Any]]
    ) -> None:
        """アノテーション結果をDBに保存

        Args:
            results: PHashAnnotationResults (phash → model_name → UnifiedResult)
            phash_mapping: pHash → {image_id, image_path} マッピング

        Note:
            保存失敗時は個別にログを記録し、処理を継続する。
        """
        success_count = 0

        for phash, annotations in results.items():
            try:
                # pHash→image_id変換
                mapping_entry = phash_mapping.get(phash)
                if not mapping_entry:
                    logger.warning(f"pHash {phash[:8]}... のマッピング未発見")
                    continue

                image_id = mapping_entry["image_id"]

                # 防御的チェック: image_id=None検証
                if image_id is None:
                    logger.error(f"pHash {phash[:8]}... のimage_idがNoneです - スキップ")
                    continue

                # 変換
                annotations_dict = self._convert_to_annotations_dict(annotations)

                # DB保存
                self.db_manager.repository.save_annotations(image_id, annotations_dict)
                success_count += 1

            except Exception as e:
                logger.error(f"保存失敗 phash={phash[:8]}...: {e}", exc_info=True)

        logger.info(f"DB保存完了: {success_count}/{len(results)}件成功")

    def _convert_to_annotations_dict(self, annotations: dict[str, Any]) -> "AnnotationsDict":
        """PHashAnnotationResults→AnnotationsDictへ変換

        Args:
            annotations: model_name → UnifiedResult マッピング

        Returns:
            AnnotationsDict: DB保存用の型付き辞書

        Note:
            - TypedDictは schema.py からimport
            - model_id解決は get_model_by_name() 使用（公開API）
            - 正しいキー名: "tag", "caption", "raw_rating_value", "normalized_rating"
        """
        from lorairo.database.schema import AnnotationsDict

        result: AnnotationsDict = {
            "scores": [],
            "tags": [],
            "captions": [],
            "ratings": [],
        }

        for model_name, unified_result in annotations.items():
            if unified_result.error:
                logger.warning(f"モデル {model_name} エラーをスキップ")
                continue

            # 公開API使用
            model = self.db_manager.repository.get_model_by_name(model_name)
            if not model:
                logger.warning(f"モデル '{model_name}' がDB未登録")
                continue

            # Scores
            if unified_result.scores:
                for score_name, score_value in unified_result.scores.items():
                    result["scores"].append({
                        "model_id": model.id,
                        "score": float(score_value),
                        "is_edited_manually": False,
                    })

            # Tags (正しいキー: "tag")
            if unified_result.tags:
                for tag_content in unified_result.tags:
                    result["tags"].append({
                        "model_id": model.id,
                        "tag": tag_content,  # ← schema.py準拠
                        "existing": False,
                        "is_edited_manually": False,
                        "confidence_score": None,
                        "tag_id": None,
                    })

            # Captions (正しいキー: "caption")
            if unified_result.captions:
                for caption_content in unified_result.captions:
                    result["captions"].append({
                        "model_id": model.id,
                        "caption": caption_content,  # ← schema.py準拠
                        "existing": False,
                        "is_edited_manually": False,
                    })

            # Ratings (正しいキー: "raw_rating_value", "normalized_rating")
            if unified_result.ratings:
                rating_value = str(unified_result.ratings)
                result["ratings"].append({
                    "model_id": model.id,
                    "raw_rating_value": rating_value,  # ← schema.py準拠
                    "normalized_rating": rating_value,  # ← schema.py準拠
                    "confidence_score": None,
                })

        return result
