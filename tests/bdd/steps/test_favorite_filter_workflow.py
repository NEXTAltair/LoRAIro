"""お気に入りフィルタの保存・再適用フローの BDD ステップ定義。

FavoriteFiltersService（JSON 永続化）と SearchFilterService（条件構築）を
横断し、保存した条件で再検索したとき保存前と同じ結果が得られることを検証する。

FavoriteFiltersService と SearchFilterService に直接の連携コードは無いため、
dict ⇄ SearchConditions の変換はステップ定義内で明示的に組む（src は変更しない）。
datetime フィールドは JSON 直列化できないためシナリオ対象外。
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_bdd import given, scenarios, then, when

from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.services.favorite_filters_service import FavoriteFiltersService
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "favorite_filter_workflow.feature"
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


@given("FavoriteFiltersService が一時ディレクトリで初期化されている", target_fixture="ctx")
def given_favorite_service_initialized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    search_filter_service: SearchFilterService,
    criteria_processor: SearchCriteriaProcessor,
) -> dict[str, Any]:
    # Path.home() を tmp_path にリダイレクトし実ユーザー設定を汚染しない
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    favorite_service = FavoriteFiltersService()
    return {
        "favorite_service": favorite_service,
        "search_filter_service": search_filter_service,
        "criteria_processor": criteria_processor,
    }


@given("DB フィルタが同一条件に対して常に同じ結果を返す")
def given_db_returns_consistent_result(ctx: dict[str, Any], mock_db_manager: Mock) -> None:
    # 1:1 フィルタ（保存条件の aspect_ratio_filter）で 2 件が残るよう width/height を設定
    images = [
        {"id": 1, "phash": "aaaa", "width": 1024, "height": 1024},  # 1:1
        {"id": 2, "phash": "bbbb", "width": 512, "height": 512},  # 1:1
        {"id": 3, "phash": "cccc", "width": 1920, "height": 1080},  # 16:9
    ]
    # 同一条件の 2 回呼び出しで常に同じ戻り値
    mock_db_manager.get_images_by_filter.return_value = (images, len(images))


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when('タグ検索条件を組み立てて "my_favorite" として保存する')
def when_build_and_save_filter(ctx: dict[str, Any]) -> None:
    # datetime を含まない素朴な dict（JSON ラウンドトリップ安全）
    filter_dict: dict[str, Any] = {
        "search_type": "tags",
        "keywords": ["1girl", "blue_eyes"],
        "excluded_keywords": ["1boy"],
        "tag_logic": "and",
        "aspect_ratio_filter": "1:1 (正方形)",
        "exclude_duplicates": False,
        "only_untagged": False,
    }
    favorite_service: FavoriteFiltersService = ctx["favorite_service"]
    saved = favorite_service.save_filter("my_favorite", filter_dict)
    assert saved is True
    ctx["saved_dict"] = filter_dict


@when("保存前の検索を実行して結果を記録する")
def when_search_before_save(ctx: dict[str, Any]) -> None:
    search_service: SearchFilterService = ctx["search_filter_service"]
    processor: SearchCriteriaProcessor = ctx["criteria_processor"]
    conditions = search_service.create_search_conditions(**ctx["saved_dict"])
    images, reported_count = processor.execute_search_with_filters(conditions)
    ctx["before_conditions"] = conditions
    ctx["before_result"] = (images, reported_count)


@when('"my_favorite" を読み込んで検索条件を再構築する')
def when_load_and_rebuild(ctx: dict[str, Any]) -> None:
    favorite_service: FavoriteFiltersService = ctx["favorite_service"]
    search_service: SearchFilterService = ctx["search_filter_service"]
    processor: SearchCriteriaProcessor = ctx["criteria_processor"]

    loaded_dict = favorite_service.load_filter("my_favorite")
    assert loaded_dict is not None
    ctx["loaded_dict"] = loaded_dict

    conditions = search_service.create_search_conditions(**loaded_dict)
    images, reported_count = processor.execute_search_with_filters(conditions)
    ctx["after_conditions"] = conditions
    ctx["after_result"] = (images, reported_count)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("保存した条件と復元した条件が一致する")
def then_dicts_match(ctx: dict[str, Any]) -> None:
    assert ctx["loaded_dict"] == ctx["saved_dict"]
    before = ctx["before_conditions"]
    after = ctx["after_conditions"]
    assert after.search_type == before.search_type
    assert after.keywords == before.keywords
    assert after.excluded_keywords == before.excluded_keywords
    assert after.tag_logic == before.tag_logic
    assert after.aspect_ratio_filter == before.aspect_ratio_filter


@then("復元後の検索結果が保存前の検索結果と一致する")
def then_results_match(ctx: dict[str, Any]) -> None:
    before_images, before_count = ctx["before_result"]
    after_images, after_count = ctx["after_result"]
    assert after_images == before_images
    assert after_count == before_count
