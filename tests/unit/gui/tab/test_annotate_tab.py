"""AnnotateTabWidget の GUI テスト (Epic #867 / #868)。

MainWindow から AnnotateTabWidget へ移送した責務 (パイプライン構成ビュー・
モデル選択 SSoT・stage ピッカー往復・preset 配線・送信前プリフライト・推論台帳・
run bar・トップレベル Signal) を、実 ``AnnotateTabWidget`` インスタンス相手に検証する。
移送元: ``tests/unit/gui/window/test_main_window_pipeline_panel.py`` (#868 で削除)。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.state.model_selection_state import ModelSelectionStateManager
from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.annotate_tab import AnnotateTabWidget
from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget
from lorairo.gui.widgets.inference_ledger_widget import InferenceLedgerWidget
from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget
from lorairo.gui.widgets.pipeline_stage_table_widget import PipelineStageTableWidget
from lorairo.gui.widgets.preflight_summary_widget import PreflightSummaryWidget
from lorairo.services.pipeline_composition import (
    PipelineCompositionService,
    PipelineStage,
    StageModelInfo,
)

GPT4O_INFO = StageModelInfo(
    litellm_model_id="openai/gpt-4o",
    display_name="gpt-4o",
    provider="openai",
    is_api=True,
    capabilities=frozenset({"multimodal", "caption", "tags", "scores"}),
)
WD_TAGGER_INFO = StageModelInfo(
    litellm_model_id="wd-v1-4-tagger",
    display_name="wd-v1-4-tagger",
    provider=None,
    is_api=False,
    capabilities=frozenset({"tags"}),
)


def _make_stub_dialog(
    exec_result: QDialog.DialogCode,
    picked_ids: list[str],
) -> tuple[type, dict[str, object]]:
    """StageModelPickerDialog 差し替え用 stub クラスと捕捉 dict を返す。

    headless で ``exec()`` がブロックしないよう固定値を返す。テストごとに新しい
    クラスを生成し、クラスレベルの状態共有 (テスト順依存) を避ける。

    Args:
        exec_result: ``exec()`` が返すダイアログ終了コード。
        picked_ids: ``selected_model_ids()`` が返す litellm_model_id リスト。

    Returns:
        (stub クラス, コンストラクタ引数を記録する dict) のタプル。
    """
    captured: dict[str, object] = {}

    class _StubPickerDialog:
        def __init__(self, stage, candidates, available_providers=None, parent=None):
            captured["stage"] = stage
            captured["candidates"] = candidates
            captured["available_providers"] = available_providers
            captured["parent"] = parent
            # Issue #755: タブが connect する設定導線シグナルの差し替え
            self.configure_key_requested = Mock()

        def exec(self) -> QDialog.DialogCode:
            return exec_result

        def selected_model_ids(self) -> list[str]:
            return picked_ids

    return _StubPickerDialog, captured


@pytest.fixture
def service_container() -> Mock:
    """ModelSelectionService.create / コスト概算を満たす最小 ServiceContainer。"""
    container = Mock()
    # ModelSelectionService.load_models() が空リストを返すよう repo を固定
    container.db_manager.model_repo.get_model_objects.return_value = []
    # _build_cost_map() が空マップで graceful に続行するよう adapter なし扱い
    container.annotator_library = None
    return container


@pytest.fixture
def db_manager() -> Mock:
    """送信前プリフライト用の rating 取得を満たす最小 db_manager。"""
    db = Mock()
    db.image_repo.get_latest_normalized_ratings_by_image_ids.return_value = {}
    return db


@pytest.fixture
def tab(qtbot, service_container: Mock, db_manager: Mock) -> AnnotateTabWidget:
    """実 AnnotateTabWidget を生成して返す。"""
    widget = AnnotateTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=StagingStateManager(),
        dataset_state_manager=DatasetStateManager(),
    )
    qtbot.addWidget(widget)
    return widget


# == 1. ホスト / 構築 =========================================================


@pytest.mark.gui
def test_tab_builds_pipeline_widgets(tab: AnnotateTabWidget) -> None:
    """生成でパイプライン各ウィジェットが実型で構築される。"""
    assert isinstance(tab.pipeline_stage_table, PipelineStageTableWidget)
    assert isinstance(tab.preflight_summary_widget, PreflightSummaryWidget)
    assert isinstance(tab.inference_ledger_widget, InferenceLedgerWidget)
    assert isinstance(tab.batch_model_selection, ModelSelectionWidget)
    assert isinstance(tab.batch_tag_add_widget, BatchTagAddWidget)


# == 2. DI 契約 ===============================================================


@pytest.mark.gui
def test_di_retains_injected_dependencies(
    tab: AnnotateTabWidget, service_container: Mock, db_manager: Mock
) -> None:
    """注入した db_manager / service_container を保持する。"""
    assert tab._db_manager is db_manager
    assert tab._service_container is service_container


@pytest.mark.gui
def test_di_graceful_with_none_managers(qtbot, service_container: Mock) -> None:
    """db_manager / staging / dataset が None でも例外なく構築できる。"""
    widget = AnnotateTabWidget(
        service_container=service_container,
        db_manager=None,
        staging_state_manager=None,
        dataset_state_manager=None,
    )
    qtbot.addWidget(widget)

    assert widget._db_manager is None
    # None db_manager でも preflight 再計算は空集合で skip され例外を出さない
    widget.refresh()


# == 3. モデル選択 SSoT: 追加ハンドラ =========================================


def _wire_model_selection(
    tab: AnnotateTabWidget,
    checkbox_widgets: dict[str, Mock],
    selected_ids: list[str],
    infos: list[StageModelInfo],
) -> Mock:
    """追加/削除ハンドラ検証用に内部コラボレータを Mock へ差し替える。

    memory: クラスレベルではなくインスタンス属性を差し替えてテスト汚染を避ける。
    """
    model_widget = Mock()
    model_widget.model_checkbox_widgets = checkbox_widgets
    model_widget.get_selected_models.return_value = selected_ids
    model_widget.model_selection_service.load_models.return_value = [
        SimpleNamespace(litellm_model_id=info.litellm_model_id) for info in infos
    ]
    tab._batch_model_selection = model_widget
    tab._build_stage_model_infos = lambda ids: infos
    tab._refresh_pipeline_panel = Mock()
    tab._available_api_providers = lambda: set()
    return model_widget


@pytest.mark.gui
class TestPipelineAddModelHandler:
    """「+ 追加」ハンドラ: ピッカー Accepted → チェック ON 変換の検証 (Phase 6b)。"""

    def test_accepted_dialog_sets_selected_true(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        checkbox = Mock()
        _wire_model_selection(tab, {"openai/gpt-4o": checkbox}, [], [GPT4O_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Accepted, ["openai/gpt-4o"])
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("tags")

        assert captured["stage"] is PipelineStage.TAGS
        checkbox.set_selected.assert_called_once_with(True)
        tab._refresh_pipeline_panel.assert_called_once_with()

    def test_candidates_filtered_by_stage_and_unselected(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        # GPT4O は選択済み → 除外。WD_TAGGER は tags 適格 → 候補。
        _wire_model_selection(tab, {}, ["openai/gpt-4o"], [GPT4O_INFO, WD_TAGGER_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("tags")

        candidates = captured["candidates"]
        assert [info.litellm_model_id for info in candidates] == ["wd-v1-4-tagger"]

    def test_stage_ineligible_model_not_in_candidates(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        # WD_TAGGER (tags のみ) も multimodal も RATING には届かない。
        _wire_model_selection(tab, {}, [], [GPT4O_INFO, WD_TAGGER_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("rating")

        assert captured["candidates"] == []

    def test_rejected_dialog_does_not_change_selection(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        checkbox = Mock()
        _wire_model_selection(tab, {"openai/gpt-4o": checkbox}, [], [GPT4O_INFO])
        stub_cls, _captured = _make_stub_dialog(QDialog.DialogCode.Rejected, ["openai/gpt-4o"])
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("tags")

        checkbox.set_selected.assert_not_called()
        tab._refresh_pipeline_panel.assert_not_called()

    def test_picked_id_missing_from_checkbox_dict_is_skipped(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        checkbox = Mock()
        _wire_model_selection(tab, {"openai/gpt-4o": checkbox}, [], [GPT4O_INFO, WD_TAGGER_INFO])
        # wd-v1-4-tagger は dict に無い → 例外なくスキップ
        stub_cls, _captured = _make_stub_dialog(
            QDialog.DialogCode.Accepted, ["wd-v1-4-tagger", "openai/gpt-4o"]
        )
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("tags")

        checkbox.set_selected.assert_called_once_with(True)
        tab._refresh_pipeline_panel.assert_called_once_with()

    def test_picker_receives_available_providers(self, tab, monkeypatch):
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        _wire_model_selection(tab, {}, [], [GPT4O_INFO])
        tab._available_api_providers = lambda: {"openai"}
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

        tab._on_pipeline_add_model_requested("tags")

        assert captured["available_providers"] == {"openai"}


# == 4. モデル選択 SSoT: 削除ハンドラ =========================================


@pytest.mark.gui
class TestPipelineRemoveModelHandler:
    """Primary × ハンドラ: チェック OFF 変換の検証 (Phase 6b)。"""

    def test_remove_sets_selected_false(self, tab):
        checkbox = Mock()
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_checkbox_widgets = {"openai/gpt-4o": checkbox}
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_remove_model_requested("caption", "openai/gpt-4o")

        checkbox.set_selected.assert_called_once_with(False)
        tab._refresh_pipeline_panel.assert_called_once_with()

    def test_remove_missing_id_is_noop_without_error(self, tab):
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_checkbox_widgets = {}
        tab._refresh_pipeline_panel = Mock()

        # dict に無い id でも例外を出さずスキップする
        tab._on_pipeline_remove_model_requested("tags", "missing/model")

        tab._refresh_pipeline_panel.assert_not_called()


# == 5. preset 配線 ===========================================================


@pytest.mark.gui
class TestFilterModelIdsForPreset:
    """プリセット ID → モデル ID フィルタの検証 (Issue #847)。"""

    def _make_info(self, litellm_id: str, capabilities: set[str], is_api: bool = True) -> StageModelInfo:
        return StageModelInfo(
            litellm_model_id=litellm_id,
            display_name=litellm_id,
            provider="openai" if is_api else None,
            is_api=is_api,
            capabilities=frozenset(capabilities),
        )

    def test_default_returns_all(self, tab):
        infos = [
            self._make_info("a/tags", {"tags"}),
            self._make_info("b/caption", {"caption", "multimodal"}),
            self._make_info("c/score", {"scores"}),
        ]
        result = tab._filter_model_ids_for_preset("default", infos)
        assert set(result) == {"a/tags", "b/caption", "c/score"}

    def test_tags_only_excludes_multimodal(self, tab):
        infos = [
            self._make_info("a/tags", {"tags"}, is_api=False),
            self._make_info("b/multi", {"tags", "caption", "multimodal"}),
            self._make_info("c/caption", {"caption"}),
        ]
        result = tab._filter_model_ids_for_preset("tags_only", infos)
        assert result == ["a/tags"]

    def test_full_caption_includes_multimodal_and_caption(self, tab):
        infos = [
            self._make_info("a/tags", {"tags"}, is_api=False),
            self._make_info("b/multi", {"tags", "caption", "multimodal"}),
            self._make_info("c/caption", {"caption"}),
        ]
        result = tab._filter_model_ids_for_preset("full_caption", infos)
        assert set(result) == {"b/multi", "c/caption"}

    def test_score_rate_includes_scores_and_ratings(self, tab):
        infos = [
            self._make_info("a/score", {"scores"}),
            self._make_info("b/rating", {"ratings"}),
            self._make_info("c/tags", {"tags"}, is_api=False),
        ]
        result = tab._filter_model_ids_for_preset("score_rate", infos)
        assert set(result) == {"a/score", "b/rating"}

    def test_unknown_preset_returns_all(self, tab):
        infos = [
            self._make_info("a/tags", {"tags"}),
            self._make_info("b/score", {"scores"}),
        ]
        result = tab._filter_model_ids_for_preset("unknown_preset", infos)
        assert set(result) == {"a/tags", "b/score"}


@pytest.mark.gui
class TestPresetSignalWiring:
    """preset_selected / save_preset_requested ハンドラの動作検証 (Issue #847)。"""

    def test_preset_selected_calls_set_selected_models(self, tab):
        info = StageModelInfo(
            litellm_model_id="wd/tagger",
            display_name="wd-tagger",
            provider=None,
            is_api=False,
            capabilities=frozenset({"tags"}),
        )
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = [
            SimpleNamespace(litellm_model_id="wd/tagger")
        ]
        tab._build_stage_model_infos = lambda ids: [info]
        tab._filter_model_ids_for_preset = lambda pid, infos: ["wd/tagger"]
        tab._pipeline_stage_table = Mock()
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_preset_selected("tags_only")

        tab._batch_model_selection.set_selected_models.assert_called_once_with(["wd/tagger"])

    def test_preset_selected_syncs_active_preset_display(self, tab):
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = []
        tab._build_stage_model_infos = lambda ids: []
        tab._filter_model_ids_for_preset = lambda pid, infos: []
        tab._pipeline_stage_table = Mock()
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_preset_selected("default")

        tab._pipeline_stage_table.set_active_preset.assert_called_once_with("default")

    def test_preset_selected_refreshes_pipeline_panel(self, tab):
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = []
        tab._build_stage_model_infos = lambda ids: []
        tab._filter_model_ids_for_preset = lambda pid, infos: []
        tab._pipeline_stage_table = Mock()
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_preset_selected("full_caption")

        tab._refresh_pipeline_panel.assert_called_once_with()

    def test_save_preset_reads_selected_models(self, tab):
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = ["wd/tagger"]

        # 永続化は未実装 (TODO #847) だがクラッシュせず選択を読み出す
        tab._on_pipeline_save_preset_requested()

        tab._batch_model_selection.get_selected_models.assert_called_once_with()


# == 6. 送信前プリフライト ====================================================


@pytest.mark.gui
class TestPreflightSummaryRefresh:
    """Issue #837: 送信前プリフライト card 配線の検証。"""

    def test_queries_ratings_and_displays(self, tab):
        tab._preflight_summary_widget = Mock()
        tab._db_manager = Mock()
        tab._pipeline_staged_image_ids = [1, 2]
        ratings = {1: "PG", 2: "X"}
        repo = tab._db_manager.image_repo
        repo.get_latest_normalized_ratings_by_image_ids.return_value = ratings

        tab._refresh_preflight_summary()

        repo.get_latest_normalized_ratings_by_image_ids.assert_called_once_with([1, 2])
        tab._preflight_summary_widget.display.assert_called_once_with(ratings, [1, 2])

    def test_empty_staging_skips_query(self, tab):
        tab._preflight_summary_widget = Mock()
        tab._db_manager = Mock()
        tab._pipeline_staged_image_ids = []

        tab._refresh_preflight_summary()

        repo = tab._db_manager.image_repo
        repo.get_latest_normalized_ratings_by_image_ids.assert_not_called()
        tab._preflight_summary_widget.display.assert_called_once_with({}, [])


# == パイプライン再描画配線 ===================================================


@pytest.mark.gui
class TestPipelinePanelRefresh:
    """選択変化・ステージング変化での再描画配線の検証。"""

    def test_models_changed_triggers_refresh_with_ids(self, tab):
        tab._refresh_pipeline_panel = Mock()
        tab._on_pipeline_models_changed(["openai/gpt-4o"])
        tab._refresh_pipeline_panel.assert_called_once_with(["openai/gpt-4o"])

    def test_refresh_composes_and_displays(self, tab):
        """実 PipelineCompositionService で multimodal 構成が表示に渡ることを検証。"""
        tab._pipeline_composition_service = PipelineCompositionService()
        tab._pipeline_staged_count = 9
        tab._build_stage_model_infos = lambda ids: [GPT4O_INFO]
        tab._pipeline_stage_table = Mock()
        tab._inference_ledger_widget = Mock()

        tab._refresh_pipeline_panel(["openai/gpt-4o"])

        rows = tab._pipeline_stage_table.display.call_args[0][0]
        rows_by_stage = {row.stage: row for row in rows}
        # multimodal は CAPTION に明示割当、TAGS/SCORE に派生、RATING には届かない
        assert [m.litellm_model_id for m in rows_by_stage[PipelineStage.CAPTION].primary_models] == [
            "openai/gpt-4o"
        ]
        assert [c.model.litellm_model_id for c in rows_by_stage[PipelineStage.TAGS].derived_chips] == [
            "openai/gpt-4o"
        ]
        assert rows_by_stage[PipelineStage.RATING].derived_chips == ()

        ledger = tab._inference_ledger_widget.display.call_args[0][0]
        assert ledger.unique_model_count == 1
        assert ledger.total_jobs == 9

    def test_set_staging_target_syncs_counts(self, tab):
        """set_staging_target で件数・image_id 集合が同期され再計算される。"""
        tab._refresh_pipeline_panel = Mock()
        tab._refresh_preflight_summary = Mock()

        tab.set_staging_target([1, 2, 3])

        assert tab._pipeline_staged_count == 3
        # Issue #837: 送信前プリフライト用の image_id 集合も同期する
        assert tab._pipeline_staged_image_ids == [1, 2, 3]
        tab._refresh_pipeline_panel.assert_called_once_with()
        tab._refresh_preflight_summary.assert_called_once_with()


# == 7. run bar テキスト ======================================================


@pytest.mark.gui
class TestRunBar:
    """run bar の表示テキスト生成と件数反映の検証 (Issue #849)。"""

    def test_scope_text_contains_count(self):
        assert "42" in AnnotateTabWidget._run_bar_scope_text(42)

    def test_scope_text_zero(self):
        assert "0" in AnnotateTabWidget._run_bar_scope_text(0)

    def test_execute_text_contains_count(self):
        assert "7" in AnnotateTabWidget._run_bar_execute_text(7)

    def test_execute_text_contains_枚(self):
        assert "枚" in AnnotateTabWidget._run_bar_execute_text(3)

    def test_update_target_ui_enables_execute_with_staging(self, tab):
        tab._update_annotation_target_ui(5)

        assert tab._btn_pipeline_execute.isEnabled() is True
        assert "5" in tab._btn_pipeline_execute.text()
        assert "5" in tab._run_bar_scope_label.text()

    def test_update_target_ui_disables_execute_when_empty(self, tab):
        tab._update_annotation_target_ui(0)

        assert tab._btn_pipeline_execute.isEnabled() is False


# == 8. トップレベル Signal ===================================================


@pytest.mark.gui
def test_execute_button_emits_annotation_execute_requested(tab, qtbot):
    """run bar 実行ボタンクリックで annotation_execute_requested が emit される。"""
    tab._update_annotation_target_ui(2)  # ボタンを有効化

    with qtbot.waitSignal(tab.annotation_execute_requested, timeout=1000):
        tab._btn_pipeline_execute.click()


@pytest.mark.gui
def test_picker_configure_key_emits_signal(tab, qtbot):
    """ピッカーの configure key 導線が configure_key_requested(provider) を emit する。"""
    tab._available_api_providers = lambda: {"anthropic"}
    tab._reload_model_widget_after_settings = Mock()
    dialog = Mock()

    with qtbot.waitSignal(tab.configure_key_requested, timeout=1000) as blocker:
        tab._on_picker_configure_key_requested("anthropic", dialog)

    assert blocker.args == ["anthropic"]
    tab._reload_model_widget_after_settings.assert_called_once_with()
    dialog.refresh_key_status.assert_called_once_with({"anthropic"})


# == 10. _available_api_providers / _build_stage_model_infos ===================


@pytest.mark.gui
class TestAvailableApiProviders:
    """Issue #755: config からの API キー設定済み provider 集合の導出。"""

    def test_only_providers_with_nonempty_keys(self, tab):
        keys = {
            ("api", "openai_key"): "sk-test",
            ("api", "claude_key"): "   ",
            ("api", "google_key"): "",
            ("api", "openrouter_key"): "or-key",
        }
        tab._service_container.config_service.get_setting.side_effect = lambda section, key, default="": (
            keys.get((section, key), default)
        )

        assert tab._available_api_providers() == {"openai", "openrouter"}

    def test_missing_config_service_returns_empty(self, tab):
        tab._service_container.config_service = None
        assert tab._available_api_providers() == set()


@pytest.mark.gui
class TestBuildStageModelInfos:
    """litellm_model_id → StageModelInfo 変換の検証。"""

    def _wire(self, tab: AnnotateTabWidget, models: list[SimpleNamespace]) -> None:
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = models
        tab._build_cost_map = lambda: {}

    def test_converts_api_model_with_capabilities(self, tab):
        self._wire(
            tab,
            [
                SimpleNamespace(
                    litellm_model_id="openai/gpt-4o",
                    name="gpt-4o",
                    provider="openai",
                    capabilities=["multimodal", "caption", "tags", "scores"],
                )
            ],
        )
        infos = tab._build_stage_model_infos(["openai/gpt-4o"])

        assert len(infos) == 1
        assert infos[0].is_api is True
        assert infos[0].is_multimodal is True
        assert infos[0].capabilities == frozenset({"multimodal", "caption", "tags", "scores"})

    def test_local_provider_none_is_not_api(self, tab):
        self._wire(
            tab,
            [
                SimpleNamespace(
                    litellm_model_id="wd-v1-4-tagger",
                    name="wd-v1-4-tagger",
                    provider=None,
                    capabilities=["tags"],
                )
            ],
        )
        infos = tab._build_stage_model_infos(["wd-v1-4-tagger"])

        assert infos[0].is_api is False
        assert infos[0].is_multimodal is False

    def test_provider_local_string_is_not_api(self, tab):
        self._wire(
            tab,
            [
                SimpleNamespace(
                    litellm_model_id="aesthetic-v2",
                    name="aesthetic-v2",
                    provider="local",
                    capabilities=["scores"],
                )
            ],
        )
        infos = tab._build_stage_model_infos(["aesthetic-v2"])

        assert infos[0].is_api is False

    def test_unknown_id_is_skipped(self, tab):
        self._wire(tab, [])
        assert tab._build_stage_model_infos(["missing/model"]) == []


# == 11. #850 負アサート ======================================================


@pytest.mark.gui
def test_tab_does_not_host_annotation_data_display(tab: AnnotateTabWidget) -> None:
    """#850: AnnotateTabWidget は batchTagAnnotationDisplay / AnnotationDataDisplayWidget を持たない。"""
    assert not hasattr(tab, "batchTagAnnotationDisplay")

    from PySide6.QtWidgets import QWidget

    for child in tab.findChildren(QWidget):
        assert type(child).__name__ != "AnnotationDataDisplayWidget"


# == 12. AnnotationFilter → ModelSelection 連携 (旧 WidgetSetupService から移送) =====


class TestFilterToModelDelegation:
    """AnnotationFilterWidget の出力を ModelSelectionWidget.apply_filters へ変換する配線。

    旧 ``WidgetSetupService._build_model_selection_filters`` /
    ``_configure_batch_model_selection_widget`` は AnnotateTabWidget へ移送された (#868)。
    """

    @pytest.mark.gui
    def test_api_environment_maps_to_execution_env(self, tab: AnnotateTabWidget) -> None:
        """API環境指定時、execution_env="APIモデルのみ" で apply_filters を呼ぶ。"""
        tab._batch_model_selection = Mock()
        tab._apply_filter_to_model({"capabilities": [], "environment": "api"})
        tab._batch_model_selection.apply_filters.assert_called_once_with(
            provider=None,
            capabilities=[],
            exclude_local=False,
            execution_env="APIモデルのみ",
            annotation_only=True,
        )

    @pytest.mark.gui
    def test_local_environment_maps_to_execution_env(self, tab: AnnotateTabWidget) -> None:
        """ローカル環境指定時、execution_env="ローカルモデルのみ" で apply_filters を呼ぶ。"""
        tab._batch_model_selection = Mock()
        tab._apply_filter_to_model({"capabilities": [], "environment": "local"})
        tab._batch_model_selection.apply_filters.assert_called_once_with(
            provider=None,
            capabilities=[],
            exclude_local=False,
            execution_env="ローカルモデルのみ",
            annotation_only=True,
        )

    @pytest.mark.gui
    def test_capabilities_passed_through_without_environment(self, tab: AnnotateTabWidget) -> None:
        """選択済み capabilities はそのまま渡し、環境未指定なら execution_env は None。"""
        tab._batch_model_selection = Mock()
        tab._apply_filter_to_model({"capabilities": ["caption"], "environment": None})
        tab._batch_model_selection.apply_filters.assert_called_once_with(
            provider=None,
            capabilities=["caption"],
            exclude_local=False,
            execution_env=None,
            annotation_only=True,
        )

    @pytest.mark.gui
    def test_missing_capabilities_defaults_to_empty_list(self, tab: AnnotateTabWidget) -> None:
        """capabilities キー欠落時も絞り込みなし (空リスト) として扱う。"""
        tab._batch_model_selection = Mock()
        tab._apply_filter_to_model({"environment": None})
        tab._batch_model_selection.apply_filters.assert_called_once_with(
            provider=None,
            capabilities=[],
            exclude_local=False,
            execution_env=None,
            annotation_only=True,
        )

    @pytest.mark.gui
    def test_model_selection_hides_internal_execution_env_combo(self, tab: AnnotateTabWidget) -> None:
        """Batch annotation ではモデル選択側の環境 Combo を操作面にしない。"""
        assert tab.batch_model_selection.executionEnvCombo.isVisible() is False


# == 13. ModelSelectionStateManager DI + 双方向同期 (#884) =====================


@pytest.fixture
def annotate_tab_with_state(
    qtbot: object, service_container: Mock, db_manager: Mock
) -> tuple[AnnotateTabWidget, ModelSelectionStateManager]:
    """ModelSelectionStateManager を注入した AnnotateTabWidget と manager を返す。"""
    state_manager = ModelSelectionStateManager()
    widget = AnnotateTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=None,
        dataset_state_manager=None,
        model_selection_state_manager=state_manager,
    )
    qtbot.addWidget(widget)
    return widget, state_manager


@pytest.mark.gui
def test_widget_selection_propagates_to_state_manager(
    qtbot: object, annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager]
) -> None:
    """ModelSelectionWidget の選択変化が state manager へ伝播する。"""
    widget, state_manager = annotate_tab_with_state
    widget.batch_model_selection.model_selection_changed.emit(["openai/gpt-4o"])
    assert state_manager.get_selected() == ["openai/gpt-4o"]


@pytest.mark.gui
def test_state_manager_change_updates_getter(
    qtbot: object, annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager]
) -> None:
    """state manager の変更が selected_litellm_model_ids() に反映される。"""
    widget, state_manager = annotate_tab_with_state
    # manager が SSoT なので getter は manager から読む
    state_manager.set_selected(["openai/gpt-4o"])
    assert widget.selected_litellm_model_ids() == ["openai/gpt-4o"]


@pytest.mark.gui
def test_state_manager_change_reflects_to_widget_view(
    qtbot: object,
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """state manager の変更が ModelSelectionWidget (view) の set_selected_models に伝播する。

    _on_state_model_selection_changed が no-op になっても getter 経路では検出できないため、
    widget.batch_model_selection.set_selected_models を spy してコール引数を直接検証する。
    """
    widget, state_manager = annotate_tab_with_state
    calls: list[list[str]] = []
    original = widget.batch_model_selection.set_selected_models
    monkeypatch.setattr(
        widget.batch_model_selection,
        "set_selected_models",
        lambda ids: (calls.append(list(ids)), original(ids)),
    )

    state_manager.set_selected(["openai/gpt-4o"])

    assert calls == [["openai/gpt-4o"]]


@pytest.mark.gui
def test_programmatic_widget_change_syncs_to_state(
    qtbot: object,
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """picker/preset 等 programmatic 変更後にヘルパーが manager を widget の ground-truth へ同期する (#884)。

    ``ModelCheckboxWidget.set_selected`` / ``ModelSelectionWidget.set_selected_models``
    は checkbox signal を抑制するため、_sync_widget_selection_to_state が
    widget の get_selected_models() を明示的に SSoT へ押し出す必要がある。
    """
    widget, state_manager = annotate_tab_with_state
    monkeypatch.setattr(
        widget.batch_model_selection, "get_selected_models", lambda: ["openai/gpt-4o", "anthropic/claude"]
    )
    widget._sync_widget_selection_to_state()
    assert state_manager.get_selected() == ["openai/gpt-4o", "anthropic/claude"]


@pytest.mark.gui
def test_preset_selected_syncs_widget_ground_truth_to_state(
    qtbot: object,
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_on_pipeline_preset_selected が manager を widget の ground-truth へ同期する (#884 P1)。

    preset 適用は set_selected_models (signal 抑制) で行われるため、
    _sync_widget_selection_to_state 呼び出しがないと manager が stale になる。
    widget.batch_model_selection.set_selected_models と get_selected_models を stub し、
    preset 適用後に state_manager.get_selected() が stub の戻り値と一致することを検証する。
    """
    widget, state_manager = annotate_tab_with_state

    preset_model_ids = ["wd/tagger", "openai/gpt-4o"]
    # set_selected_models は signal を抑制するため manager 同期は _sync_widget_selection_to_state に依存
    monkeypatch.setattr(widget.batch_model_selection, "set_selected_models", lambda ids: None)
    monkeypatch.setattr(widget.batch_model_selection, "get_selected_models", lambda: preset_model_ids)
    # 内部 Mock を差し替えてピュアに preset 経路のみを通す
    widget._batch_model_selection = widget.batch_model_selection
    widget._pipeline_stage_table = Mock()
    widget._refresh_pipeline_panel = Mock()
    widget._build_stage_model_infos = lambda ids: []
    widget._filter_model_ids_for_preset = lambda pid, infos: preset_model_ids
    service_mock = Mock()
    service_mock.load_models.return_value = []
    widget.batch_model_selection.model_selection_service = service_mock

    widget._on_pipeline_preset_selected("default")

    assert state_manager.get_selected() == preset_model_ids
