"""Annotation Worker - 層分離リファクタリング版

GUI Layer: 非同期処理とQt進捗管理のみ担当
ビジネスロジックはAnnotationLogicに委譲
"""

import traceback
from typing import TYPE_CHECKING

from image_annotator_lib import PHashAnnotationResults

from lorairo.annotations.annotation_logic import AnnotationLogic
from lorairo.utils.log import logger

from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


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
            # 前処理進捗
            self._report_progress(10, "アノテーション処理を開始...", total_count=len(self.image_paths))
            self._check_cancellation()

            # モデル単位で処理（進捗・キャンセル対応）
            merged_results: PHashAnnotationResults = {}
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

                # AnnotationLogic経由でアノテーション実行
                try:
                    model_results = self.annotation_logic.execute_annotation(
                        image_paths=self.image_paths,
                        model_names=[model_name],
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
            # 全体エラーでも各画像に対してエラーレコードを作成
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
                        logger.error(
                            f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}"
                        )

            raise
