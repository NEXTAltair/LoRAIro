"""画像処理パイプラインの BDD ステップ定義。

ImageProcessingService.process_images_in_list() のバッチ処理堅牢性ルール
(処理済みスキップ / キャンセル中断 / 部分失敗継続) を Gherkin で固定する。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.image_processing_service import ImageProcessingService
from lorairo.storage.file_system import FileSystemManager

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "image_processing_pipeline.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """ステップ間で受け渡す画像処理パイプラインの状態。"""

    service: ImageProcessingService
    mock_idm: MagicMock
    mock_ipm: MagicMock = field(default_factory=MagicMock)
    image_paths: list[Path] = field(default_factory=list)
    process_call_count: int = 0
    status_messages: list[str] = field(default_factory=list)
    expect_skip: bool = False


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("ImageProcessingService が初期化されている", target_fixture="ctx")
def given_service_initialized() -> PipelineContext:
    mock_config = MagicMock(spec=ConfigurationService)
    mock_config.get_preferred_resolutions.return_value = [(512, 512)]
    mock_config.get_image_processing_config.return_value = {
        "target_resolution": 512,
        "upscaler": "ESRGAN",
    }
    mock_fsm = MagicMock(spec=FileSystemManager)
    mock_idm = MagicMock(spec=ImageDatabaseManager)
    mock_idm.detect_duplicate_image.return_value = 1
    mock_idm.get_image_metadata.return_value = {
        "stored_image_path": "original.png",
        "has_alpha": False,
        "mode": "RGB",
    }
    mock_idm.check_processed_image_exists.return_value = None
    service = ImageProcessingService(mock_config, mock_fsm, mock_idm)
    return PipelineContext(service=service, mock_idm=mock_idm)


@given("対象画像が既に処理済みとして DB に存在する")
def given_image_already_processed(ctx: PipelineContext) -> None:
    ctx.mock_idm.check_processed_image_exists.return_value = {"stored_image_path": "processed.png"}
    ctx.image_paths = [Path("/test/images/already.png")]
    ctx.expect_skip = True


@given(parsers.parse("{count:d} 件の画像リストがある"))
def given_image_list(ctx: PipelineContext, count: int) -> None:
    ctx.image_paths = [Path(f"/test/images/img_{i}.png") for i in range(count)]


@given(parsers.parse("{count:d} 件の画像リストがあり 1 件目で例外が発生する"))
def given_image_list_with_first_failure(ctx: PipelineContext, count: int) -> None:
    ctx.image_paths = [Path(f"/test/images/img_{i}.png") for i in range(count)]

    def mock_process(image_file, upscaler, ipm):
        ctx.process_call_count += 1
        if ctx.process_call_count == 1:
            raise RuntimeError("処理失敗")

    ctx._process_side_effect = mock_process  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


def _status_callback(ctx: PipelineContext):
    def _cb(message: str) -> None:
        ctx.status_messages.append(message)

    return _cb


@when("画像リストを処理する")
def when_process_image_list(ctx: PipelineContext) -> None:
    side_effect = getattr(ctx, "_process_side_effect", None)
    with patch.dict(
        "sys.modules",
        {"lorairo.editor.image_processor": _image_processor_module(ctx)},
    ):
        if side_effect is not None:
            with patch.object(ctx.service, "_process_single_image", side_effect=side_effect):
                ctx.service.process_images_in_list(
                    ctx.image_paths, 512, status_callback=_status_callback(ctx)
                )
        elif ctx.expect_skip:
            # 処理済みスキップシナリオ: _process_single_image はモックせず
            # check_processed_image_exists の判定を実コードで通す
            with patch(
                "lorairo.database.db_core.resolve_stored_path",
                return_value=Path("/resolved/path.png"),
            ):
                ctx.service.process_images_in_list(
                    ctx.image_paths, 512, status_callback=_status_callback(ctx)
                )
        else:
            with patch.object(ctx.service, "_process_single_image") as mock_process:
                ctx.service.process_images_in_list(
                    ctx.image_paths, 512, status_callback=_status_callback(ctx)
                )
                ctx.process_call_count = mock_process.call_count


@when(parsers.parse("{cancel_at:d} 件目でキャンセルして画像リストを処理する"))
def when_process_with_cancel(ctx: PipelineContext, cancel_at: int) -> None:
    cancel_state = {"n": 0}

    def is_canceled() -> bool:
        cancel_state["n"] += 1
        return cancel_state["n"] >= cancel_at

    with patch.dict(
        "sys.modules",
        {"lorairo.editor.image_processor": _image_processor_module(ctx)},
    ):
        with patch.object(ctx.service, "_process_single_image") as mock_process:
            ctx.service.process_images_in_list(
                ctx.image_paths,
                512,
                status_callback=_status_callback(ctx),
                is_canceled=is_canceled,
            )
            ctx.process_call_count = mock_process.call_count


def _image_processor_module(ctx: PipelineContext) -> MagicMock:
    """lorairo.editor.image_processor のモジュールモック (torch 循環 import 回避)。"""
    mock_module = MagicMock()
    mock_module.ImageProcessingManager = MagicMock(return_value=ctx.mock_ipm)
    return mock_module


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("画像処理は実行されない")
def then_processing_not_executed(ctx: PipelineContext) -> None:
    ctx.mock_ipm.process_image.assert_not_called()


@then(parsers.parse("{count:d} 件のみ処理される"))
def then_only_n_processed(ctx: PipelineContext, count: int) -> None:
    assert ctx.process_call_count == count


@then("キャンセル通知が status_callback に渡される")
def then_cancel_notified(ctx: PipelineContext) -> None:
    assert any("キャンセル" in msg for msg in ctx.status_messages)


@then(parsers.parse("{count:d} 件すべての画像が処理試行される"))
def then_all_processed(ctx: PipelineContext, count: int) -> None:
    assert ctx.process_call_count == count


@then("エラー通知が status_callback に渡される")
def then_error_notified(ctx: PipelineContext) -> None:
    assert any("エラー" in msg for msg in ctx.status_messages)
