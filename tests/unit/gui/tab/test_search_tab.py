"""SearchTabWidget の GUI テスト (Epic #867 / #869)。

MainWindow から SearchTabWidget へ移送した責務 (データセット選択バー・DB 検索起動・
サムネ → プレビュー配線・選択 → 詳細反映・rating/score 編集・3 ペイン splitter の
orientation 維持 (#865)・パネルトグル・入口 Signal・MainWindow 連携スロット) を、実
``SearchTabWidget`` インスタンス相手に検証する。

移送元: 旧 ``WidgetSetupService`` / ``MainWindow`` の検索タブ配線
(``tests/unit/gui/services/test_widget_setup_service.py`` は #869 で削除)。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.search_tab import SearchTabWidget
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.gui.widgets.image_preview import ImagePreviewWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget


@pytest.fixture
def service_container() -> Mock:
    """SearchFilterService 生成 / merged reader / favorite filters を満たす最小 ServiceContainer。"""
    container = Mock()
    # ModelSelectionService.create(db_repository=...).load_models() が空で済むよう repo を固定
    container.db_manager.model_repo.get_model_objects.return_value = []
    # SelectedImageDetailsWidget へ注入する MergedTagReader (言語セレクタ初期化で iterate される)
    merged_reader = Mock()
    merged_reader.get_tag_languages.return_value = []
    container.db_manager.annotation_repo.get_merged_reader.return_value = merged_reader
    return container


@pytest.fixture
def db_manager() -> Mock:
    """rating/score 書込・詳細取得・検索ファセット供給を満たす最小 db_manager。"""
    db = Mock()
    # filterSearchPanel 初期化時のファセット供給 (QListWidget.addItems が Sequence[str] を要求)
    db.get_recently_used_model_ids.return_value = []
    db.get_created_at_histogram.return_value = []
    return db


@pytest.fixture
def dataset_state_manager() -> DatasetStateManager:
    """選択 SSoT (実インスタンス)。"""
    return DatasetStateManager()


@pytest.fixture
def tab(
    qtbot,
    service_container: Mock,
    db_manager: Mock,
    dataset_state_manager: DatasetStateManager,
) -> SearchTabWidget:
    """実 SearchTabWidget を生成して返す。"""
    widget = SearchTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        dataset_state_manager=dataset_state_manager,
        staging_state_manager=StagingStateManager(),
        worker_service=Mock(),
    )
    qtbot.addWidget(widget)
    return widget


# == 1. 構築 ==================================================================


@pytest.mark.gui
def test_tab_builds_work_area_widgets(tab: SearchTabWidget) -> None:
    """生成で 5 つの公開プロパティが実型で構築される。"""
    assert isinstance(tab.filter_search_panel, FilterSearchPanel)
    assert isinstance(tab.thumbnail_selector, ThumbnailSelectorWidget)
    assert isinstance(tab.image_preview_widget, ImagePreviewWidget)
    assert isinstance(tab.selected_image_details_widget, SelectedImageDetailsWidget)
    assert isinstance(tab.main_splitter, QSplitter)


@pytest.mark.gui
def test_splitter_orientations_follow_ui_ssot(tab: SearchTabWidget) -> None:
    """work area=Horizontal / preview-details=Vertical / 折り畳み不可 (#865 SSoT)。"""
    assert tab.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert tab.splitterPreviewDetails.orientation() == Qt.Orientation.Vertical
    assert tab.main_splitter.childrenCollapsible() is False


# == 2. DI 契約 ===============================================================


@pytest.mark.gui
def test_di_retains_injected_dependencies(
    tab: SearchTabWidget,
    service_container: Mock,
    db_manager: Mock,
    dataset_state_manager: DatasetStateManager,
) -> None:
    """注入した service_container / db_manager / dataset_state_manager / worker_service を保持する。"""
    assert tab._service_container is service_container
    assert tab._db_manager is db_manager
    assert tab._dataset_state_manager is dataset_state_manager
    assert tab._worker_service is not None


@pytest.mark.gui
def test_refinement_ignore_routes_to_injected_db_manager(
    tab: SearchTabWidget, service_container: Mock, db_manager: Mock
) -> None:
    """ignore 保存先が注入 db_manager の session factory に追従する (#978)。

    タブは container プロパティではなく ``create_refinement_service`` を
    注入 db_manager の session factory で呼び、その戻り値を詳細ペインへ配線する。
    """
    service_container.create_refinement_service.assert_called_once_with(
        db_manager.image_repo.session_factory
    )
    assert (
        tab.selected_image_details_widget._refinement_service
        is service_container.create_refinement_service.return_value
    )


@pytest.mark.gui
def test_di_graceful_with_none_state_managers(qtbot, service_container: Mock, db_manager: Mock) -> None:
    """dataset / staging / worker が None でも例外なく構築でき、refresh() も安全。"""
    widget = SearchTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        dataset_state_manager=None,
        staging_state_manager=None,
        worker_service=None,
    )
    qtbot.addWidget(widget)

    assert widget._dataset_state_manager is None
    assert widget._worker_service is None
    # DB 状態バー再計算のみで、None 依存に触れず例外を出さない
    widget.refresh()


@pytest.mark.gui
def test_missing_db_manager_aborts_construction(qtbot, service_container: Mock) -> None:
    """検索は db_manager 必須。None だと SearchFilterService 生成で ValueError を送出する。"""
    with pytest.raises(ValueError):
        SearchTabWidget(
            service_container=service_container,
            db_manager=None,
            dataset_state_manager=DatasetStateManager(),
            staging_state_manager=StagingStateManager(),
            worker_service=None,
        )


# == 3. #865 splitter orientation 再適用 ======================================


@pytest.mark.gui
def test_apply_designed_orientations_recovers_from_restore_state(tab: SearchTabWidget) -> None:
    """restoreState で巻き戻った向きを .ui SSoT (Horizontal/Vertical) へ復元する (#865)。"""
    # restoreState は orientation も復元するため、旧 Vertical state を流し込むと向きが巻き戻る
    tab.main_splitter.setOrientation(Qt.Orientation.Vertical)
    stale_state = tab.main_splitter.saveState()
    tab.main_splitter.setOrientation(Qt.Orientation.Horizontal)
    tab.main_splitter.restoreState(stale_state)
    # #865 回帰の再現: restoreState で Vertical へ巻き戻る
    assert tab.main_splitter.orientation() == Qt.Orientation.Vertical
    tab.splitterPreviewDetails.setOrientation(Qt.Orientation.Horizontal)

    tab.apply_designed_splitter_orientations()

    assert tab.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert tab.splitterPreviewDetails.orientation() == Qt.Orientation.Vertical


@pytest.mark.gui
def test_restore_layout_state_keeps_designed_orientation(tab: SearchTabWidget) -> None:
    """横保存状態を縦設計の splitter に restore しても designed orientation を維持する (#865)。"""
    from PySide6.QtCore import QSettings

    settings = QSettings("lorairo-test", "search-tab-layout")
    settings.clear()
    # preview は設計上 Vertical。横状態を保存してから復元する。
    tab.preview_splitter.setOrientation(Qt.Orientation.Horizontal)
    settings.setValue("splitter/preview_details", tab.preview_splitter.saveState())
    settings.setValue("splitter/main_work_area", tab.main_splitter.saveState())

    restored = tab.restore_layout_state(settings)

    assert restored is True
    # restore 後に designed orientation が再適用される
    assert tab.preview_splitter.orientation() == Qt.Orientation.Vertical
    assert tab.main_splitter.orientation() == Qt.Orientation.Horizontal


@pytest.mark.gui
def test_save_layout_state_writes_both_splitters(tab: SearchTabWidget) -> None:
    """main と preview の両 splitter を保存する (#869 preview 取りこぼし防止)。"""
    from PySide6.QtCore import QSettings

    settings = QSettings("lorairo-test", "search-tab-layout-save")
    settings.clear()
    tab.save_layout_state(settings)

    assert settings.value("splitter/main_work_area") is not None
    assert settings.value("splitter/preview_details") is not None


# == 4. 検索 / フィルタ統合 ===================================================


@pytest.mark.gui
def test_load_images_from_db_triggers_filter_panel_search(tab: SearchTabWidget) -> None:
    """load_images_from_db() は filterSearchPanel の検索トリガへ委譲する。"""
    tab._filter_search_panel._on_search_requested = Mock()

    tab.load_images_from_db()

    tab._filter_search_panel._on_search_requested.assert_called_once_with()


# == 5. サムネ → プレビュー / 上方 Signal =====================================


@pytest.mark.gui
def test_thumbnail_selection_forwards_to_preview(
    qtbot, service_container: Mock, db_manager: Mock, monkeypatch
) -> None:
    """thumbnail.image_selected → image_preview.load_image へ接続される。"""
    # 接続は構築時に bind されるため、構築前に load_image を Mock 化して捕捉する
    mock_load = Mock()
    monkeypatch.setattr(ImagePreviewWidget, "load_image", mock_load)
    widget = SearchTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        dataset_state_manager=DatasetStateManager(),
        staging_state_manager=StagingStateManager(),
        worker_service=Mock(),
    )
    qtbot.addWidget(widget)

    path = Path("sample.png")
    widget.thumbnail_selector.image_selected.emit(path)

    mock_load.assert_called_once_with(path)


@pytest.mark.gui
def test_stage_selected_forwards_to_top_signal(tab: SearchTabWidget, qtbot) -> None:
    """thumbnail.stage_selected_requested → stage_to_annotation_requested を上方 emit する。"""
    with qtbot.waitSignal(tab.stage_to_annotation_requested, timeout=1000) as blocker:
        tab.thumbnail_selector.stage_selected_requested.emit([1, 2])
    assert blocker.args == [[1, 2]]


@pytest.mark.gui
def test_quick_tag_request_opens_dialog_in_tab(tab: SearchTabWidget, monkeypatch) -> None:
    """thumbnail.quick_tag_requested はタブ内の _show_quick_tag_dialog を起動する (#896)。"""
    opened: list[list[int]] = []
    monkeypatch.setattr(tab, "_show_quick_tag_dialog", lambda ids: opened.append(ids))

    tab.thumbnail_selector.quick_tag_requested.emit([7])

    assert opened == [[7]]


@pytest.mark.gui
def test_show_quick_tag_dialog_empty_ids_noop(tab: SearchTabWidget, monkeypatch) -> None:
    """空 image_ids ではダイアログを起動しない (#896)。"""
    from lorairo.gui.tab import search_tab as search_tab_module

    created: list[object] = []
    monkeypatch.setattr(search_tab_module, "QuickTagDialog", lambda *a, **k: created.append(object()))

    tab._show_quick_tag_dialog([])

    assert created == []


@pytest.mark.gui
def test_handle_quick_tag_add_success_emits_status(tab: SearchTabWidget, qtbot) -> None:
    """書込成功で status_message を emit し dataset キャッシュを更新する (#896)。"""
    tab._image_db_write_service = Mock()
    tab._image_db_write_service.add_tag_batch.return_value = True
    tab._dataset_state_manager = Mock()

    with qtbot.waitSignal(tab.status_message, timeout=1000) as blocker:
        tab._handle_quick_tag_add([1, 2], "portrait")

    assert "portrait" in blocker.args[0]
    tab._image_db_write_service.add_tag_batch.assert_called_once_with([1, 2], "portrait")
    tab._dataset_state_manager.refresh_images.assert_called_once_with([1, 2])


@pytest.mark.gui
def test_handle_quick_tag_add_failure_shows_critical(tab: SearchTabWidget, monkeypatch) -> None:
    """書込失敗で QMessageBox.critical を表示する (#896)。"""
    tab._image_db_write_service = Mock()
    tab._image_db_write_service.add_tag_batch.return_value = False
    calls: list[bool] = []
    monkeypatch.setattr("lorairo.gui.tab.search_tab.show_critical", lambda *a, **k: calls.append(True))

    tab._handle_quick_tag_add([1], "x")

    assert calls == [True]


# == 6. 選択 → 詳細反映 =======================================================


@pytest.mark.gui
class TestSelectionToDetails:
    """選択件数に応じた詳細パネル表示更新 (0 件 / 1 件 / 複数件) の分岐検証。"""

    def test_no_selection_clears_display(self, tab: SearchTabWidget) -> None:
        widget = Mock()
        tab._selected_image_details_widget = widget

        tab._handle_selection_changed_for_rating([])

        widget._clear_display.assert_called_once_with()

    def test_single_selection_populates_from_image_data(self, tab: SearchTabWidget) -> None:
        widget = Mock()
        tab._selected_image_details_widget = widget
        image_data = {"id": 5, "rating": "PG"}
        tab._dataset_state_manager = Mock()
        tab._dataset_state_manager.get_image_by_id.return_value = image_data

        tab._handle_selection_changed_for_rating([5])

        tab._dataset_state_manager.get_image_by_id.assert_called_once_with(5)
        widget._rating_score_widget.populate_from_image_data.assert_called_once_with(image_data)

    def test_multiple_selection_populates_from_selection(self, tab: SearchTabWidget) -> None:
        widget = Mock()
        tab._selected_image_details_widget = widget
        tab._db_manager = Mock()

        tab._handle_selection_changed_for_rating([1, 2, 3])

        widget._rating_score_widget.populate_from_selection.assert_called_once_with(
            [1, 2, 3], tab._db_manager
        )


# == 7. rating / score 編集 (ImageDBWriteService 経由) =========================


@pytest.mark.gui
class TestRatingScoreEditing:
    """詳細パネル編集シグナルが ImageDBWriteService 経由で書き込まれる配線の検証。"""

    def test_rating_changed_writes_and_refreshes(self, tab: SearchTabWidget) -> None:
        tab._image_db_write_service = Mock()
        tab._image_db_write_service.update_rating.return_value = True
        tab._dataset_state_manager = Mock()

        tab._handle_rating_changed(5, "PG")

        tab._image_db_write_service.update_rating.assert_called_once_with(5, "PG")
        tab._dataset_state_manager.refresh_image.assert_called_once_with(5)

    def test_score_changed_writes_and_refreshes(self, tab: SearchTabWidget) -> None:
        tab._image_db_write_service = Mock()
        tab._image_db_write_service.update_score.return_value = True
        tab._dataset_state_manager = Mock()

        tab._handle_score_changed(5, 80)

        tab._image_db_write_service.update_score.assert_called_once_with(5, 80)
        tab._dataset_state_manager.refresh_image.assert_called_once_with(5)

    def test_batch_rating_changed_writes_batch(self, tab: SearchTabWidget) -> None:
        tab._image_db_write_service = Mock()
        tab._image_db_write_service.update_rating_batch.return_value = True
        tab._dataset_state_manager = Mock()

        tab._handle_batch_rating_changed([1, 2], "X")

        tab._image_db_write_service.update_rating_batch.assert_called_once_with([1, 2], "X")
        tab._dataset_state_manager.refresh_images.assert_called_once_with([1, 2])

    def test_batch_score_changed_writes_batch(self, tab: SearchTabWidget) -> None:
        tab._image_db_write_service = Mock()
        tab._image_db_write_service.update_score_batch.return_value = True
        tab._dataset_state_manager = Mock()

        tab._handle_batch_score_changed([1, 2], 50)

        tab._image_db_write_service.update_score_batch.assert_called_once_with([1, 2], 50)
        tab._dataset_state_manager.refresh_images.assert_called_once_with([1, 2])


# == 8. パネルトグル ==========================================================


@pytest.mark.gui
class TestPanelToggle:
    """フィルタ / プレビューパネルの表示トグルと splitter サイズ退避/復元の検証。"""

    def test_toggle_filter_panel_hides_then_restores(self, tab: SearchTabWidget) -> None:
        panel = tab.frameFilterSearchPanel
        assert panel.isHidden() is False

        tab.toggle_filter_panel()
        assert panel.isHidden() is True
        # 非表示化の直前に splitter サイズを退避している
        assert tab._main_splitter_sizes_before_filter_hide is not None

        tab.toggle_filter_panel()
        assert panel.isHidden() is False

    def test_toggle_preview_panel_hides_then_restores(self, tab: SearchTabWidget) -> None:
        panel = tab.framePreviewDetailPanel
        assert panel.isHidden() is False

        tab.toggle_preview_panel()
        assert panel.isHidden() is True
        assert tab._main_splitter_sizes_before_preview_hide is not None

        tab.toggle_preview_panel()
        assert panel.isHidden() is False


# == 9. 入口 Signal ===========================================================


@pytest.mark.gui
class TestEntrySignals:
    """データセット選択 / 設定 / ステージ / エクスポートの入口ボタン → 上方 Signal。"""

    def test_select_dataset_button_emits(self, tab: SearchTabWidget, qtbot) -> None:
        with qtbot.waitSignal(tab.dataset_selection_requested, timeout=1000):
            tab.pushButtonSelectDataset.click()

    def test_settings_button_emits(self, tab: SearchTabWidget, qtbot) -> None:
        with qtbot.waitSignal(tab.settings_requested, timeout=1000):
            tab.pushButtonSettings.click()

    def test_export_button_emits(self, tab: SearchTabWidget, qtbot) -> None:
        with qtbot.waitSignal(tab.export_requested, timeout=1000):
            tab.btnExportData.click()

    def test_stage_button_emits_with_selected_ids(self, tab: SearchTabWidget, qtbot) -> None:
        tab._dataset_state_manager = Mock()
        tab._dataset_state_manager.selected_image_ids = [3, 4]

        with qtbot.waitSignal(tab.stage_to_annotation_requested, timeout=1000) as blocker:
            tab.pushButtonStageToBatchTag.click()

        assert blocker.args == [[3, 4]]


# == 10. MainWindow → タブ スロット ===========================================


@pytest.mark.gui
class TestSlots:
    """MainWindow から駆動されるラベル更新スロットの検証。"""

    def test_set_db_info_updates_label(self, tab: SearchTabWidget) -> None:
        tab.set_db_info("DB: /tmp/x", "tooltip")
        assert tab.labelDbInfo.text() == "DB: /tmp/x"
        assert tab.labelDbInfo.toolTip() == "tooltip"

    def test_set_dataset_path_updates_lineedit(self, tab: SearchTabWidget) -> None:
        tab.set_dataset_path("/data/set")
        assert tab.lineEditDatasetPath.text() == "/data/set"

    def test_set_export_target_count_updates_label(self, tab: SearchTabWidget) -> None:
        tab.set_export_target_count(42)
        assert "42" in tab.labelExportTarget.text()


# == 11. 負アサート ===========================================================


@pytest.mark.gui
def test_tab_does_not_host_annotate_responsibilities(tab: SearchTabWidget) -> None:
    """SearchTab は pipeline / annotate batch-tag 表示の責務を抱えない (#869 境界)。"""
    # PipelineControlService / 推論台帳など annotate 固有の状態を持たない
    assert not hasattr(tab, "_pipeline_composition_service")
    assert not hasattr(tab, "batchTagAnnotationDisplay")

    # NOTE: AnnotationDataDisplayWidget は詳細パネルの閲覧面として SearchTab に属するため除外しない。
    # ここで弾くのは annotate バッチ実行系 (pipeline / 推論台帳 / バッチタグ付与) の widget。
    forbidden = {
        "PipelineStageTableWidget",
        "InferenceLedgerWidget",
        "BatchTagAddWidget",
        "PreflightSummaryWidget",
    }
    for child in tab.findChildren(QWidget):
        assert type(child).__name__ not in forbidden
