"""TagCloudService のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.services.tag_cloud_service import (
    CloudResult,
    TagCloudService,
    TagWeight,
)


def _make_service(image_tags: dict[int, list[str]]) -> TagCloudService:
    """TagCloudService をモック DB でインスタンス化。"""
    db_manager = MagicMock()
    svc = TagCloudService(db_manager)
    svc._load_tags = MagicMock(return_value=image_tags)  # type: ignore[method-assign]
    return svc


@pytest.mark.unit
class TestBuildCloud:
    def test_empty_keyword_returns_empty_cloud(self) -> None:
        svc = _make_service({1: ["a", "b"], 2: ["c"]})
        result = svc.build_cloud("", [])
        assert isinstance(result, CloudResult)
        assert result.entries == []
        assert result.matched_images == 0
        assert result.total_images == 2

    def test_substring_match_aggregates_cooccurring_tags(self) -> None:
        image_tags = {
            1: ["long_hair", "blonde_hair", "smile"],
            2: ["long_hair", "blue_eyes"],
            3: ["short_hair", "smile"],
            4: ["tree", "outdoor"],  # hair を含まない → 除外
        }
        svc = _make_service(image_tags)
        result = svc.build_cloud("hair", [])
        tags = {e.tag for e in result.entries}
        # hair を含む画像 (1,2,3) の全タグが対象
        assert "smile" in tags
        assert "blue_eyes" in tags
        assert "long_hair" in tags
        # hair を含まない画像のタグは出ない
        assert "tree" not in tags
        assert "outdoor" not in tags
        assert result.matched_images == 3

    def test_drilldown_and_filter_narrows_results(self) -> None:
        image_tags = {
            1: ["long_hair", "smile"],
            2: ["long_hair", "serious"],
            3: ["short_hair", "smile"],
        }
        svc = _make_service(image_tags)
        # keyword=hair + selected=smile → 画像1,3 のみ (long/short_hair 両方含む)
        result = svc.build_cloud("hair", ["smile"])
        assert result.matched_images == 2
        tags = {e.tag for e in result.entries}
        assert "serious" not in tags  # 画像2は smile を持たないので除外
        assert "long_hair" in tags
        assert "short_hair" in tags

    def test_selected_tags_excluded_from_cloud(self) -> None:
        image_tags = {1: ["long_hair", "smile"], 2: ["long_hair", "smile", "blush"]}
        svc = _make_service(image_tags)
        result = svc.build_cloud("hair", ["smile"])
        tags = {e.tag for e in result.entries}
        # 絞り込みに使った smile はクラウドに出さない
        assert "smile" not in tags
        assert "long_hair" in tags
        assert "blush" in tags

    def test_top_n_limits_entries(self) -> None:
        image_tags = {1: ["kw_tag"] + [f"tag_{i}" for i in range(100)]}
        svc = _make_service(image_tags)
        result = svc.build_cloud("kw", [], top_n=10)
        assert len(result.entries) <= 10

    def test_no_match_returns_empty_entries(self) -> None:
        svc = _make_service({1: ["cat"], 2: ["dog"]})
        result = svc.build_cloud("xyz", [])
        assert result.entries == []
        assert result.matched_images == 0
        assert result.total_images == 2

    def test_weights_normalized_in_range(self) -> None:
        image_tags = {
            1: ["kw", "common", "rare"],
            2: ["kw", "common"],
            3: ["kw", "common"],
        }
        svc = _make_service(image_tags)
        result = svc.build_cloud("kw", [])
        assert all(isinstance(e, TagWeight) for e in result.entries)
        for e in result.entries:
            assert 0.0 <= e.weight <= 1.0
        # 最頻タグの weight が最大 (1.0)
        top = max(result.entries, key=lambda e: e.count)
        assert top.weight == pytest.approx(1.0)

    def test_entries_sorted_by_count_desc(self) -> None:
        image_tags = {
            1: ["kw", "common", "mid"],
            2: ["kw", "common", "mid"],
            3: ["kw", "common"],
        }
        svc = _make_service(image_tags)
        result = svc.build_cloud("kw", [])
        counts = [e.count for e in result.entries]
        assert counts == sorted(counts, reverse=True)

    def test_case_insensitive_match(self) -> None:
        # _load_tags は小文字化済みを返す前提
        svc = _make_service({1: ["long_hair", "smile"]})
        result = svc.build_cloud("HAIR", [])
        assert result.matched_images == 1

    def test_refresh_reloads_tags(self) -> None:
        svc = _make_service({1: ["kw_a"]})
        first = svc.build_cloud("kw", [])
        assert first.total_images == 1
        # DB が更新されたと仮定して別データを返すようにする
        svc._load_tags = MagicMock(return_value={1: ["kw_a"], 2: ["kw_b"]})  # type: ignore[method-assign]
        # refresh 前はキャッシュのまま
        cached = svc.build_cloud("kw", [])
        assert cached.total_images == 1
        svc.refresh()
        after = svc.build_cloud("kw", [])
        assert after.total_images == 2
