"""CLI glyph 定数 (Issue #254) の test。"""

from __future__ import annotations

import pytest

from lorairo.cli._glyphs import FAIL, INFO, OK, WARN


@pytest.mark.unit
@pytest.mark.cli
def test_glyphs_are_ascii() -> None:
    """Issue #254: 全 glyph 定数が ASCII 表記であり cp932 console でも mojibake しない。"""
    for glyph in (OK, FAIL, WARN, INFO):
        assert glyph.isascii(), f"glyph {glyph!r} は非 ASCII"


@pytest.mark.unit
@pytest.mark.cli
def test_glyph_values() -> None:
    """Issue #254: glyph の表記が固定されていることを保証する (UI regression test)。"""
    assert OK == "[OK]"
    assert FAIL == "[--]"
    assert WARN == "[!]"
    assert INFO == "[i]"
