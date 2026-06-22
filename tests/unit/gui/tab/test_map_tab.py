"""MapTabWidget の GUI テスト (Epic #867 / #873)。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.gui.tab.map_tab import MapTabWidget
from lorairo.gui.widgets.tag_cloud_widget import TagCloudWidget


@pytest.fixture
def db_manager() -> MagicMock:
    return MagicMock()


@pytest.mark.gui
def test_map_tab_hosts_tag_cloud_widget(qtbot, db_manager: MagicMock) -> None:
    widget = MapTabWidget(db_manager=db_manager)
    qtbot.addWidget(widget)

    assert isinstance(widget.tag_cloud, TagCloudWidget)
    # TagCloudWidget は MapTabWidget の子として配置される
    assert widget.tag_cloud.parent() is widget


@pytest.mark.gui
def test_map_tab_injects_db_manager_into_tag_cloud(qtbot, db_manager: MagicMock) -> None:
    widget = MapTabWidget(db_manager=db_manager)
    qtbot.addWidget(widget)

    # 注入した db_manager が TagCloudWidget へ渡っている
    assert widget.tag_cloud._db is db_manager


@pytest.mark.gui
def test_map_tab_layout_has_zero_margins(qtbot, db_manager: MagicMock) -> None:
    widget = MapTabWidget(db_manager=db_manager)
    qtbot.addWidget(widget)

    margins = widget.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
