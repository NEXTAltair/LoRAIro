"""タグ検索・フロントエンドフィルタの BDD ステップ定義。

SearchFilterService の UI 入力解析（除外キーワード構文）と
SearchCriteriaProcessor のフロントエンドフィルタ（アスペクト比・重複除外）の
振る舞いを検証する。
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor
from lorairo.services.search_models import SearchConditions

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "tag_search_filter.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_manager() -> Mock:
    return Mock()


@pytest.fixture
def search_filter_service(mock_db_manager: Mock) -> SearchFilterService:
    return SearchFilterService(
        db_manager=mock_db_manager,
        model_selection_service=Mock(),
    )


@pytest.fixture
def criteria_processor(mock_db_manager: Mock) -> SearchCriteriaProcessor:
    return SearchCriteriaProcessor(db_manager=mock_db_manager)


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("SearchFilterService が初期化されている", target_fixture="ctx")
def given_search_filter_service_initialized(
    search_filter_service: SearchFilterService,
) -> dict[str, Any]:
    assert search_filter_service is not None
    return {"service": search_filter_service}


@given("SearchCriteriaProcessor が初期化されている", target_fixture="ctx")
def given_criteria_processor_initialized(
    criteria_processor: SearchCriteriaProcessor,
) -> dict[str, Any]:
    assert criteria_processor is not None
    return {"processor": criteria_processor}


@given("DB フィルタが幅と高さを持つ 4 件の画像を返す")
def given_db_returns_images_with_dimensions(mock_db_manager: Mock) -> None:
    # 1:1 が 2 件、それ以外が 2 件
    images = [
        {"id": 1, "width": 1024, "height": 1024},  # 1:1
        {"id": 2, "width": 512, "height": 512},  # 1:1
        {"id": 3, "width": 1920, "height": 1080},  # 16:9
        {"id": 4, "width": 720, "height": 1280},  # 9:16
    ]
    mock_db_manager.get_images_by_filter.return_value = (images, len(images))


@given("DB フィルタが pHash 重複を含む 4 件の画像を返す")
def given_db_returns_images_with_duplicate_phash(mock_db_manager: Mock) -> None:
    # phash "aaaa" が 2 件 -> 重複除外で 1 件に集約され、結果は 3 件
    images = [
        {"id": 1, "phash": "aaaa"},
        {"id": 2, "phash": "bbbb"},
        {"id": 3, "phash": "aaaa"},
        {"id": 4, "phash": "cccc"},
    ]
    mock_db_manager.get_images_by_filter.return_value = (images, len(images))


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(
    parsers.parse('タグ検索入力 "{input_text}" を解析して検索条件を作成する'),
)
def when_parse_and_create_conditions(ctx: dict[str, Any], input_text: str) -> None:
    service: SearchFilterService = ctx["service"]
    keywords, excluded_keywords = service.parse_search_input(input_text)
    conditions = service.create_search_conditions(
        search_type="tags",
        keywords=keywords,
        excluded_keywords=excluded_keywords,
        tag_logic="and",
    )
    ctx["keywords"] = keywords
    ctx["excluded_keywords"] = excluded_keywords
    ctx["conditions"] = conditions
    ctx["filter_criteria"] = conditions.to_filter_criteria()


@when(parsers.parse('アスペクト比 "{aspect_ratio}" を指定して検索を実行する'))
def when_search_with_aspect_ratio(ctx: dict[str, Any], aspect_ratio: str) -> None:
    processor: SearchCriteriaProcessor = ctx["processor"]
    conditions = SearchConditions(
        search_type="tags",
        keywords=[],
        tag_logic="and",
        aspect_ratio_filter=aspect_ratio,
    )
    images, reported_count = processor.execute_search_with_filters(conditions)
    ctx["images"] = images
    ctx["reported_count"] = reported_count


@when("重複除外を有効にして検索を実行する")
def when_search_with_duplicate_exclusion(ctx: dict[str, Any]) -> None:
    processor: SearchCriteriaProcessor = ctx["processor"]
    conditions = SearchConditions(
        search_type="tags",
        keywords=[],
        tag_logic="and",
        exclude_duplicates=True,
    )
    images, reported_count = processor.execute_search_with_filters(conditions)
    ctx["images"] = images
    ctx["reported_count"] = reported_count


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


def _parse_keyword_list(text: str) -> list[str]:
    return [k.strip() for k in text.split(",") if k.strip()]


@then(parsers.parse('通常キーワードは "{expected}" になる'))
def then_keywords_match(ctx: dict[str, Any], expected: str) -> None:
    assert ctx["keywords"] == _parse_keyword_list(expected)


@then(parsers.parse('除外キーワードは "{expected}" になる'))
def then_excluded_keywords_match(ctx: dict[str, Any], expected: str) -> None:
    assert ctx["excluded_keywords"] == _parse_keyword_list(expected)


@then(parsers.parse('フィルタ条件の除外タグは "{expected}" になる'))
def then_filter_criteria_excluded_tags_match(ctx: dict[str, Any], expected: str) -> None:
    assert ctx["filter_criteria"].excluded_tags == _parse_keyword_list(expected)


@then("報告件数はフィルタ後の件数と一致する")
def then_reported_count_matches_filtered(ctx: dict[str, Any]) -> None:
    assert ctx["reported_count"] == len(ctx["images"])


@then(parsers.parse("報告件数は {expected:d} になる"))
def then_reported_count_is(ctx: dict[str, Any], expected: int) -> None:
    assert ctx["reported_count"] == expected
