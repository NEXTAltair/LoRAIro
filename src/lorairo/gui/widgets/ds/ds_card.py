"""DS Card surface ウィジェット (Issue #852)。

claude.ai/design data/Card に対応する汎用カード面を提供する。
白地・hairline border・角丸を持ち、任意の見出し行と本体エリアで構成される。
スタイルはすべて ``lorairo.gui.theme`` のトークンを使用し、ハードコード値は持たない。
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lorairo.gui import theme


class DsCard(QFrame):
    """DS の Card surface (claude.ai/design data/Card に対応)。

    白地・hairline border・角丸を持つカード面ウィジェット。
    任意の見出し行 (title テキスト + 右端 aside ウィジェット) と
    本体エリア (:meth:`set_body` で差し替え可能) で構成される。

    スタイルトークン:
        - 地: ``theme.CARD``
        - border: ``theme.LINE`` / ``theme.BORDER_WIDTH``
        - 見出し: ``theme.FONT_SIZE_H2`` + ``theme.FONT_WEIGHT_SEMIBOLD``
        - 角丸: ``theme.RADIUS``
        - 余白: ``theme.SPACE_3`` (外側) / ``theme.SPACE_2`` (行間)
    """

    def __init__(
        self,
        title: str | None = None,
        aside: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """DsCard を初期化する。

        Args:
            title: 見出し行に表示するテキスト。None の場合は見出し行を非表示。
            aside: 見出し行の右端に配置するウィジェット。None の場合は非表示。
            parent: 親ウィジェット。
        """
        super().__init__(parent)

        # QFrame 組み込みの枠描画を無効化し、QSS のみで制御する
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._apply_card_style()

        # メインレイアウト (見出し行 + ボディエリア)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(theme.SPACE_3, theme.SPACE_3, theme.SPACE_3, theme.SPACE_3)
        self._main_layout.setSpacing(theme.SPACE_2)

        # 見出し行を事前に None で初期化 (型注釈の一元管理)
        self._title_label: QLabel | None = None

        # 見出し行 — title / aside どちらかが有る場合のみ構築
        if title is not None or aside is not None:
            self._build_header(title, aside)

        # ボディエリア (set_body() で差し替え)
        self._body_widget: QWidget | None = None

    def _apply_card_style(self) -> None:
        """カードの QSS をテーマトークンのみで設定する。

        DsCard クラスにスコープした QSS を使い、子ウィジェットへの意図しない
        継承を防ぐ。
        """
        self.setStyleSheet(
            f"DsCard {{"
            f" background-color: {theme.CARD};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" border-radius: {theme.RADIUS}px;"
            f"}}"
        )

    def _build_header(self, title: str | None, aside: QWidget | None) -> None:
        """見出し行 (title ラベル + 右端 aside) を構築してメインレイアウトに追加する。

        Args:
            title: 見出しテキスト。None の場合はラベルを生成しない。
            aside: 右端に配置するウィジェット。None の場合は配置しない。
        """
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(theme.SPACE_2)

        if title is not None:
            # セミボールド H2 フォント (FONT_SIZE_H2=14px / FONT_WEIGHT_SEMIBOLD=600)
            self._title_label = QLabel(title, self)
            self._title_label.setObjectName("dsCardTitle")
            title_font = self._title_label.font()
            title_font.setPixelSize(theme.FONT_SIZE_H2)
            title_font.setWeight(QFont.Weight(theme.FONT_WEIGHT_SEMIBOLD))
            self._title_label.setFont(title_font)
            self._title_label.setStyleSheet(f"color: {theme.INK}; border: none; background: transparent;")
            header_row.addWidget(self._title_label)

        # aside を右端に押し込むストレッチ
        header_row.addStretch(1)

        if aside is not None:
            aside.setParent(self)
            header_row.addWidget(aside)

        self._main_layout.addLayout(header_row)

    def set_body(self, widget: QWidget) -> None:
        """カード本体に widget を載せる。

        既存のボディが有る場合はレイアウトから取り除き非表示にしてから
        新しい widget を追加する。

        Args:
            widget: カード本体に表示するウィジェット。
        """
        if self._body_widget is not None:
            # 既存ボディをレイアウトから除去して非表示にする
            self._main_layout.removeWidget(self._body_widget)
            self._body_widget.hide()

        widget.setParent(self)
        self._main_layout.addWidget(widget)
        self._body_widget = widget
