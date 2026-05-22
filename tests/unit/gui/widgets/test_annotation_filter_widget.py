"""AnnotationFilterWidget 単体テスト"""

from __future__ import annotations

import pytest


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

        assert not widget.checkBoxCaption.isChecked()
        assert not widget.checkBoxTags.isChecked()
        assert not widget.checkBoxScore.isChecked()
        assert not widget.checkBoxRating.isChecked()
        assert not widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()

        assert not widget.checkBoxCaption.isEnabled()
        assert not widget.checkBoxTags.isEnabled()
        assert not widget.checkBoxScore.isEnabled()
        assert not widget.checkBoxRating.isEnabled()

    def test_initial_filters_empty(self, annotation_filter_widget):
        """初期状態でフィルターが空"""
        filters = annotation_filter_widget.get_current_filters()

        assert filters["capabilities"] == []
        assert filters["environment"] is None

    def test_labels_show_environment_before_local_capabilities(self, annotation_filter_widget):
        """実行環境がローカルモデル対応機能より上に表示される"""
        widget = annotation_filter_widget

        assert widget.mainLayout.indexOf(widget.groupBoxEnvironment) < widget.mainLayout.indexOf(
            widget.groupBoxFunctionType
        )
        assert widget.groupBoxFunctionType.title() == "ローカルモデル対応機能"
        assert widget.checkBoxTags.text() == "タグ対応"
        assert widget.checkBoxCaption.text() == "キャプション対応"
        assert widget.checkBoxScore.text() == "スコア対応"
        assert widget.checkBoxRating.text() == "レーティング対応"


class TestAnnotationFilterWidgetCapabilities:
    """ローカルモデル対応機能フィルターテスト"""

    def test_caption_filter(self, annotation_filter_widget):
        """キャプション対応フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxCaption.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == ["caption"]

    def test_tags_filter(self, annotation_filter_widget):
        """タグ対応フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == ["tags"]

    def test_score_filter(self, annotation_filter_widget):
        """スコア対応フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxScore.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == ["scores"]

    def test_ratings_filter(self, annotation_filter_widget):
        """レーティング対応フィルター"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxRating.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == ["ratings"]

    def test_multiple_capabilities(self, annotation_filter_widget):
        """複数の対応機能を選択"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        widget.checkBoxCaption.setChecked(True)
        widget.checkBoxScore.setChecked(True)
        widget.checkBoxRating.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == ["tags", "caption", "scores", "ratings"]


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
        assert filters["capabilities"] == []

    def test_neither_environment_selected(self, annotation_filter_widget):
        """両方未選択時はフィルターなし"""
        filters = annotation_filter_widget.get_current_filters()

        assert filters["environment"] is None
        assert filters["capabilities"] == []

    @pytest.mark.parametrize(
        ("web_api", "local", "enabled"),
        [
            (False, True, True),
            (True, False, False),
            (True, True, False),
            (False, False, False),
        ],
    )
    def test_capability_controls_enabled_only_for_local_only(
        self, annotation_filter_widget, web_api, local, enabled
    ):
        """Capability controls はローカルのみ選択時だけ有効"""
        widget = annotation_filter_widget

        widget.checkBoxWebAPI.setChecked(web_api)
        widget.checkBoxLocal.setChecked(local)

        assert widget.checkBoxCaption.isEnabled() is enabled
        assert widget.checkBoxTags.isEnabled() is enabled
        assert widget.checkBoxScore.isEnabled() is enabled
        assert widget.checkBoxRating.isEnabled() is enabled


class TestAnnotationFilterWidgetSignals:
    """シグナルテスト"""

    def test_filter_changed_signal_on_caption_check(self, annotation_filter_widget, qtbot):
        """Caption チェック時に filter_changed シグナル発火"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
            widget.checkBoxCaption.setChecked(True)

        filters = blocker.args[0]
        assert filters["capabilities"] == ["caption"]

    def test_filter_changed_signal_on_environment_check(self, annotation_filter_widget, qtbot):
        """環境チェック時に filter_changed シグナル発火"""
        widget = annotation_filter_widget

        with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
            widget.checkBoxLocal.setChecked(True)

        filters = blocker.args[0]
        assert filters["environment"] == "local"


class TestAnnotationFilterWidgetSetFilters:
    """set_filters メソッドテスト"""

    def test_set_capabilities(self, annotation_filter_widget):
        """capabilities を設定"""
        widget = annotation_filter_widget

        widget.set_filters(capabilities=["caption", "tags", "ratings"], environment="local")

        assert widget.checkBoxCaption.isChecked()
        assert widget.checkBoxTags.isChecked()
        assert widget.checkBoxRating.isChecked()
        assert not widget.checkBoxScore.isChecked()
        assert widget.get_current_filters()["capabilities"] == ["tags", "caption", "ratings"]

    def test_set_environment_local(self, annotation_filter_widget):
        """environment を local に設定"""
        widget = annotation_filter_widget

        widget.set_filters(environment="local")

        assert widget.checkBoxLocal.isChecked()
        assert not widget.checkBoxWebAPI.isChecked()
        assert widget.checkBoxCaption.isEnabled()

    def test_set_environment_api(self, annotation_filter_widget):
        """environment を api に設定"""
        widget = annotation_filter_widget

        widget.set_filters(environment="api")

        assert widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()
        assert not widget.checkBoxCaption.isEnabled()
        assert widget.get_current_filters()["capabilities"] == []


class TestAnnotationFilterWidgetClearFilters:
    """clear_filters メソッドテスト"""

    def test_clear_all_filters(self, annotation_filter_widget):
        """全フィルターをクリア"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        widget.checkBoxCaption.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        widget.checkBoxScore.setChecked(True)
        widget.checkBoxRating.setChecked(True)
        widget.checkBoxWebAPI.setChecked(True)

        widget.clear_filters()

        assert not widget.checkBoxCaption.isChecked()
        assert not widget.checkBoxTags.isChecked()
        assert not widget.checkBoxScore.isChecked()
        assert not widget.checkBoxRating.isChecked()
        assert not widget.checkBoxWebAPI.isChecked()
        assert not widget.checkBoxLocal.isChecked()

        filters = widget.get_current_filters()
        assert filters["capabilities"] == []
        assert filters["environment"] is None


class TestAnnotationFilterWidgetEmptyCapabilitiesWithEnvironment:
    """環境フィルターのみ設定時のテスト"""

    def test_web_api_only_empty_capabilities(self, annotation_filter_widget):
        """Web APIのみチェック時、capabilityは空"""
        widget = annotation_filter_widget

        widget.checkBoxCaption.setChecked(True)
        widget.checkBoxTags.setChecked(True)
        widget.checkBoxWebAPI.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == []
        assert filters["environment"] == "api"

    def test_local_only_empty_capabilities(self, annotation_filter_widget):
        """ローカルのみチェック時、capabilityは空"""
        widget = annotation_filter_widget

        widget.checkBoxLocal.setChecked(True)
        filters = widget.get_current_filters()

        assert filters["capabilities"] == []
        assert filters["environment"] == "local"
