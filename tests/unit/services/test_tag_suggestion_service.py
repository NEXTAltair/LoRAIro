# tests/unit/services/test_tag_suggestion_service.py
# TagSuggestionService のユニットテスト。
# genai_tag_db_tools は sys.modules モック経由で注入する。

import sys
import types

import pytest

from lorairo.services.tag_suggestion_service import TagSuggestionService


class _FakeItem:
    """TagRecordPublic の簡易モック。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.source_tag = None
        self.name = None


class _FakeResult:
    """TagSearchResult の簡易モック。"""

    def __init__(self, items: list) -> None:
        self.items = items


def _make_fake_genai(items: list, call_counter: dict | None = None) -> tuple:
    """genai_tag_db_tools のモジュールモックと呼び出しカウンターを返す。"""

    def fake_search_tags(_reader, _request):
        if call_counter is not None:
            call_counter["count"] = call_counter.get("count", 0) + 1
        return _FakeResult(items)

    fake_models = types.SimpleNamespace(TagSearchRequest=lambda **kwargs: kwargs)
    fake_module = types.SimpleNamespace(search_tags=fake_search_tags)
    return fake_module, fake_models


@pytest.fixture()
def patch_genai(monkeypatch):
    """genai_tag_db_tools をモジュールレベルでモックするフィクスチャ。"""

    def _patch(items: list, call_counter: dict | None = None):
        fake_module, fake_models = _make_fake_genai(items, call_counter)
        monkeypatch.setitem(sys.modules, "genai_tag_db_tools", fake_module)
        monkeypatch.setitem(sys.modules, "genai_tag_db_tools.models", fake_models)

    return _patch


class TestTagSuggestionServiceCache:
    """キャッシュ動作のテスト。"""

    def test_same_query_uses_cache(self, patch_genai):
        """同一クエリに対してキャッシュが使用され、DB 呼び出しが1回のみ実行される。"""
        counter: dict = {}
        patch_genai([_FakeItem("1girl"), _FakeItem("solo")], counter)

        service = TagSuggestionService(object(), cache_ttl_seconds=60)
        first = service.get_suggestions("gi")
        second = service.get_suggestions("gi")

        assert first == ["1girl", "solo"]
        assert second == ["1girl", "solo"]
        assert counter["count"] == 1

    def test_clear_cache_forces_re_query(self, patch_genai):
        """clear_cache() 後は再度 DB クエリが実行される。"""
        counter: dict = {}
        patch_genai([_FakeItem("1girl")], counter)

        service = TagSuggestionService(object(), cache_ttl_seconds=60)
        service.get_suggestions("gi")
        service.clear_cache()
        service.get_suggestions("gi")

        assert counter["count"] == 2

    def test_lru_eviction(self, patch_genai):
        """キャッシュサイズを超えると古いエントリが削除される。"""
        patch_genai([_FakeItem("tag")])

        service = TagSuggestionService(object(), cache_size=2, cache_ttl_seconds=60)
        service.get_suggestions("aa")
        service.get_suggestions("bb")
        service.get_suggestions("cc")  # aa が LRU で削除される

        assert "aa" not in service._cache
        assert "bb" in service._cache
        assert "cc" in service._cache


class TestTagSuggestionServiceMinChars:
    """最小文字数チェックのテスト。"""

    def test_short_query_returns_empty(self):
        """min_chars 未満のクエリは空リストを返す。"""
        service = TagSuggestionService(object())
        assert service.get_suggestions("a") == []
        assert service.get_suggestions("") == []

    def test_query_at_min_chars_triggers_search(self, patch_genai):
        """min_chars 以上のクエリはDB 検索を実行する。"""
        patch_genai([_FakeItem("girl")])

        service = TagSuggestionService(object(), min_chars=2)
        result = service.get_suggestions("gi")

        assert result == ["girl"]


class TestTagSuggestionServiceNoReader:
    """merged_reader が None の場合のテスト。"""

    def test_returns_empty_when_reader_is_none(self):
        """merged_reader が None の場合は空リストを返す。"""
        service = TagSuggestionService(None)
        assert service.get_suggestions("girl") == []


class TestTagSuggestionServiceMaxResults:
    """最大件数制限のテスト。"""

    def test_max_results_limit(self, patch_genai):
        """max_results を超える結果は切り捨てられる。"""
        items = [_FakeItem(f"tag_{i}") for i in range(50)]
        patch_genai(items)

        service = TagSuggestionService(object(), max_results=5)
        result = service.get_suggestions("tag")

        assert len(result) == 5

    def test_duplicate_tags_are_deduplicated(self, patch_genai):
        """重複するタグ名は1件にまとめられる。"""
        patch_genai([_FakeItem("1girl"), _FakeItem("1girl"), _FakeItem("solo")])

        service = TagSuggestionService(object())
        result = service.get_suggestions("gi")

        assert result.count("1girl") == 1


class TestExtractTagName:
    """_extract_tag_name の各フォーマット対応テスト。"""

    def test_extracts_tag_from_object(self):
        item = _FakeItem("blue_hair")
        assert TagSuggestionService._extract_tag_name(item) == "blue_hair"

    def test_extracts_tag_from_dict(self):
        item = {"tag": "red_eyes", "name": "other"}
        assert TagSuggestionService._extract_tag_name(item) == "red_eyes"

    def test_extracts_tag_from_string(self):
        assert TagSuggestionService._extract_tag_name("smile") == "smile"

    def test_returns_none_for_empty_tag(self):
        item = _FakeItem("")
        item.tag = ""
        assert TagSuggestionService._extract_tag_name(item) is None
