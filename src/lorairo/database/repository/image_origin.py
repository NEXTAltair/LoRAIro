"""画像の由来 (別プロジェクトからコピーした元) の読み取り Repository (ADR 0112, Issue #1661)。

由来の書き込みは、画像のコピーと同じトランザクションで行うため `ProjectTransferService` が
コピー先のセッションで直接行う。本 Repository は読み取りだけを持つ。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import select

from ..schema import ImageOrigin
from .base import BaseRepository

__all__ = ["ImageOriginRepository", "ImageOriginSnapshot"]


@dataclass(frozen=True)
class ImageOriginSnapshot:
    """画像 1 枚の由来 1 件。

    Attributes:
        image_id: この DB の `images.id`。
        source_project_name: コピー元のプロジェクト名。
        source_image_id: コピー元の DB での画像 ID。
        source_image_uuid: コピー元の画像の uuid。
        transfer_run_id: 取り込んだ操作 (`project_transfer_runs.id`)。
        created_at: 由来を記録した日時。
    """

    image_id: int
    source_project_name: str
    source_image_id: int
    source_image_uuid: str
    transfer_run_id: int | None
    created_at: datetime.datetime | None


class ImageOriginRepository(BaseRepository):
    """`image_origins` を読む Repository。"""

    def list_origins(self, image_ids: list[int]) -> dict[int, list[ImageOriginSnapshot]]:
        """画像ごとの由来を返す。

        Args:
            image_ids: `images.id` のリスト。

        Returns:
            画像 ID → 由来のリスト (記録順)。由来の無い画像は空のリスト。
        """
        result: dict[int, list[ImageOriginSnapshot]] = {image_id: [] for image_id in image_ids}
        if not image_ids:
            return result
        unique_ids = sorted(set(image_ids))
        with self.session_factory() as session:
            for offset in range(0, len(unique_ids), self.BATCH_CHUNK_SIZE):
                chunk = unique_ids[offset : offset + self.BATCH_CHUNK_SIZE]
                rows = session.execute(
                    select(ImageOrigin).where(ImageOrigin.image_id.in_(chunk)).order_by(ImageOrigin.id)
                ).scalars()
                for row in rows:
                    result[row.image_id].append(
                        ImageOriginSnapshot(
                            image_id=row.image_id,
                            source_project_name=row.source_project_name,
                            source_image_id=row.source_image_id,
                            source_image_uuid=row.source_image_uuid,
                            transfer_run_id=row.transfer_run_id,
                            created_at=row.created_at,
                        )
                    )
        return result
