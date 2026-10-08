"""Settings → real tab/state → execution regressions; inference backends are mocked."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog

from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
from lorairo.gui.state.model_selection_state import ModelSelectionStateManager
from lorairo.gui.tab.annotate_tab import AnnotateTabWidget
from lorairo.gui.window.main_window import MainWindow

DIRECT_ID = "openai/gpt-4o"
ROUTER_ID = "openrouter/openai/gpt-4o"
LOCAL_ID = "wd-tagger"


def _model(model_id, provider, capabilities=None):
    return SimpleNamespace(
        litellm_model_id=model_id,
        name="gpt-4o" if provider != "local" else model_id,
        provider=provider,
        capabilities=capabilities or ["caption", "tags"],
        requires_api_key=provider != "local",
        available=True,
        is_recommended=False,
    )


@pytest.fixture(params=[False, True], ids=["current-cloud-flags", "legacy-cloud-flags"])
def route_flow(qtbot, monkeypatch, request):
    settings = {"route": "openrouter", "openai_key": "mock-key", "openrouter_key": "mock-key"}
    config = Mock()
    config.get_setting.side_effect = lambda section, key, default="": (
        settings["route"] if key == "route_preference" else settings.get(key, default)
    )
    models = [
        _model(DIRECT_ID, "openai"),
        _model(ROUTER_ID, "openrouter"),
        _model(LOCAL_ID, "local"),
        _model("anthropic/claude-test", "anthropic"),
    ]
    if request.param:
        for model in models:
            if model.provider != "local":
                model.requires_api_key = False
    db = Mock()
    db.model_repo.get_model_objects.return_value = models
    db.model_repo.get_model_by_litellm_id.side_effect = lambda mid: next(
        (model for model in models if model.litellm_model_id == mid), None
    )

    class Container:
        db_manager = db
        annotator_library = Mock()
        provider_batch_workflow_service = Mock()

        @property
        def config_service(self):
            return config

        @config_service.deleter
        def config_service(self):
            pass  # emulate reloading saved settings, without filesystem config writes

    container = Container()
    container.annotator_library.list_annotator_info.return_value = []
    container.annotator_library.is_model_deprecated.return_value = False
    for module in (
        "lorairo.gui.widgets.model_selection_widget",
        "lorairo.gui.controllers.annotation_workflow_controller",
        "lorairo.gui.window.main_window",
    ):
        monkeypatch.setattr(f"{module}.get_service_container", lambda: container)
    state = ModelSelectionStateManager()
    tab = AnnotateTabWidget(
        service_container=container,
        db_manager=None,
        staging_state_manager=None,
        dataset_state_manager=None,
        model_selection_state_manager=state,
    )
    qtbot.addWidget(tab)
    monkeypatch.setattr(tab, "staged_image_paths", lambda: ["/mock/processed.png"])
    monkeypatch.setattr(tab, "get_staged_items", lambda: {1: ("processed.png", "/mock/processed.png")})
    worker = Mock()
    controller = AnnotationWorkflowController(worker, Mock(), config)
    controller.configure_async_dispatch(
        service_container=container,
        db_manager=db,
        staging_state_manager=None,
        annotate_tab=tab,
        jobs_refresh=lambda: None,
        status_callback=lambda *args: None,
        is_annotate_tab_active=lambda: True,
    )
    return SimpleNamespace(
        tab=tab,
        state=state,
        settings=settings,
        controller=controller,
        worker=worker,
        container=container,
        models=models,
    )


def _save_route(flow, route):
    """Use MainWindow's settings entry, including its real reload glue."""
    window = Mock(search_tab=None, results_tab=None, annotate_tab=flow.tab)
    window.settings_controller.open_settings_dialog.side_effect = lambda: (
        flow.settings.update(route=route) or True
    )
    window._reload_model_widget_after_settings.side_effect = lambda: (
        MainWindow._reload_model_widget_after_settings(window)
    )
    MainWindow.open_settings(window)


@pytest.mark.parametrize(
    "old_route,new_route,old_id,new_id",
    [
        ("openrouter", "direct", ROUTER_ID, DIRECT_ID),
        ("direct", "openrouter", DIRECT_ID, ROUTER_ID),
    ],
)
def test_settings_route_change_clears_ui_state_and_blocks_execution(
    route_flow, old_route, new_route, old_id, new_id, monkeypatch
):
    flow = route_flow
    _save_route(flow, old_route)
    flow.tab.batch_model_selection.model_checkbox_widgets[old_id].checkboxModel.setChecked(True)
    assert flow.state.get_selected() == [old_id]

    _save_route(flow, new_route)

    assert old_id not in flow.tab.batch_model_selection.model_checkbox_widgets
    assert new_id in flow.tab.batch_model_selection.model_checkbox_widgets
    assert flow.tab.batch_model_selection.get_selected_models() == []
    assert flow.state.get_selected() == []
    assert flow.tab._pipeline_composition_service.unique_model_ids() == []
    dialog = Mock(side_effect=AssertionError("empty selection must not open a fallback picker"))
    monkeypatch.setattr(flow.tab, "show_model_selection_dialog", dialog)
    assert flow.controller.start_annotation("sync") is False
    assert flow.controller.start_annotation("batch_api") is False
    flow.worker.start_enhanced_batch_annotation.assert_not_called()
    flow.container.provider_batch_workflow_service.list_batch_capable_models.assert_not_called()
    dialog.assert_not_called()


def test_same_route_settings_restore_selection_and_execution_target(route_flow):
    flow = route_flow
    _save_route(flow, "direct")
    checkbox = flow.tab.batch_model_selection.model_checkbox_widgets[DIRECT_ID]
    checkbox.checkboxModel.setChecked(True)
    # Force a rebuild on the same route by changing another model's key status.
    flow.settings["claude_key"] = "mock-key"
    _save_route(flow, "direct")
    assert flow.tab.batch_model_selection.model_checkbox_widgets[DIRECT_ID] is not checkbox
    assert flow.state.get_selected() == [DIRECT_ID]
    assert flow.tab.batch_model_selection.get_selected_models() == [DIRECT_ID]
    assert flow.controller.start_annotation("sync") is True
    assert flow.worker.start_enhanced_batch_annotation.call_args.kwargs["litellm_model_ids"] == [DIRECT_ID]


def test_rebuild_signal_reconciles_route_without_main_window(route_flow):
    flow = route_flow
    flow.tab.batch_model_selection.model_checkbox_widgets[ROUTER_ID].checkboxModel.setChecked(True)
    flow.settings["route"] = "direct"
    flow.tab.batch_model_selection.update_model_display()
    assert flow.state.get_selected() == []


def test_execution_preflight_prunes_stale_selection_and_keeps_valid_models(route_flow):
    flow = route_flow
    flow.state.set_selected([ROUTER_ID, LOCAL_ID])
    # Simulate a missed settings notification. Both API keys remain usable.
    flow.settings["route"] = "direct"
    assert flow.controller.start_annotation("sync") is True
    assert flow.state.get_selected() == [LOCAL_ID]
    assert flow.worker.start_enhanced_batch_annotation.call_args.kwargs["litellm_model_ids"] == [LOCAL_ID]


def test_workflow_preflight_rejects_explicit_stale_id(route_flow):
    flow = route_flow
    flow.state.set_selected([ROUTER_ID])
    flow.settings["route"] = "direct"
    assert (
        flow.controller.start_annotation_workflow(
            selected_litellm_model_ids=[ROUTER_ID], image_paths=["/mock/processed.png"]
        )
        is False
    )
    assert flow.state.get_selected() == []
    flow.worker.start_enhanced_batch_annotation.assert_not_called()


def test_key_removal_clears_unselectable_model(route_flow):
    flow = route_flow
    flow.state.set_selected([ROUTER_ID])
    flow.settings["openrouter_key"] = ""
    flow.tab.refresh_model_selection()
    assert flow.state.get_selected() == []
    assert flow.tab.batch_model_selection.get_selected_models() == []
    assert not flow.tab.batch_model_selection.model_checkbox_widgets[ROUTER_ID].is_selectable()


def test_cloud_rendering_and_auto_route_availability_use_provider_metadata(route_flow):
    flow = route_flow
    router_checkbox = flow.tab.batch_model_selection.model_checkbox_widgets[ROUTER_ID]
    assert router_checkbox.model_info.is_local is False
    assert router_checkbox.model_info.requires_api_key is True
    assert router_checkbox.labelStatus.text() == "● API ready"
    flow.state.set_selected([ROUTER_ID])
    flow.settings.update(openai_key="", openrouter_key="")
    _save_route(flow, "auto")
    assert flow.state.get_selected() == []
    direct_checkbox = flow.tab.batch_model_selection.model_checkbox_widgets[DIRECT_ID]
    assert direct_checkbox.labelStatus.text() == "○ needs key"
    assert not direct_checkbox.is_selectable()
    assert flow.tab.batch_model_selection.selectable_litellm_model_ids() == {LOCAL_ID}
    assert flow.controller.start_annotation("sync") is False
    flow.worker.start_enhanced_batch_annotation.assert_not_called()


def test_execution_environment_filters_agree_with_cloud_route_metadata(route_flow):
    flow = route_flow
    _save_route(flow, "direct")
    flow.tab.batch_model_selection.apply_filters(execution_env="APIモデルのみ")
    assert DIRECT_ID in flow.tab.batch_model_selection.model_checkbox_widgets
    assert LOCAL_ID not in flow.tab.batch_model_selection.model_checkbox_widgets
    flow.tab.batch_model_selection.apply_filters(execution_env="ローカルモデルのみ")
    assert set(flow.tab.batch_model_selection.model_checkbox_widgets) == {LOCAL_ID}


@pytest.mark.parametrize(
    "provider",
    [None, "", "local", "LOCAL", " local ", "SmilingWolf", "cafe", "xinntao", "esrgan", "openai"],
)
def test_genuine_local_metadata_survives_route_switch_and_execution(route_flow, provider):
    flow = route_flow
    local_model = next(model for model in flow.models if model.litellm_model_id == LOCAL_ID)
    local_model.provider = provider
    if provider == "openai":
        local_model.litellm_model_id = "classification_ViT-L-14_openai"
        local_model.capabilities = ["scores"]
    elif provider == "cafe":
        local_model.litellm_model_id = "cafe_aesthetic"
        local_model.capabilities = ["scores"]
    local_id = local_model.litellm_model_id
    local_model.name = local_id
    flow.settings.update(openai_key="", openrouter_key="")
    flow.state.set_selected([local_id])
    _save_route(flow, "direct")
    checkbox = flow.tab.batch_model_selection.model_checkbox_widgets[local_id]
    assert checkbox.is_selectable()
    assert checkbox.model_info.is_local is True
    assert checkbox.model_info.requires_api_key is False
    assert checkbox.labelStatus.text() == "● installed"
    assert flow.tab._build_stage_model_infos([local_id])[0].is_api is False
    flow.tab.batch_model_selection.apply_filters(execution_env="APIモデルのみ")
    assert local_id not in flow.tab.batch_model_selection.model_checkbox_widgets
    flow.tab.batch_model_selection.apply_filters(execution_env="ローカルモデルのみ")
    assert set(flow.tab.batch_model_selection.model_checkbox_widgets) == {local_id}
    _save_route(flow, "openrouter")
    assert flow.state.get_selected() == [local_id]
    assert flow.controller.start_annotation("sync") is True
    assert flow.worker.start_enhanced_batch_annotation.call_args.kwargs["litellm_model_ids"] == [local_id]


def test_picker_and_preset_selections_survive_same_route_preflight(route_flow, monkeypatch):
    flow = route_flow

    class Picker:
        configure_key_requested = Mock()

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_model_ids(self):
            return [ROUTER_ID]

    monkeypatch.setattr("lorairo.gui.tab.annotate_tab.StageModelPickerDialog", Picker)
    flow.tab._on_pipeline_add_model_requested("caption")
    assert flow.state.get_selected() == [ROUTER_ID]
    flow.tab.refresh_model_selection()
    assert flow.state.get_selected() == [ROUTER_ID]
    # Presets may contain a model hidden by the current category filter (#1186).
    flow.tab.batch_model_selection.apply_filters(execution_env="APIモデルのみ")
    monkeypatch.setattr(flow.tab, "_load_custom_presets", lambda: {"routes": [ROUTER_ID, LOCAL_ID]})
    flow.tab._on_pipeline_preset_selected("custom:routes")
    assert flow.state.get_selected() == [ROUTER_ID, LOCAL_ID]
    assert LOCAL_ID not in flow.tab.batch_model_selection.model_checkbox_widgets
    flow.tab.refresh_model_selection()
    assert flow.state.get_selected() == [ROUTER_ID, LOCAL_ID]
    assert flow.controller.start_annotation("sync") is True
    assert flow.worker.start_enhanced_batch_annotation.call_args.kwargs["litellm_model_ids"] == [
        ROUTER_ID,
        LOCAL_ID,
    ]
