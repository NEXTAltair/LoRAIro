"""image-annotator-lib の model-native rating を LoRAIro canonical rating に変換する (Issue #333)。

image-annotator-lib は rating を model-native な ``RatingPrediction``
(``raw_label`` / ``confidence_score`` / ``source_scheme``) で返す。LoRAIro 側の
``PG / PG-13 / R / X / XXX`` への変換は LoRAIro の責務 (ADR 0031)。

このモジュールは ``(source_scheme, raw_label)`` を canonical rating に変換する純粋関数を
提供する。``raw annotation`` は変更せず、保存時の derived 値として計算する。

新しい rating モデル / scheme を追加する場合:

1. ``_LABEL_MAP`` に scheme 行、または ``_SCHEME_ALIASES`` に別名を追加
2. 該当する unit test を追加 (``tests/unit/domain/test_rating_mapper.py``)

設計方針:

- mapper の出力は通常 ``PG / PG-13 / R / X`` まで。``XXX`` は
  ``openai_moderation_v1`` のような専用判定 scheme でのみ自動生成する。
- 未知 scheme / 未知 label は ``None`` を返す (呼び出し側で skip)。
"""

from __future__ import annotations

# source_scheme の別名 -> 正規 scheme 名。
# image-annotator-lib が emit する scheme 文字列の表記揺れ・モデル系統差を吸収する。
_SCHEME_ALIASES: dict[str, str] = {
    "wdtagger": "danbooru4",
    "camie": "danbooru4",
    "z3d": "e6213",
    "danbooru3": "e6213",
    "anime_rating": "sankaku3",
}

# 正規 scheme 名 -> {raw_label: canonical rating}。
# raw_label は lowercase + space->underscore 正規化済みの値で照合する。
_LABEL_MAP: dict[str, dict[str, str]] = {
    # Danbooru 4 分類 (WDTagger / camie 系)
    "danbooru4": {
        "general": "PG",
        "sensitive": "PG-13",
        "questionable": "R",
        "explicit": "X",
    },
    # e621 / Safebooru 3 分類 (Z3D / danbooru3 系)
    "e6213": {
        "safe": "PG",
        "general": "PG",
        "questionable": "R",
        "explicit": "X",
    },
    # Sankaku / anime_rating 3 分類
    "sankaku3": {
        "safe": "PG",
        "r15": "R",
        "r18": "X",
    },
    # 二値 NSFW classifier
    "binary_nsfw": {
        "sfw": "PG",
        "nsfw": "R",
    },
    # OpenAI Moderations 由来の LoRAIro rating preflight (ADR 0031 amendment / Issue #471)
    "openai_moderation_v1": {
        "pg": "PG",
        "pg13": "PG-13",
        "r": "R",
        "x": "X",
        "xxx": "XXX",
    },
}


def _normalize_scheme(source_scheme: str) -> str:
    """source_scheme を strip + lower + alias 解決して正規 scheme 名にする。"""
    scheme = source_scheme.strip().lower()
    return _SCHEME_ALIASES.get(scheme, scheme)


def _normalize_label(raw_label: str) -> str:
    """raw_label を strip + lower + space->underscore で正規化する。"""
    return raw_label.strip().lower().replace(" ", "_")


def map_rating(raw_label: str, source_scheme: str) -> str | None:
    """model-native rating を LoRAIro canonical rating に変換する。

    Args:
        raw_label: モデルが出力した生の rating ラベル (例: "general", "explicit")。
        source_scheme: rating ラベルの分類スキーム (例: "danbooru4", "e6213")。

    Returns:
        canonical rating ("PG" / "PG-13" / "R" / "X" / "XXX")。
        未知の scheme / label の場合は None。
    """
    scheme = _normalize_scheme(source_scheme)
    label = _normalize_label(raw_label)
    return _LABEL_MAP.get(scheme, {}).get(label)
