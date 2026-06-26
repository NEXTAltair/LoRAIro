"""DsCard ウィジェット単体テスト (Issue #852)。"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui.widgets.ds_card import DsCard

pytestmark = [pytest.mark.unit, pytest.mark.gui]


@pytest.fixture
def card_no_args(qtbot) -> DsCard:
    """title/aside なしの DsCard。"""
    widget = DsCard()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def card_with_title(qtbot) -> DsCard:
    """title のみ指定した DsCard。"""
    widget = DsCard(title="テストカード")
    qtbot.addWidget(widget)
    return widget


class TestDsCardConstruction:
    def test_create_without_title_and_aside(self, card_no_args: DsCard) -> None:
        """title/aside なしで生成できる。"""
        assert card_no_args._title_label is None
        assert card_no_args._body_widget is None

    def test_create_with_title_sets_label_text(self, card_with_title: DsCard) -> None:
        """title を指定すると title ラベルが生成される。"""
        assert card_with_title._title_label is not None
        assert card_with_title._title_label.text() == "テストカード"

    def test_create_with_title_label_has_correct_object_name(self, card_with_title: DsCard) -> None:
        """title ラベルの objectName が dsCardTitle である。"""
        assert card_with_title._title_label is not None
        assert card_with_title._title_label.objectName() == "dsCardTitle"

    def test_create_with_aside_sets_parent(self, qtbot) -> None:
        """aside を指定すると aside の parent が card になる。"""
        aside = QLabel("aside-widget")
        card = DsCard(title="カード", aside=aside)
        qtbot.addWidget(card)
        assert aside.parent() is card

    def test_create_with_aside_only_no_title_is_allowed(self, qtbot) -> None:
        """aside のみ (title=None) でも生成できる。"""
        aside = QLabel("aside-only")
        card = DsCard(aside=aside)
        qtbot.addWidget(card)
        assert card._title_label is None
        assert aside.parent() is card

    def test_initial_body_is_none(self, card_with_title: DsCard) -> None:
        """初期状態ではボディが None である。"""
        assert card_with_title._body_widget is None


class TestDsCardSetBody:
    def test_set_body_adds_widget(self, card_with_title: DsCard, qtbot) -> None:
        """set_body でウィジェットをカード本体に追加できる。"""
        body = QLabel("本体コンテンツ")
        qtbot.addWidget(body)
        card_with_title.set_body(body)
        assert card_with_title._body_widget is body

    def test_set_body_sets_parent_to_card(self, card_no_args: DsCard, qtbot) -> None:
        """set_body 後のウィジェットの parent が card になる。"""
        body = QLabel("body")
        qtbot.addWidget(body)
        card_no_args.set_body(body)
        assert body.parent() is card_no_args

    def test_set_body_replaces_existing_body(self, card_no_args: DsCard, qtbot) -> None:
        """set_body を 2 回呼ぶと既存ボディが新しい widget に置き換わる。"""
        first = QLabel("最初のボディ")
        second = QLabel("次のボディ")
        qtbot.addWidget(first)
        qtbot.addWidget(second)
        card_no_args.set_body(first)
        card_no_args.set_body(second)
        assert card_no_args._body_widget is second

    def test_replaced_body_is_hidden(self, card_no_args: DsCard, qtbot) -> None:
        """set_body で置き換えられた既存ボディは非表示になる。"""
        first = QLabel("最初")
        second = QLabel("次")
        qtbot.addWidget(first)
        qtbot.addWidget(second)
        card_no_args.set_body(first)
        card_no_args.set_body(second)
        assert first.isHidden()

    def test_body_visible_when_card_shown(self, card_no_args: DsCard, qtbot) -> None:
        """card を表示すると set_body で追加したウィジェットが表示される。"""
        body = QLabel("ボディ")
        qtbot.addWidget(body)
        card_no_args.set_body(body)
        card_no_args.show()
        qtbot.waitUntil(lambda: card_no_args.isVisible(), timeout=3000)
        assert not body.isHidden()
