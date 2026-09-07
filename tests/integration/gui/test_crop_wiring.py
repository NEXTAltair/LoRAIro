"""検索タブのクロップ配線の統合テスト (#1346)。

実 ``SearchTabWidget`` に実 ``ImageDatabaseManager`` / ``FileSystemManager`` を注入し、
「一覧の右クリック要求 → CropDialogLauncher → 保存 → 一覧 (DatasetStateManager) と
詳細カラムの関連画像への反映」まで、配線が通っていることを確認する。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.domain.crop_request import CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.search_tab import SearchTabWidget
from lorairo.gui.widgets.crop_dialog import CropDialog

PARENT_SIZE = (1600, 1200)


@pytest.fixture
def service_container(fs_manager: FileSystemManager) -> Mock:
    """SearchTabWidget が触る依存だけを満たす ServiceContainer スタブ。"""
    container = Mock()
    container.file_system_manager = fs_manager
    container.db_manager.model_repo.get_model_objects.return_value = []
    container.favorite_filters_service.list_filters.return_value = []
    merged_reader = Mock()
    merged_reader.get_tag_languages.return_value = []
    container.db_manager.annotation_repo.get_merged_reader.return_value = merged_reader
    return container


@pytest.fixture
def parent_image_id(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """クロップ元となる親画像を登録して ID を返す。"""
    source = tmp_path / "wiring_parent.png"
    Image.new("RGB", PARENT_SIZE, (40, 90, 170)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    image_id: int = registered[0]
    return image_id


@pytest.fixture
def dataset_state() -> DatasetStateManager:
    """選択 SSoT (実インスタンス)。"""
    return DatasetStateManager()


@pytest.fixture
def tab(
    qtbot,
    service_container: Mock,
    test_db_manager: ImageDatabaseManager,
    dataset_state: DatasetStateManager,
) -> SearchTabWidget:
    """実 DB を注入した検索タブ。"""
    dataset_state.set_db_manager(test_db_manager)
    widget = SearchTabWidget(
        service_container=service_container,
        db_manager=test_db_manager,
        dataset_state_manager=dataset_state,
        staging_state_manager=StagingStateManager(),
        worker_service=Mock(),
    )
    qtbot.addWidget(widget)
    return widget


def _crop_via_list(qtbot, tab: SearchTabWidget, image_id: int, rect: CropRect) -> tuple[CropDialog, int]:
    """一覧の crop_requested から保存まで実行し、(ダイアログ, 子 ID) を返す。"""
    tab.thumbnail_selector.crop_requested.emit(image_id)
    launcher = tab._crop_dialog_launcher
    assert launcher is not None
    dialogs = [child for child in tab.findChildren(CropDialog) if child.isVisible()]
    assert dialogs, "クロップダイアログが開かれていない"
    dialog = dialogs[-1]
    qtbot.addWidget(dialog)
    dialog.set_rect(rect)
    dialog._on_save()
    child_id = dialog.child_image_id()
    assert child_id is not None
    return dialog, child_id


@pytest.mark.integration
@pytest.mark.gui
def test_crop_entry_points_are_wired(tab: SearchTabWidget) -> None:
    """検索タブでは一覧メニューとプレビューボタンのクロップ導線が有効化される。"""
    assert tab._crop_dialog_launcher is not None
    assert tab.thumbnail_selector._crop_action_enabled is True
    assert tab.image_preview_widget._crop_action_bar.isHidden() is False
    assert tab.selected_image_details_widget._crop_relation_service is not None


@pytest.mark.integration
@pytest.mark.gui
def test_saved_crop_becomes_current_image_with_relation(
    qtbot,
    tab: SearchTabWidget,
    parent_image_id: int,
    dataset_state: DatasetStateManager,
    test_db_manager: ImageDatabaseManager,
) -> None:
    """保存でダイアログが閉じ、作成した子が現在画像として一覧へ反映される。"""
    dialog, child_id = _crop_via_list(
        qtbot, tab, parent_image_id, CropRect(x=100, y=100, width=800, height=600)
    )

    assert dialog.isVisible() is False
    assert dataset_state.current_image_id == child_id
    relation = test_db_manager.get_crop_parent(child_id)
    assert relation is not None
    assert relation.parent_image_id == parent_image_id


@pytest.mark.integration
@pytest.mark.gui
def test_details_related_section_shows_parent_and_children(
    qtbot,
    tab: SearchTabWidget,
    parent_image_id: int,
    dataset_state: DatasetStateManager,
) -> None:
    """詳細カラムから親子双方の関連画像を確認でき、行クリックで遷移する。"""
    _, child_id = _crop_via_list(qtbot, tab, parent_image_id, CropRect(x=0, y=0, width=1024, height=768))
    related = tab.selected_image_details_widget._related_images_widget

    # 子を表示中: 親が 1 件、子は無し
    parent_entry = related.parent_entry()
    assert parent_entry is not None
    assert parent_entry.image_id == parent_image_id
    assert related.child_entries() == []

    # 親へ戻ると、子が 1 件並ぶ
    dataset_state.set_current_image(parent_image_id)
    assert related.parent_entry() is None
    assert [entry.image_id for entry in related.child_entries()] == [child_id]

    # 行クリック相当で子へ遷移する
    tab.selected_image_details_widget.related_image_activated.emit(child_id)
    assert dataset_state.current_image_id == child_id


@pytest.mark.integration
@pytest.mark.gui
def test_recrop_from_preview_creates_grandchild(
    qtbot,
    tab: SearchTabWidget,
    parent_image_id: int,
    test_db_manager: ImageDatabaseManager,
) -> None:
    """プレビュー側の導線からも同じランチャーが動き、子から孫を作れる。"""
    _, child_id = _crop_via_list(qtbot, tab, parent_image_id, CropRect(x=0, y=0, width=1200, height=900))

    tab.image_preview_widget.crop_requested.emit(child_id)
    dialogs = [d for d in tab.findChildren(CropDialog) if d.isVisible()]
    assert dialogs
    dialog = dialogs[-1]
    qtbot.addWidget(dialog)
    dialog.set_rect(CropRect(x=10, y=10, width=300, height=300))
    dialog._on_save()
    grandchild_id = dialog.child_image_id()

    assert grandchild_id is not None
    relation = test_db_manager.get_crop_parent(grandchild_id)
    assert relation is not None
    assert relation.parent_image_id == child_id
