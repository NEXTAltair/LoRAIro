"""language_keys のエイリアス正規化・重複排除ヘルパーのユニットテスト (#1235 / #1236)。"""

import pytest

from lorairo.utils.language_keys import (
    canonical_language_key,
    dedupe_languages_by_family,
    dedupe_translations_by_family,
    language_alias_keys,
    translation_for_language,
)

pytestmark = pytest.mark.unit


class TestCanonicalLanguageKey:
    def test_ja_family_maps_to_ja(self):
        assert canonical_language_key("ja") == "ja"
        assert canonical_language_key("japanese") == "ja"

    def test_en_family_maps_to_en(self):
        assert canonical_language_key("en") == "en"
        assert canonical_language_key("english") == "en"

    def test_unknown_language_returns_itself(self):
        assert canonical_language_key("ko") == "ko"
        assert canonical_language_key("zh-cn") == "zh-cn"


class TestDedupeLanguagesByFamily:
    def test_collapses_ja_family_keeping_short_form(self):
        assert dedupe_languages_by_family(["ja", "japanese"]) == ["ja"]
        # 先出が legacy 表記でも短形へ昇格する。
        assert dedupe_languages_by_family(["japanese", "ja"]) == ["ja"]

    def test_single_legacy_alias_kept_as_is(self):
        # 族に短形が無ければ初出表記を残す。
        assert dedupe_languages_by_family(["japanese"]) == ["japanese"]

    def test_preserves_family_first_appearance_order(self):
        assert dedupe_languages_by_family(["ko", "ja", "japanese", "en", "english"]) == [
            "ko",
            "ja",
            "en",
        ]

    def test_unknown_languages_pass_through(self):
        assert dedupe_languages_by_family(["de", "fr", "zh-cn"]) == ["de", "fr", "zh-cn"]

    def test_empty(self):
        assert dedupe_languages_by_family([]) == []


class TestDedupeTranslationsByFamily:
    def test_collapses_fanned_out_alias_keys(self):
        # 主訳 fan-out で ja/japanese 両キーに同値が入ったケース (#1236)。
        result = dedupe_translations_by_family({"en": "dress", "ja": "ドレス", "japanese": "ドレス"})
        assert result == {"en": "dress", "ja": "ドレス"}

    def test_promotes_short_key_when_legacy_first(self):
        result = dedupe_translations_by_family({"japanese": "旧", "ja": "新"})
        # 短形 ja を代表に昇格し、その値を残す。
        assert result == {"ja": "新"}

    def test_keeps_legacy_when_no_short_form(self):
        assert dedupe_translations_by_family({"japanese": "旧"}) == {"japanese": "旧"}

    def test_unknown_languages_untouched(self):
        src = {"ko": "코", "de": "kleid"}
        assert dedupe_translations_by_family(src) == src


class TestExistingHelpersUnchanged:
    def test_language_alias_keys(self):
        assert language_alias_keys("ja") == ("ja", "japanese")
        assert language_alias_keys("ko") == ("ko",)

    def test_translation_for_language_via_alias(self):
        assert translation_for_language({"japanese": "訳"}, "ja") == "訳"
        assert translation_for_language({}, "ja") is None
