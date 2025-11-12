"""データ変換サービス

画像メタデータをUI表示用データに変換する責務を担う。
MainWindow._resolve_optimal_thumbnail_data()から抽出（Phase 2.4 Stage 1）。
"""

from pathlib import Path
from typing import Any

from loguru import logger

from lorairo.database.db_core import resolve_stored_path
from lorairo.database.db_manager import ImageDatabaseManager


class DataTransformService:
    """データ変換サービス

    画像メタデータからUI表示用データへの変換を担当。
    MainWindowから分離し、データ変換ロジックを集約。

    Phase 2.4 Stage 1で作成。
    """

    def __init__(self, db_manager: ImageDatabaseManager | None = None):
        """初期化

        Args:
            db_manager: データベースマネージャー
        """
        self.db_manager = db_manager

    def resolve_optimal_thumbnail_paths(
        self, image_metadata: list[dict[str, Any]]
    ) -> list[tuple[Path, int]]:
        """画像メタデータから最適なサムネイル表示用パスを解決

        512px処理済み画像が利用可能な場合はそれを使用し、
        利用不可能な場合は元画像にフォールバックする。

        Args:
            image_metadata: 画像メタデータリスト
                各要素は {"id": int, "stored_image_path": str, ...} を含む

        Returns:
            list[tuple[Path, int]]: (画像パス, 画像ID) のタプルリスト
        """
        if not image_metadata:
            return []

        result = []

        for metadata in image_metadata:
            image_id = metadata["id"]
            original_path = metadata["stored_image_path"]

            try:
                # 512px処理済み画像の存在を確認
                if self.db_manager:
                    processed_image = self.db_manager.check_processed_image_exists(image_id, 512)

                    if processed_image:
                        # 512px画像のパス解決
                        resolved_path = resolve_stored_path(processed_image["stored_image_path"])

                        # ファイル存在確認
                        if resolved_path.exists():
                            result.append((resolved_path, image_id))
                            continue

                # フォールバック: 元画像を使用
                result.append((Path(original_path), image_id))

            except Exception as e:
                # エラー時もフォールバック: 元画像を使用
                logger.warning(f"パス解決エラー (image_id={image_id}): {e}")
                result.append((Path(original_path), image_id))

        return result
