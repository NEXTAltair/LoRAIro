from types import SimpleNamespace

from lorairo.services import tag_suggestion_service
from lorairo.services.tag_suggestion_service import TagSuggestionService


class TestTagSuggestionService:
    def test_returns_empty_for_short_query(self):
        service = TagSuggestionService(reader=object(), min_query_length=2)
        assert service.get_suggestions("a") == []

    def test_uses_cache_for_same_query(self, monkeypatch):
        calls = {"count": 0}

        def mock_search_tags(reader, request):
            calls["count"] += 1
            item = SimpleNamespace(tag="blue_hair")
            return SimpleNamespace(items=[item])

        monkeypatch.setattr(tag_suggestion_service, "search_tags", mock_search_tags)

        service = TagSuggestionService(reader=object(), cache_ttl_seconds=300)
        first = service.get_suggestions("blue")
        second = service.get_suggestions("blue")

        assert first == ["blue_hair"]
        assert second == ["blue_hair"]
        assert calls["count"] == 1
