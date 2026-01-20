"""TabReorganizationService ユニットテスト

Phase 2.5で導入されたプログラム的UI再構成サービスのテスト。
トップレベルタブ構造（ワークスペース/バッチタグ）の作成とレイアウト再構成をテスト。
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from lorairo.gui.services.tab_reorganization_service import TabReorganizationService


class TestCreateMainTabWidget:
    """create_main_tab_widget() テスト"""

    def test_creates_qtabwidget_with_correct_objectname(self, qapp):
        """QTabWidgetが正しいobjectNameで作成される"""
        tab_widget = TabReorganizationService.create_main_tab_widget()

        assert isinstance(tab_widget, QTabWidget)
        assert tab_widget.objectName() == "tabWidgetMainMode"

    def test_returns_qtabwidget_instance(self, qapp):
        """QTabWidgetインスタンスが返される"""
        tab_widget = TabReorganizationService.create_main_tab_widget()

        assert tab_widget is not None
        assert isinstance(tab_widget, QTabWidget)


class TestExtractExistingWidgets:
    """extract_existing_widgets() テスト"""

    def test_extracts_all_four_widgets_from_mainwindow(self):
        """MainWindowから4つのウィジェットを抽出"""
        mock_window = Mock()
        mock_window.frameDatasetSelector = Mock()
        mock_window.frameDatasetSelector.objectName.return_value = "frameDatasetSelector"
        mock_window.frameDbStatus = Mock()
        mock_window.frameDbStatus.objectName.return_value = "frameDbStatus"
        mock_window.splitterMainWorkArea = Mock()
        mock_window.splitterMainWorkArea.objectName.return_value = "splitterMainWorkArea"
        mock_window.frameActionToolbar = Mock()
        mock_window.frameActionToolbar.objectName.return_value = "frameActionToolbar"

        widgets = TabReorganizationService.extract_existing_widgets(mock_window)

        assert len(widgets) == 4
        assert "dataset_selector" in widgets
        assert "db_status" in widgets
        assert "splitter" in widgets
        assert "action_toolbar" in widgets

    def test_handles_missing_widgets_gracefully(self):
        """ウィジェットが存在しない場合も正常に処理"""
        mock_window = Mock()
        # frameDatasetSelectorのみ存在
        mock_window.frameDatasetSelector = Mock()
        mock_window.frameDatasetSelector.objectName.return_value = "frameDatasetSelector"
        # 他の属性は存在しない
        del mock_window.frameDbStatus
        del mock_window.splitterMainWorkArea
        del mock_window.frameActionToolbar

        widgets = TabReorganizationService.extract_existing_widgets(mock_window)

        assert len(widgets) == 1
        assert "dataset_selector" in widgets


class TestBuildWorkspaceTab:
    """build_workspace_tab() テスト"""

    def test_creates_workspace_tab_widget(self, qapp):
        """ワークスペースタブウィジェットが作成される"""
        existing_widgets = {
            "dataset_selector": QWidget(),
            "db_status": QWidget(),
            "splitter": QWidget(),
            "action_toolbar": QWidget(),
        }

        workspace_tab = TabReorganizationService.build_workspace_tab(existing_widgets)

        assert isinstance(workspace_tab, QWidget)
        assert workspace_tab.objectName() == "tabWorkspace"

    def test_workspace_tab_has_vertical_layout(self, qapp):
        """ワークスペースタブがQVBoxLayoutを持つ"""
        existing_widgets = {
            "dataset_selector": QWidget(),
            "db_status": QWidget(),
            "splitter": QWidget(),
            "action_toolbar": QWidget(),
        }

        workspace_tab = TabReorganizationService.build_workspace_tab(existing_widgets)

        assert workspace_tab.layout() is not None
        assert isinstance(workspace_tab.layout(), QVBoxLayout)

    def test_workspace_tab_contains_all_widgets(self, qapp):
        """ワークスペースタブに全ウィジェットが含まれる"""
        existing_widgets = {
            "dataset_selector": QWidget(),
            "db_status": QWidget(),
            "splitter": QWidget(),
            "action_toolbar": QWidget(),
        }

        workspace_tab = TabReorganizationService.build_workspace_tab(existing_widgets)
        layout = workspace_tab.layout()

        assert layout.count() == 4
        # 各ウィジェットが適切に親に設定されている
        for widget in existing_widgets.values():
            assert widget.parent() == workspace_tab


class TestBuildBatchTagTab:
    """build_batch_tag_tab() テスト"""

    def test_creates_batch_tag_tab_widget(self, qapp):
        """バッチタグタブウィジェットが作成される"""
        batch_tag_tab = TabReorganizationService.build_batch_tag_tab()

        assert isinstance(batch_tag_tab, QWidget)
        assert batch_tag_tab.objectName() == "tabBatchTag"

    def test_batch_tag_tab_has_two_columns(self, qapp):
        """バッチタグタブが2カラムレイアウトを持つ"""
        batch_tag_tab = TabReorganizationService.build_batch_tag_tab()

        # メインレイアウトはQVBoxLayout
        main_layout = batch_tag_tab.layout()
        assert isinstance(main_layout, QVBoxLayout)

        # 最初の子がQHBoxLayout（2カラム）
        columns_layout = main_layout.itemAt(0).layout()
        assert isinstance(columns_layout, QHBoxLayout)
        assert columns_layout.count() == 2

    def test_batch_tag_tab_has_staging_and_operations_groups(self, qapp):
        """バッチタグタブにステージング画像グループと操作グループが存在"""
        batch_tag_tab = TabReorganizationService.build_batch_tag_tab()

        # groupBoxStagingImages（左カラム）
        staging_group = batch_tag_tab.findChild(QGroupBox, "groupBoxStagingImages")
        assert staging_group is not None
        assert staging_group.title() == "ステージング画像"

        # groupBoxBatchOperations（右カラム）
        operations_group = batch_tag_tab.findChild(QGroupBox, "groupBoxBatchOperations")
        assert operations_group is not None
        assert operations_group.title() == "操作"

    def test_batch_tag_tab_has_placeholders(self, qapp):
        """バッチタグタブにプレースホルダーが存在"""
        batch_tag_tab = TabReorganizationService.build_batch_tag_tab()

        # stagingPlaceholder
        staging_placeholder = batch_tag_tab.findChild(QLabel, "stagingPlaceholder")
        assert staging_placeholder is not None
        assert staging_placeholder.text() == "ステージング画像がありません"

        # batchTagWidgetPlaceholder
        batch_tag_placeholder = batch_tag_tab.findChild(QWidget, "batchTagWidgetPlaceholder")
        assert batch_tag_placeholder is not None


class TestReorganizeMainWindowLayout:
    """reorganize_main_window_layout() テスト"""

    def test_requires_tabwidgetmainmode_attribute(self):
        """tabWidgetMainMode属性が必須"""
        mock_window = Mock()
        # tabWidgetMainMode属性を削除
        if hasattr(mock_window, "tabWidgetMainMode"):
            del mock_window.tabWidgetMainMode

        with pytest.raises(RuntimeError, match="tabWidgetMainMode must be created"):
            TabReorganizationService.reorganize_main_window_layout(mock_window)

    def test_requires_centralwidget(self, qapp):
        """centralWidget()が必須"""
        mock_window = Mock()
        mock_window.tabWidgetMainMode = QTabWidget()
        mock_window.centralWidget.return_value = None

        with pytest.raises(RuntimeError, match="centralWidget not found"):
            TabReorganizationService.reorganize_main_window_layout(mock_window)


class TestIntegration:
    """統合テスト"""

    def test_complete_tab_reorganization_workflow(self, qapp):
        """完全なタブ再構成ワークフローをテスト"""
        # MainWindowモック作成
        mock_window = Mock()
        mock_window.tabWidgetMainMode = TabReorganizationService.create_main_tab_widget()

        # centralwidget作成
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        mock_window.centralWidget.return_value = central_widget

        # 既存ウィジェット作成（MainWindowの属性として）
        mock_window.frameDatasetSelector = QWidget()
        mock_window.frameDatasetSelector.setObjectName("frameDatasetSelector")
        mock_window.frameDbStatus = QWidget()
        mock_window.frameDbStatus.setObjectName("frameDbStatus")
        mock_window.splitterMainWorkArea = QWidget()
        mock_window.splitterMainWorkArea.setObjectName("splitterMainWorkArea")
        mock_window.frameActionToolbar = QWidget()
        mock_window.frameActionToolbar.setObjectName("frameActionToolbar")

        # 既存レイアウトにウィジェット追加
        central_layout.addWidget(mock_window.frameDatasetSelector)
        central_layout.addWidget(mock_window.frameDbStatus)
        central_layout.addWidget(mock_window.splitterMainWorkArea)
        central_layout.addWidget(mock_window.frameActionToolbar)

        # レイアウト再構成実行
        TabReorganizationService.reorganize_main_window_layout(mock_window)

        # 検証: tabWidgetMainModeが2つのタブを持つ
        assert mock_window.tabWidgetMainMode.count() == 2
        assert mock_window.tabWidgetMainMode.tabText(0) == "ワークスペース"
        assert mock_window.tabWidgetMainMode.tabText(1) == "バッチタグ"

        # 検証: ワークスペースタブに既存ウィジェットが含まれる
        workspace_tab = mock_window.tabWidgetMainMode.widget(0)
        assert workspace_tab.objectName() == "tabWorkspace"

        # 検証: バッチタグタブが存在
        batch_tag_tab = mock_window.tabWidgetMainMode.widget(1)
        assert batch_tag_tab.objectName() == "tabBatchTag"

        # 検証: tabWidgetMainModeがcentralwidgetに追加されている
        assert central_layout.indexOf(mock_window.tabWidgetMainMode) >= 0
