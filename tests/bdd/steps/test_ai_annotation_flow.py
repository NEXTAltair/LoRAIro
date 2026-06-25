"""AI アノテーション実行フローの BDD ステップ定義。

AnnotationWorkflowController.start_annotation_workflow() の振る舞いを
Gherkin で仕様化する。WorkerService / QMessageBox / get_service_container() を
モックし、実 WebAPI 推論は呼ばない。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QMessageBox
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.gui.controllers.annotation_workflow_controller import (
    AnnotationWorkflowController,
)

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "ai_annotation_flow.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class AnnotationFlowContext:
    """ステップ間で受け渡すワークフロー実行状態。"""

    worker_service: Mock
    selection_state_service: Mock
    config_service: Mock
    controller: AnnotationWorkflowController
    api_keys: dict[str, str] = field(default_factory=dict)
    deprecated_models: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("AnnotationWorkflowController が初期化されている", target_fixture="ctx")
def given_controller_initialized() -> AnnotationFlowContext:
    worker_service = Mock()
    worker_service.start_enhanced_batch_annotation = Mock(return_value="worker-id")

    selection_state_service = Mock()
    selection_state_service.get_selected_image_paths.return_value = []

    config_service = Mock()
    # デフォルトは全プロバイダーのキーを設定済みとする
    api_keys = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
        "google_key": "test-google-key",
        "openrouter_key": "test-openrouter-key",
    }
    config_service.get_setting.side_effect = lambda section, key, default="": api_keys.get(key, default)

    controller = AnnotationWorkflowController(
        worker_service=worker_service,
        selection_state_service=selection_state_service,
        config_service=config_service,
        parent=None,
    )
    return AnnotationFlowContext(
        worker_service=worker_service,
        selection_state_service=selection_state_service,
        config_service=config_service,
        controller=controller,
        api_keys=api_keys,
    )


@given(parsers.parse("選択された画像が {count:d} 件ある"))
def given_selected_images(ctx: AnnotationFlowContext, count: int) -> None:
    paths = [f"/path/to/image{i}.jpg" for i in range(1, count + 1)]
    ctx.selection_state_service.get_selected_image_paths.return_value = paths


@given(parsers.parse('"{provider}" の API キーが未設定である'))
def given_api_key_missing(ctx: AnnotationFlowContext, provider: str) -> None:
    ctx.api_keys[f"{provider}_key"] = ""


@given(parsers.parse('モデル "{model}" は廃止済みである'))
def given_deprecated_model(ctx: AnnotationFlowContext, model: str) -> None:
    ctx.deprecated_models.add(model)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


def _run_workflow(ctx: AnnotationFlowContext, model: str, reply: object) -> None:
    """get_service_container と QMessageBox.warning をモックしてワークフローを実行する。

    廃止モデル警告 / API キー警告の QMessageBox は ``parent`` が None だと
    そもそも表示されない (Controller の早期 return)。reply を効かせるため
    parent をモックで注入する (#896 PR4b で属性名が ``_parent_widget`` に変更)。
    """
    ctx.controller._parent_widget = Mock()
    container = Mock()
    container.annotator_library.is_model_deprecated.side_effect = lambda model_name: (
        model_name in ctx.deprecated_models
    )
    container.image_repository.get_model_by_litellm_id.return_value = None

    with (
        patch(
            "lorairo.gui.controllers.annotation_workflow_controller.get_service_container",
            return_value=container,
        ),
        patch(
            "lorairo.gui.controllers.annotation_workflow_controller.QMessageBox.warning",
            return_value=reply,
        ),
    ):
        ctx.controller.start_annotation_workflow(selected_litellm_model_ids=[model])


@when(parsers.parse('モデル "{model}" を指定してアノテーションを開始する'))
def when_start_with_model(ctx: AnnotationFlowContext, model: str) -> None:
    _run_workflow(ctx, model, QMessageBox.StandardButton.Ok)


@when(parsers.parse('WebAPI モデル "{model}" を指定してアノテーションを開始する'))
def when_start_with_webapi_model(ctx: AnnotationFlowContext, model: str) -> None:
    _run_workflow(ctx, model, QMessageBox.StandardButton.Ok)


@when(parsers.parse('廃止モデル警告で "OK" を選んでアノテーションを開始する'))
def when_start_deprecated_ok(ctx: AnnotationFlowContext) -> None:
    model = next(iter(ctx.deprecated_models))
    _run_workflow(ctx, model, QMessageBox.StandardButton.Ok)


@when(parsers.parse('廃止モデル警告で "Cancel" を選んでアノテーションを開始する'))
def when_start_deprecated_cancel(ctx: AnnotationFlowContext) -> None:
    model = next(iter(ctx.deprecated_models))
    _run_workflow(ctx, model, QMessageBox.StandardButton.Cancel)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("バッチアノテーションが開始される")
def then_batch_started(ctx: AnnotationFlowContext) -> None:
    ctx.worker_service.start_enhanced_batch_annotation.assert_called_once()


@then("バッチアノテーションは開始されない")
def then_batch_not_started(ctx: AnnotationFlowContext) -> None:
    ctx.worker_service.start_enhanced_batch_annotation.assert_not_called()


@then(parsers.parse('開始対象のモデルは "{model}" である'))
def then_started_model(ctx: AnnotationFlowContext, model: str) -> None:
    call_args = ctx.worker_service.start_enhanced_batch_annotation.call_args
    assert call_args.kwargs["litellm_model_ids"] == [model]
