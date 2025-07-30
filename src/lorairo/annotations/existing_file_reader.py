"""既存の画像ファイルに対応する .txt/.caption ファイルからアノテーションを読み込むモジュール。"""

from pathlib import Path
from typing import Any

from genai_tag_db_tools.utils.cleanup_str import TagCleaner

from lorairo.utils.log import logger


class ExistingFileReader:
    """画像に関連する既存のテキストファイル (.txt, .caption) からアノテーションを読み込む。"""

    def __init__(self) -> None:
        """ExistingFileReader を初期化します。"""
        self.tag_cleaner = TagCleaner()

    def get_existing_annotations(self, image_path: Path) -> dict[str, Any] | None:
        """
        画像の参照元ディレクトリから既存のタグとキャプションを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Optional[dict[str, Any]]: 'tags', 'captions', 'image_path' をキーとする辞書。
            None : 既存のアノテーションが見つからない場合

        例:
        {
            'tags': ['tag1', 'tag2'],
            'captions': ['caption1'],
            'image_path': str(image_path)
        }
        """
        existing_annotations = {
            "tags": [],
            "captions": [],
            "image_path": str(image_path),
        }

        tag_path = image_path.with_suffix(".txt")
        caption_path = image_path.with_suffix(".caption")

        try:
            if tag_path.exists():
                tags = self._read_annotations(tag_path)
                existing_annotations["tags"] = tags

            if caption_path.exists():
                captions = self._read_captions(caption_path)
                existing_annotations["captions"] = captions

            # Return result even if empty, since files exist
            if not tag_path.exists() and not caption_path.exists():
                logger.info(f"既存アノテーション無し: {image_path}")
                return None

        except Exception as e:
            logger.error(f"アノテーションファイルの読み込み中にエラーが発生しました: {e}")
            return None

        return existing_annotations

    def _read_annotations(self, file_path: Path) -> list[str]:
        """
        指定されたファイルからアノテーションを読み込みカンマで分割してリストとして返す。

        Args:
            file_path (Path): 読み込むファイルのパス

        Returns:
            list[str]: アノテーションのリスト
        """
        with open(file_path, encoding="utf-8") as f:
            clean_data = self.tag_cleaner.clean_format(f.read())
            items = clean_data.strip().split(",")
            # 空文字列を除去
            return [item.strip() for item in items if item.strip()]

    def _read_captions(self, file_path: Path) -> list[str]:
        """
        指定されたファイルからキャプションを読み込む。

        Args:
            file_path (Path): 読み込むファイルのパス

        Returns:
            list[str]: キャプションのリスト
        """
        with open(file_path, encoding="utf-8") as f:
            clean_data = self.tag_cleaner.clean_format(f.read())
            if clean_data.strip():
                return [clean_data.strip()]
            return []

    def has_existing_files(self, image_path: Path) -> bool:
        """
        指定された画像に対応する .txt または .caption ファイルが存在するかチェック。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            bool: いずれかのファイルが存在する場合 True
        """
        tag_path = image_path.with_suffix(".txt")
        caption_path = image_path.with_suffix(".caption")
        return tag_path.exists() or caption_path.exists()

    def get_tag_file_path(self, image_path: Path) -> Path:
        """
        画像に対応する .txt ファイルのパスを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Path: .txt ファイルのパス
        """
        return image_path.with_suffix(".txt")

    def get_caption_file_path(self, image_path: Path) -> Path:
        """
        画像に対応する .caption ファイルのパスを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Path: .caption ファイルのパス
        """
        return image_path.with_suffix(".caption")
