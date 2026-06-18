from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))


def _make_panel_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: bold;")
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return label


def _make_placeholder(text: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return widget


def _get_mock_image_paths(limit: int = 6) -> list[Path]:
    img_dir = ROOT / "tests" / "resources" / "img" / "1_img"
    if not img_dir.exists():
        return []
    return list(img_dir.glob("*.webp"))[:limit]


def _build_mock_thumbnail_grid() -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    image_paths = _get_mock_image_paths()
    if not image_paths:
        layout.addWidget(_make_placeholder("画像サンプルが見つかりません"), 0, 0)
        return widget

    columns = 3
    thumb_size = QSize(120, 120)
    for index, path in enumerate(image_paths):
        row = index // columns
        col = index % columns
        item = QLabel()
        item.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            item.setPixmap(pixmap.scaled(thumb_size, Qt.AspectRatioMode.KeepAspectRatio))
        item.setToolTip(path.name)
        layout.addWidget(item, row, col)
    return widget


def _build_staging_panel() -> QWidget:
    group = QGroupBox("ステージング")
    layout = QVBoxLayout(group)
    list_widget = QListWidget()
    list_widget.setMinimumHeight(80)
    list_widget.setMaximumHeight(220)
    list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    image_paths = _get_mock_image_paths(limit=4)
    for path in image_paths:
        item = QListWidgetItem(path.name)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            icon = QIcon(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
            item.setIcon(icon)
        list_widget.addItem(item)
    _adjust_staging_height(list_widget)
    layout.addWidget(list_widget)
    layout.addWidget(QPushButton("選択中の画像を追加"))
    return group


def _adjust_staging_height(list_widget: QListWidget) -> None:
    rows = list_widget.count()
    if rows == 0:
        return
    row_height = list_widget.sizeHintForRow(0)
    header_padding = 16
    target = rows * row_height + header_padding
    min_h = list_widget.minimumHeight()
    max_h = list_widget.maximumHeight()
    list_widget.setMinimumHeight(max(min_h, min(target, max_h)))


def _build_thumbnail_panel() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    layout.addWidget(_make_panel_title("サムネイル"))
    layout.addWidget(_build_mock_thumbnail_grid())

    staging_container = QWidget()
    staging_layout = QVBoxLayout(staging_container)
    staging_layout.setContentsMargins(0, 0, 0, 0)
    staging_layout.setSpacing(6)
    staging_layout.addWidget(_build_staging_panel())
    staging_group = QGroupBox("ステージング状況")
    staging_info_layout = QVBoxLayout(staging_group)
    staging_info_layout.addWidget(QLabel("編集対象: 0 件"))
    staging_info_layout.addWidget(QLabel("アノテーション対象: 0 件"))
    staging_layout.addWidget(staging_group)
    layout.addWidget(staging_container)

    layout.setStretch(1, 3)
    layout.setStretch(2, 1)
    return frame


# --- Wireframes v12 Frame 1 (Search) 寄せ用の手書き調トークン (theme.py と同値) ---
_INK = "#1a1a1a"
_INK_FAINT = "#9a9a9a"
_ACCENT = "#c25e3f"
_ACCENT_SOFT = "#f6e3dc"
_PAPER_SHADE = "#f1efe6"
_LINE = "#d9d4c7"


def _chip(text: str, *, bg: str = _PAPER_SHADE, fg: str = _INK, border: str = _LINE) -> QLabel:
    """ワイヤー風の chip ラベル (token / facet 件数 / バッジ用)。"""
    chip = QLabel(text)
    chip.setStyleSheet(
        f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {border};"
        f" border-radius: 3px; padding: 1px 7px; font-size: 11px; }}"
    )
    return chip


def _build_masthead() -> QWidget:
    """Frame 1 の masthead: タイトル + サブ + DRAFT スタンプ。"""
    frame = QFrame()
    frame.setObjectName("mockMasthead")
    frame.setStyleSheet(f"#mockMasthead {{ border-bottom: 2px solid {_INK}; }}")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(14, 10, 14, 8)
    layout.setSpacing(10)

    title = QLabel("LoRAIro")
    title.setStyleSheet("font-size: 30px; font-weight: 700; letter-spacing: -0.5px;")
    layout.addWidget(title)

    sub = QLabel("LoRA 学習用データセットを、品質を保証しながら作る道具")
    sub.setStyleSheet(f"color: {_INK}; font-size: 11px;")
    layout.addWidget(sub)
    layout.addStretch(1)

    stamp = QLabel("v12 · DRAFT")
    stamp.setStyleSheet(
        f"border: 1px solid {_ACCENT}; color: {_ACCENT}; padding: 2px 8px;"
        f" font-size: 10px; letter-spacing: 0.12em;"
    )
    layout.addWidget(stamp)
    return frame


def _build_project_line() -> QWidget:
    """project 名 + 画像総数 + stage 件数の 1 行。"""
    frame = QFrame()
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(14, 2, 14, 2)
    layout.setSpacing(8)
    layout.addWidget(QLabel("project: shiba_v3"))
    count = QLabel("· 12,480 images")
    count.setStyleSheet(f"color: {_INK_FAINT};")
    layout.addWidget(count)
    layout.addStretch(1)
    layout.addWidget(_chip("📥 stage 9", bg=_ACCENT_SOFT, border=_ACCENT))
    return frame


def _build_registration_summary() -> QWidget:
    """登録完了サマリ band (✕ で閉じるまで残る想定)。"""
    frame = QFrame()
    frame.setObjectName("mockRegSummary")
    frame.setStyleSheet(f"#mockRegSummary {{ border: 1px solid {_LINE}; background: {_PAPER_SHADE}; }}")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(12, 6, 10, 6)
    layout.setSpacing(8)
    layout.addWidget(QLabel("✅ 登録完了 — uploads/shiba_batch_07 · 24枚 · 18.2s"))
    layout.addWidget(_chip("新規 9", bg="#e3efe6", border="#bcd8c4"))
    layout.addWidget(_chip("別版 3", bg=_ACCENT_SOFT, border=_ACCENT))
    layout.addWidget(_chip("skip 12"))
    layout.addWidget(_chip("エラー 0"))
    layout.addStretch(1)
    layout.addWidget(QPushButton("✕"))
    return frame


def _build_query_bar() -> QWidget:
    """Frame 1 の統一クエリ棒 (tag / NLQ / rating / quality / score を 1 本に混在)。"""
    frame = QFrame()
    frame.setObjectName("mockQbar")
    frame.setStyleSheet(f"#mockQbar {{ border: 2px solid {_INK}; border-radius: 3px; }}")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(6)
    layout.addWidget(QLabel("⌕"))
    layout.addWidget(_chip("1girl", bg=_ACCENT_SOFT, border=_ACCENT))
    layout.addWidget(_chip("-lowres", fg=_INK_FAINT))
    layout.addWidget(_chip('"桜の下"'))
    layout.addWidget(_chip("rating=PG-13"))
    layout.addWidget(_chip("quality≥good"))
    layout.addWidget(_chip("score(aesthetic)≥0.6"))
    add = QLineEdit()
    add.setPlaceholderText("追加はタイプ…")
    add.setFrame(False)
    layout.addWidget(add, 1)
    matches = QLabel("247 matches")
    matches.setStyleSheet("font-weight: 600;")
    layout.addWidget(matches)
    layout.addWidget(QPushButton("save query"))
    return frame


def _facet_group(title: str, items: list[str]) -> QWidget:
    """facet 1 グループ (見出し + チェック項目)。decision-major の見出し。"""
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(2)
    for item in items:
        layout.addWidget(QCheckBox(item))
    return box


def _build_facet_sidebar() -> QWidget:
    """Frame 1 の facet サイドバー (決定単位を主見出しに、schema 名は従)。"""
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)
    layout.addWidget(_make_panel_title("絞り込み  filters"))
    layout.addWidget(
        _facet_group(
            "アップスケール処理",
            ["any processed 9,120", "RealESRGAN 3,420", "SwinIR 1,810", "none 3,360"],
        )
    )
    layout.addWidget(_facet_group("品質ティア", ["best / high", "good 以上", "normal", "low"]))
    layout.addWidget(_facet_group("scorer 合意", ["全 scorer 一致", "不一致あり"]))
    layout.addWidget(_facet_group("レーティング (source 別)", ["PG", "PG-13", "R", "X / XXX"]))
    layout.addWidget(_facet_group("アノテーション状態", ["手動編集あり", "タグあり", "caption あり"]))
    layout.addWidget(_facet_group("モデル", ["wd-v1-4", "gpt-4o", "aesthetic_shadow_v2"]))
    layout.addWidget(_facet_group("登録日", ["直近 7 日", "直近 30 日", "範囲指定…"]))
    layout.addWidget(_facet_group("エラー状態", ["all", "エラーありのみ", "エラー除外"]))
    layout.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    scroll.setStyleSheet(f"QScrollArea {{ background: {_PAPER_SHADE}; border: none; }}")
    scroll.setMinimumWidth(240)
    return scroll


def _build_search_frame() -> QWidget:
    """Frame 1 (Search): 全幅クエリ棒 + (facet サイドバー | サムネイル)。"""
    frame = QWidget()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(6)
    layout.addWidget(_build_query_bar())

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(_build_facet_sidebar())
    splitter.addWidget(_build_thumbnail_panel())
    splitter.setSizes([260, 880])
    splitter.setStretchFactor(0, 22)
    splitter.setStretchFactor(1, 78)
    layout.addWidget(splitter, 1)
    return frame


def _build_main_tabs() -> QTabWidget:
    tabs = QTabWidget()
    tabs.addTab(_build_search_frame(), "検索")
    for name in ("マップ", "アノテーション", "ジョブ", "結果", "エラー", "エクスポート"):
        tabs.addTab(_make_placeholder(f"{name} (Frame placeholder)"), name)
    return tabs


def _build_main_central() -> QWidget:
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    # Wireframes v12 Frame 1: masthead → project 行 → 登録サマリ → タブ。
    layout.addWidget(_build_masthead())
    layout.addWidget(_build_project_line())
    layout.addWidget(_build_registration_summary())
    layout.addWidget(_build_main_tabs(), 1)
    return central


def main() -> None:
    app = QApplication([])
    # Theme v1 (#760) を適用して紙＋手書き調のワイヤー寄せ外観にする。
    from lorairo.gui.theme import apply_theme

    apply_theme(app)
    window = QMainWindow()
    window.setWindowTitle("LoRAIro Mock — Wireframes v12 Frame 1 (Search)")
    window.setCentralWidget(_build_main_central())
    window.resize(1360, 820)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
