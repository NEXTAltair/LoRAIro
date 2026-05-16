"""CLI glyph 定数 (Issue #254) の test。"""

from __future__ import annotations

import pytest
from rich.console import Console

from lorairo.cli._glyphs import FAIL, INFO, OK, WARN


@pytest.mark.unit
@pytest.mark.cli
def test_glyphs_are_ascii() -> None:
    """Issue #254: 全 glyph 定数が ASCII 表記であり cp932 console でも mojibake しない。"""
    for glyph in (OK, FAIL, WARN, INFO):
        assert glyph.isascii(), f"glyph {glyph!r} は非 ASCII"


@pytest.mark.unit
@pytest.mark.cli
def test_glyph_values_are_rich_escaped() -> None:
    """Issue #254 / PR #263 codex review: Rich markup として安全に補間できる escape 形式。"""
    assert OK == r"\[OK]"
    assert FAIL == r"\[--]"
    assert WARN == r"\[!]"
    assert INFO == r"\[i]"


@pytest.mark.unit
@pytest.mark.cli
def test_glyphs_render_without_markup_error() -> None:
    """Issue #254 / PR #263 codex review: Rich Console 出力で literal text として描画されること。

    ``[green]{OK}[/green]`` のような markup 文字列に補間しても MarkupError 発生せず、
    capture 文字列に ``[OK]`` が literal で含まれることを確認する。
    """
    import io

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, no_color=True)

    for glyph, label in [(OK, "[OK]"), (FAIL, "[--]"), (WARN, "[!]"), (INFO, "[i]")]:
        console.print(f"[green]{glyph}[/green] message")
        output = buffer.getvalue()
        assert label in output, f"glyph {glyph!r} が literal {label!r} で出力されていない: {output!r}"
        buffer.seek(0)
        buffer.truncate(0)
