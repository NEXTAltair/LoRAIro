"""キーワード連動の共起タグ探索サービス。

任意のキーワード（部分一致）でマッチした画像群から、タグの出現頻度と
タグ同士の共起関係を集計し、ネットワーク図・タグクラウド双方の描画に使える
グラフモデルを返す。クリックによる AND ドリルダウン絞り込みに対応する。
重量 ML 依存なし（標準ライブラリのみ）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager

# ネットワーク図に表示するノード数の上限（読みやすさ優先）
_DEFAULT_MAX_NODES = 34
# 1ノードあたりのエッジ数上限（hairball 抑制）
_DEFAULT_MAX_EDGES_PER_NODE = 5
# エッジとして採用する最小共起回数
_MIN_EDGE_WEIGHT = 2


@dataclass
class GraphNode:
    """共起グラフの1ノード（1タグ）。"""

    tag: str
    count: int  # 該当画像群での出現数
    weight: float  # 0.0..1.0 正規化済み頻度（min-max、サイズ/色用）


@dataclass
class GraphEdge:
    """共起グラフの1エッジ（2タグの共起）。"""

    a: int  # ノードインデックス
    b: int  # ノードインデックス
    weight: int  # 共起回数
    norm: float  # 0.0..1.0 正規化済み共起強度（線の太さ用）


@dataclass
class GraphResult:
    """`TagCloudService.build_graph` の返り値。"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    adjacency: list[set[int]]  # nodes と同じ並び。各ノードの隣接ノード集合
    matched_images: int
    total_images: int
    tag_count: int = 0  # 該当画像群に出現したユニークタグ総数
    excluded_tags: list[str] = field(default_factory=list)  # 絞り込みに使用中のタグ


class TagCloudService:
    """共起タグのグラフモデルを構築する。

    起動時に `{image_id: [tag, ...]}` を1度ロードしてキャッシュし、
    ドリルダウン時はキャッシュの再フィルタのみで高速に再計算する。
    DB 更新を反映したい場合は `refresh()` でキャッシュを破棄する。
    """

    def __init__(self, db_manager: ImageDatabaseManager) -> None:
        self._db = db_manager
        self._image_tags: dict[int, list[str]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_graph(
        self,
        keyword: str,
        selected_tags: list[str] | None = None,
        max_nodes: int = _DEFAULT_MAX_NODES,
        max_edges_per_node: int = _DEFAULT_MAX_EDGES_PER_NODE,
    ) -> GraphResult:
        """キーワードと絞り込みタグから共起グラフを構築する。

        画像が対象となる条件:
            - `keyword` を部分文字列に含むタグを1つ以上持つ
            - `selected_tags` のタグを全て持つ（AND 絞り込み）

        ノードは該当画像群の頻度上位 `max_nodes` 個（絞り込み中タグを除く）。
        エッジは採用ノード間の共起のうち共起回数 >= 2 のものを、ノードあたり
        `max_edges_per_node` 本まで（共起の強い順に）採用する。

        Args:
            keyword: 部分一致検索キーワード。空文字なら空グラフを返す。
            selected_tags: ドリルダウンで追加された完全一致タグのリスト。
            max_nodes: ノード数の上限。
            max_edges_per_node: 1ノードあたりのエッジ採用数上限。

        Returns:
            GraphResult — ノード・エッジ・隣接情報と該当件数。
        """
        image_tags = self._get_image_tags()
        total = len(image_tags)

        keyword_norm = keyword.strip().lower()
        selected = [t.strip().lower() for t in (selected_tags or []) if t.strip()]
        selected_set = set(selected)

        if not keyword_norm:
            return GraphResult(
                nodes=[],
                edges=[],
                adjacency=[],
                matched_images=0,
                total_images=total,
                tag_count=0,
                excluded_tags=selected,
            )

        matched = self._filter_matched(image_tags, keyword_norm, selected_set)

        # 該当画像群のタグ頻度
        freq: Counter[str] = Counter()
        for tags in matched:
            freq.update(tags)

        # ノード選定: 絞り込み中タグを除いた頻度上位
        entries = [(t, c) for t, c in freq.items() if t not in selected_set]
        entries.sort(key=lambda e: e[1], reverse=True)
        top = entries[:max_nodes]
        keep = {t for t, _ in top}

        nodes = self._build_nodes(top)
        node_index = {n.tag: i for i, n in enumerate(nodes)}
        edges, adjacency = self._build_edges(matched, keep, node_index, len(nodes), max_edges_per_node)

        logger.debug(
            f"TagGraph: keyword='{keyword_norm}' selected={selected} "
            f"matched={len(matched)}/{total} nodes={len(nodes)} edges={len(edges)}"
        )
        return GraphResult(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency,
            matched_images=len(matched),
            total_images=total,
            tag_count=len(freq),
            excluded_tags=selected,
        )

    def refresh(self) -> None:
        """タグキャッシュを破棄し、次回 build 時に DB から再ロードする。"""
        self._image_tags = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_image_tags(self) -> dict[int, list[str]]:
        """キャッシュされたタグ辞書を返す（未ロードならロード）。"""
        if self._image_tags is None:
            self._image_tags = self._load_tags()
        return self._image_tags

    @staticmethod
    def _filter_matched(
        image_tags: dict[int, list[str]],
        keyword_norm: str,
        selected_set: set[str],
    ) -> list[list[str]]:
        """条件を満たす画像のタグリスト一覧を返す。"""
        matched: list[list[str]] = []
        for tags in image_tags.values():
            if selected_set and not selected_set.issubset(tags):
                continue
            if not any(keyword_norm in tag for tag in tags):
                continue
            matched.append(tags)
        return matched

    @staticmethod
    def _build_nodes(top: list[tuple[str, int]]) -> list[GraphNode]:
        """頻度上位タグを min-max 正規化したノードへ変換する。"""
        if not top:
            return []
        counts = [c for _, c in top]
        max_freq = max(counts)
        min_freq = min(counts)
        span = max_freq - min_freq
        return [
            GraphNode(tag=tag, count=count, weight=1.0 if span == 0 else (count - min_freq) / span)
            for tag, count in top
        ]

    @staticmethod
    def _build_edges(
        matched: list[list[str]],
        keep: set[str],
        node_index: dict[str, int],
        node_count: int,
        max_edges_per_node: int,
    ) -> tuple[list[GraphEdge], list[set[int]]]:
        """採用ノード間の共起ペアを集計し、エッジと隣接情報を返す。"""
        # ペア共起回数
        pair: Counter[tuple[str, str]] = Counter()
        for tags in matched:
            present = sorted({t for t in tags if t in keep})
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    pair[(present[i], present[j])] += 1

        # 共起の強い順に、ノードあたり上限まで採用
        candidates = sorted(pair.items(), key=lambda kv: kv[1], reverse=True)
        per_node: dict[int, int] = {}
        kept: list[GraphEdge] = []
        for (a_tag, b_tag), w in candidates:
            if w < _MIN_EDGE_WEIGHT:
                continue
            a, b = node_index[a_tag], node_index[b_tag]
            if per_node.get(a, 0) >= max_edges_per_node and per_node.get(b, 0) >= max_edges_per_node:
                continue
            per_node[a] = per_node.get(a, 0) + 1
            per_node[b] = per_node.get(b, 0) + 1
            kept.append(GraphEdge(a=a, b=b, weight=w, norm=0.0))

        max_w = max((e.weight for e in kept), default=1)
        for e in kept:
            e.norm = e.weight / max_w

        adjacency: list[set[int]] = [set() for _ in range(node_count)]
        for e in kept:
            adjacency[e.a].add(e.b)
            adjacency[e.b].add(e.a)
        return kept, adjacency

    def _load_tags(self) -> dict[int, list[str]]:
        """未 reject タグを全ロードして {image_id: [tag, ...]} を返す。"""
        from sqlalchemy import select

        from lorairo.database.schema import Image, Tag

        result: dict[int, list[str]] = {}
        try:
            session = self._db.image_repo.get_session()
            with session:
                image_ids = [row[0] for row in session.execute(select(Image.id)).all()]
                for iid in image_ids:
                    result[iid] = []
                rows = session.execute(select(Tag.image_id, Tag.tag).where(Tag.rejected_at.is_(None))).all()
                for image_id, tag in rows:
                    if image_id in result:
                        result[image_id].append(tag.lower())
        except Exception as exc:
            logger.opt(exception=True).error(f"タグ読込エラー: {exc}")
            raise
        return result
