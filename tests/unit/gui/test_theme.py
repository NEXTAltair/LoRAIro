"""Theme v1 (src/lorairo/gui/theme.py) のユニットテスト (Issue #760)。

SSoT は docs/design/theme-v1/hifi-mock.html。トークン hex とモックの整合、
QSS 生成 / チップ文法 API の振る舞いを検証する。
"""

import re

import pytest

from lorairo.gui import theme

pytestmark = pytest.mark.unit

_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


class TestTokenValues:
    """トークン hex がモック確定値と一致することを確認する。"""

    def test_surface_tokens(self):
        assert theme.PAPER == "#fbfaf6"
        assert theme.PAPER_SHADE == "#f1efe6"
        assert theme.CARD == "#ffffff"
        assert theme.TERMINAL == "#23211d"

    def test_ink_and_line_tokens(self):
        assert theme.INK == "#1a1a1a"
        assert theme.INK_SOFT == "#4a4a4a"
        assert theme.INK_FAINT == "#9a9a9a"
        assert theme.LINE == "#dcd8cc"
        assert theme.LINE_STRONG == "#b9b4a5"

    def test_accent_tokens(self):
        assert theme.ACCENT == "#c25e3f"
        assert theme.ACCENT_HOVER == "#a94e33"
        assert theme.ACCENT_SOFT == "#f6e3dc"

    def test_status_tokens(self):
        assert theme.OK == "#3c8a55"
        assert theme.WARN == "#b87f1f"
        assert theme.ERR == "#b8402c"
        assert theme.INFO == "#3d6f9e"

    def test_all_color_tokens_are_valid_hex(self):
        for name in dir(theme):
            value = getattr(theme, name)
            if name.isupper() and isinstance(value, str) and value.startswith("#"):
                assert _HEX_RE.match(value), f"{name} = {value} is not a valid 6-digit hex"

    def test_shape_tokens(self):
        assert theme.RADIUS == 6
        assert theme.RADIUS_CHIP == 10
        assert (theme.SPACE_1, theme.SPACE_2, theme.SPACE_3, theme.SPACE_4, theme.SPACE_5) == (
            4,
            8,
            12,
            16,
            24,
        )


class TestBuildGlobalQss:
    """グローバル QSS 生成の検証。"""

    def test_contains_core_widget_selectors(self):
        qss = theme.build_global_qss()
        for selector in (
            "QMainWindow",
            "QTabBar::tab:selected",
            "QPushButton",
            "QLineEdit",
            "QComboBox",
            "QTableView",
            "QHeaderView::section",
            "QTreeView",
            "QListView",
            "QScrollBar:vertical",
            "QGroupBox",
            "QToolTip",
            "QMenu",
            "QProgressBar::chunk",
        ):
            assert selector in qss, f"missing selector: {selector}"

    def test_active_tab_uses_accent_underline_and_bold(self):
        qss = theme.build_global_qss()
        selected = qss.split("QTabBar::tab:selected")[1].split("}")[0]
        assert f"2px solid {theme.ACCENT}" in selected
        assert "font-weight: 600" in selected

    def test_progress_chunk_uses_info_color(self):
        qss = theme.build_global_qss()
        chunk = qss.split("QProgressBar::chunk")[1].split("}")[0]
        assert theme.INFO in chunk

    def test_no_unresolved_format_placeholders(self):
        # f-string 展開漏れ ("{PAPER}" 等) が残っていないこと
        qss = theme.build_global_qss()
        assert not re.search(r"\{[A-Z_]+\}", qss)

    def test_braces_are_balanced(self):
        qss = theme.build_global_qss()
        assert qss.count("{") == qss.count("}")

    def test_no_font_family_override(self):
        # ウィジェット個別の QFont (monospace ラベル等) を壊さないため
        # グローバル QSS では font-family を設定しない
        assert "font-family" not in theme.build_global_qss()


class TestChipQss:
    """チップ文法 API の検証。"""

    @pytest.mark.parametrize(
        ("kind", "bg", "fg"),
        [
            ("ok", theme.OK_SOFT, theme.OK),
            ("warn", theme.WARN_SOFT, theme.WARN),
            ("err", theme.ERR_SOFT, theme.ERR),
            ("info", theme.INFO_SOFT, theme.INFO),
            ("neutral", theme.PAPER_SHADE, theme.INK_SOFT),
            ("muted", theme.PAPER_SHADE, theme.INK_FAINT),
            ("accent", theme.ACCENT_SOFT, theme.ACCENT_HOVER),
        ],
    )
    def test_chip_kind_maps_to_tokens(self, kind, bg, fg):
        qss = theme.chip_qss(kind)
        assert f"background-color: {bg}" in qss
        assert f"color: {fg}" in qss
        assert f"border-radius: {theme.RADIUS_CHIP}px" in qss

    def test_badge_qss_uses_neutral_tokens(self):
        qss = theme.badge_qss()
        assert theme.PAPER_SHADE in qss
        assert theme.INK_SOFT in qss
        assert theme.LINE in qss


class TestJobStatusColor:
    """ジョブ状態 → トークン色マッピングの検証。"""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("running", theme.INFO),
            ("submitted", theme.INFO),
            ("queued", theme.INK_SOFT),
            ("completed", theme.OK),
            ("imported", theme.OK),
            ("failed", theme.ERR),
            ("canceled", theme.INK_FAINT),
            ("expired", theme.INK_FAINT),
        ],
    )
    def test_known_statuses(self, status, expected):
        assert theme.job_status_color(status) == expected

    def test_case_insensitive(self):
        assert theme.job_status_color("RUNNING") == theme.INFO

    def test_unknown_status_falls_back_to_ink_soft(self):
        assert theme.job_status_color("mystery") == theme.INK_SOFT
