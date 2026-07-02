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
from loguru import logger as loguru_logger

from lorairo.gui.widgets.count_estimate import CountEstimateWidget
from lorairo.gui.widgets.favorite_filter import FavoriteFilterPanel
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.gui.widgets.pipeline_state import PipelineState, PipelineStateMachine
from lorairo.gui.widgets.tag_suggestion import TagSuggestionWidget


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


class TestSearchPreviewLogging:
    """Issue #579: 通常の大量検索結果は WARNING にしない。"""

    @pytest.fixture()
    def loguru_records(self):
        records: list = []
        sink_id = loguru_logger.add(lambda msg: records.append(msg.record), level="DEBUG")
        yield records
        loguru_logger.remove(sink_id)

    def test_large_result_logs_info_not_warning(self, panel, loguru_records):
        """10000 件超の通常プレビュー更新は INFO として記録する。"""
        panel.update_search_preview(10001)

        large_result_records = [
            record
            for record in loguru_records
            if record["message"] == "Large search result warning displayed: 10001 items"
        ]
        assert [record["level"].name for record in large_result_records] == ["INFO"]

    def test_threshold_result_does_not_log_large_result_notice(self, panel, loguru_records):
        """閾値ちょうどは大量結果通知を出さない。"""
        panel.update_search_preview(10000)

        assert all(
            "Large search result warning displayed" not in record["message"] for record in loguru_records
        )

    def test_large_result_shows_ui_warning(self, panel):
        """#1064: 10000 件超はステータスラベルに警告を表示する (log のみで終わらない)。"""
        panel.update_search_preview(10001)

        assert not panel._status_label.isHidden()
        assert "条件を絞り込んでください" in panel._status_label.text()
        assert "10,001" in panel._status_label.text()

    def test_threshold_result_hides_ui_warning(self, panel):
        """#1064: 閾値以下に戻ったら警告を消す。"""
        panel.update_search_preview(10001)
        panel.update_search_preview(500)

        assert panel._status_label.isHidden()
        assert panel._status_label.text() == ""


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

    def test_set_search_filter_service_uses_annotation_repo_reader_for_tag_suggestions(self, panel):
        """タグ補完は ImageDatabaseManager.annotation_repo の MergedTagReader を使う。"""
        merged_reader = object()
        mock_service = MagicMock()
        mock_service.create_search_conditions = MagicMock()
        mock_service.parse_search_input = MagicMock()
        mock_service.db_manager = MagicMock()
        mock_service.db_manager.annotation_repo = MagicMock()
        mock_service.db_manager.annotation_repo.get_merged_reader.return_value = merged_reader

        panel.set_search_filter_service(mock_service)

        assert panel._tag_suggestion.tag_suggestion_service is not None
        assert panel._tag_suggestion.tag_suggestion_service._merged_reader is merged_reader
        mock_service.db_manager.annotation_repo.get_merged_reader.assert_called_once()

    def test_set_search_filter_service_falls_back_to_legacy_repository_reader(self, panel):
        """旧経路 repository.merged_reader も互換性として維持する。"""
        merged_reader = object()
        mock_service = MagicMock()
        mock_service.create_search_conditions = MagicMock()
        mock_service.parse_search_input = MagicMock()
        mock_service.db_manager = MagicMock()
        mock_service.db_manager.repository = MagicMock()
        mock_service.db_manager.repository.merged_reader = merged_reader

        panel.set_search_filter_service(mock_service)

        assert panel._tag_suggestion.tag_suggestion_service is not None
        assert panel._tag_suggestion.tag_suggestion_service._merged_reader is merged_reader

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
        import lorairo.gui.widgets.tag_suggestion as tag_module

        source = open(tag_module.__file__).read()
        assert "from .count_estimate" not in source
        assert "from .favorite_filter" not in source
        assert "import count_estimate" not in source
        assert "import favorite_filter" not in source

    def test_count_estimate_does_not_import_other_sub_widgets(self):
        """ADR 0036 §3: count_estimate module は他 sub-widget を import しない。"""
        import lorairo.gui.widgets.count_estimate as count_module

        source = open(count_module.__file__).read()
        assert "from .tag_suggestion" not in source
        assert "from .favorite_filter" not in source

    def test_favorite_filter_does_not_import_other_sub_widgets(self):
        """ADR 0036 §3: favorite_filter module は他 sub-widget を import しない。"""
        import lorairo.gui.widgets.favorite_filter as fav_module

        source = open(fav_module.__file__).read()
        assert "from .tag_suggestion" not in source
        assert "from .count_estimate" not in source

    def test_favorite_filter_uses_parent_callbacks_not_direct_calls(self, panel):
        """FavoriteFilterPanel は applier/getter コールバック経由でしか panel に作用しない。"""
        # _conditions_getter / _conditions_applier が設定されている = Parent 経由連携
        assert panel._favorite_filter._conditions_getter == panel.get_current_conditions
        assert panel._favorite_filter._conditions_applier == panel.apply_conditions


class TestRatingFilterOptions:
    """Issue #811: レーティング選択を dropdown → マルチセレクト chip へ。

    手動 / AI レーティングを chip で複数選択でき、選択集合の OR で絞り込める。
    手動×AI の組合せ (AND/OR) トグルと、番兵 (UNRATED) の併用も検証する。
    """

    @pytest.fixture()
    def panel_with_service(self, panel):
        """create_search_conditions が sentinel を返す mock service を注入した panel。"""
        sentinel = object()
        mock_service = MagicMock()
        mock_service.parse_search_input.return_value = ([], [])
        mock_service.create_search_conditions.return_value = sentinel
        panel.search_filter_service = mock_service
        panel._sentinel = sentinel
        return panel

    def test_manual_rating_single_select_returns_list(self, panel):
        """手動 chip 1 個選択で単一要素リストを返す。"""
        panel._rating_chips.set_value("PG")
        assert panel._get_rating_filter_value() == ["PG"]

    def test_manual_rating_multi_select_returns_or_set(self, panel):
        """手動 chip 複数選択で選択集合 (OR) のリストを返す。"""
        panel._rating_chips.set_value("PG")
        panel._rating_chips.set_value("R")
        assert panel._get_rating_filter_value() == ["PG", "R"]

    def test_ai_rating_multi_select_with_unrated_sentinel(self, panel):
        """AI chip は通常値と番兵 (UNRATED=未設定) を併用できる。"""
        panel._ai_rating_chips.set_value("PG")
        panel._ai_rating_chips.set_value("UNRATED")
        assert panel._get_ai_rating_filter_value() == ["PG", "UNRATED"]

    def test_default_is_empty_selection(self, panel):
        """既定では chip は未選択 (絞り込みなし) で空リストを返す。"""
        assert panel._get_rating_filter_value() == []
        assert panel._get_ai_rating_filter_value() == []

    def test_combine_toggle_default_and(self, panel):
        """手動×AI の組合せトグルは既定で AND。"""
        assert panel._rating_combine_toggle.value() == "and"

    def test_ai_multi_builds_conditions_without_keyword(self, panel_with_service):
        """AI レーティング複数選択のみ(キーワード無し)で検索条件を返し list で渡す。"""
        panel = panel_with_service
        panel._ai_rating_chips.set_value("R")
        panel._ai_rating_chips.set_value("X")
        assert panel._build_search_conditions_from_ui() is panel._sentinel
        _, kwargs = panel.search_filter_service.create_search_conditions.call_args
        assert kwargs["ai_rating_filter"] == ["R", "X"]
        # NSFW (R/X) を含む選択は include_nsfw=True を解決する
        assert kwargs["include_nsfw"] is True

    def test_combine_or_passed_to_service(self, panel_with_service):
        """手動×AI 両方選択 + OR トグルで rating_combine='or' を渡す。"""
        panel = panel_with_service
        panel._rating_chips.set_value("PG")
        panel._ai_rating_chips.set_value("R")
        panel._rating_combine_toggle.set_value("or")
        assert panel._build_search_conditions_from_ui() is panel._sentinel
        _, kwargs = panel.search_filter_service.create_search_conditions.call_args
        assert kwargs["rating_filter"] == ["PG"]
        assert kwargs["ai_rating_filter"] == ["R"]
        assert kwargs["rating_combine"] == "or"

    def test_nsfw_resolution_accepts_list_and_str(self, panel):
        """_resolve_include_nsfw は単一値(後方互換)と複数値の両方を解決する。"""
        # 後方互換: 単一 str の RATED / None
        assert panel._resolve_include_nsfw("RATED", None) is True
        assert panel._resolve_include_nsfw(None, "RATED") is True
        assert panel._resolve_include_nsfw(None, None) is False
        # マルチセレクト: NSFW 値を含むリスト
        assert panel._resolve_include_nsfw(["PG", "X"], None) is True
        assert panel._resolve_include_nsfw(["PG"], ["PG-13"]) is False

    def test_manual_multi_builds_conditions_without_keyword(self, panel_with_service):
        """手動レーティング複数選択のみ(キーワード無し)で検索条件を返す (対称ケース)。"""
        panel = panel_with_service
        panel._rating_chips.set_value("PG")
        panel._rating_chips.set_value("PG-13")
        assert panel._build_search_conditions_from_ui() is panel._sentinel
        _, kwargs = panel.search_filter_service.create_search_conditions.call_args
        assert kwargs["rating_filter"] == ["PG", "PG-13"]

    def test_all_default_still_blocked(self, panel_with_service):
        """chip 未選択 (他条件・キーワード無し) は従来どおり検索をブロックする。"""
        panel = panel_with_service
        assert panel._build_search_conditions_from_ui() is None
        panel.search_filter_service.create_search_conditions.assert_not_called()

    def test_clear_resets_chips_and_combine(self, panel):
        """クリアで chip 全解除・組合せトグルが AND に戻る。"""
        panel._rating_chips.set_value("PG")
        panel._ai_rating_chips.set_value("R")
        panel._rating_combine_toggle.set_value("or")
        panel._clear_all_inputs()
        assert panel._get_rating_filter_value() == []
        assert panel._get_ai_rating_filter_value() == []
        assert panel._rating_combine_toggle.value() == "and"


class TestPublicAPICompat:
    """既存 public API の互換維持を確認する。"""

    def test_public_signals_exist(self, panel):
        """既存の public signal が引き続き定義されている。"""
        assert hasattr(panel, "filter_applied")
        assert hasattr(panel, "filter_cleared")
        assert hasattr(panel, "search_requested")
        assert hasattr(panel, "search_completed")
        assert hasattr(panel, "pipeline_state_changed")

    def test_legacy_method_extract_last_token(self, panel):
        """旧 API: 静的ヘルパー _extract_last_token が delegation で利用可能。"""
        assert panel._extract_last_token("a, b") == "b"

    def test_legacy_method_on_search_text_edited(self, panel):
        """旧 API: _on_search_text_edited が TagSuggestionWidget へ delegate される。"""
        panel._tag_suggestion.on_search_text_edited = MagicMock()
        panel._on_search_text_edited("test")
        panel._tag_suggestion.on_search_text_edited.assert_called_once_with("test")


class TestPlaceholderReplacement:
    """placeholder 差し替えのリグレッション (#821)。

    レーティング chip の placeholder はネストした子レイアウト (ratingFilterLayout)
    内にあるため、`_replace_placeholder` がネスト探索できないと chip が
    ratingGroup の末尾にまとめて追加されラベルと分離してズレる。
    """

    def test_rating_chips_placed_in_their_label_rows(self, panel):
        """各レーティング chip 行が [ラベル, chip, ...] の順で同じ行に並ぶ。"""
        from PySide6.QtWidgets import QBoxLayout, QLabel, QWidget

        from lorairo.gui.widgets.filter_search_panel import RatingChipToggleRow

        rating_group = panel.findChild(QWidget, "ratingGroup")
        rating_layout = rating_group.layout()

        chip_rows = []
        for i in range(rating_layout.count()):
            sub = rating_layout.itemAt(i).layout()
            if not isinstance(sub, QBoxLayout):
                continue
            widget_types = [
                type(sub.itemAt(j).widget()) for j in range(sub.count()) if sub.itemAt(j).widget()
            ]
            if any(t is RatingChipToggleRow for t in widget_types):
                chip_rows.append(widget_types)

        # 手動 / AI / 組合せ の 3 行それぞれにラベルと chip が同居している
        assert len(chip_rows) == 3
        for types in chip_rows:
            assert QLabel in types
            assert RatingChipToggleRow in types

        # ratingGroup 直下に RatingChipToggleRow が裸で append されていない (ズレ防止)
        direct_widgets = [
            rating_layout.itemAt(i).widget()
            for i in range(rating_layout.count())
            if rating_layout.itemAt(i).widget() is not None
        ]
        assert not any(isinstance(w, RatingChipToggleRow) for w in direct_widgets)

    def test_date_slider_replaces_placeholder(self, panel):
        """日付スライダー placeholder が CustomRangeSlider に差し替えられる。"""
        from lorairo.gui.widgets.custom_range_slider import CustomRangeSlider

        assert isinstance(panel.date_range_slider, CustomRangeSlider)
        assert panel.date_range_slider.parentWidget() is panel.ui.frameDateRange

    def test_date_filter_labels_clarify_registration_date(self, panel):
        """登録日であることが分かるラベルになっている (#821 UX)。"""
        from PySide6.QtWidgets import QWidget

        assert panel.findChild(QWidget, "dateGroup").title() == "登録日"
        assert panel.ui.checkboxDateFilter.text() == "登録日で絞り込む"


class TestFavoriteConditionsRoundtrip:
    """#1060: お気に入りフィルター条件の保存/復元スキーマ往復一致テスト。

    旧実装は保存キーと復元キーが完全不一致 (一致 0 個) で復元が silent no-op
    だった。save -> clear -> apply -> get で同値になることを固定する。
    """

    def _set_representative_state(self, panel: FilterSearchPanel) -> None:
        """UI に代表的な検索条件を設定する。"""
        panel.ui.lineEditSearch.setText("1girl, -text")
        panel.ui.checkboxTags.setChecked(True)
        panel.ui.checkboxCaption.setChecked(True)
        panel.ui.radioOr.setChecked(True)
        if panel.ui.comboResolution.count() > 1:
            panel.ui.comboResolution.setCurrentIndex(1)
        if panel.ui.comboAspectRatio.count() > 1:
            panel.ui.comboAspectRatio.setCurrentIndex(1)
        panel.ui.checkboxDateFilter.setChecked(True)
        panel.ui.checkboxOnlyUntagged.setChecked(True)
        panel.ui.checkboxOnlyUncaptioned.setChecked(True)
        panel.ui.checkboxExcludeDuplicates.setChecked(True)
        panel.ui.checkboxIncludeUnrated.setChecked(True)
        panel._rating_chips.set_value("PG")
        panel._rating_chips.set_value("R")
        panel._ai_rating_chips.set_value("X")
        panel._rating_combine_toggle.set_value("or")
        panel.score_range_slider.slider.setValue((200, 800))

    def test_save_clear_apply_roundtrip(self, panel):
        """save -> clear -> apply -> get で条件が往復一致する。"""
        self._set_representative_state(panel)

        saved = panel.get_current_conditions()
        assert saved["version"] == FilterSearchPanel.CONDITIONS_SCHEMA_VERSION

        panel._clear_all_inputs()
        # クリアで実際に状態が変わっている (前提確認)
        assert panel.get_current_conditions() != saved

        panel.apply_conditions(saved)
        restored = panel.get_current_conditions()

        assert restored == saved

    def test_save_works_without_search_execution(self, panel):
        """検索を一度も実行していなくても UI の現在状態が保存できる。"""
        panel.ui.lineEditSearch.setText("solo")

        saved = panel.get_current_conditions()

        assert saved["search_text"] == "solo"
        # 旧実装は service の「最後に実行した検索」を参照し未検索では {} を返していた
        assert saved != {}

    def test_apply_legacy_conditions_best_effort(self, panel):
        """version キー無しの旧形式 (search_type/keywords 系) を best-effort 復元する。"""
        legacy = {
            "search_type": "tags",
            "keywords": ["1girl", "solo"],
            "excluded_keywords": ["text"],
            "tag_logic": "or",
            "resolution_filter": None,
            "aspect_ratio_filter": None,
            "date_filter_enabled": False,
            "date_range_start": None,
            "date_range_end": None,
            "only_untagged": True,
            "only_uncaptioned": False,
            "exclude_duplicates": False,
        }

        panel.apply_conditions(legacy)

        assert panel.ui.lineEditSearch.text() == "1girl, solo, -text"
        assert panel.ui.checkboxTags.isChecked() is True
        assert panel.ui.radioOr.isChecked() is True
        assert panel.ui.checkboxOnlyUntagged.isChecked() is True
        # 旧スキーマは include_unrated を保存していない。歴史的既定 True を維持し
        # 未評価画像が全件除外される回帰を防ぐ (Codex P2)
        assert panel.ui.checkboxIncludeUnrated.isChecked() is True

    def test_migrate_legacy_converts_date_bounds(self, panel):
        """旧形式の date_range_start/end (epoch秒/ISO文字列) を date_range へ変換する (Codex P2)。"""
        migrated = FilterSearchPanel._migrate_legacy_conditions(
            {
                "date_filter_enabled": True,
                "date_range_start": 1700000000,
                "date_range_end": "2024-01-15T10:30:00",
            }
        )

        assert migrated["date_filter_enabled"] is True
        start_ts, end_ts = migrated["date_range"]
        assert start_ts == 1700000000
        # ISO 文字列は fromisoformat で epoch 秒へ変換される (TZ はローカル解釈)
        assert isinstance(end_ts, int) and end_ts > start_ts

    def test_migrate_legacy_drops_unconvertible_date_bounds(self, panel):
        """変換できない日付境界は date_range を落とす (誤った日付での検索を防ぐ)。"""
        migrated = FilterSearchPanel._migrate_legacy_conditions(
            {
                "date_filter_enabled": True,
                "date_range_start": "not-a-date",
                "date_range_end": 1700000000,
            }
        )

        assert "date_range" not in migrated
        assert migrated["date_filter_enabled"] is True

    def test_apply_legacy_without_score_range_resets_slider(self, panel):
        """score_range を持たない legacy 条件の適用で旧スライダー値が残留しない (Codex P2)。"""
        panel.score_range_slider.slider.setValue((200, 800))

        panel.apply_conditions({"search_type": "tags", "keywords": ["1girl"]})

        assert panel.score_range_slider.get_range() == (0, 1000)

    def test_apply_oldest_tags_shape_restores_search_text(self, panel):
        """旧々形式 (tags/use_and — 旧 _update_ui_from_conditions の入力形) を変換する (Codex P2)。"""
        panel.apply_conditions({"tags": ["1girl", "solo"], "use_and": False})

        assert panel.ui.lineEditSearch.text() == "1girl, solo"
        assert panel.ui.checkboxTags.isChecked() is True
        assert panel.ui.radioOr.isChecked() is True

    def test_apply_oldest_caption_shape_restores_search_text(self, panel):
        """旧々形式 (caption) を変換する (Codex P2)。"""
        panel.apply_conditions({"caption": "beautiful landscape"})

        assert panel.ui.lineEditSearch.text() == "beautiful landscape"
        assert panel.ui.checkboxCaption.isChecked() is True
        assert panel.ui.checkboxTags.isChecked() is False

    def test_apply_empty_conditions_is_noop(self, panel):
        """空辞書の適用は警告のみで UI を変更しない。"""
        panel.ui.lineEditSearch.setText("keep me")

        panel.apply_conditions({})

        assert panel.ui.lineEditSearch.text() == "keep me"
