"""言語キーのエイリアス正規化ヘルパー (Qt 非依存、#1084 / #1050 / #976)。

tagdb は翻訳の language を verbatim 格納するため、日本語は "japanese" と "ja"、英語は
"english" と "en" が混在しうる (#976 PR #991)。新規登録は ja/en に正規化する (#1050) が、
表示・照合は両表記を同値として扱う必要がある。

エイリアス表の定義箇所を 1 つに集約する共有ヘルパー (Qt 非依存)。GUI 側 (TagPanelWidget /
TagMetadataWorker) と Qt-free サービス (TagManagementService) の双方が参照するため、
gui/widgets への依存を避けてここへ置く。widget 側で二重定義しない。
"""

from __future__ import annotations

# 日本語/英語の言語キー表記ゆれを同値として引くためのエイリアス表。
# 値の並びは lookup の優先順 (先頭が正規表記)。
LANGUAGE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "ja": ("ja", "japanese"),
    "japanese": ("japanese", "ja"),
    "en": ("en", "english"),
    "english": ("english", "en"),
}


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
