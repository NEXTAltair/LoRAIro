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


# == 2b. staging パス解決 helper (#896 PR4a: MainWindow から移送) ==============


@pytest.mark.gui
class TestStagedPathHelpers:
    """staging 画像の {image_id: パス} 解決 helper (#896 PR4a)。

    MainWindow から ``_get_staged_id_path_map_for_annotation`` /
    ``_get_staged_image_paths_for_annotation`` を移送した先を検証する。
    """

    def test_staged_id_path_map_resolves_only_existing(self, tab, monkeypatch):
        """resolve 後に存在するパスのみ返し、存在しない画像は除外する。"""
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        monkeypatch.setattr(
            tab, "get_staged_items", lambda: {1: ("a", "stored/1.png"), 2: ("b", "stored/2.png")}
        )

        class _FakePath:
            def __init__(self, value: str) -> None:
                self._value = value

            def exists(self) -> bool:
                # 1.png のみ存在する想定
                return "1" in self._value

            def __str__(self) -> str:
                return self._value

        monkeypatch.setattr(annotate_tab_module, "resolve_stored_path", lambda p: _FakePath(p))

        assert tab.staged_id_path_map() == {1: "stored/1.png"}

    def test_staged_id_path_map_empty_without_dataset_manager(self, qtbot, service_container):
        """DatasetStateManager 未注入時はパス解決せず空辞書を返す。"""
        widget = AnnotateTabWidget(
            service_container=service_container,
            db_manager=None,
            staging_state_manager=None,
            dataset_state_manager=None,
        )
        qtbot.addWidget(widget)
        widget.get_staged_items = lambda: {1: ("a", "stored/1.png")}  # type: ignore[method-assign]

        assert widget.staged_id_path_map() == {}

    def test_staged_image_paths_returns_map_values(self, tab, monkeypatch):
        """staged_image_paths は id→path マップの値リストを返す。"""
        monkeypatch.setattr(tab, "staged_id_path_map", lambda: {1: "/a.png", 2: "/b.png"})

        assert tab.staged_image_paths() == ["/a.png", "/b.png"]

    def test_show_model_selection_dialog_returns_pick(self, tab, monkeypatch):
        """ダイアログ確定時に選択モデルを返す。"""
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        class _FakeInputDialog:
            @staticmethod
            def getItem(*args, **kwargs):
                return ("openai/gpt-4o", True)

        monkeypatch.setattr(annotate_tab_module, "QInputDialog", _FakeInputDialog)

        assert tab.show_model_selection_dialog(["openai/gpt-4o"]) == "openai/gpt-4o"

    def test_show_model_selection_dialog_cancel_returns_none(self, tab, monkeypatch):
        """ダイアログキャンセル時は None を返す。"""
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        class _FakeInputDialog:
            @staticmethod
            def getItem(*args, **kwargs):
                return ("openai/gpt-4o", False)

        monkeypatch.setattr(annotate_tab_module, "QInputDialog", _FakeInputDialog)

        assert tab.show_model_selection_dialog(["openai/gpt-4o"]) is None


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


@pytest.mark.gui
class TestCustomPresetPersistence:
    """プリセット永続化 (保存/一覧/適用) の検証 (Issue #1186)。"""

    @pytest.fixture
    def isolated_settings(self, tab, tmp_path, monkeypatch):
        """QSettings を一時 INI ファイルへ隔離する。"""
        from PySide6.QtCore import QSettings

        settings_file = tmp_path / "presets.ini"

        def _settings() -> QSettings:
            return QSettings(str(settings_file), QSettings.Format.IniFormat)

        monkeypatch.setattr(tab, "_preset_settings", _settings)
        return _settings

    @staticmethod
    def _fake_input_dialog(monkeypatch, name: str, ok: bool) -> None:
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        class _FakeInputDialog:
            @staticmethod
            def getText(*args, **kwargs):
                return (name, ok)

        monkeypatch.setattr(annotate_tab_module, "QInputDialog", _FakeInputDialog)

    def test_save_preset_persists_and_adds_chip(self, tab, isolated_settings, monkeypatch):
        """保存確定でプリセットが永続化され、chip 行へ反映・アクティブ化される。"""
        self._fake_input_dialog(monkeypatch, "My preset", True)
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = ["openai/gpt-4o", "wd/tagger"]
        tab._pipeline_stage_table = Mock()

        tab._on_pipeline_save_preset_requested()

        assert tab._load_custom_presets() == {"My preset": ["openai/gpt-4o", "wd/tagger"]}
        chips = tab._pipeline_stage_table.set_custom_presets.call_args[0][0]
        assert [(c.preset_id, c.label, c.model_count) for c in chips] == [
            ("custom:My preset", "My preset", 2)
        ]
        tab._pipeline_stage_table.set_active_preset.assert_called_once_with("custom:My preset")

    def test_save_preset_overwrites_same_name(self, tab, isolated_settings, monkeypatch):
        """同名プリセットは上書きされる。"""
        self._fake_input_dialog(monkeypatch, "mine", True)
        tab._save_custom_presets({"mine": ["old/model"]})
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = ["new/model"]
        tab._pipeline_stage_table = Mock()

        tab._on_pipeline_save_preset_requested()

        assert tab._load_custom_presets() == {"mine": ["new/model"]}

    def test_save_preset_canceled_does_not_persist(self, tab, isolated_settings, monkeypatch):
        """名前入力キャンセル時は何も保存しない。"""
        self._fake_input_dialog(monkeypatch, "mine", False)
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = ["wd/tagger"]
        tab._pipeline_stage_table = Mock()

        tab._on_pipeline_save_preset_requested()

        assert tab._load_custom_presets() == {}
        tab._pipeline_stage_table.set_custom_presets.assert_not_called()

    def test_save_preset_blank_name_does_not_persist(self, tab, isolated_settings, monkeypatch):
        """空白のみの名前は保存しない。"""
        self._fake_input_dialog(monkeypatch, "   ", True)
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = ["wd/tagger"]
        tab._pipeline_stage_table = Mock()

        tab._on_pipeline_save_preset_requested()

        assert tab._load_custom_presets() == {}

    def test_save_preset_empty_selection_warns(self, tab, isolated_settings, monkeypatch):
        """選択モデルゼロでは警告して保存しない。"""
        from lorairo.gui.tab import annotate_tab as annotate_tab_module

        warnings: list[tuple] = []
        monkeypatch.setattr(
            annotate_tab_module, "show_warning", lambda *args, **kwargs: warnings.append(args)
        )
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.get_selected_models.return_value = []
        tab._pipeline_stage_table = Mock()

        tab._on_pipeline_save_preset_requested()

        assert len(warnings) == 1
        assert tab._load_custom_presets() == {}

    def test_custom_preset_selected_applies_stored_models(self, tab, isolated_settings):
        """保存済みプリセット選択で、現在利用可能なモデルに絞って適用される。"""
        info = StageModelInfo(
            litellm_model_id="wd/tagger",
            display_name="wd-tagger",
            provider=None,
            is_api=False,
            capabilities=frozenset({"tags"}),
        )
        # "gone/model" は保存後に利用不能になった想定
        tab._save_custom_presets({"mine": ["wd/tagger", "gone/model"]})
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = [
            SimpleNamespace(litellm_model_id="wd/tagger")
        ]
        tab._build_stage_model_infos = lambda ids: [info]
        tab._pipeline_stage_table = Mock()
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_preset_selected("custom:mine")

        tab._batch_model_selection.set_selected_models.assert_called_once_with(["wd/tagger"])
        tab._pipeline_stage_table.set_active_preset.assert_called_once_with("custom:mine")

    def test_custom_preset_missing_is_skipped(self, tab, isolated_settings):
        """存在しない保存済みプリセットの選択は適用せずスキップする。"""
        tab._batch_model_selection = Mock()
        tab._batch_model_selection.model_selection_service.load_models.return_value = []
        tab._build_stage_model_infos = lambda ids: []
        tab._pipeline_stage_table = Mock()
        tab._refresh_pipeline_panel = Mock()

        tab._on_pipeline_preset_selected("custom:nothere")

        tab._batch_model_selection.set_selected_models.assert_not_called()

    def test_load_custom_presets_tolerates_broken_json(self, tab, isolated_settings):
        """破損 JSON は空として扱いクラッシュしない。"""
        settings = tab._preset_settings()
        settings.setValue("annotate_tab/custom_presets", "{broken json")
        settings.sync()

        assert tab._load_custom_presets() == {}


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

    def test_batch_api_dispatch_splits_batch_capable_to_batch_lane(self, tab):
        """#884 Phase 4b: dispatch_mode=batch_api で lib の batch 対応集合を消費しレーン分割。"""
        from types import SimpleNamespace

        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        tab._pipeline_composition_service = PipelineCompositionService()
        tab._pipeline_staged_count = 9
        tab._build_stage_model_infos = lambda ids: [GPT4O_INFO]
        tab._pipeline_stage_table = Mock()
        tab._inference_ledger_widget = Mock()
        tab._pipeline_run_options = RunOptions(dispatch_mode="batch_api")
        tab._service_container.provider_batch_workflow_service.list_batch_capable_models.return_value = [
            "openai/gpt-4o"
        ]
        # #1136: LEDGER レーン判定が実振り分けと同じ eligibility (DB 解決 + task_type) を使うため
        # gpt-4o を解決可能な直 openai モデルとして返す。
        tab._db_manager.model_repo.get_model_by_litellm_id.return_value = SimpleNamespace(
            id=1, provider="openai", litellm_model_id="openai/gpt-4o"
        )

        tab._refresh_pipeline_panel(["openai/gpt-4o"])

        ledger = tab._inference_ledger_widget.display.call_args[0][0]
        assert len(ledger.batch_entries) == 1
        assert ledger.batch_entries[0].model.litellm_model_id == "openai/gpt-4o"

    def test_batch_capable_ids_task_type_aware_excludes_normal_with_moderation(self, tab):
        """#1136 Codex P2 #3: moderation 混在時、通常モデルは batch レーンから外れ実振り分けと一致。"""
        from types import SimpleNamespace

        tab._service_container.provider_batch_workflow_service.list_batch_capable_models.return_value = [
            "openai/omni-moderation-latest",
            "openai/gpt-4o",
        ]
        models = {
            "openai/omni-moderation-latest": SimpleNamespace(
                id=5, provider="openai", litellm_model_id="openai/omni-moderation-latest"
            ),
            "openai/gpt-4o": SimpleNamespace(id=1, provider="openai", litellm_model_id="openai/gpt-4o"),
        }
        tab._db_manager.model_repo.get_model_by_litellm_id.side_effect = models.get

        capable = tab._resolve_batch_capable_ids(["openai/omni-moderation-latest", "openai/gpt-4o"])

        # moderation → rating_preflight で batch、通常 gpt-4o は rating_preflight 非対応 → sync
        assert capable == {"openai/omni-moderation-latest"}

    def test_batch_capable_ids_annotation_includes_normal(self, tab):
        """#1136: moderation 無しなら通常モデルは annotation で batch レーンに乗る。"""
        from types import SimpleNamespace

        tab._service_container.provider_batch_workflow_service.list_batch_capable_models.return_value = [
            "openai/gpt-4o"
        ]
        tab._db_manager.model_repo.get_model_by_litellm_id.return_value = SimpleNamespace(
            id=1, provider="openai", litellm_model_id="openai/gpt-4o"
        )

        capable = tab._resolve_batch_capable_ids(["openai/gpt-4o"])

        assert capable == {"openai/gpt-4o"}

    def test_resolve_batch_capable_ids_with_real_service_no_attribute_error(self, tab):
        """#1147: 実 ProviderBatchWorkflowService でも AttributeError を出さず LEDGER 判定できる。

        実機クラッシュ (workflow service に list_batch_capable_models が無い) の GUI 経路 regression。
        MagicMock でなく **実サービス** (adapter stub 注入) を container に差し込んで検証する。
        """
        from types import SimpleNamespace
        from unittest.mock import Mock

        from lorairo.services.provider_batch_workflow_service import ProviderBatchWorkflowService

        class _StubAdapter:
            provider = "openai"

            def list_batch_capable_models(self):
                return ("openai/gpt-4o",)

        real_service = ProviderBatchWorkflowService(
            provider_batch_repo=Mock(),
            image_repo=Mock(),
            annotation_repo=Mock(),
            config_service=Mock(),
            adapters={"openai": _StubAdapter()},
            job_service=Mock(),
            annotation_save_service=Mock(),
        )
        tab._service_container.provider_batch_workflow_service = real_service
        tab._db_manager.model_repo.get_model_by_litellm_id.return_value = SimpleNamespace(
            id=1, provider="openai", litellm_model_id="openai/gpt-4o"
        )

        # 実サービス経由でも AttributeError なく batch-capable 集合を得られる
        capable = tab._resolve_batch_capable_ids(["openai/gpt-4o"])

        assert capable == {"openai/gpt-4o"}

    def test_sync_dispatch_does_not_query_batch_models(self, tab):
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        tab._pipeline_composition_service = PipelineCompositionService()
        tab._pipeline_staged_count = 9
        tab._build_stage_model_infos = lambda ids: [GPT4O_INFO]
        tab._pipeline_stage_table = Mock()
        tab._inference_ledger_widget = Mock()
        tab._pipeline_run_options = RunOptions(dispatch_mode="sync")

        tab._refresh_pipeline_panel(["openai/gpt-4o"])

        tab._service_container.provider_batch_workflow_service.list_batch_capable_models.assert_not_called()
        ledger = tab._inference_ledger_widget.display.call_args[0][0]
        assert ledger.batch_entries == ()

    def test_batch_api_discovery_failure_degrades_to_sync(self, tab):
        from lorairo.gui.widgets.run_settings_dialog import RunOptions
        from lorairo.services.provider_batch_service import ProviderBatchError

        tab._pipeline_composition_service = PipelineCompositionService()
        tab._pipeline_staged_count = 9
        tab._build_stage_model_infos = lambda ids: [GPT4O_INFO]
        tab._pipeline_stage_table = Mock()
        tab._inference_ledger_widget = Mock()
        tab._pipeline_run_options = RunOptions(dispatch_mode="batch_api")
        tab._service_container.provider_batch_workflow_service.list_batch_capable_models.side_effect = (
            ProviderBatchError("discovery failed")
        )

        tab._refresh_pipeline_panel(["openai/gpt-4o"])

        ledger = tab._inference_ledger_widget.display.call_args[0][0]
        assert ledger.batch_entries == ()  # 失敗時は全 sync に degrade

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

    def test_sync_execute_text_contains_count(self):
        assert "7" in AnnotateTabWidget._run_bar_sync_execute_text(7)

    def test_batch_execute_text_contains_count(self):
        assert "7" in AnnotateTabWidget._run_bar_batch_execute_text(7)

    def test_sync_execute_text_contains_枚(self):
        assert "枚" in AnnotateTabWidget._run_bar_sync_execute_text(3)

    def test_batch_execute_text_contains_枚(self):
        assert "枚" in AnnotateTabWidget._run_bar_batch_execute_text(3)

    def test_execute_texts_are_distinct(self):
        # #1099: 2ボタンは同期 / Batch API を明確に区別する
        assert "同期" in AnnotateTabWidget._run_bar_sync_execute_text(1)
        assert "Batch API" in AnnotateTabWidget._run_bar_batch_execute_text(1)

    def test_update_target_ui_enables_both_execute_buttons_with_staging(self, tab):
        tab._update_annotation_target_ui(5)

        assert tab._btn_sync_execute.isEnabled() is True
        assert tab._btn_batch_api_execute.isEnabled() is True
        assert "5" in tab._btn_sync_execute.text()
        assert "5" in tab._btn_batch_api_execute.text()
        assert "5" in tab._run_bar_scope_label.text()

    def test_update_target_ui_disables_both_execute_buttons_when_empty(self, tab):
        tab._update_annotation_target_ui(0)

        assert tab._btn_sync_execute.isEnabled() is False
        assert tab._btn_batch_api_execute.isEnabled() is False

    def test_set_execution_running_disables_buttons_and_shows_running(self, tab):
        """#1156: 実行中は両ボタン無効 + 「実行中…」表示。"""
        tab._pipeline_staged_count = 5
        tab.set_execution_running(True)

        assert tab._execute_in_flight is True
        assert tab._btn_sync_execute.isEnabled() is False
        assert tab._btn_batch_api_execute.isEnabled() is False
        assert "実行中" in tab._btn_sync_execute.text()
        assert "実行中" in tab._btn_batch_api_execute.text()

    def test_set_execution_running_false_re_enables_by_staging(self, tab):
        """#1156: 終端で staging 件数に応じて再有効化する。"""
        tab._pipeline_staged_count = 5
        tab.set_execution_running(True)
        tab.set_execution_running(False)

        assert tab._execute_in_flight is False
        assert tab._btn_sync_execute.isEnabled() is True
        assert tab._btn_batch_api_execute.isEnabled() is True
        assert "5" in tab._btn_sync_execute.text()

    def test_staging_change_keeps_buttons_disabled_while_running(self, tab):
        """#1156: 実行中に staging が変化してもボタンは無効・「実行中…」のまま。"""
        tab.set_execution_running(True)

        tab._update_annotation_target_ui(9)  # staging 変化

        assert tab._btn_sync_execute.isEnabled() is False
        assert tab._btn_batch_api_execute.isEnabled() is False
        assert "実行中" in tab._btn_sync_execute.text()


# == 8. トップレベル Signal ===================================================


@pytest.mark.gui
def test_sync_execute_button_emits_sync_mode(tab, qtbot):
    """同期実行ボタンクリックで dispatch_mode="sync" を載せて emit される (#1099)。"""
    tab._update_annotation_target_ui(2)  # ボタンを有効化

    with qtbot.waitSignal(tab.annotation_execute_requested, timeout=1000) as blocker:
        tab._btn_sync_execute.click()

    assert blocker.args == ["sync"]
    assert tab.run_options().dispatch_mode == "sync"


@pytest.mark.gui
def test_execute_reentry_guard_emits_only_once_on_rapid_clicks(tab, qtbot):
    """#1156: 連打しても _execute_in_flight ガードで実行要求は 1 回だけ emit される。"""
    tab._update_annotation_target_ui(3)  # ボタン有効化
    emitted: list[str] = []
    tab.annotation_execute_requested.connect(emitted.append)

    # glue が set_execution_running を呼ぶ前に高速連打 → 2 回目以降は in-flight で塞がれる
    tab._btn_sync_execute.click()
    tab._btn_sync_execute.click()
    tab._btn_sync_execute.click()

    assert emitted == ["sync"]
    assert tab._execute_in_flight is True


@pytest.mark.gui
def test_execute_reentry_guard_clears_when_running_reset(tab, qtbot):
    """#1156: 開始前拒否 (set_execution_running(False)) で再度実行できる。"""
    tab._pipeline_staged_count = 3  # 再有効化は staging 件数を見るため設定
    tab._update_annotation_target_ui(3)
    emitted: list[str] = []
    tab.annotation_execute_requested.connect(emitted.append)

    tab._btn_sync_execute.click()
    tab.set_execution_running(False)  # 拒否 → 再有効化
    tab._btn_batch_api_execute.click()

    assert emitted == ["sync", "batch_api"]


@pytest.mark.gui
def test_batch_api_execute_button_emits_batch_mode(tab, qtbot):
    """Batch API 実行ボタンクリックで dispatch_mode="batch_api" を載せて emit される (#1099)。"""
    tab._update_annotation_target_ui(2)  # ボタンを有効化

    with qtbot.waitSignal(tab.annotation_execute_requested, timeout=1000) as blocker:
        tab._btn_batch_api_execute.click()

    assert blocker.args == ["batch_api"]
    assert tab.run_options().dispatch_mode == "batch_api"


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


@pytest.mark.gui
def test_refresh_pipeline_panel_sources_from_state_manager(
    monkeypatch: pytest.MonkeyPatch,
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
) -> None:
    """manager 注入時、selected_ids 省略の pipeline 再描画は manager (SSoT) を読む (#884 P2)。

    widget と manager を意図的に乖離させ、None 経路 (refresh()/set_staging_target())
    が widget ではなく manager から読むことを ``_build_stage_model_infos`` への
    引数捕捉で直接検証する。
    """
    widget, state_manager = annotate_tab_with_state

    # manager の値を先にセット (selection_changed で _refresh_pipeline_panel が1回呼ばれる)
    state_manager.set_selected(["manager/a", "manager/b"])

    # monkeypatch を set_selected 後に行う (instruction 通り)
    # widget と manager を乖離させる
    monkeypatch.setattr(widget.batch_model_selection, "get_selected_models", lambda: ["widget-only"])

    captured: list[list[str]] = []
    monkeypatch.setattr(widget, "_build_stage_model_infos", lambda ids: captured.append(list(ids)) or [])

    widget.refresh()  # selected_ids=None 経路

    assert captured, "_build_stage_model_infos が呼ばれなかった"
    assert captured[-1] == ["manager/a", "manager/b"], (
        f"widget ではなく manager から読むはずだが実際: {captured[-1]}"
    )


def _make_mutable_checkbox(selected_ids: list[str], litellm_model_id: str) -> Mock:
    """checkbox.set_selected() で ``selected_ids`` を実際に書き換える Mock を返す。

    Codex review (#1034 PR#1048): get_selected_models を静的スタブにすると、
    ハンドラが checkbox.set_selected() より前に _sync_widget_selection_to_state()
    を呼ぶ回帰があってもテストが検知できない。checkbox 操作と get_selected_models
    の戻り値を連動させることで、sync が widget 状態変化の後に読むことを保証する。
    """

    def _set_selected(value: bool) -> None:
        if value:
            if litellm_model_id not in selected_ids:
                selected_ids.append(litellm_model_id)
        elif litellm_model_id in selected_ids:
            selected_ids.remove(litellm_model_id)

    checkbox = Mock()
    checkbox.set_selected.side_effect = _set_selected
    return checkbox


@pytest.mark.gui
def test_add_model_handler_syncs_state_manager(
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「+ 追加」ハンドラが実 manager (SSoT) へ選択を同期する (#1034)。

    ``TestPipelineAddModelHandler`` は ``_batch_model_selection`` を丸ごと Mock 化するため
    manager=None 前提の tab fixture では ``_sync_widget_selection_to_state`` が no-op になり
    manager 同期経路が未検証だった。ここでは実 manager 注入下で end-to-end に検証する。
    """
    from lorairo.gui.tab import annotate_tab as annotate_tab_module

    widget, state_manager = annotate_tab_with_state
    selected_ids: list[str] = []
    checkbox = _make_mutable_checkbox(selected_ids, "openai/gpt-4o")
    monkeypatch.setattr(widget.batch_model_selection, "model_checkbox_widgets", {"openai/gpt-4o": checkbox})
    monkeypatch.setattr(widget.batch_model_selection, "get_selected_models", lambda: list(selected_ids))
    widget._build_stage_model_infos = lambda ids: [GPT4O_INFO]
    widget._refresh_pipeline_panel = Mock()
    widget._available_api_providers = lambda: set()
    stub_cls, _captured = _make_stub_dialog(QDialog.DialogCode.Accepted, ["openai/gpt-4o"])
    monkeypatch.setattr(annotate_tab_module, "StageModelPickerDialog", stub_cls)

    widget._on_pipeline_add_model_requested("tags")

    checkbox.set_selected.assert_called_once_with(True)
    # manager が ["openai/gpt-4o"] になるのは sync が checkbox 更新後の
    # get_selected_models() を読んだ場合のみ (更新前に読めば [] のまま)。
    assert state_manager.get_selected() == ["openai/gpt-4o"]
    widget._refresh_pipeline_panel.assert_called_once_with()


@pytest.mark.gui
def test_remove_model_handler_updates_state_manager_directly(
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
) -> None:
    """#1134: × ハンドラは SSoT (manager) を直接更新し、view/panel は既存配線に任せる。

    旧実装は checkbox ウィジェット経由でしか外せず、未表示だと silent no-op だった。
    SSoT-first に変更し、``set_model_selected(id, False)`` で除外 → ``selection_changed`` →
    ``_on_state_model_selection_changed`` で view 追従 + panel 再描画が走る。
    """
    widget, state_manager = annotate_tab_with_state
    widget._refresh_pipeline_panel = Mock()
    state_manager.set_selected(["openai/gpt-4o", "wd-v1-4-tagger"])
    widget._refresh_pipeline_panel.reset_mock()

    widget._on_pipeline_remove_model_requested("tags", "openai/gpt-4o")

    # SSoT から該当モデルが外れる
    assert state_manager.get_selected() == ["wd-v1-4-tagger"]
    # selection_changed 経由で panel 再描画が新しい選択集合で走る
    widget._refresh_pipeline_panel.assert_called_once_with(["wd-v1-4-tagger"])


@pytest.mark.gui
def test_remove_model_works_when_checkbox_not_displayed(
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1134: checkbox 未表示でも SSoT 直接更新で除外が成立する (warning + no-op 廃止)。"""
    widget, state_manager = annotate_tab_with_state
    # 該当モデルの checkbox が一覧に無い (フィルタ絞り込み中・未構築) 状態を再現
    monkeypatch.setattr(widget.batch_model_selection, "model_checkbox_widgets", {})
    widget._refresh_pipeline_panel = Mock()
    state_manager.set_selected(["openai/gpt-4o", "wd-v1-4-tagger"])
    widget._refresh_pipeline_panel.reset_mock()

    widget._on_pipeline_remove_model_requested("tags", "openai/gpt-4o")

    # checkbox が無くても SSoT から外れる (旧実装は warning のみで残っていた)
    assert state_manager.get_selected() == ["wd-v1-4-tagger"]
    widget._refresh_pipeline_panel.assert_called_once_with(["wd-v1-4-tagger"])


@pytest.mark.gui
def test_remove_model_drops_from_inference_ledger(
    annotate_tab_with_state: tuple[AnnotateTabWidget, ModelSelectionStateManager],
) -> None:
    """#1134: × でモデルを外すと INFERENCE LEDGER の unique model 数・合計が減る (runtime)。"""
    widget, state_manager = annotate_tab_with_state
    infos = {"openai/gpt-4o": GPT4O_INFO, "wd-v1-4-tagger": WD_TAGGER_INFO}
    widget._build_stage_model_infos = lambda ids: [infos[i] for i in ids if i in infos]
    widget._pipeline_staged_count = 9
    widget._inference_ledger_widget = Mock()

    # 2 件選択 → LEDGER は unique 2 件
    state_manager.set_selected(["openai/gpt-4o", "wd-v1-4-tagger"])
    ledger_before = widget._inference_ledger_widget.display.call_args[0][0]
    assert ledger_before.unique_model_count == 2

    # × で 1 件除外 → LEDGER の unique 数・合計が減る
    widget._on_pipeline_remove_model_requested("tags", "openai/gpt-4o")

    ledger_after = widget._inference_ledger_widget.display.call_args[0][0]
    assert ledger_after.unique_model_count == 1
    assert ledger_after.total_jobs < ledger_before.total_jobs


# == バッチタグ書込 (#896 PR3: MainWindow から移送) ===========================


@pytest.mark.gui
def test_execute_batch_tag_write_refreshes_on_success(tab: AnnotateTabWidget) -> None:
    """書込成功時に dataset_state_manager.refresh_images を呼ぶ (#896)。"""
    tab._image_db_write_service = Mock()
    tab._image_db_write_service.add_tag_batch.return_value = True
    tab._dataset_state_manager = Mock()

    result = tab._execute_batch_tag_write([1, 2], "landscape")

    assert result is True
    tab._image_db_write_service.add_tag_batch.assert_called_once_with([1, 2], "landscape")
    tab._dataset_state_manager.refresh_images.assert_called_once_with([1, 2])


@pytest.mark.gui
def test_execute_batch_tag_write_no_service_returns_false(tab: AnnotateTabWidget) -> None:
    """ImageDBWriteService 未初期化時は False を返し書込しない (#896)。"""
    tab._image_db_write_service = None

    assert tab._execute_batch_tag_write([1], "t") is False


@pytest.mark.gui
def test_handle_batch_tag_add_success_emits_status_and_clears_staging(
    tab: AnnotateTabWidget, qtbot
) -> None:
    """書込成功で status_message を emit しステージングをクリアする (#896)。"""
    tab._image_db_write_service = Mock()
    tab._image_db_write_service.add_tag_batch.return_value = True
    tab._dataset_state_manager = Mock()
    tab._staging_state_manager = Mock()

    with qtbot.waitSignal(tab.status_message, timeout=1000) as blocker:
        tab._handle_batch_tag_add([1, 2], "landscape")

    assert "landscape" in blocker.args[0]
    tab._staging_state_manager.clear.assert_called_once()


@pytest.mark.gui
def test_handle_batch_tag_add_failure_shows_critical(tab: AnnotateTabWidget, monkeypatch) -> None:
    """書込失敗で QMessageBox.critical を表示する (#896)。"""
    tab._image_db_write_service = Mock()
    tab._image_db_write_service.add_tag_batch.return_value = False
    calls: list[bool] = []
    monkeypatch.setattr("lorairo.gui.tab.annotate_tab.show_critical", lambda *a, **k: calls.append(True))

    tab._handle_batch_tag_add([1], "x")

    assert calls == [True]


@pytest.mark.gui
def test_handle_batch_tag_add_empty_ids_noop(tab: AnnotateTabWidget) -> None:
    """空 image_ids では書込せず早期 return する (#896)。"""
    tab._image_db_write_service = Mock()

    tab._handle_batch_tag_add([], "x")

    tab._image_db_write_service.add_tag_batch.assert_not_called()


@pytest.mark.gui
def test_batch_tag_add_widget_signal_handled_in_tab(tab: AnnotateTabWidget, monkeypatch) -> None:
    """BatchTagAddWidget の tag_add_requested はタブ内で処理し上方 bubble しない (#896)。"""
    handled: list[tuple[list[int], str]] = []
    monkeypatch.setattr(tab, "_handle_batch_tag_add", lambda ids, t: handled.append((ids, t)))
    # 再配線 (monkeypatch 後の接続を張り直す)
    tab._batch_tag_add_widget.tag_add_requested.disconnect()
    tab._batch_tag_add_widget.tag_add_requested.connect(tab._handle_batch_tag_add)

    tab._batch_tag_add_widget.tag_add_requested.emit([3], "sky")

    assert handled == [([3], "sky")]
