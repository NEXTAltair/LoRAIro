"""AnnotationWorker 部分失敗階層伝播 BDD steps (ADR 0033 #406)."""

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

from PySide6.QtWidgets import QTableWidget
from pytest_bdd import given, parsers, scenarios, then, when
from pytestqt.qtbot import QtBot

from lorairo.gui.widgets.annotation_summary_dialog import AnnotationSummaryDialog
from lorairo.gui.workers.annotation_worker import AnnotationExecutionResult, AnnotationWorker

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "annotation_worker_failure_propagation.feature"
scenarios(str(_FEATURE_FILE))


def _success_result(model: str) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        f"phash{i}": {model: {"tags": [f"tag-{i}"], "formatted_output": {}, "error": None}}
        for i in range(1, 4)
    }


def _error_result(model: str, message: str) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        f"phash{i}": {model: {"tags": [], "formatted_output": {}, "error": message}} for i in range(1, 4)
    }


def _exception_from_name(exc_type: str, message: str) -> Exception:
    exc_cls = (
        RuntimeError
        if exc_type == "RuntimeError"
        else ValueError
        if exc_type == "ValueError"
        else Exception
    )
    return exc_cls(message)


@given("AnnotationWorker が 2 モデル × 3 画像のタスクで初期化されている", target_fixture="worker_ctx")
def given_worker_initialized() -> dict[str, object]:
    image_paths = [f"/images/image_{i}.jpg" for i in range(1, 4)]
    db_manager = Mock()
    db_manager.image_repo.get_phashes_by_filepaths.return_value = {
        image_path: f"phash{i}" for i, image_path in enumerate(image_paths, start=1)
    }
    db_manager.image_repo.find_image_ids_by_phashes_multi.return_value = {
        f"phash{i}": [i] for i in range(1, 4)
    }
    db_manager.model_repo.get_models_by_litellm_ids.return_value = {
        "model-a": Mock(id=1),
        "model-b": Mock(id=2),
    }
    db_manager.annotation_repo.save_annotations = Mock()
    db_manager.image_repo.get_image_ids_by_filepaths.return_value = {
        image_path: i for i, image_path in enumerate(image_paths, start=1)
    }
    db_manager.get_image_id_by_filepath.side_effect = lambda path: {
        image_path: i for i, image_path in enumerate(image_paths, start=1)
    }.get(path)

    model_registry = Mock()
    model_registry.get_available_models.return_value = []
    annotation_runner = Mock()

    worker = AnnotationWorker(
        annotation_runner=annotation_runner,
        image_paths=image_paths,
        litellm_model_ids=["model-a", "model-b"],
        db_manager=db_manager,
        model_registry=model_registry,
    )
    return {
        "worker": worker,
        "annotation_runner": annotation_runner,
        "db_manager": db_manager,
        "behaviors": {},
        "result": None,
        "exception": None,
    }


@given("db_manager および model_registry が利用可能である")
def given_db_and_registry(worker_ctx: dict[str, object]) -> None:
    assert worker_ctx["db_manager"] is not None


@given(
    parsers.parse('image-annotator-lib がモデル "{model}" で全画像に対し result.error="{message}" を返す')
)
def given_lib_returns_result_error(worker_ctx: dict[str, object], model: str, message: str) -> None:
    behaviors = worker_ctx["behaviors"]
    assert isinstance(behaviors, dict)
    behaviors[model] = _error_result(model, message)


@given(parsers.parse('モデル "{model}" は全画像で成功する'))
def given_model_succeeds(worker_ctx: dict[str, object], model: str) -> None:
    behaviors = worker_ctx["behaviors"]
    assert isinstance(behaviors, dict)
    behaviors[model] = _success_result(model)


@given(parsers.parse('image-annotator-lib がモデル "{model}" の呼び出しで {exc_type} を raise する'))
def given_lib_raises_exception(worker_ctx: dict[str, object], model: str, exc_type: str) -> None:
    behaviors = worker_ctx["behaviors"]
    assert isinstance(behaviors, dict)
    behaviors[model] = _exception_from_name(exc_type, f"{model} failed")


@given(parsers.parse("refusal filter が {exc_type} を raise する"))
def given_refusal_filter_raises(worker_ctx: dict[str, object], exc_type: str) -> None:
    worker = worker_ctx["worker"]
    assert isinstance(worker, AnnotationWorker)
    worker._apply_refusal_prefilter = Mock(side_effect=_exception_from_name(exc_type, "filter failed"))  # type: ignore[method-assign]


@given(
    parsers.parse(
        'image-annotator-lib が litellm_model_ids に含まれない model_id "{model_id}" を結果に混入させる'
    )
)
def given_lib_inserts_unknown_model_id(worker_ctx: dict[str, object], model_id: str) -> None:
    behaviors = worker_ctx["behaviors"]
    assert isinstance(behaviors, dict)
    behaviors["model-a"] = {f"phash{i}": {model_id: {"tags": ["cat"], "error": None}} for i in range(1, 4)}


@when("AnnotationWorker を実行する")
def when_run_worker(worker_ctx: dict[str, object]) -> None:
    worker = worker_ctx["worker"]
    annotation_runner = worker_ctx["annotation_runner"]
    behaviors = worker_ctx["behaviors"]
    assert isinstance(worker, AnnotationWorker)
    assert isinstance(annotation_runner, Mock)
    assert isinstance(behaviors, dict)

    def execute_annotation(*_args: object, **kwargs: object) -> object:
        models = cast("list[str]", kwargs["litellm_model_ids"])
        if len(models) > 1:
            merged: dict[str, dict[str, dict[str, Any]]] = {}
            for model in models:
                behavior = behaviors.get(model, _success_result(model))
                if isinstance(behavior, Exception):
                    raise behavior
                for phash, annotations in behavior.items():
                    merged.setdefault(phash, {}).update(annotations)
            return merged

        model = models[0]
        behavior = behaviors.get(model, _success_result(model))
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    annotation_runner.execute_annotation.side_effect = execute_annotation
    try:
        worker_ctx["result"] = worker.execute()
    except Exception as exc:
        worker_ctx["exception"] = exc


@then("error_records テーブルに該当 row は追加されない")
def then_no_error_records_added(worker_ctx: dict[str, object]) -> None:
    db_manager = worker_ctx["db_manager"]
    assert isinstance(db_manager, Mock)
    db_manager.save_error_record.assert_not_called()


@then(parsers.parse('model_statistics の "{model}" の error_count は {count:d} である'))
def then_error_count_equals(worker_ctx: dict[str, object], model: str, count: int) -> None:
    result = worker_ctx["result"]
    assert isinstance(result, AnnotationExecutionResult)
    assert result.model_statistics[model].error_count == count


@then(parsers.parse('model_statistics の "{model}" の success_count は {count:d} である'))
def then_success_count_equals(worker_ctx: dict[str, object], model: str, count: int) -> None:
    result = worker_ctx["result"]
    assert isinstance(result, AnnotationExecutionResult)
    assert result.model_statistics[model].success_count == count


@then(parsers.parse('サマリーダイアログの model_errors に "{model}" のエラーが含まれる'))
def then_summary_includes_model_error(worker_ctx: dict[str, object], model: str) -> None:
    result = worker_ctx["result"]
    assert isinstance(result, AnnotationExecutionResult)
    assert any(error.model_name == model for error in result.model_errors)


@then(parsers.parse('error_records テーブルに {count:d} 行追加される (対象モデル="{model}")'))
def then_error_records_added_for_model(worker_ctx: dict[str, object], count: int, model: str) -> None:
    db_manager = worker_ctx["db_manager"]
    assert isinstance(db_manager, Mock)
    calls = [
        call for call in db_manager.save_error_record.call_args_list if call.kwargs["model_name"] == model
    ]
    assert len(calls) == count


@then(parsers.parse('各 row の error_type は "{expected}" または例外型名である'))
def then_error_type_matches(worker_ctx: dict[str, object], expected: str) -> None:
    db_manager = worker_ctx["db_manager"]
    assert isinstance(db_manager, Mock)
    error_types = {call.kwargs["error_type"] for call in db_manager.save_error_record.call_args_list}
    assert error_types <= {expected, "RuntimeError", "ValueError", "Exception"}


@then(parsers.parse('モデル "{model}" の処理は完了する'))
def then_model_completes(worker_ctx: dict[str, object], model: str) -> None:
    result = worker_ctx["result"]
    assert isinstance(result, AnnotationExecutionResult)
    assert any(model in annotations for annotations in result.results.values())


@then(parsers.parse("error_records テーブルに {count:d} 行追加される (model_name は NULL)"))
def then_error_records_added_no_model(worker_ctx: dict[str, object], count: int) -> None:
    db_manager = worker_ctx["db_manager"]
    assert isinstance(db_manager, Mock)
    calls = [
        call for call in db_manager.save_error_record.call_args_list if call.kwargs["model_name"] is None
    ]
    assert len(calls) == count


@then("Worker は失敗 Signal を emit する")
def then_worker_emits_failure_signal(worker_ctx: dict[str, object]) -> None:
    assert worker_ctx["exception"] is not None


@then(parsers.parse('error_records テーブルに該当 row が追加され error_type は "{expected}" である'))
def then_integrity_violation_recorded(worker_ctx: dict[str, object], expected: str) -> None:
    db_manager = worker_ctx["db_manager"]
    assert isinstance(db_manager, Mock)
    assert any(
        call.kwargs["error_type"] == expected for call in db_manager.save_error_record.call_args_list
    )


@then("サマリーダイアログの integrity_violation 専用セクションに該当エントリが表示される")
def then_integrity_violation_displayed(worker_ctx: dict[str, object], qtbot: QtBot) -> None:
    result = worker_ctx["result"]
    assert isinstance(result, AnnotationExecutionResult)
    dialog = AnnotationSummaryDialog(result)
    qtbot.addWidget(dialog)

    table = dialog.findChild(QTableWidget, "integrityViolationTable")
    assert table is not None
    assert table.rowCount() >= 1
    model_item = table.item(0, 1)
    assert model_item is not None
    assert model_item.text() == "unknown-model"
