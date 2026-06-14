"""TagCloudWidget の GUI テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui.widgets.tag_cloud_widget import (
    FlowLayout,
    TagCloudWidget,
    _TagCloudLabel,
)
from lorairo.services.tag_cloud_service import CloudResult, TagWeight


def _make_widget(qtbot: pytest.FixtureRequest, result: CloudResult) -> TagCloudWidget:
    """build_cloud をスタブした TagCloudWidget を生成（同期パス）。"""
    widget = TagCloudWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    widget._service = MagicMock()
    widget._service.build_cloud = MagicMock(return_value=result)
    widget._loaded_once = True  # ワーカーを介さず同期で recompute
    return widget


def _sample_result() -> CloudResult:
    return CloudResult(
        entries=[
            TagWeight(tag="long_hair", count=10, weight=1.0),
            TagWeight(tag="smile", count=5, weight=0.5),
            TagWeight(tag="blush", count=2, weight=0.0),
        ],
        matched_images=8,
        total_images=20,
    )


@pytest.mark.unit
@pytest.mark.gui
class TestFlowLayout:
    def test_add_count_take(self, qtbot: pytest.FixtureRequest) -> None:
        container = QWidget()
        qtbot.addWidget(container)
        layout = FlowLayout(container)
        layout.addWidget(QLabel("a"))
        layout.addWidget(QLabel("b"))
        assert layout.count() == 2
        item = layout.takeAt(0)
        assert item is not None
        assert layout.count() == 1
        assert layout.takeAt(5) is None


@pytest.mark.unit
@pytest.mark.gui
class TestTagCloudWidget:
    def test_initial_state_shows_placeholder(self, qtbot: pytest.FixtureRequest) -> None:
        widget = TagCloudWidget(db_manager=MagicMock())
        qtbot.addWidget(widget)
        # キーワード未入力 → クラウドはプレースホルダーラベル1つのみ
        assert widget._cloud_layout.count() == 1
        assert widget._status_label.text() == ""
        assert widget._selected_tags == []

    def test_keyword_builds_cloud(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "hair"
        widget._recompute()
        # 3 エントリ分の _TagCloudLabel が並ぶ
        labels = [widget._cloud_layout.itemAt(i).widget() for i in range(widget._cloud_layout.count())]
        assert all(isinstance(label, _TagCloudLabel) for label in labels)
        assert len(labels) == 3
        assert "該当 8枚" in widget._status_label.text()

    def test_empty_keyword_recompute_shows_placeholder(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "   "
        widget._recompute()
        assert widget._cloud_layout.count() == 1
        widget._service.build_cloud.assert_not_called()

    def test_tag_click_adds_drill_chip_and_recomputes(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "hair"
        widget._recompute()
        widget._on_tag_clicked("smile")
        assert widget._selected_tags == ["smile"]
        # チップが1つ生成される
        assert widget._chip_layout.count() == 1
        # build_cloud が selected_tags 付きで再呼び出し
        widget._service.build_cloud.assert_called_with("hair", ["smile"])

    def test_duplicate_tag_click_ignored(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "hair"
        widget._on_tag_clicked("smile")
        widget._on_tag_clicked("smile")
        assert widget._selected_tags == ["smile"]

    def test_chip_removed_recomputes(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "hair"
        widget._selected_tags = ["smile", "blush"]
        widget._on_chip_removed("smile")
        assert widget._selected_tags == ["blush"]

    def test_reset_clears_state(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword_edit.setText("hair")
        widget._selected_tags = ["smile"]
        widget._on_reset()
        assert widget._keyword == ""
        assert widget._selected_tags == []
        assert widget._keyword_edit.text() == ""
        assert widget._cloud_layout.count() == 1  # placeholder

    def test_reload_refreshes_service(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._keyword = "hair"
        widget._on_reload()
        widget._service.refresh.assert_called_once()

    def test_keyword_change_resets_drilldown(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_result())
        widget._selected_tags = ["smile"]
        widget._on_keyword_changed("eyes")
        assert widget._keyword == "eyes"
        assert widget._selected_tags == []
