"""AnnotationFilterWidget 単体テスト"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt


@pytest.fixture
def annotation_filter_widget(qtbot):
    """AnnotationFilterWidget インスタンスを作成"""
    from lorairo.gui.widgets.annotation_filter_widget import AnnotationFilterWidget

    widget = AnnotationFilterWidget()
    qtbot.addWidget(widget)
    return widget


class TestAnnotationFilterWidgetInitialization:
    """初期化テスト"""

    def test_initial_state_all_unchecked(self, annotation_filter_widget):
        """初期状態で全チェックボックスが未チェック"""
        widget = annotation_filter_widget

        # 機能タイプ
        assert not widget.checkBoxCaption.isChecked()
        assert not widget.checkBoxTags.isChecked()
        assert not widget.checkBoxScore.isChecked()

        # 実行環境
        assert not widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()

    def test_initial_filters_empty(self, annotation_filter_widget):
        """初期状態でフィルターが空"""
        filters = annotation_filter_widget.get_current_filters()

        assert filters["capabilities"] == []
        assert filters["environment"] is None


class TestAnnotationFilterWidgetCapabilities:
    """機能タイプフィルターテスト"""

    def test_caption_filter(self, annotation_filter_widget, qtbot):
        """Caption生成フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxCaption.setChecked(True)
        filters = widget.get_current_filters()

        assert "caption" in filters["capabilities"]
        assert "tags" not in filters["capabilities"]
        assert "scores" not in filters["capabilities"]

    def test_tags_filter(self, annotation_filter_widget):
        """Tag生成フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxTags.setChecked(True)
        filters = widget.get_current_filters()

        assert "tags" in filters["capabilities"]
        assert "caption" not in filters["capabilities"]

    def test_score_filter(self, annotation_filter_widget):
        """品質スコアフィルター"""
        widget = annotation_filter_widget

        widget.checkBoxScore.setChecked(True)
        filters = widget.get_current_filters()

        assert "scores" in filters["capabilities"]

    def test_multiple_capabilities(self, annotation_filter_widget):
        """複数の機能タイプを選択"""
        widget = annotation_filter_widget

        widget.checkBoxCaption.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        widget.checkBoxScore.setChecked(True)
        filters = widget.get_current_filters()

        assert len(filters["capabilities"]) == 3
        assert "caption" in filters["capabilities"]
        assert "tags" in filters["capabilities"]
        assert "scores" in filters["capabilities"]


class TestAnnotationFilterWidgetEnvironment:
    """実行環境フィルターテスト"""

    def test_local_only(self, annotation_filter_widget):
        """ローカルモデルのみ選択"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["environment"] == "local"

    def test_web_api_only(self, annotation_filter_widget):
        """Web APIのみ選択"""
        widget = annotation_filter_widget

        widget.checkBoxWebAPI.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["environment"] == "api"

    def test_both_environments_selected(self, annotation_filter_widget):
        """両方選択時はフィルターなし"""
        widget = annotation_filter_widget

        widget.checkBoxWebAPI.setChecked(True)
        widget.checkBoxLocal.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["environment"] is None

    def test_neither_environment_selected(self, annotation_filter_widget):
        """両方未選択時はフィルターなし"""
        filters = annotation_filter_widget.get_current_filters()

        assert filters["environment"] is None


class TestAnnotationFilterWidgetSignals:
    """シグナルテスト"""

    def test_filter_changed_signal_on_caption_check(self, annotation_filter_widget, qtbot):
        """Caption チェック時に filter_changed シグナル発火"""
        widget = annotation_filter_widget

        with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
            widget.checkBoxCaption.setChecked(True)

        filters = blocker.args[0]
        assert "caption" in filters["capabilities"]

    def test_filter_changed_signal_on_environment_check(self, annotation_filter_widget, qtbot):
        """環境チェック時に filter_changed シグナル発火"""
        widget = annotation_filter_widget

        with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
            widget.checkBoxLocal.setChecked(True)

        filters = blocker.args[0]
        assert filters["environment"] == "local"


class TestAnnotationFilterWidgetSetFilters:
    """set_filters メソッドテスト"""

    def test_set_capabilities(self, annotation_filter_widget, qtbot):
        """capabilities を設定"""
        widget = annotation_filter_widget

        widget.set_filters(capabilities=["caption", "tags"])

        assert widget.checkBoxCaption.isChecked()
        assert widget.checkBoxTags.isChecked()
        assert not widget.checkBoxScore.isChecked()

    def test_set_environment_local(self, annotation_filter_widget):
        """environment を local に設定"""
        widget = annotation_filter_widget

        widget.set_filters(environment="local")

        assert widget.checkBoxLocal.isChecked()
        assert not widget.checkBoxWebAPI.isChecked()

    def test_set_environment_api(self, annotation_filter_widget):
        """environment を api に設定"""
        widget = annotation_filter_widget

        widget.set_filters(environment="api")

        assert widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()


class TestAnnotationFilterWidgetClearFilters:
    """clear_filters メソッドテスト"""

    def test_clear_all_filters(self, annotation_filter_widget, qtbot):
        """全フィルターをクリア"""
        widget = annotation_filter_widget

        # まず全てチェック
        widget.checkBoxCaption.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        widget.checkBoxScore.setChecked(True)
        widget.checkBoxWebAPI.setChecked(True)

        # クリア
        widget.clear_filters()

        # 全て未チェック
        assert not widget.checkBoxCaption.isChecked()
        assert not widget.checkBoxTags.isChecked()
        assert not widget.checkBoxScore.isChecked()
        assert not widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()

        # フィルターも空
        filters = widget.get_current_filters()
        assert filters["capabilities"] == []
        assert filters["environment"] is None
