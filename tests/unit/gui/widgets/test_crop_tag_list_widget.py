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
