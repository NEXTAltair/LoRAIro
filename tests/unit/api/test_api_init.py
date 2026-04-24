"""lorairo.api.__init__ の遅延ロードテスト。"""

import pytest

import lorairo.api as api


class TestApiLazyLoad:
    """api.__getattr__ による遅延ロードのテスト。"""

    def test_create_project_is_callable(self):
        """create_project はモジュール属性として取得できる。"""
        func = api.create_project
        assert callable(func)

    def test_list_projects_is_callable(self):
        """list_projects はモジュール属性として取得できる。"""
        func = api.list_projects
        assert callable(func)

    def test_unknown_attribute_raises_attribute_error(self):
        """存在しない属性アクセスはAttributeErrorを送出する。"""
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = api.nonexistent_function_xyz
