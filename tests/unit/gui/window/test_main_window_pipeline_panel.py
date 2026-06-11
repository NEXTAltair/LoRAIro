"""MainWindow × パイプライン構成ビュー (Phase 6a) の配線テスト。

Wireframes v11 Frame 2A: ModelSelectionWidget の選択購読 → ステージ自動仕分け →
派生チップ・推論台帳のリアルタイム表示の配線を Mock ベースで検証する。
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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


@pytest.mark.unit
class TestBuildStageModelInfos:
    """litellm_model_id → StageModelInfo 変換の検証。"""

    def _make_window(self, models: list[SimpleNamespace]) -> Mock:
        mock_window = Mock()
        mock_window.batchModelSelection.model_selection_service.load_models.return_value = models
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
