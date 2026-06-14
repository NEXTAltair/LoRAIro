"""TagCloudService のユニットテスト（共起グラフモデル）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.services.tag_cloud_service import (
    GraphResult,
    TagCloudService,
)


def _make_service(image_tags: dict[int, list[str]]) -> TagCloudService:
    """TagCloudService をモック DB でインスタンス化。"""
    db_manager = MagicMock()
    svc = TagCloudService(db_manager)
    svc._load_tags = MagicMock(return_value=image_tags)  # type: ignore[method-assign]
    return svc


@pytest.mark.unit
class TestBuildGraph:
    def test_empty_keyword_returns_empty_graph(self) -> None:
        svc = _make_service({1: ["a", "b"], 2: ["c"]})
        result = svc.build_graph("", [])
        assert isinstance(result, GraphResult)
        assert result.nodes == []
        assert result.edges == []
        assert result.matched_images == 0
        assert result.total_images == 2

    def test_substring_match_builds_nodes(self) -> None:
        image_tags = {
            1: ["long_hair", "blonde_hair", "smile"],
            2: ["long_hair", "blue_eyes"],
            3: ["short_hair", "smile"],
            4: ["tree", "outdoor"],  # hair を含まない → 除外
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("hair", [])
        tags = {n.tag for n in result.nodes}
        assert "smile" in tags
        assert "blue_eyes" in tags
        assert "tree" not in tags
        assert result.matched_images == 3

    def test_drilldown_and_filter_narrows_results(self) -> None:
        image_tags = {
            1: ["long_hair", "smile"],
            2: ["long_hair", "serious"],
            3: ["short_hair", "smile"],
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("hair", ["smile"])
        assert result.matched_images == 2
        tags = {n.tag for n in result.nodes}
        assert "serious" not in tags
        assert "long_hair" in tags
        assert "short_hair" in tags

    def test_selected_tags_excluded_from_nodes(self) -> None:
        image_tags = {1: ["long_hair", "smile"], 2: ["long_hair", "smile", "blush"]}
        svc = _make_service(image_tags)
        result = svc.build_graph("hair", ["smile"])
        tags = {n.tag for n in result.nodes}
        assert "smile" not in tags
        assert "long_hair" in tags
        assert result.excluded_tags == ["smile"]

    def test_max_nodes_limits_nodes(self) -> None:
        image_tags = {1: ["kw_tag", *[f"tag_{i}" for i in range(100)]]}
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [], max_nodes=10)
        assert len(result.nodes) <= 10

    def test_no_match_returns_empty_nodes(self) -> None:
        svc = _make_service({1: ["cat"], 2: ["dog"]})
        result = svc.build_graph("xyz", [])
        assert result.nodes == []
        assert result.matched_images == 0
        assert result.total_images == 2

    def test_node_weights_normalized_in_range(self) -> None:
        image_tags = {
            1: ["kw", "common", "rare"],
            2: ["kw", "common"],
            3: ["kw", "common"],
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [])
        for n in result.nodes:
            assert 0.0 <= n.weight <= 1.0
        top = max(result.nodes, key=lambda n: n.count)
        assert top.weight == pytest.approx(1.0)

    def test_edges_built_from_cooccurrence(self) -> None:
        image_tags = {
            1: ["kw_a", "long_hair", "smile"],
            2: ["kw_a", "long_hair", "smile"],
            3: ["kw_a", "long_hair", "smile"],
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [])
        assert len(result.edges) > 0
        for e in result.edges:
            assert 0 <= e.a < len(result.nodes)
            assert 0 <= e.b < len(result.nodes)
            assert 0.0 <= e.norm <= 1.0

    def test_edge_below_min_weight_excluded(self) -> None:
        # 各ペアの共起が1回のみ → エッジ採用されない（min=2）
        image_tags = {
            1: ["kw_a", "x1", "y1"],
            2: ["kw_b", "x2", "y2"],
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [])
        assert result.edges == []

    def test_adjacency_is_symmetric(self) -> None:
        image_tags = {
            1: ["kw_a", "p", "q"],
            2: ["kw_a", "p", "q"],
        }
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [])
        assert len(result.adjacency) == len(result.nodes)
        for e in result.edges:
            assert e.b in result.adjacency[e.a]
            assert e.a in result.adjacency[e.b]

    def test_tag_count_reflects_unique_tags(self) -> None:
        image_tags = {1: ["kw", "a", "b"], 2: ["kw", "b", "c"]}
        svc = _make_service(image_tags)
        result = svc.build_graph("kw", [])
        assert result.tag_count == 4

    def test_case_insensitive_match(self) -> None:
        svc = _make_service({1: ["long_hair", "smile"]})
        result = svc.build_graph("HAIR", [])
        assert result.matched_images == 1

    def test_refresh_reloads_tags(self) -> None:
        svc = _make_service({1: ["kw_a"]})
        first = svc.build_graph("kw", [])
        assert first.total_images == 1
        svc._load_tags = MagicMock(return_value={1: ["kw_a"], 2: ["kw_b"]})  # type: ignore[method-assign]
        cached = svc.build_graph("kw", [])
        assert cached.total_images == 1
        svc.refresh()
        after = svc.build_graph("kw", [])
        assert after.total_images == 2
