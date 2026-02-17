"""タグ管理API。

TagManagementService をラップし、タグ検索・登録機能を提供。
"""

from lorairo.api.exceptions import TagNotFoundError, TagRegistrationError
from lorairo.api.types import TagInfo, TagSearchResult
from lorairo.services.service_container import ServiceContainer


def get_unknown_tags() -> list[TagInfo]:
    """Unknown type タグを取得。

    Returns:
        list[TagInfo]: タグ情報のリスト。

    使用例:
        >>> from lorairo.api import get_unknown_tags
        >>>
        >>> tags = get_unknown_tags()
        >>> print(f"Unknown タグ: {len(tags)}件")
    """
    container = ServiceContainer()
    service = container.tag_management_service

    tag_records = service.get_unknown_tags()

    return [
        TagInfo(
            name=tag.name,
            type_name="unknown",
            count=0,
        )
        for tag in tag_records
    ]


def get_available_types() -> list[str]:
    """利用可能なタグ種類を取得。

    Returns:
        list[str]: タグ種類のリスト。
    """
    container = ServiceContainer()
    service = container.tag_management_service

    return service.get_all_available_types()
