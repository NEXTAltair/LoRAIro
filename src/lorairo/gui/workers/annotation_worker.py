# src/lorairo/workers/annotation_worker.py

from typing import List

from PIL.Image import Image

from ...utils.log import logger
from .base import LoRAIroWorkerBase


class AnnotationWorker(LoRAIroWorkerBase):
    """AI アノテーション専用ワーカー"""

    def __init__(self, images: list[Image], phash_list: list[str], models: list[str]):
        super().__init__()
        self.images = images
        self.phash_list = phash_list
        self.models = models

    def execute(self):
        """アノテーション処理を実行"""
        logger.info(f"アノテーション開始: {len(self.images)}件, モデル: {self.models}")

        # 前処理進捗
        self._report_progress(
            10,
            "AIアノテーション処理を開始...",
            total_count=len(self.images),
        )

        # キャンセルチェック
        self._check_cancellation()

        # メイン処理進捗
        self._report_progress(
            50,
            f"AIモデル実行中: {', '.join(self.models)}",
            processed_count=0,
            total_count=len(self.images),
        )

        # AIライブラリ呼び出し
        try:
            from image_annotator_lib import annotate

            results = annotate(self.images, self.models, self.phash_list)

            # 完了進捗
            self._report_progress(
                100,
                "アノテーション処理が完了しました",
                processed_count=len(self.images),
                total_count=len(self.images),
            )

            logger.info(f"アノテーション完了: {len(self.images)}件処理")
            return results

        except Exception as e:
            logger.error(f"アノテーション処理エラー: {e}")
            raise
