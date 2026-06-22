"""DsChip 単体テスト (Issue #852 DS 部品ライブラリ)。"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.ds.ds_chip import DsChip

pytestmark = [pytest.mark.unit, pytest.mark.gui]


# ---------------------------------------------------------------------------
# ヘルパー定数
# ---------------------------------------------------------------------------

_DOT_FILLED = "●"
_DOT_OPEN = "○"


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture
def chip_ok(qtbot) -> DsChip:
    """kind="ok" の基本チップ。"""
    w = DsChip("完了", kind="ok")
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# デフォルトドット (dot=None 自動決定)
# ---------------------------------------------------------------------------


class TestDefaultDot:
    """dot=None のとき kind に応じたデフォルトドットが付与されることを検証する。"""

    @pytest.mark.parametrize("kind", ["ok", "info", "accent", "err"])
    def test_filled_dot_for_filled_kinds(self, qtbot, kind):
        """filled kinds (ok/info/accent/err) は ● ドットが先頭に付く。"""
        chip = DsChip("テスト", kind=kind)  # type: ignore[arg-type]
        qtbot.addWidget(chip)
        assert chip.text().startswith(_DOT_FILLED)

    @pytest.mark.parametrize("kind", ["warn", "neutral", "muted"])
    def test_open_dot_for_open_kinds(self, qtbot, kind):
        """open kinds (warn/neutral/muted) は ○ ドットが先頭に付く。"""
        chip = DsChip("テスト", kind=kind)  # type: ignore[arg-type]
        qtbot.addWidget(chip)
        assert chip.text().startswith(_DOT_OPEN)

    def test_text_follows_dot(self, chip_ok):
        """テキストはドット + スペースの後に続く。"""
        assert chip_ok.text() == f"{_DOT_FILLED} 完了"


# ---------------------------------------------------------------------------
# dot 明示指定
# ---------------------------------------------------------------------------


class TestExplicitDot:
    """dot を明示指定したとき kind に関わらず指定が優先されることを検証する。"""

    def test_dot_filled_overrides_open_kind(self, qtbot):
        """dot="filled" は warn (既定 ○) でも ● を使う。"""
        chip = DsChip("警告", kind="warn", dot="filled")
        qtbot.addWidget(chip)
        assert chip.text().startswith(_DOT_FILLED)

    def test_dot_open_overrides_filled_kind(self, qtbot):
        """dot="open" は ok (既定 ●) でも ○ を使う。"""
        chip = DsChip("完了", kind="ok", dot="open")
        qtbot.addWidget(chip)
        assert chip.text().startswith(_DOT_OPEN)

    def test_dot_none_suppresses_dot(self, qtbot):
        """dot="none" はドットなしでテキストのみ表示する。"""
        chip = DsChip("テキストのみ", kind="ok", dot="none")
        qtbot.addWidget(chip)
        assert chip.text() == "テキストのみ"
        assert _DOT_FILLED not in chip.text()
        assert _DOT_OPEN not in chip.text()


# ---------------------------------------------------------------------------
# set_text
# ---------------------------------------------------------------------------


class TestSetText:
    """set_text() でテキストが更新されドット文字が保持されることを検証する。"""

    def test_set_text_updates_label(self, chip_ok):
        """set_text() 後のテキストは新しい本文になる。"""
        chip_ok.set_text("更新後")
        assert "更新後" in chip_ok.text()

    def test_set_text_preserves_dot(self, chip_ok):
        """set_text() 後もドット文字が引き続き付与される。"""
        chip_ok.set_text("更新後")
        assert chip_ok.text().startswith(_DOT_FILLED)

    def test_set_text_with_no_dot_kind(self, qtbot):
        """dot="none" のチップは set_text 後もドットなし。"""
        chip = DsChip("元テキスト", kind="ok", dot="none")
        qtbot.addWidget(chip)
        chip.set_text("新テキスト")
        assert chip.text() == "新テキスト"


# ---------------------------------------------------------------------------
# set_kind
# ---------------------------------------------------------------------------


class TestSetKind:
    """set_kind() でスタイルとドットが再描画されることを検証する。"""

    def test_set_kind_changes_stylesheet(self, chip_ok):
        """set_kind() 後は新 kind の QSS が適用される (空でない)。"""
        chip_ok.set_kind("err")
        assert chip_ok.styleSheet() != ""

    def test_set_kind_changes_dot_when_auto(self, chip_ok):
        """dot=None (自動) のとき set_kind() でドット文字が切り替わる。"""
        # ok (●) → warn (○)
        chip_ok.set_kind("warn")
        assert chip_ok.text().startswith(_DOT_OPEN)

    def test_set_kind_preserves_explicit_dot(self, qtbot):
        """dot 明示指定のとき set_kind() してもドット指定が保たれる。"""
        chip = DsChip("テキスト", kind="ok", dot="filled")
        qtbot.addWidget(chip)
        # warn (既定 ○) に変えても dot="filled" なので ● のまま
        chip.set_kind("warn")
        assert chip.text().startswith(_DOT_FILLED)

    def test_set_kind_text_unchanged(self, chip_ok):
        """set_kind() しても本文テキストは変化しない。"""
        chip_ok.set_kind("info")
        assert "完了" in chip_ok.text()


# ---------------------------------------------------------------------------
# 全 kind 生成確認
# ---------------------------------------------------------------------------


class TestAllKindsCreation:
    """全 ChipKind で DsChip が例外なく生成できることを確認する。"""

    @pytest.mark.parametrize("kind", ["ok", "warn", "err", "info", "neutral", "muted", "accent"])
    def test_creates_without_error(self, qtbot, kind):
        """全 kind で DsChip のインスタンス化が成功する。"""
        chip = DsChip("テスト", kind=kind)  # type: ignore[arg-type]
        qtbot.addWidget(chip)
        assert chip.text() != ""

    @pytest.mark.parametrize("kind", ["ok", "warn", "err", "info", "neutral", "muted", "accent"])
    def test_stylesheet_is_non_empty(self, qtbot, kind):
        """全 kind でスタイルシートが設定される。"""
        chip = DsChip("テスト", kind=kind)  # type: ignore[arg-type]
        qtbot.addWidget(chip)
        assert chip.styleSheet() != ""
