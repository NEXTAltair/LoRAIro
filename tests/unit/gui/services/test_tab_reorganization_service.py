"""TabReorganizationService ユニットテスト

MainWindow.uiで定義されたタブ構造の検証ユーティリティのテスト。
"""

from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtWidgets import QGroupBox, QTabWidget, QWidget

from lorairo.gui.services.tab_reorganization_service import TabReorganizationService


class TestRequiredConstants:
    """定数テスト"""

    def test_required_widgets_contains_tab_structure(self):
        """REQUIRED_WIDGETSがタブ構造の必須要素を含む"""
        required = TabReorganizationService.REQUIRED_WIDGETS

        assert "tabWidgetMainMode" in required
        assert "tabWorkspace" in required
        assert "tabBatchTag" in required
        assert "groupBoxBatchOperations" in required
        assert "groupBoxAnnotation" in required

    def test_required_placeholders_contains_widget_setup_targets(self):
        """REQUIRED_PLACEHOLDERSがwidget_setup_serviceの置換対象を含む"""
        placeholders = TabReorganizationService.REQUIRED_PLACEHOLDERS

        assert "batchTagWidgetPlaceholder" in placeholders
        assert "annotationDisplayPlaceholder" in placeholders
        assert "annotationFilterPlaceholder" in placeholders
        assert "modelSelectionPlaceholder" in placeholders


class TestValidateTabStructure:
    """validate_tab_structure() テスト"""

    def test_returns_true_when_all_widgets_exist(self, qapp):
        """全必須ウィジェットが存在する場合Trueを返す"""
        mock_window = MagicMock()

        # findChildが全ウィジェットに対してMockを返す
        def find_child_mock(cls, name):
            return Mock()

        mock_window.findChild = find_child_mock

        result = TabReorganizationService.validate_tab_structure(mock_window)

        assert result is True

    def test_returns_false_when_required_widget_missing(self, qapp):
        """必須ウィジェットが不足している場合Falseを返す"""
        mock_window = MagicMock()

        # 一部のウィジェットのみ存在
        existing_widgets = {"tabWidgetMainMode", "tabWorkspace"}

        def find_child_mock(cls, name):
            if name in existing_widgets:
                return Mock()
            return None

        mock_window.findChild = find_child_mock

        result = TabReorganizationService.validate_tab_structure(mock_window)

        assert result is False

    def test_warns_but_passes_when_only_placeholders_missing(self, qapp):
        """プレースホルダーのみ不足の場合は警告するがTrueを返す"""
        mock_window = MagicMock()

        # 必須ウィジェットは全て存在、プレースホルダーは存在しない
        required_widgets = set(TabReorganizationService.REQUIRED_WIDGETS)

        def find_child_mock(cls, name):
            if name in required_widgets:
                return Mock()
            return None

        mock_window.findChild = find_child_mock

        result = TabReorganizationService.validate_tab_structure(mock_window)

        # プレースホルダーが無くても必須ウィジェットがあればTrueを返す
        assert result is True


class TestGetTabWidgetCount:
    """get_tab_widget_count() テスト"""

    def test_returns_tab_count_when_tabwidgetmainmode_exists(self, qapp):
        """tabWidgetMainModeが存在する場合タブ数を返す"""
        mock_window = MagicMock()
        mock_tab_widget = QTabWidget()
        mock_tab_widget.addTab(QWidget(), "Tab 1")
        mock_tab_widget.addTab(QWidget(), "Tab 2")
        mock_window.tabWidgetMainMode = mock_tab_widget

        result = TabReorganizationService.get_tab_widget_count(mock_window)

        assert result == 2

    def test_returns_zero_when_tabwidgetmainmode_not_exists(self, qapp):
        """tabWidgetMainModeが存在しない場合0を返す"""
        mock_window = MagicMock()
        del mock_window.tabWidgetMainMode

        result = TabReorganizationService.get_tab_widget_count(mock_window)

        assert result == 0

    def test_returns_zero_when_tabwidgetmainmode_is_none(self, qapp):
        """tabWidgetMainModeがNoneの場合0を返す"""
        mock_window = MagicMock()
        mock_window.tabWidgetMainMode = None

        result = TabReorganizationService.get_tab_widget_count(mock_window)

        assert result == 0


class TestIntegrationWithRealWidgets:
    """実際のQtウィジェットを使用した統合テスト"""

    def test_validate_with_complete_widget_hierarchy(self, qapp):
        """完全なウィジェット階層での検証"""
        # 親ウィンドウ
        parent = QWidget()
        parent.setObjectName("MainWindow")

        # タブウィジェット
        tab_widget = QTabWidget(parent)
        tab_widget.setObjectName("tabWidgetMainMode")

        # ワークスペースタブ
        workspace_tab = QWidget()
        workspace_tab.setObjectName("tabWorkspace")
        tab_widget.addTab(workspace_tab, "ワークスペース")

        # バッチタグタブ
        batch_tag_tab = QWidget()
        batch_tag_tab.setObjectName("tabBatchTag")
        tab_widget.addTab(batch_tag_tab, "バッチタグ")

        # バッチタグタブ内のグループボックス
        operations_group = QGroupBox("操作", batch_tag_tab)
        operations_group.setObjectName("groupBoxBatchOperations")

        annotation_group = QGroupBox("アノテーション", operations_group)
        annotation_group.setObjectName("groupBoxAnnotation")

        # プレースホルダー
        placeholder1 = QWidget(operations_group)
        placeholder1.setObjectName("batchTagWidgetPlaceholder")

        placeholder2 = QWidget(operations_group)
        placeholder2.setObjectName("annotationDisplayPlaceholder")

        placeholder3 = QWidget(annotation_group)
        placeholder3.setObjectName("annotationFilterPlaceholder")

        placeholder4 = QWidget(annotation_group)
        placeholder4.setObjectName("modelSelectionPlaceholder")

        # 検証実行
        result = TabReorganizationService.validate_tab_structure(parent)

        assert result is True
        assert TabReorganizationService.get_tab_widget_count(parent) == 0  # 親にはtabWidgetMainMode属性なし

    def test_validate_fails_with_incomplete_hierarchy(self, qapp):
        """不完全なウィジェット階層での検証失敗"""
        parent = QWidget()
        parent.setObjectName("MainWindow")

        # tabWidgetMainModeのみ作成
        tab_widget = QTabWidget(parent)
        tab_widget.setObjectName("tabWidgetMainMode")

        # 検証実行（他の必須ウィジェットがない）
        result = TabReorganizationService.validate_tab_structure(parent)

        assert result is False
