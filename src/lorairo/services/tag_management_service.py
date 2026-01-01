"""タグ管理サービスモジュール。

unknown typeタグの検索、type_name選択、一括更新を担当します。
"""

from genai_tag_db_tools import (
    get_all_type_names,
    get_format_type_names,
    get_unknown_type_tags,
    update_tags_type_batch,
)
from genai_tag_db_tools.db.repository import get_default_reader, get_default_repository
from genai_tag_db_tools.models import TagRecordPublic, TagTypeUpdate

from ..utils.log import logger


class TagManagementService:
    """LoRAIro format (format_id=1000) のタグ管理サービス。

    genai-tag-db-tools の公開APIを使用して、unknown typeタグの検索、
    type_name一覧取得、一括type更新を提供します。
    """

    LORAIRO_FORMAT_ID = 1000  # LoRAIro専用format_id（ユーザーDB範囲: 1000-）

    def __init__(self) -> None:
        """TagManagementServiceを初期化します。"""
        self.reader = get_default_reader()
        self.repository = get_default_repository()
        logger.info("TagManagementService initialized with format_id=%d", self.LORAIRO_FORMAT_ID)

    def get_unknown_tags(self) -> list[TagRecordPublic]:
        """unknown typeタグ一覧を取得します。

        Returns:
            list[TagRecordPublic]: type_name="unknown"のタグリスト

        Raises:
            Exception: タグ検索中にエラーが発生した場合
        """
        try:
            tags = get_unknown_type_tags(self.reader, format_id=self.LORAIRO_FORMAT_ID)
            logger.info("Found %d unknown type tags for format_id=%d", len(tags), self.LORAIRO_FORMAT_ID)
            return tags
        except Exception as e:
            logger.error("Error getting unknown type tags: %s", e, exc_info=True)
            raise

    def get_all_available_types(self) -> list[str]:
        """利用可能な全type_nameを取得します。

        Returns:
            list[str]: すべてのtype_name一覧（例: ["character", "general", "meta", "unknown"]）

        Raises:
            Exception: type_name一覧取得中にエラーが発生した場合
        """
        try:
            types = get_all_type_names(self.reader)
            logger.debug("Retrieved %d type names", len(types))
            return types
        except Exception as e:
            logger.error("Error getting all type names: %s", e, exc_info=True)
            raise

    def get_format_specific_types(self) -> list[str]:
        """LoRAIro format固有のtype_nameを取得します。

        Returns:
            list[str]: format_id=1000で使用中のtype_name一覧

        Raises:
            Exception: format固有type_name取得中にエラーが発生した場合
        """
        try:
            types = get_format_type_names(self.reader, format_id=self.LORAIRO_FORMAT_ID)
            logger.debug(
                "Retrieved %d format-specific type names for format_id=%d",
                len(types),
                self.LORAIRO_FORMAT_ID,
            )
            return types
        except Exception as e:
            logger.error("Error getting format-specific type names: %s", e, exc_info=True)
            raise

    def update_tag_types(self, updates: list[TagTypeUpdate]) -> None:
        """タグのtypeを一括更新します。

        Args:
            updates (list[TagTypeUpdate]): 更新するタグとtype_nameのリスト

        Raises:
            ValueError: 無効なformat_idまたはtag_idが指定された場合
            Exception: 更新処理中にエラーが発生した場合
        """
        if not updates:
            logger.warning("No tag updates provided")
            return

        try:
            update_tags_type_batch(self.repository, updates, format_id=self.LORAIRO_FORMAT_ID)
            logger.info(
                "Successfully updated %d tags for format_id=%d", len(updates), self.LORAIRO_FORMAT_ID
            )
        except ValueError as e:
            logger.error("Invalid tag update request: %s", e)
            raise
        except Exception as e:
            logger.error("Error updating tag types: %s", e, exc_info=True)
            raise

    def update_single_tag_type(self, tag_id: int, type_name: str) -> None:
        """単一タグのtypeを更新します。

        Args:
            tag_id (int): 更新するタグのID
            type_name (str): 新しいtype_name

        Raises:
            ValueError: 無効なtag_idまたはtype_nameが指定された場合
            Exception: 更新処理中にエラーが発生した場合
        """
        update = TagTypeUpdate(tag_id=tag_id, type_name=type_name)
        self.update_tag_types([update])
