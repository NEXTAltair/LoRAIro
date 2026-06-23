"""MainWindow エクスポート入口（下部バー）のテスト。

Issue #611 (S1: エクスポート入口追加) / ADR 0055 (対象=ステージング集合) /
ADR 0072 (単一選択ソース・clicked(bool) 注意) 準拠。

検証内容:
- ツールバーは 8タブナビへの移行で削除済み（アノテーション/エクスポート等は tabs で到達）
- menuTools 経由でアクションが引き続き利用可能
- サムネグリッド下部バー起動（対象件数ラベル + エクスポートボタン）
- 件数表示がステージング件数（staged_images_changed）に追従する
- clicked(bool) / triggered(bool) ペイロードを画像 ID と誤認しない回帰
"""

import types
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from lorairo.gui.designer.MainWindow_ui import Ui_MainWindow
from lorairo.gui.window.main_window import MainWindow


class _BareMainWindow(QMainWindow, Ui_MainWindow):
    """サービス層を初期化しない素の MainWindow。

    本番 MainWindow と同じく Ui_MainWindow を多重継承し setupUi を適用するが、
    DB / Worker 等のサービス初期化は行わない。エクスポート入口 UI の存在と
    実ウィジェットへの件数反映を軽量に検証するための土台。
    """

    def __init__(self) -> None:
        super().__init__()
        setup_ui = self.setupUi  # type: ignore[attr-defined]
        setup_ui(self)

    # MainWindow.ui の auto-connection が参照するスロットのスタブ
    # （本テストでは入口ハンドラのみ検証するため空実装で十分）
    def select_and_process_dataset(self) -> None:
        pass

    def open_settings(self) -> None:
        pass

    def start_annotation(self) -> None:
        pass

    def send_selected_to_batch_tag(self) -> None:
        pass

    # Phase 6a: _on_staged_images_changed がパイプライン構成ビューを再描画するため、
    # サービス未初期化の素ウィンドウでは no-op スタブで受ける
    def _refresh_pipeline_panel(self, selected_ids: list[str] | None = None) -> None:
        pass

    # Issue #837: _on_staged_images_changed が送信前プリフライト card も再描画するため
    def _refresh_preflight_summary(self) -> None:
        pass


@pytest.fixture
def bare_window(qtbot):
    win = _BareMainWindow()
    qtbot.addWidget(win)
    return win


class TestExportEntryUiStructure:
    """下部バーの存在検証（起動）。"""

    def test_no_standalone_toolbar(self, bare_window):
        """8タブナビ移行後、mainToolBar は削除されている。"""
        assert not hasattr(bare_window, "mainToolBar")

    def test_old_design_menu_actions_removed(self, bare_window):
        """8タブナビ移行に伴い、タブ重複/dead だった旧メニューアクションは除去済み。"""
        # タブ重複（Annotate⌘3 / Export⌘7 / Errors⌘6 へ集約） → 「移動」メニューが担う
        assert not hasattr(bare_window, "actionAnnotation")
        assert not hasattr(bare_window, "actionExport")
        assert not hasattr(bare_window, "actionErrorLog")
        # dead（何も起きなかった）アクション
        assert not hasattr(bare_window, "actionOpenDataset")
        assert not hasattr(bare_window, "actionEditImage")
        # 残すアクション（設定 / 終了 / About）
        assert hasattr(bare_window, "actionSettings")
        assert hasattr(bare_window, "actionExit")
        assert hasattr(bare_window, "actionAbout")

    def test_navigate_menu_built_from_tabs(self, bare_window):
        """「移動」メニューがタブ数ぶんのアクション（Ctrl+N ショートカット付き）を持つ。"""
        MainWindow._setup_tab_shortcuts(bare_window)

        assert hasattr(bare_window, "menuNavigate")
        actions = bare_window.menuNavigate.actions()
        assert len(actions) == bare_window.tabWidgetMainMode.count()
        assert actions[0].shortcut().toString() == "Ctrl+1"


class TestExportTargetFollowsStaging:
    """件数表示がステージング件数に追従する（ADR 0055）。

    #869: エクスポート下部バー (labelExportTarget / btnExportData) は SearchTabWidget へ
    移管された。MainWindow 側は ``_update_export_target_ui`` で
    ``search_tab.set_export_target_count`` へ委譲する。下部バー自体の表示・ボタン結線の
    検証は tests/unit/gui/tab/test_search_tab.py が担う。
    """

    def test_update_export_target_ui_delegates_to_search_tab(self, bare_window):
        """_update_export_target_ui は search_tab.set_export_target_count へ委譲する。"""
        bare_window.search_tab = Mock()
        MainWindow._update_export_target_ui(bare_window, 7)
        bare_window.search_tab.set_export_target_count.assert_called_once_with(7)

    def test_staged_images_changed_follows_staging_count(self, bare_window):
        """staged_images_changed 経路でステージング件数が各タブへ fan-out される。

        サムネ選択数ではなくステージング集合のサイズを反映する。エクスポート件数は
        SearchTab へ、アノテ対象は AnnotateTab へそれぞれ委譲される (ADR 0074)。
        """
        bare_window._update_export_target_ui = types.MethodType(
            MainWindow._update_export_target_ui, bare_window
        )
        bare_window.search_tab = Mock()
        bare_window.annotate_tab = Mock()

        MainWindow._on_staged_images_changed(bare_window, [10, 20, 30, 40])

        bare_window.search_tab.set_export_target_count.assert_called_once_with(4)
        bare_window.annotate_tab.set_staging_target.assert_called_once_with([10, 20, 30, 40])

    def test_staged_images_changed_empty_resets_to_zero(self, bare_window):
        bare_window._update_export_target_ui = types.MethodType(
            MainWindow._update_export_target_ui, bare_window
        )
        bare_window.search_tab = Mock()
        bare_window.annotate_tab = Mock()

        MainWindow._on_staged_images_changed(bare_window, [])

        bare_window.search_tab.set_export_target_count.assert_called_once_with(0)
        bare_window.annotate_tab.set_staging_target.assert_called_once_with([])


class TestStagedExportIdsProvider:
    """_get_staged_export_ids（エクスポートタブの対象ソース）の検証。

    #868 以降は StagingStateManager (ADR 0074 の SSoT) を直接読む。下部バーの件数表示と
    実エクスポート対象を一致させるため、batchTagAddWidget 経由の参照は廃止された。
    """

    def test_returns_staging_image_ids(self):
        mock_window = Mock()
        mock_window.staging_state_manager.get_image_ids.return_value = [3, 1, 2]

        result = MainWindow._get_staged_export_ids(mock_window)
        assert result == [3, 1, 2]

    def test_returns_empty_when_staging_state_manager_none(self):
        mock_window = Mock()
        mock_window.staging_state_manager = None
        assert MainWindow._get_staged_export_ids(mock_window) == []
