"""アノテーション実行の受付・待機・メモリ不足後の継続 BDD steps (ADR 0109)."""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.gui.workers.annotation_worker import MEMORY_SKIP_ERROR_TYPE, AnnotationWorker
from lorairo.services.annotation_execution_policy import (
    AnnotationExecutionPolicy,
    AnnotationExecutionSettings,
    MemorySnapshot,
)
from lorairo.services.annotation_progress import AnnotationPhase
from lorairo.services.model_registry_protocol import ModelInfo

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "annotation_execution_control.feature"
scenarios(str(_FEATURE_FILE))

GIB = 1024**3
IMAGE_PATHS = ["/images/one.jpg", "/images/two.jpg"]
PHASHES = ["phash-1", "phash-2"]


@dataclass
class ExecutionContext:
    models: list[str]
    settings: AnnotationExecutionSettings = field(default_factory=AnnotationExecutionSettings)
    ram_gb: list[float] = field(default_factory=lambda: [16.0])
    oom_after_first: set[str] = field(default_factory=set)
    called_models: list[str] = field(default_factory=list)
    waiting_details: list[str] = field(default_factory=list)
    db_manager: Mock = field(default_factory=Mock)
    worker: AnnotationWorker | None = None


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _result(model: str, *, oom_after_first: bool) -> dict[str, dict[str, dict[str, object]]]:
    results: dict[str, dict[str, dict[str, object]]] = {
        PHASHES[0]: {model: {"tags": [f"{model}-tag"], "error": None}}
    }
    if oom_after_first:
        results[PHASHES[1]] = {
            model: {"tags": None, "error": "推論中にメモリ不足になりました", "error_code": "OUT_OF_MEMORY"}
        }
    else:
        results[PHASHES[1]] = {model: {"tags": [f"{model}-tag"], "error": None}}
    return results


@given(
    parsers.parse('ローカルモデル "{model_a}" と "{model_b}" を 2 枚の画像に実行するアノテーションがある'),
    target_fixture="ctx",
)
def given_two_local_models(model_a: str, model_b: str) -> ExecutionContext:
    db = Mock()
    db.image_repo.get_phashes_by_filepaths.return_value = dict(zip(IMAGE_PATHS, PHASHES, strict=True))
    db.image_repo.find_image_ids_by_phashes.return_value = {PHASHES[0]: 1, PHASHES[1]: 2}
    db.image_repo.find_image_ids_by_phashes_multi.return_value = {PHASHES[0]: [1], PHASHES[1]: [2]}
    db.image_repo.get_image_ids_by_filepaths.return_value = {IMAGE_PATHS[0]: 1, IMAGE_PATHS[1]: 2}
    db.model_repo.get_models_by_litellm_ids.return_value = {model_a: Mock(id=1), model_b: Mock(id=2)}
    return ExecutionContext(models=[model_a, model_b], db_manager=db)


@given(
    parsers.parse(
        "安全余裕は {margin:d} GB、確認間隔は {poll:d} 秒、待機タイムアウトは {timeout:d} 秒である"
    )
)
def given_settings(ctx: ExecutionContext, margin: int, poll: int, timeout: int) -> None:
    ctx.settings = AnnotationExecutionSettings(
        ram_safety_margin_gb=float(margin),
        wait_poll_interval_sec=float(poll),
        wait_timeout_sec=float(timeout),
    )


@given(parsers.parse("空きメモリは常に {ram:d} GB である"))
def given_constant_memory(ctx: ExecutionContext, ram: int) -> None:
    ctx.ram_gb = [float(ram)]


@given(parsers.parse('空きメモリは "{sequence}" GB と推移する'))
def given_memory_sequence(ctx: ExecutionContext, sequence: str) -> None:
    ctx.ram_gb = [float(value) for value in sequence.split(",")]


@given(parsers.parse('"{model}" は 1 枚目を処理した後にメモリ不足を返す'))
def given_oom_after_first(ctx: ExecutionContext, model: str) -> None:
    ctx.oom_after_first.add(model)


@when("アノテーションを実行する")
def when_run(ctx: ExecutionContext) -> None:
    probe_calls = {"count": 0}

    def probe() -> MemorySnapshot:
        value = ctx.ram_gb[min(probe_calls["count"], len(ctx.ram_gb) - 1)]
        probe_calls["count"] += 1
        return MemorySnapshot(available_ram_bytes=int(value * GIB))

    clock = _FakeClock()
    runner = Mock()

    def execute_annotation(
        image_paths: list[str], litellm_model_ids: list[str], phash_list: list[str] | None = None
    ) -> object:
        model = litellm_model_ids[0]
        ctx.called_models.append(model)
        return _result(model, oom_after_first=model in ctx.oom_after_first)

    runner.execute_annotation.side_effect = execute_annotation
    runner.get_execution_device.return_value = None
    registry = Mock()
    registry.get_available_models.return_value = [
        ModelInfo(
            name=model,
            provider="local",
            capabilities=["tags"],
            litellm_model_id=model,
            requires_api_key=False,
            estimated_size_gb=None,
        )
        for model in ctx.models
    ]
    worker = AnnotationWorker(
        annotation_runner=runner,
        image_paths=list(IMAGE_PATHS),
        litellm_model_ids=list(ctx.models),
        db_manager=ctx.db_manager,
        model_registry=registry,
        execution_policy=AnnotationExecutionPolicy(
            ctx.settings, memory_probe=probe, clock=clock, sleep=clock.sleep
        ),
    )
    worker.progress_updated.connect(
        lambda p: (
            ctx.waiting_details.append(p.annotation_progress.detail_text())
            if p.annotation_progress.phase is AnnotationPhase.WAITING_FOR_MEMORY
            else None
        )
    )
    ctx.worker = worker
    worker.execute()


def _memory_records(ctx: ExecutionContext, model: str) -> list[dict[str, object]]:
    return [
        call.kwargs
        for call in ctx.db_manager.save_error_record.call_args_list
        if call.kwargs.get("error_type") == MEMORY_SKIP_ERROR_TYPE
        and call.kwargs.get("model_name") == model
    ]


@then(parsers.parse('モデルは "{order}" の順に実行される'))
def then_models_run_in_order(ctx: ExecutionContext, order: str) -> None:
    assert ctx.called_models == [model.strip() for model in order.split(",")]


@then("モデルは 1 つも実行されない")
def then_no_model_runs(ctx: ExecutionContext) -> None:
    assert ctx.called_models == []


@then("メモリ不足の記録は残らない")
def then_no_memory_record(ctx: ExecutionContext) -> None:
    assert all(_memory_records(ctx, model) == [] for model in ctx.models)


@then(parsers.parse('待機中の進捗に "{shortage}" と残り秒が表示される'))
def then_waiting_detail(ctx: ExecutionContext, shortage: str) -> None:
    assert ctx.waiting_details
    assert shortage in ctx.waiting_details[0]
    assert "残り 20秒" in ctx.waiting_details[0]


@then(parsers.parse('"{model}" のメモリ不足の記録が {count:d} 件残る'))
def then_memory_records(ctx: ExecutionContext, model: str, count: int) -> None:
    records = _memory_records(ctx, model)
    assert len(records) == count
    assert sorted(str(r["file_path"]) for r in records) == sorted(IMAGE_PATHS)


@then(parsers.parse('記録の理由に "{reason}" が含まれる'))
def then_record_reason(ctx: ExecutionContext, reason: str) -> None:
    records = [r for model in ctx.models for r in _memory_records(ctx, model)]
    assert records
    assert all(reason in str(r["error_message"]) for r in records)


@then(parsers.parse('"{model}" の 1 枚目の結果は保存されている'))
def then_first_result_saved(ctx: ExecutionContext, model: str) -> None:
    assert ctx.worker is not None
    assert (PHASHES[0], model) in ctx.worker._persisted_keys
