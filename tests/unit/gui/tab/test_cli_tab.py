"""CliTabWidget の GUI テスト (Epic #867 / #873)。"""

from __future__ import annotations

import pytest

from lorairo.gui.tab.cli_tab import CliTabWidget
from lorairo.gui.widgets.cli_reference_widget import CliReferenceWidget


@pytest.mark.gui
def test_cli_tab_hosts_reference_widget(qtbot) -> None:
    widget = CliTabWidget()
    qtbot.addWidget(widget)

    assert isinstance(widget.reference, CliReferenceWidget)
    assert widget.reference.parent() is widget


@pytest.mark.gui
def test_cli_tab_content_is_lazy(qtbot) -> None:
    widget = CliTabWidget()
    qtbot.addWidget(widget)

    # 表示前はコンテンツ未生成 (遅延生成)
    assert widget.reference.content_loaded is False
