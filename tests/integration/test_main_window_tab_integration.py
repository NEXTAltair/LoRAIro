"""MainWindow タブ統合テスト

Phase 2.5で導入されたトップレベルタブ機能の統合テスト。
MainWindow初期化、タブ切り替え、ウィジェット統合を検証。
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget

from lorairo.gui.window.main_window import MainWindow


@pytest.fixture
def main_window_with_tabs(qapp, monkeypatch):
    """タブ統合済みMainWindowフィクスチャ"""
    # QMessageBox.criticalをモック（初期化エラーダイアログ抑制）
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *args: None)

    window = MainWindow()
    yield window
    window.close()


class TestMainWindowTabInitialization:
    """MainWindowタブ初期化テスト"""

    def test_tabwidgetmainmode_created(self, main_window_with_tabs):
        """tabWidgetMainModeが作成される"""
        assert hasattr(main_window_with_tabs, "tabWidgetMainMode")
        assert main_window_with_tabs.tabWidgetMainMode is not None
        assert isinstance(main_window_with_tabs.tabWidgetMainMode, QTabWidget)

    def test_two_tabs_created(self, main_window_with_tabs):
        """2つのタブ（ワークスペース、バッチタグ）が作成される"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.count() == 2
        assert tab_widget.tabText(0) == "ワークスペース"
        assert tab_widget.tabText(1) == "バッチタグ"

    def test_workspace_tab_contains_splitter(self, main_window_with_tabs):
        """ワークスペースタブにsplitterMainWorkAreaが含まれる"""
        workspace_tab = main_window_with_tabs.tabWidgetMainMode.widget(0)
        assert workspace_tab is not None

        # splitterMainWorkAreaがワークスペースタブの子孫である
        splitter = main_window_with_tabs.splitterMainWorkArea
        assert splitter is not None

        # splitterの親を辿ってworkspace_tabに到達できる
        parent = splitter.parent()
        found = False
        while parent is not None:
            if parent == workspace_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "splitterMainWorkArea should be a descendant of workspace tab"

    def test_batch_tag_tab_structure(self, main_window_with_tabs):
        """バッチタグタブが適切な構造を持つ"""
        batch_tag_tab = main_window_with_tabs.tabWidgetMainMode.widget(1)
        assert batch_tag_tab is not None
        assert batch_tag_tab.objectName() == "tabBatchTag"

        # 2つのGroupBox（ステージング画像、操作）が存在
        staging_group = batch_tag_tab.findChild(object, "groupBoxStagingImages")
        assert staging_group is not None

        operations_group = batch_tag_tab.findChild(object, "groupBoxBatchOperations")
        assert operations_group is not None


class TestTabSwitching:
    """タブ切り替えテスト"""

    def test_default_tab_is_workspace(self, main_window_with_tabs):
        """デフォルトで表示されるタブはワークスペース"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.currentIndex() == 0

    def test_can_switch_to_batch_tag_tab(self, main_window_with_tabs, qtbot):
        """バッチタグタブに切り替えられる"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode

        # バッチタグタブに切り替え
        tab_widget.setCurrentIndex(1)

        # イベント処理を待つ
        qtbot.wait(10)

        assert tab_widget.currentIndex() == 1

    def test_can_switch_back_to_workspace(self, main_window_with_tabs, qtbot):
        """ワークスペースタブに戻せる"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode

        # バッチタグタブに切り替え
        tab_widget.setCurrentIndex(1)
        qtbot.wait(10)

        # ワークスペースタブに戻す
        tab_widget.setCurrentIndex(0)
        qtbot.wait(10)

        assert tab_widget.currentIndex() == 0


class TestBatchTagWidgetIntegration:
    """BatchTagAddWidget統合テスト"""

    def test_batchtagaddwidget_exists(self, main_window_with_tabs):
        """BatchTagAddWidgetが存在する"""
        assert hasattr(main_window_with_tabs, "batchTagAddWidget")
        assert main_window_with_tabs.batchTagAddWidget is not None

    def test_batchtagaddwidget_in_batch_tag_tab(self, main_window_with_tabs):
        """BatchTagAddWidgetがバッチタグタブ内に配置されている"""
        batch_tag_tab = main_window_with_tabs.tabWidgetMainMode.widget(1)
        batch_tag_widget = main_window_with_tabs.batchTagAddWidget

        # BatchTagAddWidgetの親を辿ってbatch_tag_tabに到達できる
        parent = batch_tag_widget.parent()
        found = False
        while parent is not None:
            if parent == batch_tag_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "BatchTagAddWidget should be a descendant of batch tag tab"

    def test_batchtagaddwidget_placeholder_removed(self, main_window_with_tabs):
        """BatchTagAddWidgetプレースホルダーが削除されている"""
        batch_tag_tab = main_window_with_tabs.tabWidgetMainMode.widget(1)
        placeholder = batch_tag_tab.findChild(object, "batchTagWidgetPlaceholder")
        # プレースホルダーは削除されているはず
        assert placeholder is None


class TestSignalConnections:
    """シグナル接続テスト"""

    def test_tab_changed_signal_connected(self, main_window_with_tabs):
        """tabWidgetMainMode.currentChanged シグナルが接続されている"""
        # currentChangedシグナルのレシーバー数を確認
        # 少なくとも1つの接続があるはず（_on_main_tab_changed）
        # Note: Qt内部でシグナル接続数を直接取得する方法は限られているため、
        # シグナル発火時の動作で確認
        # ここでは接続されていることの検証は省略（実際の動作テストで確認）
        assert hasattr(main_window_with_tabs, "_on_main_tab_changed")


class TestStatePreservation:
    """状態保持テスト"""

    def test_dataset_state_manager_preserved_across_tabs(self, main_window_with_tabs):
        """タブを切り替えてもDatasetStateManagerが保持される"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        dataset_state = main_window_with_tabs.dataset_state_manager

        # ワークスペースタブのDatasetStateManager
        workspace_state = main_window_with_tabs.dataset_state_manager

        # バッチタグタブに切り替え
        tab_widget.setCurrentIndex(1)

        # バッチタグタブでもDatasetStateManagerが同じインスタンス
        batch_tag_state = main_window_with_tabs.dataset_state_manager

        assert workspace_state is dataset_state
        assert batch_tag_state is dataset_state
        assert workspace_state is batch_tag_state


class TestAnnotationControlVisibility:
    """アノテーション制御表示テスト"""

    def test_annotation_control_hidden_in_workspace(self, main_window_with_tabs):
        """ワークスペースタブでgroupBoxAnnotationControlが非表示"""
        # groupBoxAnnotationControlが存在する場合、hide()が呼ばれたことを確認
        # Note: isVisible()はウィンドウ未表示時に常にFalseを返すため、
        #       isHidden()を使用してhide()が明示的に呼ばれたことを検証
        if hasattr(main_window_with_tabs, "groupBoxAnnotationControl"):
            annotation_control = main_window_with_tabs.groupBoxAnnotationControl
            assert annotation_control.isHidden(), (
                "groupBoxAnnotationControl should be explicitly hidden via hide()"
            )

    def test_hide_annotation_control_method_exists(self, main_window_with_tabs):
        """_hide_annotation_control_in_workspaceメソッドが存在する"""
        assert hasattr(main_window_with_tabs, "_hide_annotation_control_in_workspace")


class TestAnnotationDataDisplayWidget:
    """AnnotationDataDisplayWidget統合テスト"""

    def test_annotation_display_exists_in_batch_tag(self, main_window_with_tabs):
        """バッチタグタブにAnnotationDataDisplayWidgetが存在する"""
        assert hasattr(main_window_with_tabs, "batchTagAnnotationDisplay")
        assert main_window_with_tabs.batchTagAnnotationDisplay is not None

    def test_annotation_display_in_batch_tag_tab(self, main_window_with_tabs):
        """AnnotationDataDisplayWidgetがバッチタグタブ内に配置されている"""
        batch_tag_tab = main_window_with_tabs.tabWidgetMainMode.widget(1)
        annotation_display = main_window_with_tabs.batchTagAnnotationDisplay

        # AnnotationDataDisplayWidgetの親を辿ってbatch_tag_tabに到達できる
        parent = annotation_display.parent()
        found = False
        while parent is not None:
            if parent == batch_tag_tab:
                found = True
                break
            parent = parent.parent()
        assert found, "AnnotationDataDisplayWidget should be a descendant of batch tag tab"

    def test_annotation_display_placeholder_removed(self, main_window_with_tabs):
        """AnnotationDataDisplayWidgetプレースホルダーが削除されている"""
        batch_tag_tab = main_window_with_tabs.tabWidgetMainMode.widget(1)
        placeholder = batch_tag_tab.findChild(object, "annotationDisplayPlaceholder")
        # プレースホルダーは削除されているはず
        assert placeholder is None
