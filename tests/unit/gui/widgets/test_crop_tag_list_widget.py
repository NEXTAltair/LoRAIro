"""ClickableTagListWidget / CropDialog のタグ一覧がスクロール可能であることを固定する (#1339 受け入れ条件 10)。"""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from lorairo.domain.crop_request import CropCreateRequest
from lorairo.gui.widgets.crop_dialog import CropDialog
from lorairo.gui.widgets.crop_tag_list_widget import ClickableTagListWidget

pytestmark = pytest.mark.unit

MANY_TAGS = [f"tag_{index:03d}" for index in range(60)]


def _save_stub(request: CropCreateRequest) -> int:
    return 1


class TestClickableTagListScroll:
    def test_many_tags_in_small_height_are_scrollable(self, qtbot):
        widget = ClickableTagListWidget()
        qtbot.addWidget(widget)
        widget.setFixedSize(240, 80)
        widget.set_tags(MANY_TAGS)
        widget.show()
        qtbot.waitExposed(widget)

        assert widget.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        qtbot.waitUntil(lambda: widget.verticalScrollBar().maximum() > 0, timeout=2000)
        assert widget.tags() == MANY_TAGS

    def test_scroll_reaches_last_tag(self, qtbot):
        widget = ClickableTagListWidget()
        qtbot.addWidget(widget)
        widget.setFixedSize(240, 80)
        widget.set_tags(MANY_TAGS)
        widget.show()
        qtbot.waitExposed(widget)

        widget.scrollToBottom()
        last_item = widget.item(widget.count() - 1)
        assert last_item is not None
        assert widget.visualItemRect(last_item).bottom() <= widget.viewport().height()


class TestClickableTagListLabels:
    """表示ラベルと原文タグの分離 (#1355)。"""

    def test_labels_change_display_while_tags_stay_original(self, qtbot):
        """ラベルを渡すと表示だけ変わり、tags() は原文を返す。"""
        widget = ClickableTagListWidget()
        qtbot.addWidget(widget)

        widget.set_tags(["blue hair", "smile"], {"blue hair": "blue hair / 青い髪"})

        assert widget.labels() == ["blue hair / 青い髪", "smile"]
        assert widget.tags() == ["blue hair", "smile"]

    def test_tag_clicked_emits_original_tag_for_labeled_row(self, qtbot):
        """翻訳ラベル付きの行をクリックしても emit されるのは原文タグ。"""
        widget = ClickableTagListWidget()
        qtbot.addWidget(widget)
        widget.set_tags(["blue hair"], {"blue hair": "blue hair / 青い髪"})
        widget.show()
        qtbot.waitExposed(widget)

        with qtbot.waitSignal(widget.tag_clicked, timeout=2000) as blocker:
            item = widget.item(0)
            assert item is not None
            qtbot.mouseClick(
                widget.viewport(),
                Qt.MouseButton.LeftButton,
                pos=widget.visualItemRect(item).center(),
            )

        assert blocker.args == ["blue hair"]

    def test_labels_are_dropped_when_set_tags_called_without_labels(self, qtbot):
        """ラベルなしで再設定すると原文表示へ戻る。"""
        widget = ClickableTagListWidget()
        qtbot.addWidget(widget)
        widget.set_tags(["blue hair"], {"blue hair": "blue hair / 青い髪"})

        widget.set_tags(["blue hair"])

        assert widget.labels() == ["blue hair"]
        assert widget.tags() == ["blue hair"]


class TestCropDialogTagListsScroll:
    def test_candidate_and_adopted_lists_scroll_with_many_tags(self, qtbot, tmp_path: Path):
        image_path = tmp_path / "parent.png"
        Image.new("RGB", (1600, 1200), (120, 140, 160)).save(image_path)
        dialog = CropDialog(
            image_path=image_path,
            parent_image_id=1,
            candidate_tags=MANY_TAGS,
            parent_rating="PG",
            save_callback=_save_stub,
        )
        qtbot.addWidget(dialog)
        dialog.resize(900, 500)
        dialog.show()
        qtbot.waitExposed(dialog)

        qtbot.waitUntil(lambda: dialog._candidate_list.verticalScrollBar().maximum() > 0, timeout=2000)
        for tag in MANY_TAGS[:40]:
            dialog._on_candidate_clicked(tag)
        qtbot.waitUntil(lambda: dialog._adopted_list.verticalScrollBar().maximum() > 0, timeout=2000)
