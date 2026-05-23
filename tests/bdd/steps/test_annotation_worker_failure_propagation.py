"""AnnotationWorker 部分失敗階層伝播 BDD step skeleton (ADR 0033 #406).

Worker 側の修正 (#399-#403) が未完了の段階では各 step が `pytest.skip` で保留される。
Worker 側 PR が main に merge されたら、対応する step を実装に置き換える。
"""

from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "annotation_worker_failure_propagation.feature"
scenarios(str(_FEATURE_FILE))

_PENDING_MESSAGE = (
    "pending: AnnotationWorker 部分失敗階層伝播の実装 (ADR 0033 #400/#401/#402/#403) 完了待ち"
)


@given("AnnotationWorker が 2 モデル × 3 画像のタスクで初期化されている", target_fixture="worker_ctx")
def given_worker_initialized() -> dict[str, object]:
    pytest.skip(_PENDING_MESSAGE)


@given("db_manager および model_registry が利用可能である")
def given_db_and_registry() -> None:
    pytest.skip(_PENDING_MESSAGE)


@given(
    parsers.parse('image-annotator-lib がモデル "{model}" で全画像に対し result.error="{message}" を返す')
)
def given_lib_returns_result_error(model: str, message: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@given(parsers.parse('モデル "{model}" は全画像で成功する'))
def given_model_succeeds(model: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@given(parsers.parse('image-annotator-lib がモデル "{model}" の呼び出しで {exc_type} を raise する'))
def given_lib_raises_exception(model: str, exc_type: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@given(parsers.parse("refusal filter が {exc_type} を raise する"))
def given_refusal_filter_raises(exc_type: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@given(
    parsers.parse(
        'image-annotator-lib が litellm_model_ids に含まれない model_id "{model_id}" を結果に混入させる'
    )
)
def given_lib_inserts_unknown_model_id(model_id: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@when("AnnotationWorker を実行する")
def when_run_worker() -> None:
    pytest.skip(_PENDING_MESSAGE)


@then("error_records テーブルに該当 row は追加されない")
def then_no_error_records_added() -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('model_statistics の "{model}" の error_count は {count:d} である'))
def then_error_count_equals(model: str, count: int) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('model_statistics の "{model}" の success_count は {count:d} である'))
def then_success_count_equals(model: str, count: int) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('サマリーダイアログの model_errors に "{model}" のエラーが含まれる'))
def then_summary_includes_model_error(model: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('error_records テーブルに {count:d} 行追加される (対象モデル="{model}")'))
def then_error_records_added_for_model(count: int, model: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('各 row の error_type は "{expected}" または例外型名である'))
def then_error_type_matches(expected: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('モデル "{model}" の処理は完了する'))
def then_model_completes(model: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse("error_records テーブルに {count:d} 行追加される (model_name は NULL)"))
def then_error_records_added_no_model(count: int) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then("Worker は失敗 Signal を emit する")
def then_worker_emits_failure_signal() -> None:
    pytest.skip(_PENDING_MESSAGE)


@then(parsers.parse('error_records テーブルに該当 row が追加され error_type は "{expected}" である'))
def then_integrity_violation_recorded(expected: str) -> None:
    pytest.skip(_PENDING_MESSAGE)


@then("サマリーダイアログの integrity_violation 専用セクションに該当エントリが表示される")
def then_integrity_violation_displayed() -> None:
    pytest.skip(_PENDING_MESSAGE)
