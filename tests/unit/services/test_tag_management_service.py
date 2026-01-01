"""TagManagementService の単体テスト"""

from unittest.mock import Mock, patch

import pytest
from genai_tag_db_tools.models import TagRecordPublic, TagTypeUpdate

from lorairo.services.tag_management_service import TagManagementService


@pytest.mark.unit
class TestTagManagementService:
    """TagManagementService のテストクラス"""

    @pytest.fixture
    def service(self) -> TagManagementService:
        """TagManagementService インスタンスを提供"""
        with patch("lorairo.services.tag_management_service.get_default_reader"):
            with patch("lorairo.services.tag_management_service.get_default_repository"):
                return TagManagementService()

    def test_lorairo_format_id_constant(self, service: TagManagementService) -> None:
        """LoRAIro format_id が 1000 であることを確認"""
        assert service.LORAIRO_FORMAT_ID == 1000

    def test_get_unknown_tags_success(self, service: TagManagementService) -> None:
        """unknown typeタグ取得成功"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag1",
                tag_id=1,
                source_tag="test_tag1",
                type_name="unknown",
                format_name="Lorairo",
            ),
            TagRecordPublic(
                tag="test_tag2",
                tag_id=2,
                source_tag="test_tag2",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]

        with patch("lorairo.services.tag_management_service.get_unknown_type_tags", return_value=mock_tags):
            result = service.get_unknown_tags()

            assert len(result) == 2
            assert result[0].tag_id == 1
            assert result[1].tag_id == 2
            assert all(tag.type_name == "unknown" for tag in result)

    def test_get_unknown_tags_empty(self, service: TagManagementService) -> None:
        """unknown typeタグが存在しない場合"""
        with patch("lorairo.services.tag_management_service.get_unknown_type_tags", return_value=[]):
            result = service.get_unknown_tags()
            assert result == []

    def test_get_unknown_tags_error(self, service: TagManagementService) -> None:
        """unknown typeタグ取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_unknown_type_tags",
            side_effect=Exception("DB error"),
        ):
            with pytest.raises(Exception, match="DB error"):
                service.get_unknown_tags()

    def test_get_all_available_types_success(self, service: TagManagementService) -> None:
        """全type_name取得成功"""
        mock_types = ["character", "general", "meta", "unknown"]

        with patch("lorairo.services.tag_management_service.get_all_type_names", return_value=mock_types):
            result = service.get_all_available_types()

            assert result == mock_types
            assert "unknown" in result
            assert "character" in result

    def test_get_all_available_types_error(self, service: TagManagementService) -> None:
        """全type_name取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_all_type_names",
            side_effect=Exception("API error"),
        ):
            with pytest.raises(Exception, match="API error"):
                service.get_all_available_types()

    def test_get_format_specific_types_success(self, service: TagManagementService) -> None:
        """format固有type_name取得成功"""
        mock_types = ["unknown", "character", "general"]

        with patch(
            "lorairo.services.tag_management_service.get_format_type_names", return_value=mock_types
        ):
            result = service.get_format_specific_types()

            assert result == mock_types
            assert len(result) == 3

    def test_get_format_specific_types_error(self, service: TagManagementService) -> None:
        """format固有type_name取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            side_effect=Exception("Format error"),
        ):
            with pytest.raises(Exception, match="Format error"):
                service.get_format_specific_types()

    def test_update_tag_types_success(self, service: TagManagementService) -> None:
        """タグtype一括更新成功"""
        updates = [
            TagTypeUpdate(tag_id=1, type_name="character"),
            TagTypeUpdate(tag_id=2, type_name="general"),
        ]

        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_tag_types(updates)

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][1] == updates  # updates リスト
            assert call_args[1]["format_id"] == 1000  # format_id

    def test_update_tag_types_empty_list(self, service: TagManagementService) -> None:
        """空のupdatesリストの処理"""
        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_tag_types([])

            # 空リストの場合は API 呼び出ししない
            mock_update.assert_not_called()

    def test_update_tag_types_value_error(self, service: TagManagementService) -> None:
        """無効なupdatesでValueError"""
        updates = [TagTypeUpdate(tag_id=999, type_name="invalid")]

        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=ValueError("Invalid format_id"),
        ):
            with pytest.raises(ValueError, match="Invalid format_id"):
                service.update_tag_types(updates)

    def test_update_tag_types_error(self, service: TagManagementService) -> None:
        """タグtype更新時のエラーハンドリング"""
        updates = [TagTypeUpdate(tag_id=1, type_name="character")]

        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=Exception("Update error"),
        ):
            with pytest.raises(Exception, match="Update error"):
                service.update_tag_types(updates)

    def test_update_single_tag_type_success(self, service: TagManagementService) -> None:
        """単一タグtype更新成功"""
        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_single_tag_type(tag_id=1, type_name="character")

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            updates = call_args[0][1]
            assert len(updates) == 1
            assert updates[0].tag_id == 1
            assert updates[0].type_name == "character"
            assert call_args[1]["format_id"] == 1000

    def test_update_single_tag_type_error(self, service: TagManagementService) -> None:
        """単一タグtype更新時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=ValueError("Invalid tag_id"),
        ):
            with pytest.raises(ValueError, match="Invalid tag_id"):
                service.update_single_tag_type(tag_id=999, type_name="invalid")
