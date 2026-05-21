"""rating_mapper ユニットテスト (Issue #333)。"""

import pytest

from lorairo.domain.rating_mapper import map_rating


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_label", "source_scheme", "expected"),
    [
        # Danbooru 4 分類
        ("general", "danbooru4", "PG"),
        ("sensitive", "danbooru4", "PG-13"),
        ("questionable", "danbooru4", "R"),
        ("explicit", "danbooru4", "X"),
        # e621 / Safebooru 3 分類
        ("safe", "e6213", "PG"),
        ("general", "e6213", "PG"),
        ("questionable", "e6213", "R"),
        ("explicit", "e6213", "X"),
        # Sankaku / anime_rating 3 分類 (r15 -> R は ADR 0031 で確定)
        ("safe", "sankaku3", "PG"),
        ("r15", "sankaku3", "R"),
        ("r18", "sankaku3", "X"),
        # 二値 NSFW
        ("sfw", "binary_nsfw", "PG"),
        ("nsfw", "binary_nsfw", "R"),
    ],
)
def test_map_rating_canonical_pairs(raw_label: str, source_scheme: str, expected: str) -> None:
    """Issue #333 の対応表どおりに canonical rating へ変換される。"""
    assert map_rating(raw_label, source_scheme) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("wdtagger", "danbooru4"),
        ("camie", "danbooru4"),
        ("z3d", "e6213"),
        ("danbooru3", "e6213"),
        ("anime_rating", "sankaku3"),
    ],
)
def test_map_rating_scheme_aliases(alias: str, canonical: str) -> None:
    """scheme 別名は正規 scheme と同じ結果になる。"""
    assert map_rating("explicit" if canonical != "sankaku3" else "r18", alias) == map_rating(
        "explicit" if canonical != "sankaku3" else "r18", canonical
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_label", "source_scheme"),
    [
        ("GENERAL", "DANBOORU4"),
        ("  Explicit  ", "  Danbooru4  "),
        ("R15", "Sankaku3"),
        ("not safe", "binary_nsfw"),  # space -> underscore 正規化はされるが not_safe は未知 -> None
    ],
)
def test_map_rating_case_and_whitespace_insensitive(raw_label: str, source_scheme: str) -> None:
    """大文字小文字・前後空白に依存せず照合できる。"""
    # "not safe" は未知ラベルなので None、それ以外は変換成功
    result = map_rating(raw_label, source_scheme)
    if raw_label.strip().lower() == "not safe":
        assert result is None
    else:
        assert result is not None


@pytest.mark.unit
def test_map_rating_unknown_scheme_returns_none() -> None:
    """未知の source_scheme は None を返す。"""
    assert map_rating("general", "unknown") is None
    assert map_rating("general", "") is None


@pytest.mark.unit
def test_map_rating_unknown_label_returns_none() -> None:
    """既知 scheme でも未知 label は None を返す。"""
    assert map_rating("nonexistent", "danbooru4") is None
    assert map_rating("sensitive", "e6213") is None  # e6213 に sensitive は無い


@pytest.mark.unit
def test_map_rating_never_produces_xxx() -> None:
    """mapper は XXX を自動生成しない (ADR 0031)。"""
    all_outputs = set()
    schemes = ["danbooru4", "e6213", "sankaku3", "binary_nsfw"]
    labels = [
        "general",
        "sensitive",
        "questionable",
        "explicit",
        "safe",
        "r15",
        "r18",
        "sfw",
        "nsfw",
    ]
    for scheme in schemes:
        for label in labels:
            mapped = map_rating(label, scheme)
            if mapped is not None:
                all_outputs.add(mapped)
    assert "XXX" not in all_outputs
    assert all_outputs <= {"PG", "PG-13", "R", "X"}
