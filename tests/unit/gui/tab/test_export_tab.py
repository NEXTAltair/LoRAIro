"""ExportTabWidget の GUI テスト (Epic #867 / #872 / #896)。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.export_tab import ExportTabWidget
from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget


@pytest.fixture
def service_container() -> Mock:
    container = Mock()
    container.dataset_export_service = Mock()
    return container


@pytest.fixture
def staging_manager() -> StagingStateManager:
    """実 StagingStateManager (メタ解決は Mock DatasetStateManager)。"""
    manager = StagingStateManager()
    dataset_state = Mock()
    dataset_state.get_image_by_id.side_effect = lambda image_id: {
        "stored_image_path": f"/images/{image_id}.png"
    }
    manager.set_dataset_state_manager(dataset_state)
    return manager


@pytest.fixture
def export_tab_with_staging(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> tuple[ExportTabWidget, StagingStateManager]:
    tab = ExportTabWidget(
        service_container=service_container,
        staging_state_manager=staging_manager,
    )
    qtbot.addWidget(tab)
    return tab, staging_manager


@pytest.mark.gui
def test_export_tab_hosts_export_widget(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)

    assert isinstance(widget.export_widget, DatasetExportWidget)
    assert widget.export_widget.parent() is widget


@pytest.mark.gui
def test_set_image_ids_delegates_to_export_widget(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    widget.export_widget.set_image_ids = Mock()

    widget.set_image_ids([4, 5, 6])

    widget.export_widget.set_image_ids.assert_called_once_with([4, 5, 6])


@pytest.mark.gui
def test_export_tab_refreshes_on_staging_change(qtbot, export_tab_with_staging) -> None:
    """staging 変更時に export 対象が自治購読でライブ更新される (#896)。"""
    tab, staging = export_tab_with_staging
    staging.add_image_ids([1, 2, 3])  # staged_images_changed 発火

    assert tab.current_export_ids() == [1, 2, 3]


@pytest.mark.gui
def test_export_tab_refreshes_to_empty_on_staging_clear(qtbot, export_tab_with_staging) -> None:
    """staging クリア時に export 対象も空集合へ同期する (#896, clear は changed([]) も発火)。"""
    tab, staging = export_tab_with_staging
    staging.add_image_ids([1, 2, 3])
    assert tab.current_export_ids() == [1, 2, 3]

    staging.clear()

    assert tab.current_export_ids() == []


@pytest.mark.gui
def test_export_tab_refresh_reads_staging_set(qtbot, export_tab_with_staging) -> None:
    """refresh() は staging 集合を読んで export 対象へ反映する (ADR 0055 安全網, #896)。"""
    tab, staging = export_tab_with_staging
    staging.add_image_ids([7, 8])
    # 直接 set_image_ids で別状態へ汚しても refresh で staging 集合へ戻る
    tab.set_image_ids([99])
    assert tab.current_export_ids() == [99]

    tab.refresh()

    assert tab.current_export_ids() == [7, 8]
