"""タグ共起ベースのクラスタリングと2D配置サービス。

numpy + scipy のみを使用。GPU・重量MLモデル不要。
既存 Tag テーブルのデータからクラスタを導出する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager

# 語彙サイズ上限（タグ頻度上位）
_VOCAB_SIZE = 300
# クラスタ表示名に使う上位タグ数
_LABEL_TOP_K = 3
# 未タグ画像のクラスタID
OUTLIER_CLUSTER_ID = -1

_CLUSTER_COLORS = [
    "#c44a2f",
    "#2f7fa0",
    "#1f8a5b",
    "#7a4bc4",
    "#c08a2c",
    "#3a6ea5",
    "#c0392b",
    "#5a8a3f",
    "#a04060",
    "#3a8a8a",
]


@dataclass
class DotInfo:
    """散布図上の1点（1画像）の情報。"""

    image_id: int
    x: float  # 0..1 正規化済み
    y: float  # 0..1 正規化済み
    cluster_id: int
    top_tags: list[str]  # ツールチップ用上位タグ


@dataclass
class ClusterInfo:
    """クラスタメタデータ。"""

    id: int
    label: str  # タグ頻度から自動生成
    image_ids: list[int] = field(default_factory=list)
    color: str = "#8a8a8a"


@dataclass
class ClusterResult:
    """`TagClusterService.build_cluster_result` の返り値。"""

    dots: list[DotInfo]
    clusters: list[ClusterInfo]
    total_images: int
    tagged_images: int


class TagClusterService:
    """タグ共起行列から2Dクラスタ散布図を構築する。

    - ステップ1: DB から未 reject タグを全ロード
    - ステップ2: 頻出上位タグを語彙に選定、二値ベクトル化
    - ステップ3: PCA で2次元に圧縮
    - ステップ4: k-means でクラスタリング
    - ステップ5: クラスタをタグ頻度から命名
    """

    def __init__(self, db_manager: ImageDatabaseManager) -> None:
        self._db = db_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_cluster_result(self, n_clusters: int = 7) -> ClusterResult:
        """全画像のタグを読み込みクラスタ結果を返す。

        Args:
            n_clusters: 目標クラスタ数（実際のクラスタ数はデータ量で変動可）。

        Returns:
            ClusterResult — 点座標・クラスタ情報を含む。
        """
        image_tags = self._load_tags()
        tagged_ids = [iid for iid, tags in image_tags.items() if tags]
        untagged_ids = [iid for iid, tags in image_tags.items() if not tags]
        total = len(image_tags)
        logger.debug(f"タグ読込: 全{total}件 (タグあり={len(tagged_ids)}, なし={len(untagged_ids)})")

        if not tagged_ids:
            # タグあり画像が0件 → 全画像をアウトライアクラスタへ
            return self._all_untagged_result(image_tags)

        if len(tagged_ids) < max(n_clusters, 2):
            return self._fallback_result(image_tags)

        X, ids_in_order, vocab = self._build_vectors(image_tags, tagged_ids)
        coords_2d = self._pca_2d(X)
        labels = self._kmeans(coords_2d, min(n_clusters, len(tagged_ids)))
        coords_norm = self._normalize_coords(coords_2d)

        clusters = self._build_cluster_infos(labels, ids_in_order, image_tags, vocab, n_clusters)
        dots = self._build_dots(ids_in_order, coords_norm, labels, image_tags)

        # 未タグ画像はアウトライアクラスタへ
        if untagged_ids:
            outlier = ClusterInfo(id=OUTLIER_CLUSTER_ID, label="未タグ", color="#aaaaaa")
            outlier.image_ids = untagged_ids
            clusters.append(outlier)
            # 外縁に均等配置
            for i, iid in enumerate(untagged_ids):
                angle = 2 * math.pi * i / max(len(untagged_ids), 1)
                dots.append(
                    DotInfo(
                        image_id=iid,
                        x=0.5 + 0.48 * math.cos(angle),
                        y=0.5 + 0.48 * math.sin(angle),
                        cluster_id=OUTLIER_CLUSTER_ID,
                        top_tags=[],
                    )
                )

        return ClusterResult(
            dots=dots,
            clusters=clusters,
            total_images=total,
            tagged_images=len(tagged_ids),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_tags(self) -> dict[int, list[str]]:
        """未 reject タグを全ロードして {image_id: [tag, ...]} を返す。"""
        from sqlalchemy import select

        from lorairo.database.schema import Image, Tag

        result: dict[int, list[str]] = {}
        try:
            with self._db.session_scope() as session:
                # 全画像IDを取得
                image_ids = [row[0] for row in session.execute(select(Image.id)).all()]
                for iid in image_ids:
                    result[iid] = []
                # タグ取得（rejected_at IS NULL）
                rows = session.execute(select(Tag.image_id, Tag.tag).where(Tag.rejected_at.is_(None))).all()
                for image_id, tag in rows:
                    if image_id in result:
                        result[image_id].append(tag.lower())
        except Exception as exc:
            logger.error(f"タグ読込エラー: {exc}", exc_info=True)
            raise
        return result

    def _build_vectors(
        self,
        image_tags: dict[int, list[str]],
        tagged_ids: list[int],
    ) -> tuple[np.ndarray, list[int], list[str]]:
        """タグ頻度上位 _VOCAB_SIZE の二値ベクトル行列を構築する。"""
        from collections import Counter

        # 語彙選定
        all_tags: list[str] = []
        for iid in tagged_ids:
            all_tags.extend(image_tags[iid])
        freq = Counter(all_tags)
        vocab = [tag for tag, _ in freq.most_common(_VOCAB_SIZE)]
        vocab_idx = {t: i for i, t in enumerate(vocab)}

        # 二値行列
        n = len(tagged_ids)
        m = len(vocab)
        X = np.zeros((n, m), dtype=np.float32)
        for row_i, iid in enumerate(tagged_ids):
            for tag in image_tags[iid]:
                if tag in vocab_idx:
                    X[row_i, vocab_idx[tag]] = 1.0

        return X, tagged_ids, vocab

    def _pca_2d(self, X: np.ndarray) -> np.ndarray:
        """numpy SVD による PCA で2次元射影を返す。"""
        X_centered = X - X.mean(axis=0)
        # 分散がゼロの列を除去
        std = X_centered.std(axis=0)
        mask = std > 0
        if mask.sum() < 2:
            # タグが全く分散しない場合はランダム配置
            rng = np.random.default_rng(42)
            return rng.random((len(X), 2)).astype(np.float32)
        X_scaled = X_centered[:, mask]
        # 特異値分解（大規模行列では truncated SVD が有利だが scipy なし → 全量）
        try:
            _, _, Vt = np.linalg.svd(X_scaled, full_matrices=False)
            coords = X_scaled @ Vt[:2].T
        except np.linalg.LinAlgError:
            rng = np.random.default_rng(42)
            coords = rng.random((len(X), 2)).astype(np.float32)
        return coords.astype(np.float32)

    def _kmeans(self, coords: np.ndarray, k: int, max_iter: int = 50) -> np.ndarray:
        """簡易 k-means（scipy.cluster.vq を使用）。"""
        from scipy.cluster.vq import kmeans2

        try:
            _, labels = kmeans2(coords, k, iter=max_iter, minit="points", seed=42)
        except Exception as exc:
            logger.warning(f"k-means 失敗、均等分割にフォールバック: {exc}")
            labels = np.arange(len(coords)) % k
        return labels.astype(np.int32)

    def _normalize_coords(self, coords: np.ndarray) -> np.ndarray:
        """座標を [0.05, 0.95] に正規化する（端に余白）。"""
        mn = coords.min(axis=0)
        mx = coords.max(axis=0)
        rng = mx - mn
        rng[rng == 0] = 1.0
        normalized = (coords - mn) / rng * 0.90 + 0.05
        return normalized.astype(np.float32)

    def _build_cluster_infos(
        self,
        labels: np.ndarray,
        ids_in_order: list[int],
        image_tags: dict[int, list[str]],
        vocab: list[str],
        n_clusters: int,
    ) -> list[ClusterInfo]:
        """クラスタごとの上位タグからラベルを生成する。"""
        from collections import Counter

        clusters: dict[int, ClusterInfo] = {}
        for cid in range(n_clusters):
            color = _CLUSTER_COLORS[cid % len(_CLUSTER_COLORS)]
            clusters[cid] = ClusterInfo(id=cid, label="", color=color)

        # 各クラスタの画像IDとタグ収集
        cluster_tags: dict[int, Counter[str]] = {cid: Counter() for cid in range(n_clusters)}
        for _row_i, (iid, cid) in enumerate(zip(ids_in_order, labels, strict=False)):
            cid_int = int(cid)
            if cid_int not in clusters:
                continue
            clusters[cid_int].image_ids.append(iid)
            cluster_tags[cid_int].update(image_tags.get(iid, []))

        # タグ上位3つからクラスタ名を生成
        for cid, counter in cluster_tags.items():
            top = [t for t, _ in counter.most_common(_LABEL_TOP_K)]
            clusters[cid].label = " · ".join(top) if top else f"Cluster {cid}"

        return list(clusters.values())

    def _build_dots(
        self,
        ids_in_order: list[int],
        coords_norm: np.ndarray,
        labels: np.ndarray,
        image_tags: dict[int, list[str]],
    ) -> list[DotInfo]:
        """DotInfo リストを構築する。"""
        dots = []
        for row_i, iid in enumerate(ids_in_order):
            tags = image_tags.get(iid, [])
            dots.append(
                DotInfo(
                    image_id=iid,
                    x=float(coords_norm[row_i, 0]),
                    y=float(coords_norm[row_i, 1]),
                    cluster_id=int(labels[row_i]),
                    top_tags=tags[:5],
                )
            )
        return dots

    def _all_untagged_result(self, image_tags: dict[int, list[str]]) -> ClusterResult:
        """タグあり画像が0件のケース。全画像をアウトライアクラスタへ配置。"""
        ids = list(image_tags.keys())
        outlier = ClusterInfo(id=OUTLIER_CLUSTER_ID, label="未タグ", color="#aaaaaa", image_ids=ids)
        dots = [
            DotInfo(
                image_id=iid,
                x=0.5 + 0.48 * math.cos(2 * math.pi * i / max(len(ids), 1)),
                y=0.5 + 0.48 * math.sin(2 * math.pi * i / max(len(ids), 1)),
                cluster_id=OUTLIER_CLUSTER_ID,
                top_tags=[],
            )
            for i, iid in enumerate(ids)
        ]
        return ClusterResult(dots=dots, clusters=[outlier], total_images=len(ids), tagged_images=0)

    def _fallback_result(self, image_tags: dict[int, list[str]]) -> ClusterResult:
        """タグが少なすぎる場合のフォールバック。"""
        rng = np.random.default_rng(42)
        ids = list(image_tags.keys())
        dots = [
            DotInfo(
                image_id=iid,
                x=float(rng.random()),
                y=float(rng.random()),
                cluster_id=0,
                top_tags=image_tags.get(iid, [])[:5],
            )
            for iid in ids
        ]
        cluster = ClusterInfo(id=0, label="全画像", color=_CLUSTER_COLORS[0], image_ids=ids)
        return ClusterResult(
            dots=dots,
            clusters=[cluster],
            total_images=len(ids),
            tagged_images=sum(1 for t in image_tags.values() if t),
        )
