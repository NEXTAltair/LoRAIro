"""MainWindow × パイプライン構成ビュー (Phase 6a/6b) の配線テスト。

Wireframes v11 Frame 2A/2B: ModelSelectionWidget の選択購読 → ステージ自動仕分け →
派生チップ・推論台帳のリアルタイム表示の配線と、ステージ単位の追加/削除
ハンドラ (Phase 6b) を Mock ベースで検証する。
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog

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
    exec_result: QDialog.DialogCode, picked_ids: list[str]
) -> tuple[type, dict[str, object]]:
    """StageModelPickerDialog 差し替え用 stub クラスと捕捉 dict を返す。

    headless で exec() がブロックしないよう固定値を返す。テストごとに新しい
    クラスを生成し、クラスレベルの状態共有 (テスト順依存) を避ける。
    """
    captured: dict[str, object] = {}

    class _StubPickerDialog:
        def __init__(self, stage, candidates, available_providers=None, parent=None):
            captured["stage"] = stage
            captured["candidates"] = candidates
            captured["available_providers"] = available_providers
            captured["parent"] = parent
            # Issue #755: MainWindow が connect する設定導線シグナルの差し替え
            self.configure_key_requested = Mock()

        def exec(self) -> QDialog.DialogCode:
            return exec_result

        def selected_model_ids(self) -> list[str]:
            return picked_ids

    return _StubPickerDialog, captured


@pytest.mark.unit
class TestBuildStageModelInfos:
    """litellm_model_id → StageModelInfo 変換の検証。"""

    def _make_window(self, models: list[SimpleNamespace]) -> Mock:
        mock_window = Mock()
        mock_window.batchModelSelection.model_selection_service.load_models.return_value = models
        # Issue #747: コストマップ取得は real dict を返させ、Mock のアンパック失敗を避ける
        mock_window._build_cost_map.return_value = {}
        return mock_window

    def test_converts_api_model_with_capabilities(self):
        from lorairo.gui.window.main_window import MainWindow

        model = SimpleNamespace(
            litellm_model_id="openai/gpt-4o",
            name="gpt-4o",
            provider="openai",
            capabilities=["multimodal", "caption", "tags", "scores"],
        )
        mock_window = self._make_window([model])
        infos = MainWindow._build_stage_model_infos(mock_window, ["openai/gpt-4o"])

        assert len(infos) == 1
        assert infos[0].is_api is True
        assert infos[0].is_multimodal is True
        assert infos[0].capabilities == frozenset({"multimodal", "caption", "tags", "scores"})

    def test_local_provider_none_is_not_api(self):
        from lorairo.gui.window.main_window import MainWindow

        model = SimpleNamespace(
            litellm_model_id="wd-v1-4-tagger",
            name="wd-v1-4-tagger",
            provider=None,
            capabilities=["tags"],
        )
        mock_window = self._make_window([model])
        infos = MainWindow._build_stage_model_infos(mock_window, ["wd-v1-4-tagger"])

        assert infos[0].is_api is False
        assert infos[0].is_multimodal is False

    def test_provider_local_string_is_not_api(self):
        from lorairo.gui.window.main_window import MainWindow

        model = SimpleNamespace(
            litellm_model_id="aesthetic-v2",
            name="aesthetic-v2",
            provider="local",
            capabilities=["scores"],
        )
        mock_window = self._make_window([model])
        infos = MainWindow._build_stage_model_infos(mock_window, ["aesthetic-v2"])

        assert infos[0].is_api is False

    def test_unknown_id_is_skipped(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = self._make_window([])
        infos = MainWindow._build_stage_model_infos(mock_window, ["missing/model"])

        assert infos == []


@pytest.mark.unit
class TestPipelinePanelRefresh:
    """選択変化・ステージング変化での再描画配線の検証。"""

    def test_models_changed_triggers_refresh_with_ids(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_pipeline_models_changed(mock_window, ["openai/gpt-4o"])
        mock_window._refresh_pipeline_panel.assert_called_once_with(["openai/gpt-4o"])

    def test_refresh_skips_when_widgets_missing(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_stage_table = None
        mock_window.inference_ledger_widget = None
        # widget 未構築でも例外なく早期 return する
        MainWindow._refresh_pipeline_panel(mock_window, ["openai/gpt-4o"])
        mock_window.pipeline_composition_service.compose_from_models.assert_not_called()

    def test_refresh_composes_and_displays(self):
        """実 PipelineCompositionService で multimodal 構成が表示に渡ることを検証。"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.pipeline_composition_service = PipelineCompositionService()
        mock_window._pipeline_staged_count = 9
        mock_window._build_stage_model_infos = lambda ids: [GPT4O_INFO]

        MainWindow._refresh_pipeline_panel(mock_window, ["openai/gpt-4o"])

        rows = mock_window.pipeline_stage_table.display.call_args[0][0]
        rows_by_stage = {row.stage: row for row in rows}
        # multimodal は CAPTION に明示割当、TAGS/SCORE に派生、RATING には届かない
        assert [m.litellm_model_id for m in rows_by_stage[PipelineStage.CAPTION].primary_models] == [
            "openai/gpt-4o"
        ]
        assert [c.model.litellm_model_id for c in rows_by_stage[PipelineStage.TAGS].derived_chips] == [
            "openai/gpt-4o"
        ]
        assert rows_by_stage[PipelineStage.RATING].derived_chips == ()

        ledger = mock_window.inference_ledger_widget.display.call_args[0][0]
        assert ledger.unique_model_count == 1
        assert ledger.total_jobs == 9

    def test_staged_images_changed_syncs_ledger_count(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        MainWindow._on_staged_images_changed(mock_window, [1, 2, 3])

        assert mock_window._pipeline_staged_count == 3
        mock_window._refresh_pipeline_panel.assert_called_once_with()


@pytest.mark.unit
class TestPipelineAddModelHandler:
    """「+ 追加」ハンドラ: ピッカー Accepted → チェック ON 変換の検証 (Phase 6b)。"""

    def _make_window(
        self,
        checkbox_widgets: dict[str, Mock],
        selected_ids: list[str],
        infos: list[StageModelInfo],
    ) -> Mock:
        mock_window = Mock()
        mock_window.batchModelSelection.model_checkbox_widgets = checkbox_widgets
        mock_window.batchModelSelection.get_selected_models.return_value = selected_ids
        mock_window.batchModelSelection.model_selection_service.load_models.return_value = [
            SimpleNamespace(litellm_model_id=info.litellm_model_id) for info in infos
        ]
        mock_window._build_stage_model_infos = lambda ids: infos
        return mock_window

    def test_accepted_dialog_sets_selected_true(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        checkbox = Mock()
        mock_window = self._make_window({"openai/gpt-4o": checkbox}, [], [GPT4O_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Accepted, ["openai/gpt-4o"])
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "tags")

        assert captured["stage"] is PipelineStage.TAGS
        checkbox.set_selected.assert_called_once_with(True)
        mock_window._refresh_pipeline_panel.assert_called_once_with()

    def test_candidates_filtered_by_stage_and_unselected(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        # GPT4O は選択済み → 除外。WD_TAGGER は tags 適格 → 候補。
        mock_window = self._make_window({}, ["openai/gpt-4o"], [GPT4O_INFO, WD_TAGGER_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "tags")

        candidates = captured["candidates"]
        assert [info.litellm_model_id for info in candidates] == ["wd-v1-4-tagger"]

    def test_stage_ineligible_model_not_in_candidates(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        # WD_TAGGER (tags のみ) は RATING 候補に出ない。multimodal も rating には届かない。
        mock_window = self._make_window({}, [], [GPT4O_INFO, WD_TAGGER_INFO])
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "rating")

        assert captured["candidates"] == []

    def test_rejected_dialog_does_not_change_selection(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        checkbox = Mock()
        mock_window = self._make_window({"openai/gpt-4o": checkbox}, [], [GPT4O_INFO])
        stub_cls, _captured = _make_stub_dialog(QDialog.DialogCode.Rejected, ["openai/gpt-4o"])
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "tags")

        checkbox.set_selected.assert_not_called()
        mock_window._refresh_pipeline_panel.assert_not_called()

    def test_picked_id_missing_from_checkbox_dict_is_skipped(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        checkbox = Mock()
        mock_window = self._make_window({"openai/gpt-4o": checkbox}, [], [GPT4O_INFO, WD_TAGGER_INFO])
        # wd-v1-4-tagger はフィルタで非表示 (dict に無い) → 例外なくスキップ
        stub_cls, _captured = _make_stub_dialog(
            QDialog.DialogCode.Accepted, ["wd-v1-4-tagger", "openai/gpt-4o"]
        )
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "tags")

        checkbox.set_selected.assert_called_once_with(True)
        mock_window._refresh_pipeline_panel.assert_called_once_with()


@pytest.mark.unit
class TestPickerConfigureKeyRoundTrip:
    """Issue #755: needs key チップ → 設定 → ● API ready 解消の往復導線。"""

    def test_picker_receives_available_providers(self, monkeypatch):
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.batchModelSelection.model_checkbox_widgets = {}
        mock_window.batchModelSelection.get_selected_models.return_value = []
        mock_window.batchModelSelection.model_selection_service.load_models.return_value = []
        mock_window._build_stage_model_infos = lambda ids: [GPT4O_INFO]
        mock_window._available_api_providers.return_value = {"openai"}
        stub_cls, captured = _make_stub_dialog(QDialog.DialogCode.Rejected, [])
        monkeypatch.setattr(main_window_module, "StageModelPickerDialog", stub_cls)

        MainWindow._on_pipeline_add_model_requested(mock_window, "tags")

        assert captured["available_providers"] == {"openai"}

    def test_configure_key_applied_refreshes_widget_and_dialog(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.settings_controller.open_settings_dialog.return_value = True
        mock_window._available_api_providers.return_value = {"anthropic"}
        dialog = Mock()

        MainWindow._on_picker_configure_key_requested(mock_window, "anthropic", dialog)

        mock_window.settings_controller.open_settings_dialog.assert_called_once_with(
            highlight_provider="anthropic"
        )
        mock_window._reload_model_widget_after_settings.assert_called_once_with()
        dialog.refresh_key_status.assert_called_once_with({"anthropic"})

    def test_configure_key_cancelled_does_not_refresh(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.settings_controller.open_settings_dialog.return_value = False
        dialog = Mock()

        MainWindow._on_picker_configure_key_requested(mock_window, "anthropic", dialog)

        mock_window._reload_model_widget_after_settings.assert_not_called()
        dialog.refresh_key_status.assert_not_called()

    def test_configure_key_without_settings_controller_is_noop(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.settings_controller = None
        dialog = Mock()

        MainWindow._on_picker_configure_key_requested(mock_window, "anthropic", dialog)

        dialog.refresh_key_status.assert_not_called()

    def test_reload_after_settings_resets_container_config_service(self, monkeypatch):
        """Codex review (PR #757): container 側 config_service を破棄して保存値を再読込させる。

        MainWindow.config_service と ServiceContainer.config_service は別インスタンス
        のため、保存後に container 側を破棄しないと widget が stale なキー状況を見る。
        """
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        class _StubContainer:
            def __init__(self) -> None:
                self.config_deleted = False

            @property
            def config_service(self) -> Mock:
                return Mock()

            @config_service.deleter
            def config_service(self) -> None:
                self.config_deleted = True

        container = _StubContainer()
        monkeypatch.setattr(main_window_module, "get_service_container", lambda: container)
        mock_window = Mock()

        MainWindow._reload_model_widget_after_settings(mock_window)

        assert container.config_deleted is True
        mock_window.batchModelSelection.update_model_display.assert_called_once_with()


@pytest.mark.unit
class TestAvailableApiProviders:
    """Issue #755: config からの API キー設定済み provider 集合の導出。"""

    def _make_window_with_keys(self, keys: dict[tuple[str, str], str]) -> Mock:
        mock_window = Mock()
        mock_window.config_service.get_setting.side_effect = lambda section, key, default="": keys.get(
            (section, key), default
        )
        return mock_window

    def test_only_providers_with_nonempty_keys(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = self._make_window_with_keys(
            {
                ("api", "openai_key"): "sk-test",
                ("api", "claude_key"): "   ",
                ("api", "google_key"): "",
                ("api", "openrouter_key"): "or-key",
            }
        )
        providers = MainWindow._available_api_providers(mock_window)
        assert providers == {"openai", "openrouter"}

    def test_missing_config_service_returns_empty(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.config_service = None
        assert MainWindow._available_api_providers(mock_window) == set()


@pytest.mark.unit
class TestPipelineRemoveModelHandler:
    """Primary × ハンドラ: チェック OFF 変換の検証 (Phase 6b)。"""

    def test_remove_sets_selected_false(self):
        from lorairo.gui.window.main_window import MainWindow

        checkbox = Mock()
        mock_window = Mock()
        mock_window.batchModelSelection.model_checkbox_widgets = {"openai/gpt-4o": checkbox}

        MainWindow._on_pipeline_remove_model_requested(mock_window, "caption", "openai/gpt-4o")

        checkbox.set_selected.assert_called_once_with(False)
        mock_window._refresh_pipeline_panel.assert_called_once_with()

    def test_remove_missing_id_is_noop_without_error(self):
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.batchModelSelection.model_checkbox_widgets = {}

        # dict に無い id でも例外を出さずスキップする
        MainWindow._on_pipeline_remove_model_requested(mock_window, "tags", "missing/model")

        mock_window._refresh_pipeline_panel.assert_not_called()
