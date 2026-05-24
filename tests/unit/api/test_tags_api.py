"""タグ管理API テスト。

lorairo.api.tags モジュールのユニットテスト。
ServiceContainer を通じた TagManagementService のラッパー関数を検証する。
"""

from unittest.mock import MagicMock, patch

import pytest

from lorairo.api.tags import get_available_types, get_unknown_tags
from lorairo.api.types import TagInfo


@pytest.mark.unit
class TestGetUnknownTags:
    """get_unknown_tags() のユニットテスト。"""

    def test_returns_empty_list_when_no_unknown_tags(self) -> None:
        """unknown タグがない場合は空リストを返す。"""
        mock_service = MagicMock()
        mock_service.get_unknown_tags.return_value = []

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_unknown_tags()

        assert result == []
        mock_service.get_unknown_tags.assert_called_once()

    def test_returns_tag_info_list_from_service(self) -> None:
        """サービスが返すタグレコードを TagInfo リストに変換して返す。"""
        mock_tag_1 = MagicMock()
        mock_tag_1.name = "artist"
        mock_tag_2 = MagicMock()
        mock_tag_2.name = "style"

        mock_service = MagicMock()
        mock_service.get_unknown_tags.return_value = [mock_tag_1, mock_tag_2]

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_unknown_tags()

        assert len(result) == 2
        assert all(isinstance(tag, TagInfo) for tag in result)
        assert result[0].name == "artist"
        assert result[0].type_name == "unknown"
        assert result[0].count == 0
        assert result[1].name == "style"
        assert result[1].type_name == "unknown"
        assert result[1].count == 0

    def test_each_tag_has_type_name_unknown(self) -> None:
        """返される TagInfo の type_name はすべて 'unknown'。"""
        mock_tag = MagicMock()
        mock_tag.name = "some_tag"

        mock_service = MagicMock()
        mock_service.get_unknown_tags.return_value = [mock_tag]

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_unknown_tags()

        assert result[0].type_name == "unknown"
        assert result[0].count == 0

    def test_each_tag_has_zero_count(self) -> None:
        """返される TagInfo の count は常に 0。"""
        mock_tag = MagicMock()
        mock_tag.name = "character_tag"

        mock_service = MagicMock()
        mock_service.get_unknown_tags.return_value = [mock_tag]

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_unknown_tags()

        assert result[0].count == 0

    def test_uses_service_container_for_service_lookup(self) -> None:
        """ServiceContainer を経由してサービスを取得する。"""
        mock_service = MagicMock()
        mock_service.get_unknown_tags.return_value = []

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_instance = mock_container_cls.return_value
            mock_instance.tag_management_service = mock_service
            get_unknown_tags()

        mock_container_cls.assert_called_once()


@pytest.mark.unit
class TestGetAvailableTypes:
    """get_available_types() のユニットテスト。"""

    def test_returns_list_of_type_names(self) -> None:
        """利用可能なタグ種類のリストを返す。"""
        expected_types = ["character", "copyright", "artist", "general", "unknown"]

        mock_service = MagicMock()
        mock_service.get_all_available_types.return_value = expected_types

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_available_types()

        assert result == expected_types
        mock_service.get_all_available_types.assert_called_once()

    def test_returns_empty_list_when_no_types(self) -> None:
        """利用可能なタグ種類がない場合は空リストを返す。"""
        mock_service = MagicMock()
        mock_service.get_all_available_types.return_value = []

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_available_types()

        assert result == []

    def test_delegates_to_tag_management_service(self) -> None:
        """TagManagementService.get_all_available_types() に委譲する。"""
        mock_service = MagicMock()
        mock_service.get_all_available_types.return_value = ["general"]

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            get_available_types()

        mock_service.get_all_available_types.assert_called_once()

    def test_returns_single_type(self) -> None:
        """単一種類のリストを正しく返す。"""
        mock_service = MagicMock()
        mock_service.get_all_available_types.return_value = ["general"]

        with patch("lorairo.api.tags.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.tag_management_service = mock_service
            result = get_available_types()

        assert len(result) == 1
        assert result[0] == "general"
