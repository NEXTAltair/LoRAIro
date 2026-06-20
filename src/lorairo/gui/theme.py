"""LoRAIro Theme v1 デザイントークンとグローバル QSS 生成 (Issue #760)。

SSoT は ``docs/design/theme-v1/hifi-mock.html``。トークン hex を変更する場合は
モックと本モジュールを必ず同時に更新する。

提供する API:

- 色 / フォント / 角丸 / 余白のトークン定数
- :func:`build_global_qss` — ``QApplication.setStyleSheet()`` に渡すグローバル QSS
- :func:`apply_theme` — QSS + placeholder palette の一括適用
- :func:`chip_qss` / :func:`badge_qss` / :func:`job_status_color` —
  ウィジェット個別スタイルから参照するトークンベースのスタイル生成
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from ..utils.log import logger

# ---------------------------------------------------------------------------
# カラートークン (hifi-mock.html :root と 1:1 対応)
# ---------------------------------------------------------------------------

# --- surface ---
PAPER = "#fbfaf6"  # アプリ背景
PAPER_SHADE = "#f1efe6"  # サイドバー・ヘッダ帯・行 hover
CARD = "#ffffff"  # カード・入力欄の地
TERMINAL = "#23211d"  # コード / JSONL ダークペイン

# --- ink ---
INK = "#1a1a1a"  # 本文
INK_SOFT = "#4a4a4a"  # 補助テキスト
INK_FAINT = "#9a9a9a"  # placeholder・無効

# --- line ---
LINE = "#dcd8cc"  # 標準 border (1px)
LINE_STRONG = "#b9b4a5"  # 強調 border・フォーカス枠の下地

# --- accent ---
ACCENT = "#c25e3f"  # 主アクション・選択状態・アクティブタブ下線
ACCENT_HOVER = "#a94e33"
ACCENT_SOFT = "#f6e3dc"  # 選択行の背景・accent バッジ地
ACCENT_BORDER = "#ecc9bd"  # accent チップの同系 border (mock .tagchip)

# --- status ---
OK = "#3c8a55"  # 成功・installed・API ready
OK_SOFT = "#e2f0e6"
OK_BORDER = "#bedfc8"
WARN = "#b87f1f"  # 警告・needs key・low confidence
WARN_SOFT = "#f7ecd8"
WARN_BORDER = "#e7d3a8"
ERR = "#b8402c"  # エラー・failed
ERR_SOFT = "#f7e1dc"
ERR_BORDER = "#e8c2ba"
INFO = "#3d6f9e"  # 実行中・進捗
INFO_SOFT = "#e1ebf4"
INFO_BORDER = "#bcd2e5"

# --- terminal pane (mock .term の構文色) ---
TERMINAL_FG = "#d8d4c8"
TERMINAL_KEY = "#8ab4d8"
TERMINAL_STR = "#a8c890"
TERMINAL_NUM = "#d8b070"
TERMINAL_BOOL = "#c98a8a"
TERMINAL_MUTED = "#8a877f"  # ダークペイン上の補助テキスト (TERMINAL_FG から減光)

# ---------------------------------------------------------------------------
# タイポグラフィ (フォントファイルは同梱しない。フォールバックチェーンのみ)
# ---------------------------------------------------------------------------

FONT_SANS_FAMILIES: tuple[str, ...] = ("Noto Sans JP", "Segoe UI", "Hiragino Sans")
FONT_MONO_FAMILIES: tuple[str, ...] = ("JetBrains Mono", "Cascadia Mono", "monospace")
FONT_SIZE_BASE = 13  # px
FONT_SIZE_SMALL = 11  # px

# ---------------------------------------------------------------------------
# 形状・余白
# ---------------------------------------------------------------------------

RADIUS = 6  # カード・ボタン
RADIUS_CHIP = 10  # チップ・バッジ
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24

# ---------------------------------------------------------------------------
# チップ / バッジ (チップ文法: ● = 利用可 ok / ○ = 要対応 warn or 無効 faint)
# ---------------------------------------------------------------------------

ChipKind = Literal["ok", "warn", "err", "info", "neutral", "muted", "accent"]

_CHIP_PALETTE: dict[str, tuple[str, str, str]] = {
    # kind: (背景, 文字, border) — soft 地 + 同系 border
    "ok": (OK_SOFT, OK, OK_BORDER),  # installed / API ready / 完了
    "warn": (WARN_SOFT, WARN, WARN_BORDER),  # needs key / 要対応
    "err": (ERR_SOFT, ERR, ERR_BORDER),  # failed
    "info": (INFO_SOFT, INFO, INFO_BORDER),  # 実行中
    "neutral": (PAPER_SHADE, INK_SOFT, LINE),  # 待機 / queued
    "muted": (PAPER_SHADE, INK_FAINT, LINE),  # 無効 / discontinued / 中止
    "accent": (ACCENT_SOFT, ACCENT_HOVER, ACCENT_BORDER),  # タグチップ / multi バッジ
}


def chip_qss(kind: ChipKind) -> str:
    """ステータスチップ用の QLabel QSS を返す。

    Args:
        kind: チップ種別。利用可 = "ok"、要対応 = "warn"、失敗 = "err"、
            実行中 = "info"、待機 = "neutral"、無効/中止 = "muted"、
            タグ/マルチ強調 = "accent"。

    Returns:
        soft 地 + 同系 border + 角丸 10px の QLabel スタイル文字列。
    """
    bg, fg, border = _CHIP_PALETTE[kind]
    return (
        f"QLabel {{ background-color: {bg}; color: {fg}; border: 1px solid {border};"
        f" border-radius: {RADIUS_CHIP}px; padding: 1px 9px;"
        f" font-size: {FONT_SIZE_SMALL}px; font-weight: 600; }}"
    )


def badge_qss() -> str:
    """種別バッジ (mock .badge-type) 用の QLabel QSS を返す。

    provider 名や job 種別などの中立的なメタ情報表示に使う。

    Returns:
        paper-shade 地 + line border + 小角丸の QLabel スタイル文字列。
    """
    return (
        f"QLabel {{ background-color: {PAPER_SHADE}; color: {INK_SOFT};"
        f" border: 1px solid {LINE}; border-radius: 3px; padding: 1px 6px;"
        f" font-size: {FONT_SIZE_SMALL}px; font-weight: 500; }}"
    )


def tag_chip_untranslated_qss() -> str:
    """翻訳が存在しないタグ chip 用の QLabel QSS を返す。

    表示言語に翻訳が無く英語原文へフォールバックしたタグを、点線 border +
    faint 文字色で視覚的に区別する (DS wireframe v12 TagChip: borderStyle dashed)。

    Returns:
        paper-shade 地 + 点線 border + faint 文字の chip スタイル文字列。
    """
    return (
        f"QLabel {{ background-color: {PAPER_SHADE}; color: {INK_FAINT};"
        f" border: 1px dashed {LINE}; border-radius: {RADIUS_CHIP}px; padding: 1px 9px;"
        f" font-size: {FONT_SIZE_SMALL}px; font-weight: 600; }}"
    )


# ジョブ状態 → トークン色 (実行中=info / 待機=灰 / 完了=ok / 失敗=err / 中止=灰)
_JOB_STATUS_COLORS: dict[str, str] = {
    "submitted": INFO,
    "validating": INFO,
    "running": INFO,
    "canceling": INFO,
    "queued": INK_SOFT,
    "waiting": INK_SOFT,
    "pending": INK_SOFT,
    "completed": OK,
    "imported": OK,
    "done": OK,
    "failed": ERR,
    "error": ERR,
    "canceled": INK_FAINT,
    "cancelled": INK_FAINT,
    "expired": INK_FAINT,
}


def job_status_color(status: str) -> str:
    """ジョブ状態文字列に対応するトークン色 hex を返す。

    Args:
        status: ジョブ状態 (例: "running", "completed", "failed")。

    Returns:
        対応するトークン色。未知の状態は補助テキスト色 (INK_SOFT)。
    """
    return _JOB_STATUS_COLORS.get(status.lower(), INK_SOFT)


# 半透明スクリム (ページロード中オーバーレイ等)。token palette 外だが一元管理する。
LOADING_OVERLAY_QSS = "background-color: rgba(26, 26, 26, 120); color: white; font-weight: bold;"

# 完了状態のプログレスバー chunk を ok 色へ切り替える追加 QSS
PROGRESS_CHUNK_OK_QSS = f"QProgressBar::chunk {{ background-color: {OK}; }}"

# ---------------------------------------------------------------------------
# グローバル QSS
# ---------------------------------------------------------------------------


def build_global_qss() -> str:
    """Theme v1 のグローバル QSS 文字列を生成する。

    フォント family/size はウィジェット個別の ``QFont`` 指定 (monospace ラベル等)
    を壊さないよう QSS には含めず、``QApplication.setFont()`` 側で設定する。

    Returns:
        ``QApplication.setStyleSheet()`` に渡す QSS 文字列。
    """
    return f"""
/* === LoRAIro Theme v1 — SSoT: docs/design/theme-v1/hifi-mock.html === */

QMainWindow, QDialog {{
    background-color: {PAPER};
}}
QWidget {{
    color: {INK};
}}
QWidget:disabled {{
    color: {INK_FAINT};
}}
QLabel {{
    background: transparent;
}}

/* --- ナビタブ (mock .nav): アクティブ = accent 下線 + 太字 --- */
QTabWidget::pane {{
    border: 1px solid {LINE};
    background-color: {PAPER};
    top: -1px;
}}
QTabBar {{
    background: {PAPER_SHADE};
}}
QTabBar::tab {{
    background: transparent;
    color: {INK_SOFT};
    padding: 7px {SPACE_4}px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{
    color: {INK};
}}
QTabBar::tab:selected {{
    color: {INK};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
    background: {PAPER};
}}

/* --- ボタン (mock .btn) --- */
QPushButton {{
    background-color: {CARD};
    color: {INK};
    border: 1px solid {LINE_STRONG};
    border-radius: {RADIUS}px;
    padding: {SPACE_1}px {SPACE_3}px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_SOFT};
}}
QPushButton:disabled {{
    background-color: {PAPER_SHADE};
    color: {INK_FAINT};
    border-color: {LINE};
}}
QPushButton:default {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton:default:hover {{
    background-color: {ACCENT_HOVER};
    color: #ffffff;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS}px;
    padding: 2px 6px;
}}
QToolButton:hover {{
    background-color: {PAPER_SHADE};
    border-color: {LINE_STRONG};
}}

/* --- 入力欄 (mock .input) --- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QDateTimeEdit, QTimeEdit {{
    background-color: {CARD};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: {RADIUS}px;
    padding: 3px {SPACE_2}px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {PAPER_SHADE};
    color: {INK_FAINT};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    color: {INK};
    border: 1px solid {LINE};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}

/* --- テーブル / ツリー / リスト (mock .tbl) --- */
QTableView, QTreeView, QListView, QListWidget {{
    background-color: {CARD};
    alternate-background-color: {PAPER};
    color: {INK};
    border: 1px solid {LINE};
    gridline-color: {LINE};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}
QTableView::item:hover, QTreeView::item:hover, QListView::item:hover {{
    background-color: {PAPER_SHADE};
}}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {INK};
}}
QHeaderView::section {{
    background-color: {PAPER_SHADE};
    color: {INK_SOFT};
    border: none;
    border-bottom: 1px solid {LINE_STRONG};
    padding: {SPACE_1}px {SPACE_2}px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background-color: {PAPER_SHADE};
    border: none;
    border-bottom: 1px solid {LINE_STRONG};
}}

/* --- スクロールバー --- */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {LINE_STRONG};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {LINE_STRONG};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {INK_FAINT};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* --- グループボックス (mock .card) --- */
QGroupBox {{
    background-color: {CARD};
    border: 1px solid {LINE};
    border-radius: {RADIUS}px;
    margin-top: {SPACE_2}px;
    padding-top: {SPACE_2}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACE_2}px;
    padding: 0 {SPACE_1}px;
    color: {INK};
    font-weight: 600;
}}

/* --- ツールチップ / メニュー --- */
QToolTip {{
    background-color: {CARD};
    color: {INK};
    border: 1px solid {LINE_STRONG};
    padding: {SPACE_1}px 6px;
}}
QMenu {{
    background-color: {CARD};
    color: {INK};
    border: 1px solid {LINE};
}}
QMenu::item {{
    padding: {SPACE_1}px 20px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {INK};
}}
QMenu::separator {{
    height: 1px;
    background: {LINE};
    margin: {SPACE_1}px {SPACE_2}px;
}}
QMenuBar {{
    background-color: {PAPER_SHADE};
    color: {INK};
}}
QMenuBar::item:selected {{
    background-color: {ACCENT_SOFT};
}}

/* --- プログレスバー (mock .prog): 進行 = info 色 --- */
QProgressBar {{
    background-color: {PAPER_SHADE};
    border: 1px solid {LINE};
    border-radius: {SPACE_1}px;
    text-align: center;
    color: {INK_SOFT};
    font-size: {FONT_SIZE_SMALL}px;
}}
QProgressBar::chunk {{
    background-color: {INFO};
    border-radius: 3px;
}}

/* --- その他 --- */
QStatusBar {{
    background-color: {PAPER_SHADE};
    border-top: 1px solid {LINE};
}}
QSplitter::handle {{
    background-color: {LINE};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
"""


def _build_light_palette() -> QPalette:
    """Theme v1 のフル light パレットを構築する。

    Windows ダークモード等、OS テーマが優先されるケースで QSS が届かない
    ウィジェット（コンテナ背景等）のフォールバックとして機能する。
    """
    p = QPalette()

    roles_light: list[tuple[QPalette.ColorRole, str]] = [
        (QPalette.ColorRole.Window, PAPER),
        (QPalette.ColorRole.WindowText, INK),
        (QPalette.ColorRole.Base, CARD),
        (QPalette.ColorRole.AlternateBase, PAPER),
        (QPalette.ColorRole.Text, INK),
        (QPalette.ColorRole.BrightText, "#ffffff"),
        (QPalette.ColorRole.Button, PAPER_SHADE),
        (QPalette.ColorRole.ButtonText, INK),
        (QPalette.ColorRole.Highlight, ACCENT_SOFT),
        (QPalette.ColorRole.HighlightedText, INK),
        (QPalette.ColorRole.Link, ACCENT),
        (QPalette.ColorRole.LinkVisited, ACCENT_HOVER),
        (QPalette.ColorRole.ToolTipBase, CARD),
        (QPalette.ColorRole.ToolTipText, INK),
        (QPalette.ColorRole.PlaceholderText, INK_FAINT),
        (QPalette.ColorRole.Mid, LINE),
        (QPalette.ColorRole.Midlight, PAPER_SHADE),
        (QPalette.ColorRole.Light, "#ffffff"),
        (QPalette.ColorRole.Dark, LINE_STRONG),
        (QPalette.ColorRole.Shadow, LINE_STRONG),
    ]

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, hex_color in roles_light:
            p.setColor(group, role, QColor(hex_color))

    roles_disabled: list[tuple[QPalette.ColorRole, str]] = [
        (QPalette.ColorRole.Window, PAPER_SHADE),
        (QPalette.ColorRole.WindowText, INK_FAINT),
        (QPalette.ColorRole.Base, PAPER_SHADE),
        (QPalette.ColorRole.Text, INK_FAINT),
        (QPalette.ColorRole.Button, PAPER_SHADE),
        (QPalette.ColorRole.ButtonText, INK_FAINT),
        (QPalette.ColorRole.Highlight, PAPER_SHADE),
        (QPalette.ColorRole.HighlightedText, INK_FAINT),
    ]
    for role, hex_color in roles_disabled:
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(hex_color))

    return p


def apply_theme(app: QApplication) -> None:
    """Theme v1 を QApplication に適用する。

    Windows ダークモード等の OS テーマを Fusion スタイルで切り離し、
    light パレットを明示した上でグローバル QSS を上乗せする。

    Args:
        app: 適用対象の QApplication。
    """
    # Fusion スタイルはプラットフォーム固有 UI を描画せず OS ダークモードを無視する。
    # これにより QSS が全ウィジェットで一貫して機能する。
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)

    app.setPalette(_build_light_palette())
    app.setStyleSheet(build_global_qss())
    logger.info("Theme v1 グローバル QSS を適用しました (Fusion style)")
