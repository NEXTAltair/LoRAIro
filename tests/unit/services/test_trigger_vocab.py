"""TriggerVocabService の unit テスト（Issue #946）。

genai-tag-db-tools の public API（register_tag / search_tags /
get_user_tag_reader / create_tag_register_service）をモックし、
TriggerVocabService が正しい request を組み立て、検索結果を VocabEntry へ
マッピングし、graceful degradation することを検証する。

実ユーザー DB を使う round-trip / USER_TAGS 隔離の検証は
tests/integration/services/test_trigger_vocab_integration.py を参照。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import TagRecordPublic, TagRegisterRequest, TagSearchRequest, TagSearchResult

from lorairo.services.trigger_vocab import (
    _TRIGGER_FORMAT,
    TriggerVocabService,
    VocabEntry,
)

pytestmark = pytest.mark.unit


def _record(tag: str, *, source_tag: str | None = None, usage_count: int | None = None) -> TagRecordPublic:
    """テスト用 TagRecordPublic を生成するヘルパー。"""
    return TagRecordPublic(
        tag=tag,
        source_tag=source_tag,
        tag_id=1_000_000_001,
        format_name=_TRIGGER_FORMAT,
        type_name="unknown",
        usage_count=usage_count,
    )


# ------------------------------------------------------------------
# search
# ------------------------------------------------------------------


class TestSearch:
    """search() の request 組み立て・結果マッピング・ソートテスト。"""

    def test_search_builds_user_trigger_request(self, monkeypatch) -> None:
        """search が trigger format 限定・partial=True の request を投げること。"""
        captured: dict[str, TagSearchRequest] = {}

        def fake_search(reader, request: TagSearchRequest) -> TagSearchResult:
            captured["request"] = request
            return TagSearchResult(items=[], total=0)

        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", fake_search)
        service = TriggerVocabService(reader=object())

        service.search("mag")

        req = captured["request"]
        assert req.query == "mag"
        assert req.partial is True
        assert req.format_names == [_TRIGGER_FORMAT]
        assert req.include_aliases is False
        assert req.include_deprecated is False

    def test_search_maps_source_tag_and_usage_count(self, monkeypatch) -> None:
        """word は source_tag(リテラル)優先、freq は usage_count にマップされること。"""
        result = TagSearchResult(
            items=[_record("magic girl", source_tag="魔法少女", usage_count=5)],
            total=1,
        )
        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", lambda reader, request: result)
        service = TriggerVocabService(reader=object())

        entries = service.search("魔")

        assert entries == [VocabEntry(word="魔法少女", freq=5)]

    def test_search_falls_back_to_tag_when_no_source_tag(self, monkeypatch) -> None:
        """source_tag が無い場合は正規化形 tag を word に使うこと。"""
        result = TagSearchResult(items=[_record("smile", source_tag=None, usage_count=None)], total=1)
        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", lambda reader, request: result)
        service = TriggerVocabService(reader=object())

        entries = service.search("sm")

        assert entries == [VocabEntry(word="smile", freq=0)]

    def test_search_sorts_by_freq_desc_then_word_asc(self, monkeypatch) -> None:
        """freq 降順・同数は word 昇順でソートされること。"""
        result = TagSearchResult(
            items=[
                _record("alpha", usage_count=1),
                _record("zeta", usage_count=9),
                _record("beta", usage_count=9),
            ],
            total=3,
        )
        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", lambda reader, request: result)
        service = TriggerVocabService(reader=object())

        words = [e.word for e in service.search("")]

        assert words == ["beta", "zeta", "alpha"]

    def test_search_dedups_word_first_wins(self, monkeypatch) -> None:
        """同一 word の重複は初出優先で1件に畳まれること。"""
        result = TagSearchResult(
            items=[_record("dup", usage_count=3), _record("dup", usage_count=1)],
            total=2,
        )
        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", lambda reader, request: result)
        service = TriggerVocabService(reader=object())

        entries = service.search("d")

        assert entries == [VocabEntry(word="dup", freq=3)]

    def test_search_normalizes_query(self, monkeypatch) -> None:
        """検索クエリがアンダースコア除去・空白整形で正規化されること。"""
        captured: dict[str, TagSearchRequest] = {}

        def fake_search(reader, request: TagSearchRequest) -> TagSearchResult:
            captured["request"] = request
            return TagSearchResult(items=[], total=0)

        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", fake_search)
        service = TriggerVocabService(reader=object())

        service.search("  long_hair  ")

        assert captured["request"].query == "long hair"

    def test_search_returns_empty_when_reader_unavailable(self, monkeypatch) -> None:
        """reader 初期化失敗時は空リストを返すこと（graceful degradation）。"""

        def raise_runtime() -> object:
            raise RuntimeError("user DB not initialized")

        monkeypatch.setattr("lorairo.services.trigger_vocab.get_user_tag_reader", raise_runtime)
        service = TriggerVocabService()

        assert service.search("x") == []

    def test_search_returns_empty_on_search_error(self, monkeypatch) -> None:
        """検索が例外を投げても空リストで継続すること。"""

        def raise_value(reader, request) -> TagSearchResult:
            raise ValueError("bad query")

        monkeypatch.setattr("lorairo.services.trigger_vocab.search_tags", raise_value)
        service = TriggerVocabService(reader=object())

        assert service.search("x") == []


# ------------------------------------------------------------------
# register
# ------------------------------------------------------------------


class TestRegister:
    """register() の request 組み立て・正規化・graceful degradation テスト。"""

    def test_register_builds_user_scope_request(self, monkeypatch) -> None:
        """register が scope=user・専用 format でリテラルと正規化形を渡すこと。"""
        captured: dict[str, TagRegisterRequest] = {}

        def fake_register(service, request: TagRegisterRequest):
            captured["request"] = request
            return type("R", (), {"created": True, "tag_id": 1_000_000_001})()

        monkeypatch.setattr("lorairo.services.trigger_vocab.register_tag", fake_register)
        service = TriggerVocabService(register_service=object())

        service.register("魔法少女")

        req = captured["request"]
        assert req.tag == "魔法少女"
        assert req.source_tag == "魔法少女"
        assert req.format_name == _TRIGGER_FORMAT
        assert req.scope == "user"

    def test_register_normalizes_tag_keeps_literal_source(self, monkeypatch) -> None:
        """tag は正規化形、source_tag はリテラルを保持すること。"""
        captured: dict[str, TagRegisterRequest] = {}

        def fake_register(service, request: TagRegisterRequest):
            captured["request"] = request
            return type("R", (), {"created": True, "tag_id": 1})()

        monkeypatch.setattr("lorairo.services.trigger_vocab.register_tag", fake_register)
        service = TriggerVocabService(register_service=object())

        service.register("  my_trigger  ")

        req = captured["request"]
        assert req.tag == "my trigger"
        assert req.source_tag == "my_trigger"

    def test_register_skips_empty_word(self, monkeypatch) -> None:
        """空文字・空白のみの word は登録しないこと。"""
        called = {"register": False}
        monkeypatch.setattr(
            "lorairo.services.trigger_vocab.register_tag",
            lambda service, request: called.__setitem__("register", True),
        )
        service = TriggerVocabService(register_service=object())

        service.register("   ")

        assert called["register"] is False

    def test_register_noop_when_service_unavailable(self, monkeypatch) -> None:
        """register service 初期化失敗時は no-op（例外を投げない）こと。"""

        def raise_runtime() -> object:
            raise RuntimeError("no user DB")

        monkeypatch.setattr("lorairo.services.trigger_vocab.create_tag_register_service", raise_runtime)
        service = TriggerVocabService()

        # 例外が伝播しないこと
        service.register("trigger")

    def test_register_swallows_register_error(self, monkeypatch) -> None:
        """登録が ValueError を投げても no-op で継続すること。"""

        def raise_value(service, request):
            raise ValueError("invalid type")

        monkeypatch.setattr("lorairo.services.trigger_vocab.register_tag", raise_value)
        service = TriggerVocabService(register_service=object())

        service.register("trigger")  # 例外が伝播しない
