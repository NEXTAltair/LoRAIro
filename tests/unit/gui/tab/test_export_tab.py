"""ExportTabWidget の GUI テスト (Epic #867 / #872)。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from lorairo.gui.tab.export_tab import ExportTabWidget
from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget


@pytest.fixture
def service_container() -> Mock:
    container = Mock()
    container.dataset_export_service = Mock()
    return container


@pytest.mark.gui
def test_export_tab_hosts_export_widget(qtbot, service_container: Mock) -> None:
    widget = ExportTabWidget(service_container=service_container, initial_image_ids=[1, 2])
    qtbot.addWidget(widget)

    assert isinstance(widget.export_widget, DatasetExportWidget)
    assert widget.export_widget.parent() is widget


@pytest.mark.gui
def test_set_image_ids_delegates_to_export_widget(qtbot, service_container: Mock) -> None:
    widget = ExportTabWidget(service_container=service_container, initial_image_ids=[])
    qtbot.addWidget(widget)
    widget.export_widget.set_image_ids = Mock()

    widget.set_image_ids([4, 5, 6])

    widget.export_widget.set_image_ids.assert_called_once_with([4, 5, 6])
