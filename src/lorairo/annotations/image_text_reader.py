"""画像ファイルに紐づくテキストファイル (.txt, .caption) からタグやキャプションを読み込むモジュール。"""

from pathlib import Path

# 相対インポートのパスを修正 (.. -> ..)
from ..database.db_manager import ImageDatabaseManager
from ..storage.file_system import FileSystemManager  # ファイルベースも考慮する場合
from ..utils.log import logger


# クラス名を AnnotationService から ImageTextFileReader に変更
class ImageTextFileReader:
    """画像に関連するテキストファイル (.txt, .caption) やDBからアノテーションを読み込む。"""

    # __init__ の docstring もクラス名に合わせて更新
    def __init__(self, idm: ImageDatabaseManager, fsm: FileSystemManager | None = None):
        """ImageTextFileReader を初期化します。

        Args:
            idm: イメージデータベースマネージャー (DBからの読み込みに必要)。
            fsm: ファイルシステムマネージャー (オプション、ファイルからの読み込み用、現状未実装)。
        """
        self.idm = idm
        self.fsm = fsm  # 現状未使用だが保持

    # メソッド名は一旦そのまま
    def get_annotations_for_display(self, image_path: Path) -> dict[str, list[str]] | None:
        """指定された画像パスに対応するアノテーションをDBから取得し、表示用に整形します。
           ファイルベース (.txt/.json) のアノテーション取得は未実装。

        Args:
            image_path: アノテーションを取得する画像のパス。

        Returns:
            dict[str, list[str]] | None: {'tags': [...], 'captions': [...]} 形式の辞書、
                                         またはアノテーションが見つからない場合は None。
        """
        logger.debug(f"Getting annotations for display: {image_path.name}")
        try:
            # まずDBで画像IDを検索
            image_id = self.idm.detect_duplicate_image(image_path)

            if image_id is not None:
                # DBからアノテーションを取得
                db_annotations = self.idm.get_image_annotations(image_id)
                if db_annotations:
                    tags = [tag_data.get("tag", "") for tag_data in db_annotations.get("tags", [])]
                    captions = [
                        cap_data.get("caption", "") for cap_data in db_annotations.get("captions", [])
                    ]
                    # 空文字を除去
                    tags = [tag for tag in tags if tag]
                    captions = [caption for caption in captions if caption]
                    logger.debug(
                        f"Found annotations in DB for {image_path.name}: Tags={len(tags)}, Captions={len(captions)}"
                    )
                    return {"tags": tags, "captions": captions}
                else:
                    logger.debug(f"No annotations found in DB for {image_path.name} (ID: {image_id})")
                    return {"tags": [], "captions": []}  # DBには存在するがアノテーションなし
            else:
                # TODO: ファイルベースのアノテーション (.txt/.json) を探す処理を追加する場合
                # logger.debug(f"Image not found in DB: {image_path.name}. Checking for file annotations...")
                # file_annotations = self._get_annotations_from_file(image_path)
                # if file_annotations:
                #     return file_annotations
                logger.debug(f"Image not found in DB and file checking not implemented: {image_path.name}")
                return None  # DBにもファイルにも見つからない

        except Exception as e:
            logger.error(f"Error getting annotations for {image_path.name}: {e}", exc_info=True)
            return None  # エラー発生時

    # --- ファイルベースのアノテーション取得 ---
    # src/lorairo/annotations/existing_file_reader.py に定義
