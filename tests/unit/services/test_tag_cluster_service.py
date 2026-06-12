"""TagClusterService のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from lorairo.services.tag_cluster_service import (
    OUTLIER_CLUSTER_ID,
    ClusterResult,
    TagClusterService,
)


def _make_service(image_tags: dict[int, list[str]]) -> TagClusterService:
    """TagClusterService をモック DB でインスタンス化。"""
    db_manager = MagicMock()
    svc = TagClusterService(db_manager)
    svc._load_tags = MagicMock(return_value=image_tags)
    return svc


@pytest.mark.unit
class TestTagClusterServiceBasic:
    def test_empty_db_returns_fallback(self) -> None:
        svc = _make_service({})
        result = svc.build_cluster_result(n_clusters=3)
        assert isinstance(result, ClusterResult)
        assert result.total_images == 0
        assert result.tagged_images == 0

    def test_all_untagged_goes_to_outlier_cluster(self) -> None:
        image_tags = {1: [], 2: [], 3: []}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=2)
        outlier_clusters = [c for c in result.clusters if c.id == OUTLIER_CLUSTER_ID]
        assert len(outlier_clusters) == 1
        assert set(outlier_clusters[0].image_ids) == {1, 2, 3}
        assert result.tagged_images == 0

    def test_tagged_images_get_dot_positions(self) -> None:
        image_tags = {i: [f"tag_{i % 5}", "common_tag"] for i in range(20)}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=3)
        assert len(result.dots) == 20
        for dot in result.dots:
            assert 0.0 <= dot.x <= 1.0
            assert 0.0 <= dot.y <= 1.0

    def test_cluster_labels_from_top_tags(self) -> None:
        # 桜タグを持つグループとバラタグを持つグループ
        image_tags: dict[int, list[str]] = {}
        for i in range(15):
            image_tags[i] = ["sakura", "outdoor", f"style_{i % 3}"]
        for i in range(15, 30):
            image_tags[i] = ["rose", "indoor", f"tone_{i % 3}"]
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=2)
        labels = [c.label for c in result.clusters if c.id != OUTLIER_CLUSTER_ID]
        assert all(label != "" for label in labels)

    def test_total_and_tagged_counts(self) -> None:
        image_tags = {1: ["a", "b"], 2: [], 3: ["c"], 4: []}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=2)
        assert result.total_images == 4
        assert result.tagged_images == 2

    def test_dot_top_tags_capped_at_5(self) -> None:
        image_tags = {1: [f"tag{i}" for i in range(20)]}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=1)
        for dot in result.dots:
            assert len(dot.top_tags) <= 5

    def test_n_clusters_respected_approximately(self) -> None:
        image_tags = {i: [f"tag_{i % 10}", f"sub_{i % 5}"] for i in range(50)}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=4)
        real_clusters = [c for c in result.clusters if c.id != OUTLIER_CLUSTER_ID]
        # k-means は指定数を返す（空クラスタは除外されない可能性あり）
        assert len(real_clusters) <= 4

    def test_fallback_on_too_few_tagged_images(self) -> None:
        # タグあり画像が n_clusters より少ない場合
        image_tags = {1: ["a"], 2: ["b"]}
        svc = _make_service(image_tags)
        result = svc.build_cluster_result(n_clusters=7)
        assert result.total_images == 2


@pytest.mark.unit
class TestBuildVectors:
    def test_returns_binary_matrix(self) -> None:
        svc = _make_service({})
        image_tags = {1: ["a", "b"], 2: ["b", "c"]}
        tagged_ids = [1, 2]
        X, _ids, vocab = svc._build_vectors(image_tags, tagged_ids)
        assert X.shape == (2, len(vocab))
        assert X.dtype == np.float32
        # 各行の値は 0 か 1
        assert set(X.flatten().tolist()).issubset({0.0, 1.0})

    def test_vocab_size_capped(self) -> None:
        svc = _make_service({})
        # 500 以上のユニークタグを持つ画像
        many_tags = [f"tag_{i}" for i in range(600)]
        image_tags = {1: many_tags}
        tagged_ids = [1]
        _X, _, vocab = svc._build_vectors(image_tags, tagged_ids)
        assert len(vocab) <= 300  # _VOCAB_SIZE


@pytest.mark.unit
class TestPCA2D:
    def test_returns_2d_array(self) -> None:
        svc = _make_service({})
        X = np.random.default_rng(0).random((30, 50)).astype(np.float32)
        coords = svc._pca_2d(X)
        assert coords.shape == (30, 2)

    def test_handles_zero_variance_columns(self) -> None:
        svc = _make_service({})
        X = np.ones((10, 5), dtype=np.float32)  # 全列が定数 → 分散 0
        coords = svc._pca_2d(X)
        assert coords.shape == (10, 2)


@pytest.mark.unit
class TestNormalizeCoords:
    def test_output_in_range(self) -> None:
        svc = _make_service({})
        coords = np.array([[0, 0], [1, 1], [0.5, 0.5]], dtype=np.float32)
        norm = svc._normalize_coords(coords)
        assert norm.min() >= 0.04
        assert norm.max() <= 0.96
