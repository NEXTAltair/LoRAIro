"""GUI ランチャー (``lorairo``) の help 出力に関する unit テスト。

Issue #541: GUI ランチャーの help がバッチ/アノテーション/データセット操作に
言及していないため、``lorairo-cli`` への誘導が表示されることを検証する。
"""

import pytest

from lorairo.main import _build_parser


@pytest.mark.unit
def test_help_text_guides_to_lorairo_cli() -> None:
    """help テキストに ``lorairo-cli`` への誘導が含まれることを検証する。"""
    help_text = _build_parser().format_help()
    assert "lorairo-cli" in help_text


@pytest.mark.unit
def test_help_text_retains_existing_options() -> None:
    """既存の ``--debug`` / ``--version`` の記述が help に残ることを検証する。"""
    help_text = _build_parser().format_help()
    assert "--debug" in help_text
    assert "--version" in help_text
