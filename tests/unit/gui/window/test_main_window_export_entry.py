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

    def test_export_bottom_bar_widgets_exist(self, bare_window):
        """サムネグリッド下部バーの件数ラベルとエクスポートボタンが起動する。"""
        assert hasattr(bare_window, "labelExportTarget")
        assert hasattr(bare_window, "btnExportData")
        assert bare_window.btnExportData.text() == "エクスポート"
        # 初期ラベルは 0 枚
        assert "0 枚" in bare_window.labelExportTarget.text()


class TestExportTargetFollowsStaging:
    """件数表示がステージング件数に追従する（ADR 0055）。"""

    def test_update_export_target_ui_sets_real_label(self, bare_window):
        MainWindow._update_export_target_ui(bare_window, 7)
        assert bare_window.labelExportTarget.text() == "エクスポート対象: 7 枚"

    def test_staged_images_changed_follows_staging_count(self, bare_window):
        """staged_images_changed 経路で下部バー件数がステージング件数に追従する。

        サムネ選択数ではなくステージング集合のサイズを反映することを、
        実ウィジェット（labelExportTarget / labelAnnotationTarget）で検証する。
        """
        bare_window._update_annotation_target_ui = types.MethodType(
            MainWindow._update_annotation_target_ui, bare_window
        )
        bare_window._update_export_target_ui = types.MethodType(
            MainWindow._update_export_target_ui, bare_window
        )

        MainWindow._on_staged_images_changed(bare_window, [10, 20, 30, 40])

        assert bare_window.labelExportTarget.text() == "エクスポート対象: 4 枚"
        assert "4 枚" in bare_window.labelAnnotationTarget.text()

    def test_staged_images_changed_empty_resets_to_zero(self, bare_window):
        bare_window._update_annotation_target_ui = types.MethodType(
            MainWindow._update_annotation_target_ui, bare_window
        )
        bare_window._update_export_target_ui = types.MethodType(
            MainWindow._update_export_target_ui, bare_window
        )

        MainWindow._on_staged_images_changed(bare_window, [])

        assert bare_window.labelExportTarget.text() == "エクスポート対象: 0 枚"


class TestExportEntryHandlers:
    """入口ハンドラが bool ペイロードを画像 ID と誤認しない（ADR 0072 / #570）。"""

    def test_on_export_entry_triggered_ignores_clicked_bool(self):
        mock_window = Mock()
        # QPushButton.clicked / QAction.triggered は checked(bool) を渡す
        MainWindow._on_export_entry_triggered(mock_window, True)
        # export_data は引数なしで呼ばれる（bool が ID として漏れない）
        mock_window.export_data.assert_called_once_with()

    def test_on_export_entry_triggered_default_arg(self):
        mock_window = Mock()
        MainWindow._on_export_entry_triggered(mock_window)
        mock_window.export_data.assert_called_once_with()


class TestExportEntryWiring:
    """_connect_export_entry_signals の結線を実ウィジェットで検証。"""

    def test_connect_wires_bottom_bar_export_button(self, bare_window, qtbot):
        bare_window.export_data = Mock()
        bare_window._update_export_target_ui = types.MethodType(
            MainWindow._update_export_target_ui, bare_window
        )
        bare_window._on_export_entry_triggered = types.MethodType(
            MainWindow._on_export_entry_triggered, bare_window
        )

        MainWindow._connect_export_entry_signals(bare_window)

        # 結線時に件数ラベルが初期化される
        assert bare_window.labelExportTarget.text() == "エクスポート対象: 0 枚"

        # 下部バーボタンの clicked(bool) → export_data（引数なし、bool を ID 化しない）
        qtbot.mouseClick(bare_window.btnExportData, Qt.MouseButton.LeftButton)
        bare_window.export_data.assert_called_once_with()


class TestStagedExportIdsProvider:
    """_get_staged_export_ids（エクスポートタブの対象ソース）の検証（ADR 0055 / #620 案A）。"""

    def test_returns_staging_image_ids(self):
        mock_window = Mock()
        staging_widget = Mock()
        staging_widget.get_image_ids.return_value = [3, 1, 2]
        mock_window.batchTagAddWidget = Mock()
        mock_window.batchTagAddWidget.get_staging_widget.return_value = staging_widget

        result = MainWindow._get_staged_export_ids(mock_window)
        assert result == [3, 1, 2]

    def test_returns_empty_when_no_batch_widget(self):
        mock_window = Mock(spec=[])
        assert MainWindow._get_staged_export_ids(mock_window) == []

    def test_returns_empty_when_no_get_staging_widget(self):
        mock_window = Mock()
        mock_window.batchTagAddWidget = Mock(spec=[])
        assert MainWindow._get_staged_export_ids(mock_window) == []

    def test_returns_empty_when_staging_widget_none(self):
        mock_window = Mock()
        mock_window.batchTagAddWidget = Mock()
        mock_window.batchTagAddWidget.get_staging_widget.return_value = None
        assert MainWindow._get_staged_export_ids(mock_window) == []
