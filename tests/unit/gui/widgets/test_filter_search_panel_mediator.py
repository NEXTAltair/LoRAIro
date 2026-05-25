# tests/unit/gui/widgets/test_filter_search_panel_mediator.py
"""FilterSearchPanel の mediator 動作テスト (ADR 0036 §3 / §6)。

FilterSearchPanel が以下を満たすかを検証する:

- 4 sub-widget (Tag/Count/Favorite/Pipeline) を composition で保持する
- Sub-widget 同士が直接接続されていない (ADR 0036 §3)
- Sub-widget からのコールバック / signal を Parent (mediator) が受けて他へ流通させる
- Pipeline state listener が pipeline_state_changed シグナルを emit する
"""

from unittest.mock import MagicMock

import pytest

from lorairo.gui.widgets.filter_search import (
    CountEstimateWidget,
    FavoriteFilterPanel,
    PipelineState,
    PipelineStateMachine,
    TagSuggestionWidget,
)
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


@pytest.fixture()
def panel(qtbot):
    """FilterSearchPanel インスタンスを作成して qtbot に登録する。"""
    widget = FilterSearchPanel()
    qtbot.addWidget(widget)
    return widget


class TestCompositionStructure:
    """ADR 0036 §2 / §6: 4 sub-widget の composition 構造を検証する。"""

    def test_holds_pipeline_state_machine(self, panel):
        """_pipeline は PipelineStateMachine インスタンス。"""
        assert isinstance(panel._pipeline, PipelineStateMachine)

    def test_holds_tag_suggestion_widget(self, panel):
        """_tag_suggestion は TagSuggestionWidget インスタンス。"""
        assert isinstance(panel._tag_suggestion, TagSuggestionWidget)

    def test_holds_count_estimate_widget(self, panel):
        """_count_estimate は CountEstimateWidget インスタンス。"""
        assert isinstance(panel._count_estimate, CountEstimateWidget)

    def test_holds_favorite_filter_panel(self, panel):
        """_favorite_filter は FavoriteFilterPanel インスタンス。"""
        assert isinstance(panel._favorite_filter, FavoriteFilterPanel)

    def test_sub_widgets_are_descendants_of_panel(self, panel):
        """Qt の sub-widget は composition で panel から到達可能 (再配置後の親は別 layout の場合あり)。

        ADR 0036 §2: parent は panel 自身もしくは panel が管理する layout 配下。
        Qt は addWidget() 後に parent を layout が属する widget に変更するため、
        ancestor チェーンで panel に到達することを確認する。
        """
        # PipelineStateMachine は Qt 非依存のため除外
        for sub in (panel._tag_suggestion, panel._count_estimate, panel._favorite_filter):
            ancestor = sub.parent()
            while ancestor is not None and ancestor is not panel:
                ancestor = ancestor.parent()
            assert ancestor is panel, f"{type(sub).__name__} is not a descendant of panel"


class TestPipelineStateMediation:
    """Pipeline state machine の遷移を mediator が pipeline_state_changed として emit する。"""

    def test_pipeline_state_emit_on_transition(self, panel, qtbot):
        """PipelineStateMachine が遷移すると panel.pipeline_state_changed が emit される。"""
        with qtbot.waitSignal(panel.pipeline_state_changed, timeout=1000) as blocker:
            panel._pipeline.transition_to(PipelineState.SEARCHING)
        assert blocker.args == [PipelineState.SEARCHING]

    def test_pipeline_state_idle_calls_set_visible_false(self, panel):
        """IDLE 遷移で progress_bar.setVisible(False) が呼ばれる (要 SEARCHING → IDLE)。"""
        # 初期状態が IDLE なので一度 SEARCHING へ遷移してから IDLE に戻す
        panel._pipeline.transition_to(PipelineState.SEARCHING)
        panel.progress_bar.setVisible = MagicMock()
        panel._pipeline.transition_to(PipelineState.IDLE)
        panel.progress_bar.setVisible.assert_called_with(False)

    def test_pipeline_state_searching_calls_set_visible_true(self, panel):
        """SEARCHING 遷移で progress_bar.setVisible(True) と value(10) が呼ばれる。"""
        panel.progress_bar.setVisible = MagicMock()
        panel.progress_bar.setValue = MagicMock()
        panel._pipeline.transition_to(PipelineState.SEARCHING)
        panel.progress_bar.setVisible.assert_called_with(True)
        panel.progress_bar.setValue.assert_called_with(10)

    def test_get_current_pipeline_state(self, panel):
        """get_current_pipeline_state は _pipeline.current_state を返す。"""
        assert panel.get_current_pipeline_state() == panel._pipeline.current_state

    def test_is_pipeline_active_delegates(self, panel):
        """is_pipeline_active は _pipeline.is_active() を返す。"""
        panel._pipeline.transition_to(PipelineState.SEARCHING)
        assert panel.is_pipeline_active() is True
        panel._pipeline.transition_to(PipelineState.IDLE)
        assert panel.is_pipeline_active() is False


class TestServiceInjectionMediation:
    """Service 注入が sub-widget へ正しく伝搬する。"""

    def test_set_search_filter_service_propagates_to_count_estimate(self, panel):
        """SearchFilterService 設定が CountEstimateWidget に伝搬する。"""
        mock_service = MagicMock()
        mock_service.create_search_conditions = MagicMock()
        mock_service.parse_search_input = MagicMock()
        mock_service.db_manager = None  # tag suggestion 経路は無効化

        panel.set_search_filter_service(mock_service)

        assert panel.search_filter_service is mock_service
        assert panel._count_estimate.search_filter_service is mock_service

    def test_set_tag_suggestion_service_propagates(self, panel):
        """TagSuggestionService 設定が TagSuggestionWidget に伝搬する。"""
        mock_service = MagicMock()
        panel.set_tag_suggestion_service(mock_service)
        assert panel._tag_suggestion.tag_suggestion_service is mock_service

    def test_set_favorite_filters_service_propagates(self, panel):
        """FavoriteFiltersService 設定が FavoriteFilterPanel に伝搬する。"""
        mock_service = MagicMock()
        mock_service.list_filters.return_value = []
        panel.set_favorite_filters_service(mock_service)
        assert panel._favorite_filter.favorite_filters_service is mock_service


class TestFilterChangeMediation:
    """フィルター変更 → CountEstimateWidget へのスケジュール伝搬。"""

    def test_filter_value_changed_schedules_count_update(self, panel):
        """_on_filter_value_changed が _count_estimate.schedule_update を呼ぶ。"""
        panel._count_estimate.schedule_update = MagicMock()
        panel._on_filter_value_changed()
        panel._count_estimate.schedule_update.assert_called_once()

    def test_clear_all_inputs_resets_count_estimate(self, panel):
        """_clear_all_inputs が _count_estimate.reset を呼ぶ。"""
        panel._count_estimate.reset = MagicMock()
        panel._clear_all_inputs()
        panel._count_estimate.reset.assert_called_once()


class TestSubComponentDirectConnectionForbidden:
    """ADR 0036 §3: sub-widget 同士の直接接続が無いことを検証する。"""

    def test_tag_suggestion_does_not_import_count_estimate(self):
        """ADR 0036 §3: tag_suggestion module は count_estimate / favorite_filter を import しない。

        sub-widget 同士の直接接続を防ぐため、static な module 依存も避ける。
        """
        import lorairo.gui.widgets.filter_search.tag_suggestion as tag_module

        source = open(tag_module.__file__).read()
        assert "from .count_estimate" not in source
        assert "from .favorite_filter" not in source
        assert "import count_estimate" not in source
        assert "import favorite_filter" not in source

    def test_count_estimate_does_not_import_other_sub_widgets(self):
        """ADR 0036 §3: count_estimate module は他 sub-widget を import しない。"""
        import lorairo.gui.widgets.filter_search.count_estimate as count_module

        source = open(count_module.__file__).read()
        assert "from .tag_suggestion" not in source
        assert "from .favorite_filter" not in source

    def test_favorite_filter_does_not_import_other_sub_widgets(self):
        """ADR 0036 §3: favorite_filter module は他 sub-widget を import しない。"""
        import lorairo.gui.widgets.filter_search.favorite_filter as fav_module

        source = open(fav_module.__file__).read()
        assert "from .tag_suggestion" not in source
        assert "from .count_estimate" not in source

    def test_favorite_filter_uses_parent_callbacks_not_direct_calls(self, panel):
        """FavoriteFilterPanel は applier/getter コールバック経由でしか panel に作用しない。"""
        # _conditions_getter / _conditions_applier が設定されている = Parent 経由連携
        assert panel._favorite_filter._conditions_getter == panel.get_current_conditions
        assert panel._favorite_filter._conditions_applier == panel.apply_conditions


class TestPublicAPICompat:
    """既存 public API の互換維持を確認する。"""

    def test_public_signals_exist(self, panel):
        """既存の public signal が引き続き定義されている。"""
        assert hasattr(panel, "filter_applied")
        assert hasattr(panel, "filter_cleared")
        assert hasattr(panel, "search_requested")
        assert hasattr(panel, "search_progress_started")
        assert hasattr(panel, "search_progress_updated")
        assert hasattr(panel, "search_completed")
        assert hasattr(panel, "pipeline_state_changed")

    def test_legacy_property_tag_suggestion_service(self, panel):
        """旧 API: panel.tag_suggestion_service プロパティでアクセス可能。"""
        mock_service = MagicMock()
        panel.tag_suggestion_service = mock_service
        assert panel.tag_suggestion_service is mock_service
        # 内部実体は TagSuggestionWidget が保持
        assert panel._tag_suggestion.tag_suggestion_service is mock_service

    def test_legacy_property_favorite_filters_list(self, panel):
        """旧 API: panel.favorite_filters_list でアクセス可能。"""
        assert panel.favorite_filters_list is panel._favorite_filter.favorite_filters_list

    def test_legacy_property_estimated_count_label(self, panel):
        """旧 API: panel._estimated_count_label でアクセス可能。"""
        assert panel._estimated_count_label is panel._count_estimate.label

    def test_legacy_method_extract_last_token(self, panel):
        """旧 API: 静的ヘルパー _extract_last_token が delegation で利用可能。"""
        assert panel._extract_last_token("a, b") == "b"

    def test_legacy_method_on_search_text_edited(self, panel):
        """旧 API: _on_search_text_edited が TagSuggestionWidget へ delegate される。"""
        panel._tag_suggestion.on_search_text_edited = MagicMock()
        panel._on_search_text_edited("test")
        panel._tag_suggestion.on_search_text_edited.assert_called_once_with("test")
