import sys
import time
import types

from lorairo.services.tag_suggestion_service import TagSuggestionService


class TestTagSuggestionService:
    def test_get_suggestions_returns_empty_when_too_short(self):
        service = TagSuggestionService(min_chars=2)

        assert service.get_suggestions("a") == []

    def test_get_suggestions_normalizes_and_deduplicates_results(self, monkeypatch):
        fake_module = types.ModuleType("genai_tag_db_tools")
        fake_module.search_tags = lambda query, limit=None: [
            {"tag": "blue_hair"},
            {"name": "Blue_Hair"},
            {"tag_name": "1girl"},
            "solo",
            {"unknown": "skip"},
        ]
        monkeypatch.setitem(sys.modules, "genai_tag_db_tools", fake_module)

        service = TagSuggestionService(max_suggestions=10)
        result = service.get_suggestions("blue")

        assert result == ["blue_hair", "1girl", "solo"]

    def test_get_suggestions_uses_cache(self, monkeypatch):
        calls = {"count": 0}

        fake_module = types.ModuleType("genai_tag_db_tools")

        def fake_search_tags(query, limit=None):
            calls["count"] += 1
            return ["cached_tag"]

        fake_module.search_tags = fake_search_tags
        monkeypatch.setitem(sys.modules, "genai_tag_db_tools", fake_module)

        service = TagSuggestionService(cache_ttl_seconds=60)

        assert service.get_suggestions("cache") == ["cached_tag"]
        assert service.get_suggestions("cache") == ["cached_tag"]
        assert calls["count"] == 1

    def test_get_suggestions_cache_expires(self, monkeypatch):
        calls = {"count": 0}

        fake_module = types.ModuleType("genai_tag_db_tools")

        def fake_search_tags(query, limit=None):
            calls["count"] += 1
            return [f"tag_{calls['count']}"]

        fake_module.search_tags = fake_search_tags
        monkeypatch.setitem(sys.modules, "genai_tag_db_tools", fake_module)

        service = TagSuggestionService(cache_ttl_seconds=0.01)

        first = service.get_suggestions("expire")
        time.sleep(0.02)
        second = service.get_suggestions("expire")

        assert first == ["tag_1"]
        assert second == ["tag_2"]
        assert calls["count"] == 2
