"""Theme v1 (src/lorairo/gui/theme.py) のユニットテスト (Issue #760)。

SSoT は docs/design/theme-v1/hifi-mock.html。トークン hex とモックの整合、
QSS 生成 / チップ文法 API の振る舞いを検証する。
"""

import re
from pathlib import Path

import pytest

from lorairo.gui import theme

pytestmark = pytest.mark.unit

_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")

# DS token SSoT (theme.py と 1:1 で維持される。Issue #782)
_DS_TOKENS_DIR = Path(__file__).parents[3] / "docs" / "design" / "lorairo-design-system" / "tokens"
# CSS var (--accent-hover) -> theme.py 定数名 (ACCENT_HOVER) への素直な変換で対応する色トークン
_CSS_HEX_RE = re.compile(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6});")


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
        assert theme.RADIUS_BADGE == 3
        assert theme.RADIUS_SHELL == 8
        assert (theme.SPACE_1, theme.SPACE_2, theme.SPACE_3, theme.SPACE_4, theme.SPACE_5) == (
            4,
            8,
            12,
            16,
            24,
        )

    def test_border_width_tokens(self):
        # tokens/spacing.css --bw / --bw-accent と 1:1
        assert theme.BORDER_WIDTH == 1
        assert theme.BORDER_WIDTH_ACCENT == 2

    def test_typography_size_tokens(self):
        # tokens/typography.css --fs-* と 1:1
        assert theme.FONT_SIZE_BASE == 13
        assert theme.FONT_SIZE_SMALL == 11
        assert theme.FONT_SIZE_H2 == 14
        assert theme.FONT_SIZE_H1 == 18
        assert theme.FONT_SIZE_META == 10

    def test_typography_weight_tokens(self):
        # tokens/typography.css --fw-* と 1:1
        assert theme.FONT_WEIGHT_REGULAR == 400
        assert theme.FONT_WEIGHT_MEDIUM == 500
        assert theme.FONT_WEIGHT_SEMIBOLD == 600
        assert theme.FONT_WEIGHT_BOLD == 700

    def test_letter_caps_token(self):
        assert theme.LETTER_CAPS == "0.06em"

    def test_font_css_helpers_quote_family_chain(self):
        # tokens/typography.css --font-sans / --font-mono と 1:1 (QSS 用の引用符付き連結)
        assert theme.FONT_MONO_CSS == "'JetBrains Mono', 'Cascadia Mono', 'monospace'"
        assert theme.FONT_SANS_CSS == "'Noto Sans JP', 'Segoe UI', 'Hiragino Sans'"
        for family in theme.FONT_MONO_FAMILIES:
            assert f"'{family}'" in theme.FONT_MONO_CSS
        for family in theme.FONT_SANS_FAMILIES:
            assert f"'{family}'" in theme.FONT_SANS_CSS


class TestDsTokenParity:
    """DS token CSS (SSoT) と theme.py 定数が 1:1 で一致することを保証する (Issue #782)。"""

    def test_color_tokens_match_ds_colors_css(self):
        colors_css = (_DS_TOKENS_DIR / "colors.css").read_text(encoding="utf-8")
        # :root 直下の生 hex トークンのみ対象 (var() 参照の semantic alias は除外)
        ds_tokens = dict(_CSS_HEX_RE.findall(colors_css))
        assert ds_tokens, "DS colors.css から hex トークンを抽出できなかった"

        for css_name, hex_value in ds_tokens.items():
            py_name = css_name.upper().replace("-", "_")
            actual = getattr(theme, py_name, None)
            assert actual is not None, f"theme.{py_name} が存在しない (DS --{css_name})"
            assert actual == hex_value, f"theme.{py_name}={actual} が DS --{css_name}={hex_value} と不一致"


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
            "QCheckBox::indicator",
        ):
            assert selector in qss, f"missing selector: {selector}"

    def test_checkbox_indicator_has_visible_border_states(self):
        # Issue #1092: QCheckBox の枠線がテーマ QSS 未定義で見えなかった回帰防止。
        # unchecked は LINE_STRONG 枠 + CARD 地、checked は ACCENT 塗りでコントラストを確保。
        qss = theme.build_global_qss()
        unchecked = qss.split("QCheckBox::indicator:unchecked {")[1].split("}")[0]
        assert f"1px solid {theme.LINE_STRONG}" in unchecked
        assert f"background: {theme.CARD}" in unchecked
        checked = qss.split("QCheckBox::indicator:checked {")[1].split("}")[0]
        assert f"background: {theme.ACCENT}" in checked

    def test_checkbox_indicator_hover_uses_accent(self):
        qss = theme.build_global_qss()
        assert "QCheckBox::indicator:unchecked:hover" in qss
        hover = qss.split("QCheckBox::indicator:unchecked:hover {")[1].split("}")[0]
        assert f"border-color: {theme.ACCENT}" in hover

    def test_checkbox_checked_disabled_stays_filled(self):
        # Codex P2 (#1092): checked のまま disabled でも unchecked と区別できるよう
        # 塗り (accent 減光) を残す。汎用 :disabled ルールに上書きされないこと。
        qss = theme.build_global_qss()
        assert "QCheckBox::indicator:checked:disabled" in qss
        checked_disabled = qss.split("QCheckBox::indicator:checked:disabled {")[1].split("}")[0]
        assert f"background: {theme.ACCENT_SOFT}" in checked_disabled

    def test_checkbox_indicator_uses_no_image_url(self):
        # Codex P2 (#1092): Qt QSS は image: url() の CSS data URI をデコードしないため、
        # チェックマーク画像は使わず塗りのみで表現する (radio と同流儀)。
        qss = theme.build_global_qss()
        assert "image: url(" not in qss

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
            # #1105: pipeline chip 定数から移植した色
            ("primary", theme.CARD, theme.INK),
            ("multi", theme.CARD, theme.ACCENT_HOVER),
            ("derived", "transparent", theme.INK_SOFT),
        ],
    )
    def test_chip_kind_maps_to_tokens(self, kind, bg, fg):
        qss = theme.chip_qss(kind)
        assert f"background-color: {bg}" in qss
        assert f"color: {fg}" in qss
        assert f"border-radius: {theme.RADIUS_CHIP}px" in qss

    def test_new_chip_kinds_use_expected_borders(self):
        # #1105: 移植 kind の border 色が手書き定数と一致すること
        assert f"solid {theme.LINE_STRONG}" in theme.chip_qss("primary")
        assert f"solid {theme.ACCENT_BORDER}" in theme.chip_qss("multi")
        assert f"solid {theme.LINE_STRONG}" in theme.chip_qss("derived")

    def test_badge_qss_uses_neutral_tokens(self):
        qss = theme.badge_qss()
        assert theme.PAPER_SHADE in qss
        assert theme.INK_SOFT in qss
        assert theme.LINE in qss

    def test_badge_qss_with_kind_recolors(self):
        # #1105: DsBadge 用に kind で recolor できる (geometry は共通)
        accent_badge = theme.badge_qss("accent")
        assert f"background-color: {theme.ACCENT_SOFT}" in accent_badge
        assert f"color: {theme.ACCENT_HOVER}" in accent_badge
        # badge geometry (小角丸) は維持
        assert f"border-radius: {theme.RADIUS_BADGE}px" in accent_badge
        # neutral (kind=None) とは異なる
        assert accent_badge != theme.badge_qss()


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
