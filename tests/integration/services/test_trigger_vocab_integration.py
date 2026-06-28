"""TriggerVocabService の統合テスト（Issue #946）。

実ユーザー DB（conftest の test_tag_db_path フィクスチャが init_user_db で構築）に対して
trigger 語彙を register → search する round-trip を検証する。受け入れ条件:

- 漢字 trigger を register → search で取得できる。
- USER_TAGS（tag_id >= 1_000_000_000）にのみ入り、canonical タグ DB を汚染しない。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools import get_user_tag_reader, search_tags
from genai_tag_db_tools.models import TagSearchRequest

from lorairo.services.trigger_vocab import _TRIGGER_FORMAT, TriggerVocabService

# user tag の tag_id 下限（genai-tag-db-tools USER_TAG_ID_OFFSET）。
_USER_TAG_ID_OFFSET = 1_000_000_000

pytestmark = pytest.mark.integration


class TestTriggerVocabRoundTrip:
    """実ユーザー DB を使った register → search round-trip テスト。"""

    def test_register_then_search_kanji_trigger(self, test_tag_db_path) -> None:
        """漢字 trigger を登録し、prefix 検索で取得できること。"""
        service = TriggerVocabService()
        service.register("魔法少女")

        entries = service.search("魔法")

        words = [e.word for e in entries]
        assert "魔法少女" in words

    def test_register_is_idempotent(self, test_tag_db_path) -> None:
        """同じ trigger を二度登録しても検索結果は1件に保たれること。"""
        service = TriggerVocabService()
        service.register("twin tails")
        service.register("twin tails")

        entries = service.search("twin")

        matched = [e for e in entries if e.word == "twin tails"]
        assert len(matched) == 1

    def test_registered_trigger_lands_in_user_tags_only(self, test_tag_db_path) -> None:
        """登録した trigger が USER_TAGS（tag_id >= offset）に入ること（canonical 非汚染）。"""
        service = TriggerVocabService()
        service.register("近未来都市")

        # user DB のみを読む reader で trigger format を直接検索し tag_id を確認する。
        reader = get_user_tag_reader()
        result = search_tags(
            reader,
            TagSearchRequest(
                query="近未来都市",
                partial=False,
                format_names=[_TRIGGER_FORMAT],
                resolve_preferred=False,
                include_aliases=False,
            ),
        )

        assert result.items, "登録した trigger が user DB に見つからない"
        assert all(item.tag_id >= _USER_TAG_ID_OFFSET for item in result.items)

    def test_search_unknown_prefix_returns_empty(self, test_tag_db_path) -> None:
        """未登録 prefix の検索は空リストを返すこと。"""
        service = TriggerVocabService()
        service.register("steampunk")

        entries = service.search("no_such_prefix_xyz")

        assert entries == []
