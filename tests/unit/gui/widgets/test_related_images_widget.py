"""関連画像 (クロップ親子) セクションの GUI テスト (#1346)。

`RelatedImagesWidget` は DB 非依存の表示専用ウィジェットで、親 / 子の有無に応じた表示と
行クリックの遷移要求 Signal を検証する。詳細カラム側は `CropRelationService` を注入した
ときだけセクションを表示し、`related_image_activated` を再公開することを確認する。
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from sqlalchemy.exc import SQLAlchemyError

from lorairo.gui.widgets.related_images_widget import RelatedImageEntry, RelatedImagesWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

PARENT_ENTRY = RelatedImageEntry(image_id=7, x=10, y=20, width=640, height=480, origin="manual")
CHILD_ENTRIES = [
    RelatedImageEntry(image_id=101, x=0, y=0, width=512, height=512, origin="manual"),
    RelatedImageEntry(image_id=102, x=64, y=64, width=256, height=256, origin="manual"),
]


@pytest.fixture
def widget(qtbot) -> RelatedImagesWidget:
    """関連画像ウィジェット。"""
    instance = RelatedImagesWidget()
    qtbot.addWidget(instance)
    return instance


@pytest.mark.gui
def test_empty_state_shows_none_for_both(widget: RelatedImagesWidget) -> None:
    """親子ともに無ければ「なし」表示で行ボタンは 0 個。"""
    assert widget.parent_entry() is None
    assert widget.child_entries() == []
    assert widget.entry_buttons() == []


@pytest.mark.gui
def test_children_only_lists_each_child(widget: RelatedImagesWidget) -> None:
    """親なし・子ありでは子の行だけが座標付きで並ぶ。"""
    widget.set_related(None, CHILD_ENTRIES)

    assert widget.parent_entry() is None
    assert [entry.image_id for entry in widget.child_entries()] == [101, 102]
    texts = [button.text() for button in widget.entry_buttons()]
    assert texts == [
        "#101  x=0, y=0, 512×512 (manual)",
        "#102  x=64, y=64, 256×256 (manual)",
    ]


@pytest.mark.gui
def test_parent_row_is_listed_before_children(widget: RelatedImagesWidget) -> None:
    """親ありでは親 → 子の順に行が並ぶ。"""
    widget.set_related(PARENT_ENTRY, CHILD_ENTRIES[:1])

    assert widget.parent_entry() == PARENT_ENTRY
    assert [button.text() for button in widget.entry_buttons()] == [
        "#7  x=10, y=20, 640×480 (manual)",
        "#101  x=0, y=0, 512×512 (manual)",
    ]


@pytest.mark.gui
def test_row_click_emits_image_activated(qtbot, widget: RelatedImagesWidget) -> None:
    """行クリックで遷移先 image_id が image_activated に乗る。"""
    widget.set_related(PARENT_ENTRY, CHILD_ENTRIES)

    with qtbot.waitSignal(widget.image_activated, timeout=1000) as blocker:
        qtbot.mouseClick(widget.entry_buttons()[0], Qt.MouseButton.LeftButton)

    assert blocker.args == [7]


@pytest.mark.gui
def test_clear_resets_to_empty_state(widget: RelatedImagesWidget) -> None:
    """clear() で親子表示が「なし」に戻る。"""
    widget.set_related(PARENT_ENTRY, CHILD_ENTRIES)

    widget.clear()

    assert widget.parent_entry() is None
    assert widget.child_entries() == []
    assert widget.entry_buttons() == []


class TestSelectedImageDetailsRelatedSection:
    """詳細カラムへの関連画像セクション統合 (#1346)。"""

    @pytest.fixture
    def details(self, qtbot) -> SelectedImageDetailsWidget:
        """詳細ウィジェット (クロップサービス未配線)。"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.mark.gui
    def test_section_hidden_until_service_injected(self, details: SelectedImageDetailsWidget) -> None:
        """CropRelationService 未配線のタブではセクションを表示しない。"""
        assert details._related_images_widget.isHidden() is True

    @pytest.mark.gui
    def test_service_injection_shows_section_and_populates(
        self, details: SelectedImageDetailsWidget
    ) -> None:
        """サービス配線後は現在画像の親子がセクションへ反映される。"""
        service = Mock()
        service.get_parent.return_value = PARENT_ENTRY
        service.get_children.return_value = CHILD_ENTRIES
        details.set_crop_relation_service(service)

        details._on_image_data_received({"id": 55, "stored_image_path": "dummy.png"})

        assert details._related_images_widget.isHidden() is False
        assert details._related_images_widget.parent_entry() == PARENT_ENTRY
        assert [e.image_id for e in details._related_images_widget.child_entries()] == [101, 102]
        service.get_parent.assert_called_with(55)
        service.get_children.assert_called_with(55)

    @pytest.mark.gui
    def test_row_click_reemitted_as_related_image_activated(
        self, qtbot, details: SelectedImageDetailsWidget
    ) -> None:
        """行クリックは詳細ウィジェットの related_image_activated として再公開される。"""
        service = Mock()
        service.get_parent.return_value = PARENT_ENTRY
        service.get_children.return_value = []
        details.set_crop_relation_service(service)
        details._on_image_data_received({"id": 55, "stored_image_path": "dummy.png"})

        with qtbot.waitSignal(details.related_image_activated, timeout=1000) as blocker:
            qtbot.mouseClick(details._related_images_widget.entry_buttons()[0], Qt.MouseButton.LeftButton)

        assert blocker.args == [7]

    @pytest.mark.gui
    def test_db_error_degrades_to_empty_section(self, details: SelectedImageDetailsWidget) -> None:
        """DB エラーでも詳細表示は落とさず、関連画像だけ「なし」に留める。"""
        service = Mock()
        service.get_parent.side_effect = SQLAlchemyError("boom")
        details.set_crop_relation_service(service)

        details._on_image_data_received({"id": 55, "stored_image_path": "dummy.png"})

        assert details._related_images_widget.parent_entry() is None
        assert details._related_images_widget.child_entries() == []
