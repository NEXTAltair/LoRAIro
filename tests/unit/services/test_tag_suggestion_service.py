import sys
import types

from lorairo.services.tag_suggestion_service import TagSuggestionService


class _Item:
    def __init__(self, tag: str):
        self.tag = tag


class _Result:
    def __init__(self, items):
        self.items = items


def test_suggest_tags_uses_cache(monkeypatch):
    calls = {"count": 0}

    def fake_search_tags(_reader, _request):
        calls["count"] += 1
        return _Result([_Item("1girl"), _Item("solo")])

    fake_models = types.SimpleNamespace(TagSearchRequest=lambda **kwargs: kwargs)
    fake_module = types.SimpleNamespace(search_tags=fake_search_tags, models=fake_models)

    monkeypatch.setitem(sys.modules, "genai_tag_db_tools", fake_module)
    monkeypatch.setitem(sys.modules, "genai_tag_db_tools.models", fake_models)

    service = TagSuggestionService(object(), cache_ttl_seconds=60)

    first = service.suggest_tags("gi")
    second = service.suggest_tags("gi")

    assert first == ["1girl", "solo"]
    assert second == ["1girl", "solo"]
    assert calls["count"] == 1


def test_suggest_tags_returns_empty_when_query_short():
    service = TagSuggestionService(object())
    assert service.suggest_tags("a") == []
