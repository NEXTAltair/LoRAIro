from types import SimpleNamespace
from unittest.mock import Mock, patch

from lorairo.services.tag_suggestion_service import TagSuggestionService


class TestTagSuggestionService:
    def test_get_suggestions_returns_empty_when_short_query(self):
        service = TagSuggestionService(merged_reader=Mock())

        assert service.get_suggestions("a") == []

    def test_get_suggestions_uses_cache(self):
        reader = Mock()
        service = TagSuggestionService(merged_reader=reader)

        result_obj = SimpleNamespace(items=[SimpleNamespace(tag="cat"), SimpleNamespace(tag="catgirl")])
        with patch("lorairo.services.tag_suggestion_service.search_tags", return_value=result_obj) as mock_search:
            first = service.get_suggestions("cat")
            second = service.get_suggestions("cat")

        assert first == ["cat", "catgirl"]
        assert second == ["cat", "catgirl"]
        assert mock_search.call_count == 1

    def test_get_suggestions_returns_empty_when_reader_unavailable(self):
        service = TagSuggestionService(merged_reader=None)

        assert service.get_suggestions("cat") == []
