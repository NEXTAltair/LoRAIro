"""キーワード連動の共起タグクラウドサービス。

任意のキーワード（部分一致）でマッチした画像群の共起タグを頻度集計し、
タグクラウド表示用のウェイト付きエントリを返す。クリックによる AND ドリル
ダウン絞り込みに対応する。重量 ML 依存なし（標準ライブラリのみ）。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager

# クラウドに表示するタグ数の既定上限
_DEFAULT_TOP_N = 80


@dataclass
class TagWeight:
    """タグクラウドの1エントリ。"""

    tag: str
    count: int  # 該当画像群での出現数
    weight: float  # 0.0..1.0 正規化済み（フォントサイズ用）


@dataclass
class CloudResult:
    """`TagCloudService.build_cloud` の返り値。"""

    entries: list[TagWeight]
    matched_images: int
    total_images: int


class TagCloudService:
    """共起タグクラウドを構築する。

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

    def build_cloud(
        self,
        keyword: str,
        selected_tags: list[str] | None = None,
        top_n: int = _DEFAULT_TOP_N,
    ) -> CloudResult:
        """キーワードと絞り込みタグから共起タグクラウドを構築する。

        画像が対象となる条件:
            - `keyword` を部分文字列に含むタグを1つ以上持つ
            - `selected_tags` のタグを全て持つ（AND 絞り込み）

        Args:
            keyword: 部分一致検索キーワード。空文字なら空クラウドを返す。
            selected_tags: ドリルダウンで追加された完全一致タグのリスト。
            top_n: クラウドに含めるタグ数の上限。

        Returns:
            CloudResult — ウェイト付きタグエントリと該当件数。
        """
        image_tags = self._get_image_tags()
        total = len(image_tags)

        keyword_norm = keyword.strip().lower()
        selected = [t.strip().lower() for t in (selected_tags or []) if t.strip()]
        selected_set = set(selected)

        if not keyword_norm:
            return CloudResult(entries=[], matched_images=0, total_images=total)

        # 条件を満たす画像のタグを集計
        counter: Counter[str] = Counter()
        matched = 0
        for tags in image_tags.values():
            tag_set = set(tags)
            if selected_set and not selected_set.issubset(tag_set):
                continue
            if not any(keyword_norm in tag for tag in tags):
                continue
            matched += 1
            counter.update(tags)

        # 絞り込みに使ったタグはクラウドから除外
        for sel in selected_set:
            counter.pop(sel, None)

        entries = self._build_entries(counter, top_n)
        logger.debug(
            f"TagCloud: keyword='{keyword_norm}' selected={selected} "
            f"matched={matched}/{total} entries={len(entries)}"
        )
        return CloudResult(entries=entries, matched_images=matched, total_images=total)

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

    def _build_entries(self, counter: Counter[str], top_n: int) -> list[TagWeight]:
        """頻度 Counter を sqrt 正規化したウェイト付きエントリへ変換する。"""
        if not counter:
            return []
        top = counter.most_common(top_n)
        counts = [c for _, c in top]
        # sqrt スケールで歪みを抑えた min-max 正規化
        sqrt_counts = [math.sqrt(c) for c in counts]
        s_min = min(sqrt_counts)
        s_max = max(sqrt_counts)
        span = s_max - s_min
        entries: list[TagWeight] = []
        for (tag, count), s in zip(top, sqrt_counts, strict=True):
            weight = 1.0 if span == 0 else (s - s_min) / span
            entries.append(TagWeight(tag=tag, count=count, weight=weight))
        return entries

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
            logger.error(f"タグ読込エラー: {exc}", exc_info=True)
            raise
        return result
