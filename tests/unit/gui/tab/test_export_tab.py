"""ExportTabWidget の GUI テスト (Epic #942 #949 / 旧 #867 #872 #896)。

エクスポート前タグ編集パネルへ再構成 (#949): 3ペイン splitter + ExportOverlayBar。
本テストは骨格 (PR1) を検証する: レイアウト構成・ステージング集合の自治同期。
ウィジェット間配線・エクスポート実行の検証は PR2/PR3 で追加する。
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.export_tab import ExportTabWidget
from lorairo.gui.widgets.export_overlay_bar import ExportOverlayBar
from lorairo.gui.widgets.staging_tag_panel import StagingTagPanel


@pytest.fixture
def service_container() -> Mock:
    container = Mock()
    container.dataset_export_service = Mock()
    # MergedTagReader 無し (None) で構築 → 詳細ウィジェットの言語セレクタ初期化を回避し、
    # ExportOverlayBar は convert スキップで動作する。
    container.db_manager.annotation_repo.get_merged_reader.return_value = None
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
def test_export_tab_builds_three_pane_layout(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """3ペイン splitter + 下部 ExportOverlayBar が構成されること。"""
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)

    # 左/中/右の3ペイン
    assert widget.main_splitter.count() == 3
    assert isinstance(widget.staging_tag_panel, StagingTagPanel)
    assert widget.main_splitter.widget(0) is widget.staging_tag_panel
    assert widget.main_splitter.widget(1) is widget.thumbnail_selector
    assert widget.main_splitter.widget(2) is widget.preview_splitter
    # 右ペインは縦 splitter[プレビュー, 詳細]
    assert widget.preview_splitter.count() == 2
    # 下部 overlay バー
    assert isinstance(widget.overlay_bar, ExportOverlayBar)


@pytest.mark.gui
def test_set_image_ids_updates_current_export_ids(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """set_image_ids がエクスポート対象 ID を更新すること。"""
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)

    widget.set_image_ids([4, 5, 6])

    assert widget.current_export_ids() == [4, 5, 6]


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


@pytest.mark.gui
def test_uses_tab_local_dataset_state_manager(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """選択 SSoT はタブローカルに生成され、共有 manager を汚染しないこと (#961 P1)。"""
    from lorairo.gui.state.dataset_state import DatasetStateManager

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)

    # 内部 DSM は専用インスタンス (検索タブと共有しない)
    assert isinstance(widget._dataset_state_manager, DatasetStateManager)


@pytest.mark.gui
def test_export_requested_runs_worker(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """エクスポートボタンが出力先選択 → DatasetExportService 経由で書き出すこと (#961 P1)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])

    with qtbot.waitSignal(widget._overlay_bar.export_requested, timeout=1000):
        widget._overlay_bar._export_btn.click()
    # worker は別スレッド。export_service が呼ばれるまで待つ。
    qtbot.waitUntil(lambda: export_service.export_with_criteria.called, timeout=3000)

    assert export_service.export_with_criteria.called


@pytest.mark.gui
def test_export_requested_without_targets_warns(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """対象が空のエクスポート要求は警告し、出力先選択へ進まないこと。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    warned: list[bool] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(True))
    file_dialog_called: list[bool] = []
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *a, **k: file_dialog_called.append(True) or "",
    )

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)  # staging 空

    widget._overlay_bar._export_btn.click()

    assert warned == [True]
    assert file_dialog_called == []
