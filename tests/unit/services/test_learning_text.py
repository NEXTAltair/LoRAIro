"""学習テキストの要素分割と連結のユニットテスト。"""

import pytest

from lorairo.services.learning_text import join_elements, split_elements

pytestmark = pytest.mark.unit


def test_split_elements_keeps_case_underscore_and_parentheses() -> None:
    raw = "Kariginu, long_sleeves, (tag:1.2), \\(x\\)"
    assert split_elements(raw) == ["Kariginu", "long_sleeves", "(tag:1.2)", "\\(x\\)"]


def test_split_elements_drops_empty_items() -> None:
    assert split_elements("a,, b ,\n") == ["a", "b"]


def test_split_elements_multiline_is_joined_by_comma_only() -> None:
    assert split_elements("a\nb, c") == ["a\nb", "c"]


def test_split_elements_empty_text_returns_empty_list() -> None:
    assert split_elements("") == []


def test_join_elements_uses_comma_space() -> None:
    assert join_elements(["a", "b"]) == "a, b"
