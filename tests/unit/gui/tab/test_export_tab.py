"""ExportTabWidget の GUI テスト (Epic #942 #949 / 旧 #867 #872 #896)。

エクスポート前タグ編集パネルへ再構成 (#949): 3ペイン splitter + ExportOverlayBar。
レイアウト構成・ステージング集合の自治同期 (骨格) に加え、ウィジェット間配線
(タグ絞り込み / overlay 受け / DB reject / 選択→プレビュー / スコープ) を検証する。
"""

from __future__ import annotations

from datetime import datetime
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
    # #1106: エクスポート前検証・実在解像度取得はデフォルトで「全て有効」を返す
    # (個別テストで欠落ケースを上書きする)。
    container.dataset_export_service.validate_export_requirements.return_value = {
        "total_images": 0,
        "valid_images": 1,
        "missing_processed": 0,
        "missing_metadata": 0,
        "issues": [],
    }
    container.dataset_export_service.get_available_resolutions.return_value = {}
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
def test_export_tab_refinement_ignore_routes_to_injected_db_manager(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """db_manager 注入時、ignore 保存先がその session factory に追従する (#978)。"""
    db_manager = Mock()
    widget = ExportTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=staging_manager,
    )
    qtbot.addWidget(widget)

    service_container.create_refinement_service.assert_called_once_with(
        db_manager.image_repo.session_factory
    )
    assert (
        widget._selected_image_details_widget._refinement_service
        is service_container.create_refinement_service.return_value
    )


@pytest.mark.gui
def test_export_tab_refinement_falls_back_to_active_db_without_db_manager(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """db_manager 未注入時は container のアクティブ DB プロパティへフォールバックする (#978)。"""
    widget = ExportTabWidget(
        service_container=service_container,
        staging_state_manager=staging_manager,
    )
    qtbot.addWidget(widget)

    service_container.create_refinement_service.assert_not_called()
    assert widget._selected_image_details_widget._refinement_service is service_container.refinement_service


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
    """非表示時の set_image_ids は ID だけ更新し、重い再描画は遅延する。"""
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    widget._populate = Mock()

    widget.set_image_ids([4, 5, 6])

    assert widget.current_export_ids() == [4, 5, 6]
    widget._populate.assert_not_called()
    assert widget._staging_refresh_pending is True


@pytest.mark.gui
def test_hidden_staging_change_populates_once_when_shown(qtbot, export_tab_with_staging) -> None:
    """非表示中に受けた staging 変更は表示時に 1 回だけ反映する (#1272)。"""
    tab, staging = export_tab_with_staging
    tab._populate = Mock()

    staging.add_image_ids([1, 2, 3])

    assert tab.current_export_ids() == [1, 2, 3]
    tab._populate.assert_not_called()

    tab.show()
    qtbot.waitUntil(lambda: tab.isVisible(), timeout=1000)

    tab._populate.assert_called_once_with([1, 2, 3])
    assert tab._staging_refresh_pending is False


@pytest.mark.gui
def test_visible_staging_change_populates_immediately(qtbot, export_tab_with_staging) -> None:
    """表示中の staging 変更は従来通り即時反映する。"""
    tab, staging = export_tab_with_staging
    tab.show()
    qtbot.waitUntil(lambda: tab.isVisible(), timeout=1000)
    tab._populate = Mock()

    staging.add_image_ids([1, 2, 3])

    tab._populate.assert_called_once_with([1, 2, 3])
    assert tab._staging_refresh_pending is False


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
    """エクスポートボタンが出力先選択 → DatasetExportService 経由で書き出すこと (#961 P1)。

    実 QThread を起動すると loguru queued writer + Qt teardown の race で segfault する
    ため、_start_export_worker を同期実行へ差し替えて配線のみを決定的に検証する。
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(
        "lorairo.gui.tab.export_tab.show_warning", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])
    # 実スレッドを起動せず worker.run() を同期実行する。
    monkeypatch.setattr(widget, "_start_export_worker", lambda worker: worker.run())

    widget._overlay_bar._export_btn.click()

    assert export_service.export_with_criteria.called
    # 対象 ID が worker (= criteria) へ正しく渡ること
    _, kwargs = export_service.export_with_criteria.call_args
    assert kwargs.get("format_type") in {"txt", "json"}


@pytest.mark.gui
def test_export_applies_changed_since_filter(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """changed-since 有効時は filter_changed_since の結果だけを worker へ渡す (#962)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(
        "lorairo.gui.tab.export_tab.show_warning", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"
    cutoff = datetime(2026, 6, 28, 10, 30)
    export_service.filter_changed_since.return_value = [2, 3]

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])
    widget._overlay_bar._changed_since_filter.set_filter(True, cutoff)
    monkeypatch.setattr(widget, "_start_export_worker", lambda worker: worker.run())

    widget._overlay_bar._export_btn.click()

    export_service.filter_changed_since.assert_called_once_with([1, 2, 3], cutoff)
    _, kwargs = export_service.export_with_criteria.call_args
    assert kwargs["criteria"].image_ids == [2, 3]


@pytest.mark.gui
def test_export_changed_since_empty_warns_before_directory_dialog(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """changed-since 結果が空なら出力先選択へ進まない (#962)。"""
    from PySide6.QtWidgets import QFileDialog

    warned: list[bool] = []
    monkeypatch.setattr("lorairo.gui.tab.export_tab.show_warning", lambda *a, **k: warned.append(True))
    file_dialog_called: list[bool] = []
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *a, **k: file_dialog_called.append(True) or "",
    )
    export_service = service_container.dataset_export_service
    export_service.filter_changed_since.return_value = []

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])
    widget._overlay_bar._changed_since_filter.set_filter(True, datetime(2026, 6, 28, 10, 30))

    widget._overlay_bar._export_btn.click()

    assert warned == [True]
    assert file_dialog_called == []


@pytest.mark.gui
def test_export_passes_overlay_plan(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """overlay を追加した状態で export すると ExportOverlayPlan が渡ること (#961 P1)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from lorairo.services.export_overlay import ExportOverlayPlan

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])
    widget._overlay_bar.add_overlay_exclude("smile")  # overlay 非空にする
    monkeypatch.setattr(widget, "_start_export_worker", lambda worker: worker.run())

    widget._overlay_bar._export_btn.click()

    _, kwargs = export_service.export_with_criteria.call_args
    assert isinstance(kwargs.get("overlay_plan"), ExportOverlayPlan)


@pytest.mark.gui
def test_empty_overlay_passes_none_plan(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """overlay が空なら overlay_plan=None でレガシー挙動を維持すること (#955 契約)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])  # overlay 未設定
    monkeypatch.setattr(widget, "_start_export_worker", lambda worker: worker.run())

    widget._overlay_bar._export_btn.click()

    _, kwargs = export_service.export_with_criteria.call_args
    assert kwargs.get("overlay_plan") is None


@pytest.mark.gui
def test_populate_clears_stale_current_image(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """staging 変更で消えた画像が current image なら clear されること (#961 P2)。"""
    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    dsm = widget._dataset_state_manager
    dsm.set_current_image(42)
    assert dsm.current_image_id == 42

    # 42 を含まない新集合で populate (db_manager=None なので metadata は空、画像集合だけ評価)
    widget._populate([1, 2, 3])

    assert dsm.current_image_id is None


@pytest.fixture
def wired_tab(qtbot, service_container: Mock, staging_manager: StagingStateManager):
    """db_manager 付きで配線を有効化したタブ (集計・サムネ I/O はスタブ)。

    StagingTagAggregationService は実 DB セッションを使うため、集計 (panel.load_tags) と
    サムネ読込 (load_thumbnails_from_paths) をスタブし、シグナル配線ロジックだけを検証する。
    """
    db_manager = Mock()
    db_manager.get_image_metadata.side_effect = lambda image_id: {
        "id": image_id,
        "stored_image_path": f"/img/{image_id}.png",
    }
    db_manager.soft_reject_tag_batch.return_value = 3
    # current_image_data_changed の co-connected slot (詳細ペイン) が引く DB 取得を空に。
    db_manager.get_rejected_tags.return_value = []
    tab = ExportTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=staging_manager,
    )
    qtbot.addWidget(tab)
    # 実 DB / 実ファイル I/O を避けるためスタブ化 (配線のみ検証)。
    tab._staging_tag_panel.load_tags = Mock()
    tab._thumbnail_selector.load_thumbnails_from_paths = Mock()
    tab._aggregation_service = Mock()
    return tab, db_manager


@pytest.mark.gui
def test_filter_tag_changed_filters_thumbnails_and_scope_counts(qtbot, wired_tab) -> None:
    """左ペインのタグ絞り込みでサムネ再描画 + scope counts 更新 (#949)。"""
    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [2]
    scope_counts: list[tuple[int, int]] = []
    tab._overlay_bar.set_scope_counts = lambda a, f: scope_counts.append((a, f))

    tab._staging_tag_panel.filter_tag_changed.emit("smile")

    tab._aggregation_service.images_with_tag.assert_called_once_with([1, 2, 3], "smile")
    assert tab._filtered_ids == [2]
    assert scope_counts[-1] == (3, 1)


@pytest.mark.gui
def test_filter_reset_restores_all(qtbot, wired_tab) -> None:
    """絞り込みリセット (None) で全 staged に戻る (#949)。"""
    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")
    assert tab._filtered_ids == [2]

    tab._staging_tag_panel.filter_tag_changed.emit(None)

    assert tab._filtered_ids == [1, 2, 3]
    assert tab._active_filter_tag is None


@pytest.mark.gui
def test_overlay_exclude_wired_to_bar(qtbot, wired_tab) -> None:
    """⊘ 出力除外が overlay bar の overlay に反映される (#949)。"""
    tab, _db = wired_tab

    tab._staging_tag_panel.overlay_exclude_requested.emit("smile")

    assert "smile" in tab._overlay_bar.current_overlay().exclude


@pytest.mark.gui
def test_overlay_replace_wired_to_bar(qtbot, wired_tab) -> None:
    """⇄ 置換が overlay bar の overlay に反映される (#949)。"""
    tab, _db = wired_tab

    tab._staging_tag_panel.overlay_replace_requested.emit("girl", "1girl")

    assert tab._overlay_bar.current_overlay().replace.get("girl") == "1girl"


@pytest.mark.gui
def test_db_reject_everywhere_confirmed(qtbot, monkeypatch, wired_tab) -> None:
    """✎ reject(DB): 確認 Yes で全 staged 画像へ batch soft-reject (#949)。"""
    from PySide6.QtWidgets import QMessageBox

    tab, db = wired_tab
    tab.set_image_ids([1, 2, 3])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    tab._staging_tag_panel.db_reject_everywhere_requested.emit("smile")

    db.soft_reject_tag_batch.assert_called_once_with([1, 2, 3], "smile")


@pytest.mark.gui
def test_db_reject_everywhere_cancelled(qtbot, monkeypatch, wired_tab) -> None:
    """✎ reject(DB): 確認 No で DB 操作しない (#949)。"""
    from PySide6.QtWidgets import QMessageBox

    tab, db = wired_tab
    tab.set_image_ids([1, 2, 3])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    tab._staging_tag_panel.db_reject_everywhere_requested.emit("smile")

    db.soft_reject_tag_batch.assert_not_called()


@pytest.mark.gui
def test_selection_updates_overlay_bar_preview(qtbot, wired_tab) -> None:
    """サムネ選択 (DSM 経由) が overlay bar のライブプレビューへ渡る (#949)。"""
    tab, _db = wired_tab
    calls: list[tuple] = []
    tab._overlay_bar.set_selected_image = lambda image_id, db_tags: calls.append((image_id, db_tags))

    tab._dataset_state_manager.current_image_data_changed.emit(
        {"id": 7, "tags": [{"tag": "flower"}, {"tag": "rose"}]}
    )

    assert calls == [(7, ["flower", "rose"])]


@pytest.mark.gui
def test_scope_filtered_keeps_all_export_ids(qtbot, wired_tab) -> None:
    """scope=filtered でもエクスポート対象は全 staged のまま (overlay 適用範囲のみ変わる, Codex P1)。"""
    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")

    tab._overlay_bar.scope_changed.emit("filtered")

    assert tab._scope == "filtered"
    # 非一致の staged 画像も落とさない
    assert tab._effective_export_ids() == [1, 2, 3]


@pytest.mark.gui
def test_overlay_rule_global_when_scope_all(qtbot, wired_tab) -> None:
    """scope=all の overlay rule は全画像適用 (image_ids=None) (#949)。"""
    from lorairo.services.export_overlay import ExportTagOverlay

    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    overlay = ExportTagOverlay(add=["trigger"], exclude=set(), replace={})

    rule = tab._overlay_rule(overlay)

    assert rule.image_ids is None


@pytest.mark.gui
def test_overlay_rule_scoped_when_filtered(qtbot, wired_tab) -> None:
    """scope=filtered の overlay rule は絞り込み一致画像のみへ適用 + export 時 DB 再計算 (Codex P1/P2)。"""
    from lorairo.services.export_overlay import ExportTagOverlay

    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")
    tab._overlay_bar.scope_changed.emit("filtered")
    overlay = ExportTagOverlay(add=["trigger"], exclude=set(), replace={})

    rule = tab._overlay_rule(overlay)
    assert rule.image_ids == {2}

    # 詳細編集で image 2 が tag を失った想定 → export 時の再計算で scope が空になる
    tab._aggregation_service.images_with_tag.return_value = []
    assert tab._overlay_rule(overlay).image_ids == set()


@pytest.mark.gui
def test_filter_preserves_staging_order(qtbot, wired_tab) -> None:
    """絞り込み結果は staging 挿入順を保つ (images_with_tag の set 順崩れに耐える, Codex P3)。"""
    tab, _db = wired_tab
    tab.set_image_ids([3, 1, 2])
    # images_with_tag が順不同 (set 由来) で返しても staging 順 [3,1,2] に整列する
    tab._aggregation_service.images_with_tag.return_value = [2, 3]

    tab._staging_tag_panel.filter_tag_changed.emit("smile")

    assert tab._filtered_ids == [3, 2]


@pytest.mark.gui
def test_inplace_tag_edit_refreshes_filter(qtbot, wired_tab) -> None:
    """詳細ペインで現在画像のタグを編集すると集計/絞り込みが再計算される (Codex P2)。"""
    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [1, 2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")
    # 画像1を選択 (直近プレビュー状態を確立、タグ smile あり)
    tab._dataset_state_manager.current_image_data_changed.emit({"id": 1, "tags": [{"tag": "smile"}]})
    # 実 load_tags の filter リセット副作用を再現
    tab._staging_tag_panel.load_tags = lambda ids: tab._staging_tag_panel.filter_tag_changed.emit(None)

    # in-place 編集: 画像1が smile を失う (同一 image_id でタグ集合変化)。集計は [2] を返す。
    tab._aggregation_service.images_with_tag.return_value = [2]
    tab._dataset_state_manager.current_image_data_changed.emit({"id": 1, "tags": []})

    assert tab._active_filter_tag == "smile"  # 絞り込みは維持
    assert tab._filtered_ids == [2]  # 編集を反映して再計算


@pytest.mark.gui
def test_mere_selection_does_not_refresh_filter(qtbot, wired_tab) -> None:
    """通常の画像選択 (別 image_id) では集計/絞り込みを再計算しない (Codex P2 の誤発火防止)。"""
    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [1, 2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")
    load_calls: list = []
    tab._staging_tag_panel.load_tags = lambda ids: load_calls.append(ids)

    # 別画像の選択 → in-place 編集ではないので再集計しない
    tab._dataset_state_manager.current_image_data_changed.emit({"id": 1, "tags": [{"tag": "smile"}]})
    tab._dataset_state_manager.current_image_data_changed.emit({"id": 2, "tags": [{"tag": "smile"}]})

    assert load_calls == []


@pytest.mark.gui
def test_preview_dedupes_duplicate_tags(qtbot, wired_tab) -> None:
    """ライブプレビューは重複タグ (複数モデル由来) を出現順で unique 化する (Codex P2)。"""
    tab, _db = wired_tab
    calls: list[tuple] = []
    tab._overlay_bar.set_selected_image = lambda image_id, db_tags: calls.append((image_id, db_tags))

    tab._dataset_state_manager.current_image_data_changed.emit(
        {"id": 7, "tags": [{"tag": "smile"}, {"tag": "rose"}, {"tag": "smile"}]}
    )

    assert calls == [(7, ["smile", "rose"])]


@pytest.mark.gui
def test_current_image_cleared_clears_overlay_preview(qtbot, wired_tab) -> None:
    """選択クリアで overlay bar のライブプレビューも空になる (Codex P2)。"""
    tab, _db = wired_tab
    calls: list[tuple] = []
    tab._overlay_bar.set_selected_image = lambda image_id, db_tags: calls.append((image_id, db_tags))

    tab._dataset_state_manager.current_image_cleared.emit()

    assert calls == [(None, [])]


@pytest.mark.gui
def test_db_reject_preserves_active_filter(qtbot, monkeypatch, wired_tab) -> None:
    """DB reject 後もアクティブな絞り込みが維持される (load_tags の filter リセットに耐える, Codex P2)。"""
    from PySide6.QtWidgets import QMessageBox

    tab, _db = wired_tab
    tab.set_image_ids([1, 2, 3])
    tab._aggregation_service.images_with_tag.return_value = [2]
    tab._staging_tag_panel.filter_tag_changed.emit("smile")
    assert tab._active_filter_tag == "smile"
    # 実 StagingTagPanel.load_tags は filter をリセットし filter_tag_changed(None) を同期 emit する。
    # その挙動を stub で再現し、リセットに耐えて絞り込みが復元されることを検証する。
    tab._staging_tag_panel.load_tags = lambda ids: tab._staging_tag_panel.filter_tag_changed.emit(None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    tab._staging_tag_panel.db_reject_everywhere_requested.emit("other")

    assert tab._active_filter_tag == "smile"
    assert tab._filtered_ids == [2]


@pytest.mark.gui
def test_export_requested_without_targets_warns(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """対象が空のエクスポート要求は警告し、出力先選択へ進まないこと。"""
    from PySide6.QtWidgets import QFileDialog

    warned: list[bool] = []
    monkeypatch.setattr("lorairo.gui.tab.export_tab.show_warning", lambda *a, **k: warned.append(True))
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


@pytest.mark.gui
def test_export_blocks_when_no_valid_processed_images(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """#1106: 指定解像度の処理済み画像が 0 枚なら警告して出力先選択へ進まない。"""
    from PySide6.QtWidgets import QFileDialog

    warned: list[bool] = []
    monkeypatch.setattr("lorairo.gui.tab.export_tab.show_warning", lambda *a, **k: warned.append(True))
    file_dialog_called: list[bool] = []
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: file_dialog_called.append(True) or ""
    )
    export_service = service_container.dataset_export_service
    export_service.validate_export_requirements.return_value = {
        "total_images": 3,
        "valid_images": 0,
        "missing_processed": 3,
        "missing_metadata": 0,
        "issues": [],
    }

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])

    widget._overlay_bar._export_btn.click()

    assert warned == [True]
    assert file_dialog_called == []
    assert not export_service.export_with_criteria.called


@pytest.mark.gui
def test_export_confirms_when_some_processed_images_missing(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """#1106: 一部の解像度欠落は続行確認 (No なら中止)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    file_dialog_called: list[bool] = []
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: file_dialog_called.append(True) or ""
    )
    export_service = service_container.dataset_export_service
    export_service.validate_export_requirements.return_value = {
        "total_images": 3,
        "valid_images": 2,
        "missing_processed": 1,
        "missing_metadata": 0,
        "issues": [],
    }

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])

    widget._overlay_bar._export_btn.click()

    assert file_dialog_called == []  # No 選択で中止
    assert not export_service.export_with_criteria.called


@pytest.mark.gui
def test_export_validates_effective_ids_and_resolution(
    qtbot, monkeypatch, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """#1106: 検証は effective_ids と選択解像度で呼ばれ、全 valid なら続行する。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/tmp/export_out")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    export_service = service_container.dataset_export_service
    export_service.export_with_criteria.return_value = "/tmp/export_out"

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    staging_manager.add_image_ids([1, 2, 3])
    monkeypatch.setattr(widget, "_start_export_worker", lambda worker: worker.run())

    widget._overlay_bar._export_btn.click()

    resolution = widget._overlay_bar.selected_resolution()
    export_service.validate_export_requirements.assert_called_with([1, 2, 3], resolution)
    assert export_service.export_with_criteria.called


@pytest.mark.gui
def test_populate_updates_available_resolutions_from_service(
    qtbot, service_container: Mock, staging_manager: StagingStateManager
) -> None:
    """#1106: staging 更新で実在解像度の union が overlay bar に反映される。"""
    export_service = service_container.dataset_export_service
    export_service.get_available_resolutions.return_value = {1: [512, 1024], 2: [1024, 1536]}

    widget = ExportTabWidget(service_container=service_container, staging_state_manager=staging_manager)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitUntil(lambda: widget.isVisible(), timeout=1000)
    staging_manager.add_image_ids([1, 2])

    combo = widget._overlay_bar._resolution_combo
    choices = [combo.itemText(i) for i in range(combo.count())]
    assert choices == ["512", "1024", "1536"]
    export_service.get_available_resolutions.assert_called_with([1, 2])
