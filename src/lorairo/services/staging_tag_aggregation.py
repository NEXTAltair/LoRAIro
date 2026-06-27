"""ステージング集合内のタグを集計するサービス（Issue #945）。

左ペイン StagingTagPanel (#947) が消費する Qt-free サービス。
デザインの ``aggregateTags`` / ``imagesWithTag`` 相当の契約 (ADR 0080 S0)。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


@dataclass
class TagCount:
    """タグの出現数と手動編集フラグを保持するデータクラス。

    Attributes:
        tag: タグ文字列。
        count: ステージング集合内でこのタグを持つ画像数。
        manual: ステージング集合内のいずれか1画像で ``is_edited_manually=True`` なら True。
    """

    tag: str
    count: int
    manual: bool


class StagingTagAggregationService:
    """ステージング集合のタグを集計するサービス。

    `image_ids` で指定した画像群の有効タグ（soft-reject 済みを除く）を
    バルク取得し、タグごとの出現数と手動編集フラグを集計して返す。
    N+1 クエリを避けるため、1回の一括 SQL クエリのみで完結する。
    """

    def __init__(self, db_manager: ImageDatabaseManager) -> None:
        self._db = db_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def aggregate(self, image_ids: list[int]) -> list[TagCount]:
        """ステージング集合のタグを集計する。

        指定画像群の有効タグ（``rejected_at is None``）を一括取得し、
        タグごとの件数と手動編集フラグを集計して返す。

        ソート順: 件数降順、同数の場合はタグ名昇順（安定ソート）。

        Args:
            image_ids: 対象画像 ID のリスト。

        Returns:
            タグ件数リスト。件数降順・タグ名昇順でソート済み。
        """
        if not image_ids:
            return []

        rows = self._load_tags_for_images(image_ids)

        # tag -> (count, any_manual) を集計
        count_map: dict[str, int] = defaultdict(int)
        manual_map: dict[str, bool] = defaultdict(bool)

        for _image_id, tag, is_manual in rows:
            count_map[tag] += 1
            if is_manual:
                manual_map[tag] = True

        result = [
            TagCount(tag=tag, count=count, manual=manual_map[tag]) for tag, count in count_map.items()
        ]

        # 件数降順、同数はタグ名昇順
        result.sort(key=lambda tc: (-tc.count, tc.tag))

        logger.debug(f"StagingTagAggregationService.aggregate: images={len(image_ids)}, tags={len(result)}")
        return result

    def images_with_tag(self, image_ids: list[int], tag: str) -> list[int]:
        """指定タグを有効（非 reject）で持つ画像 ID を返す。

        Args:
            image_ids: 対象画像 ID のリスト。
            tag: 検索対象のタグ文字列。

        Returns:
            そのタグを持つ画像 ID のリスト（重複なし）。
        """
        if not image_ids:
            return []

        rows = self._load_tags_for_images(image_ids)

        # 指定タグを持つ画像 ID を重複なしで収集
        matching_ids: set[int] = set()
        for image_id, row_tag, _is_manual in rows:
            if row_tag == tag:
                matching_ids.add(image_id)

        return list(matching_ids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_tags_for_images(
        self,
        image_ids: list[int],
    ) -> list[tuple[int, str, bool | None]]:
        """指定画像の有効タグを一括取得する（N+1 回避のバルク SQL）。

        ``rejected_at IS NULL`` の行のみを対象とし、soft-reject 済みタグは除外する。
        これは ``_resolve_export_tags``（DatasetExportService）の ``rejected_at`` 除外ロジックと整合する。

        Args:
            image_ids: 対象画像 ID のリスト。空リストの場合は空リストを返す。

        Returns:
            ``(image_id, tag, is_edited_manually)`` のリスト。
            ``is_edited_manually`` は NULL を含む場合がある。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
        """
        if not image_ids:
            return []

        from sqlalchemy import select

        from lorairo.database.schema import Tag

        session = self._db.image_repo.get_session()
        with session:
            rows = session.execute(
                select(Tag.image_id, Tag.tag, Tag.is_edited_manually).where(
                    Tag.image_id.in_(image_ids),
                    Tag.rejected_at.is_(None),
                )
            ).all()
        return [(row.image_id, row.tag, row.is_edited_manually) for row in rows if row.image_id is not None]
