"""アノテーション業務ロジック

Business Logic Layer: アノテーション処理のコアロジック
Qt非依存、AnnotatorLibraryAdapterとDBRepositoryを使用
"""

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from image_annotator_lib import (
        PHashAnnotationResults,
    )


class AnnotationLogic:
    """アノテーション業務ロジック

    アノテーション処理のコアロジックを提供する。
    Qt非依存のため、GUIレイヤーとは独立してテスト・再利用が可能。

    責務:
    - 画像パスからPIL.Image読み込み
    - AnnotatorLibraryAdapter経由でアノテーション実行
    """

    def __init__(
        self,
        annotator_adapter: AnnotatorLibraryAdapter,
    ):
        """AnnotationLogic初期化

        Args:
            annotator_adapter: image-annotator-lib統合アダプター
        """
        self.annotator_adapter = annotator_adapter
        logger.info("AnnotationLogic初期化完了")

    def execute_annotation(
        self,
        image_paths: list[str],
        litellm_model_ids: list[str],
        phash_list: list[str] | None = None,
    ) -> "PHashAnnotationResults":
        """アノテーション実行

        画像パスリストと `litellm_model_id` リストを受け取り、アノテーションを実行する。
        結果はPHashAnnotationResults（pHashをキーとする辞書）として返される。

        Issue #245 / ADR 0023 Phase 1.11: 引数は `Model.litellm_model_id` (registry
        key SSoT)。同 `Model.name` で異なる `provider`/route の行が共存しうるため、
        registry lookup を経由する送信値は必ず `litellm_model_id` を使う。

        Args:
            image_paths: アノテーション対象画像パスリスト
            litellm_model_ids: 使用モデルの `litellm_model_id` リスト
            phash_list: 画像のpHashリスト（省略時はライブラリ側で自動計算）

        Returns:
            PHashAnnotationResults: アノテーション結果（pHashをキーとする辞書）

        Raises:
            FileNotFoundError: 画像ファイルが見つからない場合
            ValueError: 画像読み込みエラー
            Exception: アノテーション実行エラー
        """
        try:
            logger.info(f"アノテーション処理開始: {len(image_paths)}画像, {len(litellm_model_ids)}モデル")
            logger.debug(f"  litellm_model_ids: {litellm_model_ids}")
            logger.debug(f"  pHashリスト指定: {'あり' if phash_list else 'なし（自動計算）'}")

            # 画像読み込み
            images = self._load_images(image_paths)
            logger.debug(f"  画像読み込み完了: {len(images)}枚, サイズ={[img.size for img in images]}")

            # アノテーション実行（AnnotatorLibraryAdapter経由）
            results = self.annotator_adapter.annotate(
                images=images,
                litellm_model_ids=litellm_model_ids,
                phash_list=phash_list,  # NEW: 呼び出し元から渡されたpHashを使用
            )

            logger.info(f"アノテーション処理完了: {len(results)}件の結果")
            logger.debug(f"  結果pHashキー: {list(results.keys())[:5]}{'...' if len(results) > 5 else ''}")
            return results

        except Exception as e:
            error_msg = f"アノテーション処理エラー: {e}"
            logger.error(error_msg, exc_info=True)
            raise

    def _load_images(self, image_paths: list[str]) -> list[Image.Image]:
        """画像パスリストからPIL.Imageリストを作成

        Args:
            image_paths: 画像パスリスト

        Returns:
            list[Image.Image]: PIL.Imageリスト

        Raises:
            FileNotFoundError: 画像ファイルが見つからない場合
            ValueError: 画像読み込みエラー
        """
        images: list[Image.Image] = []

        for path_str in image_paths:
            path = Path(path_str)

            if not path.exists():
                error_msg = f"画像ファイルが見つかりません: {path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            try:
                image = Image.open(path)
                images.append(image)
                logger.debug(f"画像読み込み成功: {path.name}")

            except Exception as e:
                error_msg = f"画像読み込みエラー: {path}, {e}"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg) from e

        logger.debug(f"画像読み込み完了: {len(images)}枚")
        return images
