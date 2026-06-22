"""DS v12 AnnotateScreen の「送信前プリフライト」card (表示専用)。

ステージング集合の **既存 rating** から、annotation WebAPI へ送信可能な枚数
(送信可 / sendable) と X/XXX で保留する枚数 (保留 / held)、まだ rating が無く
moderation 行きになる枚数 (未判定) を集計表示する。

このカードは moderation を実行しない。実際の送信前 moderation は
``ModerationPreflightService`` が担い、本 widget は同じ分類境界
(``SENDABLE_RATINGS`` / ``HELD_RATINGS``) を共有して概算を見せるだけ。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.services.moderation_preflight_service import HELD_RATINGS, SENDABLE_RATINGS

_TITLE_TEXT = "送信前プリフライト — OpenAI Moderations で rating 判定"
# DS preflight card の説明文 (X / XXX を ink 強調)。
_DESCRIPTION_HTML = (
    "API へ送る画像は先に moderation で canonical rating を付与。"
    f"<b style='color:{theme.INK};'>X / XXX は annotation API に送らない</b>"
    "（PG/PG-13/R は送信）。violence/graphic は R 止まり。"
)
_PLACEHOLDER_TEXT = "ステージング画像なし"
_BADGE_TEXT = "task_type=rating_preflight"
_HELD_TOOLTIP = "最新 rating が X / XXX の画像は annotation WebAPI に送らず保留します"
_UNRATED_TOOLTIP = "rating 未登録の画像。送信前 moderation で判定してから送信可否が決まります"


@dataclass(frozen=True)
class PreflightSummary:
    """ステージング集合の rating 分類結果。"""

    sendable: int
    held: int
    unrated: int

    @property
    def total(self) -> int:
        return self.sendable + self.held + self.unrated


def _normalize_rating(value: str | None) -> str:
    """rating を strip + upper して照合用に正規化する。"""
    return value.strip().upper() if isinstance(value, str) and value.strip() else ""


def classify_preflight_counts(
    ratings_by_id: dict[int, str | None], staged_image_ids: list[int]
) -> PreflightSummary:
    """ステージング集合を送信可 / 保留 / 未判定 に分類して件数を返す。

    Args:
        ratings_by_id: ``{image_id: 最新 normalized_rating}``。rating 未登録の
            image_id は含まれない (= 未判定 扱い)。
        staged_image_ids: ステージング集合の image_id 一覧。

    Returns:
        分類件数を保持する :class:`PreflightSummary`。
    """
    sendable = held = unrated = 0
    for image_id in staged_image_ids:
        rating = _normalize_rating(ratings_by_id.get(image_id))
        if rating in HELD_RATINGS:
            held += 1
        elif rating in SENDABLE_RATINGS:
            sendable += 1
        else:
            unrated += 1
    return PreflightSummary(sendable=sendable, held=held, unrated=unrated)


class PreflightSummaryWidget(QWidget):
    """DS v12 AnnotateScreen の送信前プリフライト card (表示専用)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACE_1)

        title = QLabel(_TITLE_TEXT, self)
        title.setObjectName("preflightTitleLabel")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {theme.INK}; font-size: {theme.FONT_SIZE_BASE}px;")
        layout.addWidget(title)

        self._description_label = QLabel(self)
        self._description_label.setObjectName("preflightDescriptionLabel")
        self._description_label.setTextFormat(Qt.TextFormat.RichText)
        self._description_label.setText(_DESCRIPTION_HTML)
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        layout.addWidget(self._description_label)

        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, theme.SPACE_1, 0, 0)
        chip_row.setSpacing(theme.SPACE_2)

        self._sendable_chip = QLabel(self)
        self._sendable_chip.setObjectName("preflightSendableChip")
        self._sendable_chip.setStyleSheet(theme.chip_qss("ok"))
        chip_row.addWidget(self._sendable_chip)

        self._held_chip = QLabel(self)
        self._held_chip.setObjectName("preflightHeldChip")
        self._held_chip.setStyleSheet(theme.chip_qss("warn"))
        self._held_chip.setToolTip(_HELD_TOOLTIP)
        chip_row.addWidget(self._held_chip)

        # 未判定 (rating 未登録) は 0 件のとき非表示にする。
        self._unrated_chip = QLabel(self)
        self._unrated_chip.setObjectName("preflightUnratedChip")
        self._unrated_chip.setStyleSheet(theme.chip_qss("neutral"))
        self._unrated_chip.setToolTip(_UNRATED_TOOLTIP)
        chip_row.addWidget(self._unrated_chip)

        self._badge = QLabel(_BADGE_TEXT, self)
        self._badge.setObjectName("preflightTypeBadge")
        self._badge.setStyleSheet(theme.badge_qss())
        chip_row.addWidget(self._badge)

        chip_row.addStretch(1)
        self._chip_row = chip_row
        layout.addLayout(chip_row)

        self._placeholder_label = QLabel(_PLACEHOLDER_TEXT, self)
        self._placeholder_label.setObjectName("preflightPlaceholderLabel")
        self._placeholder_label.setStyleSheet(f"color: {theme.INK_FAINT};")
        layout.addWidget(self._placeholder_label)

        layout.addStretch(1)

        self.clear()

    def display(self, ratings_by_id: dict[int, str | None], staged_image_ids: list[int]) -> None:
        """ステージング集合の rating から送信可 / 保留 / 未判定 を再描画する。"""
        if not staged_image_ids:
            self.clear()
            return

        summary = classify_preflight_counts(ratings_by_id, staged_image_ids)
        self._placeholder_label.setVisible(False)

        self._sendable_chip.setText(f"{summary.sendable} 送信可 sendable")
        self._sendable_chip.setVisible(True)
        self._held_chip.setText(f"{summary.held} 保留 held")
        self._held_chip.setVisible(True)
        self._unrated_chip.setText(f"{summary.unrated} 未判定")
        self._unrated_chip.setVisible(summary.unrated > 0)
        self._badge.setVisible(True)

    def clear(self) -> None:
        """「ステージング画像なし」プレースホルダ状態に切り替える。"""
        self._sendable_chip.setVisible(False)
        self._held_chip.setVisible(False)
        self._unrated_chip.setVisible(False)
        self._badge.setVisible(False)
        self._placeholder_label.setVisible(True)
