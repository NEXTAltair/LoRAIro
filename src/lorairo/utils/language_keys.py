"""言語キーのエイリアス正規化ヘルパー (Qt 非依存、#1084 / #1050 / #976)。

tagdb は翻訳の language を verbatim 格納するため、日本語は "japanese" と "ja"、英語は
"english" と "en" が混在しうる (#976 PR #991)。新規登録は ja/en に正規化する (#1050) が、
表示・照合は両表記を同値として扱う必要がある。

エイリアス表の定義箇所を 1 つに集約する共有ヘルパー (Qt 非依存)。GUI 側 (TagPanelWidget /
TagMetadataWorker) と Qt-free サービス (TagManagementService) の双方が参照するため、
gui/widgets への依存を避けてここへ置く。widget 側で二重定義しない。
"""

from __future__ import annotations

from collections.abc import Iterable

# 日本語/英語の言語キー表記ゆれを同値として引くためのエイリアス表。
# 値の並びは lookup の優先順 (先頭が正規表記)。
LANGUAGE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "ja": ("ja", "japanese"),
    "japanese": ("japanese", "ja"),
    "en": ("en", "english"),
    "english": ("english", "en"),
}

# エイリアス族の代表 (正規) キー。表示・dedup では短形 (ja/en) を優先代表とする。
_CANONICAL_LANGUAGE_KEY: dict[str, str] = {
    "ja": "ja",
    "japanese": "ja",
    "en": "en",
    "english": "en",
}


def canonical_language_key(language: str) -> str:
    """エイリアス族の代表キー (短形 ``ja`` / ``en``) を返す (#1235 / #1236)。

    エイリアスが未定義の言語は自身をそのまま返す。族単位で重複を畳む際の
    グルーピングキーに使う。

    Args:
        language: 言語コード (例: "ja" / "japanese" / "en" / "english")。

    Returns:
        当該言語が属するエイリアス族の代表キー。
    """
    return _CANONICAL_LANGUAGE_KEY.get(language, language)


def dedupe_languages_by_family(languages: Iterable[str]) -> list[str]:
    """言語リストをエイリアス族ごとに 1 つへ畳む (#1235)。

    tagdb は language を verbatim 格納するため、同一言語が ``ja`` と ``japanese`` の
    両表記で distinct 値として返ることがある。族ごとに 1 要素へ畳み、族の初出順を保つ。
    族内の代表は短形 (``ja`` / ``en``) を優先し、短形が無ければ初出の表記を残す。

    Args:
        languages: 畳み込み対象の言語キー列。

    Returns:
        族ごとに 1 つへ畳んだ言語リスト (族の初出順)。
    """
    representatives: dict[str, str] = {}
    order: list[str] = []
    for lang in languages:
        canon = canonical_language_key(lang)
        if canon not in representatives:
            representatives[canon] = lang
            order.append(canon)
        elif lang == canon and representatives[canon] != canon:
            # 既に別表記が代表なら短形へ昇格 (例: japanese 先出 → ja を代表に)。
            representatives[canon] = lang
    return [representatives[canon] for canon in order]


def dedupe_translations_by_family(translations: dict[str, str]) -> dict[str, str]:
    """翻訳マップをエイリアス族ごとに 1 エントリへ畳む (#1236)。

    主訳の全エイリアスキーへの fan-out (TagMetadataWorker) や legacy/正規表記の
    混在により、``{"ja": x, "japanese": x}`` のように同一言語が複数キーで入りうる。
    族ごとに 1 エントリへ畳み、族の初出順を保つ。族内の代表キーは短形を優先する。

    Args:
        translations: ``{language: translation}`` の翻訳マップ。

    Returns:
        族ごとに 1 エントリへ畳んだ翻訳マップ (族の初出順)。
    """
    chosen_key: dict[str, str] = {}
    result: dict[str, str] = {}
    for key, value in translations.items():
        canon = canonical_language_key(key)
        if canon not in chosen_key:
            chosen_key[canon] = key
            result[key] = value
        elif key == canon and chosen_key[canon] != canon:
            # 短形キーを代表へ昇格し、旧代表エントリを差し替える。
            del result[chosen_key[canon]]
            chosen_key[canon] = key
            result[key] = value
    return result


def language_alias_keys(language: str) -> tuple[str, ...]:
    """指定言語の同値エイリアスキー列を返す (#1084)。

    エイリアスが未定義の言語は自身のみを含む 1 要素タプルを返す。

    Args:
        language: 言語コード (例: "ja" / "japanese" / "en" / "english")。

    Returns:
        当該言語として扱うキー列。先頭が正規表記。
    """
    return LANGUAGE_KEY_ALIASES.get(language, (language,))


def translation_for_language(translations: dict[str, str], language: str) -> str | None:
    """言語キーのエイリアス (ja/japanese, en/english) を同値として翻訳を引く (#1050)。

    Args:
        translations: ``{language: translation}`` の翻訳マップ。
        language: 引きたい言語コード。

    Returns:
        エイリアスのいずれかで見つかった翻訳。無ければ None。
    """
    for key in language_alias_keys(language):
        if key in translations:
            return translations[key]
    return None
