"""export_with_criteria の BDD ステップ定義。"""

import warnings
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from pytest_bdd import given, scenarios, then, when

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.dataset_export_service import DatasetExportService

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "export_filter_required.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def export_context() -> dict[str, Any]:
    return {"result_path": None, "warnings": [], "exception": None}


@pytest.fixture
def mock_db_manager() -> Mock:
    return Mock()


@pytest.fixture
def export_service(mock_db_manager: Mock) -> DatasetExportService:
    return DatasetExportService(
        config_service=Mock(),
        file_system_manager=Mock(),
        db_manager=mock_db_manager,
        search_processor=Mock(),
    )


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("DatasetExportService が初期化されている")
def given_service_initialized(export_service: DatasetExportService) -> None:
    assert export_service is not None


@given("DB フィルタが 1 件の画像を返す")
def given_db_returns_one_image(mock_db_manager: Mock) -> None:
    mock_db_manager.get_images_by_filter.return_value = ([{"id": 1}], 1)


@given("DB フィルタが 0 件の画像を返す")
def given_db_returns_zero_images(mock_db_manager: Mock) -> None:
    mock_db_manager.get_images_by_filter.return_value = ([], 0)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("criteria を指定して export_with_criteria を呼び出す")
def when_call_with_criteria(
    export_service: DatasetExportService,
    export_context: dict[str, Any],
    tmp_path: Path,
) -> None:
    output = tmp_path / "export_out"
    criteria = ImageFilterCriteria(tags=["cat"])
    try:
        with patch.object(export_service, "export_filtered_dataset", return_value=output) as mock_exp:
            export_context["result_path"] = export_service.export_with_criteria(
                output_path=output,
                criteria=criteria,
            )
            export_context["mock_export"] = mock_exp
    except Exception as e:
        export_context["exception"] = e


@when("image_ids を指定して export_with_criteria を呼び出す")
def when_call_with_image_ids(
    export_service: DatasetExportService,
    export_context: dict[str, Any],
    tmp_path: Path,
) -> None:
    output = tmp_path / "export_out"
    try:
        with patch.object(export_service, "export_filtered_dataset", return_value=output):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                export_context["result_path"] = export_service.export_with_criteria(
                    output_path=output,
                    image_ids=[1, 2],
                )
                export_context["warnings"] = list(caught)
    except Exception as e:
        export_context["exception"] = e


@when("引数なしで export_with_criteria を呼び出す")
def when_call_without_args(
    export_service: DatasetExportService,
    export_context: dict[str, Any],
    tmp_path: Path,
) -> None:
    try:
        export_service.export_with_criteria(output_path=tmp_path / "out")
    except Exception as e:
        export_context["exception"] = e


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("エクスポートが正常に完了する")
def then_export_completes(export_context: dict[str, Any]) -> None:
    assert export_context["exception"] is None


@then("db_manager.get_images_by_filter が呼ばれた")
def then_db_filter_called(mock_db_manager: Mock) -> None:
    mock_db_manager.get_images_by_filter.assert_called_once()


@then("DeprecationWarning が発生する")
def then_deprecation_warning(export_context: dict[str, Any]) -> None:
    caught = export_context.get("warnings", [])
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


@then("ValueError が発生する")
def then_value_error(export_context: dict[str, Any]) -> None:
    assert isinstance(export_context["exception"], ValueError)
