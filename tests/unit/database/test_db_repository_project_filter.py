"""ISSUE #174: ImageFilterCriteria の project_name/project_id フィールドテスト。"""

import logging
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from lorairo.database.filter_criteria import ImageFilterCriteria


class TestImageFilterCriteriaProjectFields:
    """ImageFilterCriteria のプロジェクトフィールド追加を検証。"""

    def test_construct_with_project_name(self):
        """project_name を指定して ImageFilterCriteria を構築できる。"""
        criteria = ImageFilterCriteria(project_name="my_project")
        assert criteria.project_name == "my_project"

    def test_construct_with_project_id(self):
        """project_id を指定して ImageFilterCriteria を構築できる。"""
        criteria = ImageFilterCriteria(project_id=42)
        assert criteria.project_id == 42

    def test_default_values_are_none(self):
        """デフォルト値は None。"""
        criteria = ImageFilterCriteria()
        assert criteria.project_name is None
        assert criteria.project_id is None

    def test_from_kwargs_with_project_name(self):
        """from_kwargs で project_name を渡せる。"""
        criteria = ImageFilterCriteria.from_kwargs(project_name="foo")
        assert criteria.project_name == "foo"

    def test_from_kwargs_with_project_id(self):
        """from_kwargs で project_id を渡せる。"""
        criteria = ImageFilterCriteria.from_kwargs(project_id=7)
        assert criteria.project_id == 7

    def test_from_kwargs_combined_with_tags(self):
        """project_name と既存フィルタ（tags）を組み合わせて構築できる。"""
        criteria = ImageFilterCriteria.from_kwargs(project_name="foo", tags=["landscape", "anime"])
        assert criteria.project_name == "foo"
        assert criteria.tags == ["landscape", "anime"]

    def test_to_dict_includes_project_fields(self):
        """to_dict() に project_name と project_id が含まれる。"""
        criteria = ImageFilterCriteria(project_name="bar", project_id=99)
        result = criteria.to_dict()
        assert "project_name" in result
        assert result["project_name"] == "bar"
        assert "project_id" in result
        assert result["project_id"] == 99

    def test_to_dict_none_by_default(self):
        """to_dict() のデフォルト値は None。"""
        criteria = ImageFilterCriteria()
        result = criteria.to_dict()
        assert result["project_name"] is None
        assert result["project_id"] is None


class TestApplyProjectFilter:
    """_apply_project_filter() メソッドのテスト。"""

    @pytest.fixture
    def repository(self):
        """テスト用 ImageRepository。"""
        from lorairo.database.db_repository import ImageRepository

        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def test_apply_project_filter_returns_same_query_when_none(self, repository):
        """project_name/project_id ともに None の場合、クエリを変更しない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_project_filter(base_query, None, None)
        assert result == base_query

    def test_apply_project_filter_warns_for_project_name(self, repository, caplog):
        """project_name 指定時に WARNING を出力し、クエリを変更しない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        with caplog.at_level(logging.WARNING, logger="lorairo.database.db_repository"):
            result = repository._apply_project_filter(base_query, "my_project", None)
        assert result == base_query
        assert any("my_project" in msg for msg in caplog.messages)

    def test_apply_project_filter_warns_for_project_id(self, repository, caplog):
        """project_id 指定時に WARNING を出力し、クエリを変更しない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        with caplog.at_level(logging.WARNING, logger="lorairo.database.db_repository"):
            result = repository._apply_project_filter(base_query, None, 42)
        assert result == base_query
        assert any("42" in msg for msg in caplog.messages)

    def test_apply_project_filter_project_id_takes_priority(self, repository, caplog):
        """project_id と project_name が両方指定された場合、project_id の WARNING が出る。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        with caplog.at_level(logging.WARNING, logger="lorairo.database.db_repository"):
            result = repository._apply_project_filter(base_query, "foo", 42)
        assert result == base_query
        assert any("42" in msg for msg in caplog.messages)
