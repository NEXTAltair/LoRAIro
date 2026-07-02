"""tags を (image_id, model_id, tag) 単位で一意化する (Issue #1065)。

再アノテーションのたびに同一 (画像, モデル, タグ) の行が蓄積して DB が線形に
膨張していた。既存の重複行を畳んでから UNIQUE インデックスを追加する。

畳み方 (ユーザー確認済みポリシー):
- 最古の行 (MIN(id)) を残す。created_at は「初回付与日時」の意味を保つ
- updated_at はグループ内の最新付与日時 (MAX(COALESCE(updated_at, created_at)))
- soft-reject はユーザー判断を優先して維持する: グループ内に rejected 行が
  あれば、その最新の rejected_at / reject_reason を残す行へ集約する
- is_edited_manually はグループ内に True があれば True
- confidence_score は最新行 (MAX(id)) の値を採用する

異なるモデルが同じタグを付けた場合は従来どおり別行 (provenance 維持)。
NULL model_id 同士は GROUP BY では畳まれるが、SQLite の UNIQUE インデックスは
NULL を別値として扱うため将来の NULL 同士の重複は制約では防げない
(通常経路は model_id 必須のため実害なし)。

Revision ID: b8c9d0e1f2a3
Revises: f6a7b8c9d0e1
Create Date: 2026-07-02
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNIQUE_INDEX_NAME = "uq_tags_image_model_tag"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tags" not in set(inspector.get_table_names()):
        return

    # 本番 schema の列が揃っていない場合 (旧 migration テストの縮約 seed 等) は
    # 畳み・index とも skip する (実 DB は initial schema 由来で必ず揃う)
    columns = {column["name"] for column in inspector.get_columns("tags")}
    required = {
        "image_id",
        "model_id",
        "tag",
        "created_at",
        "updated_at",
        "is_edited_manually",
        "confidence_score",
        "rejected_at",
        "reject_reason",
    }
    if not required <= columns:
        logger.info("tags unique migration skipped: required columns missing (reduced test schema)")
        return

    # 1) 重複グループを検出する (NULL image_id / model_id も GROUP BY で同値扱い)
    duplicate_groups = bind.execute(
        sa.text(
            """
            SELECT MIN(id) AS keep_id, COUNT(*) AS cnt,
                   MAX(COALESCE(updated_at, created_at)) AS latest_ts,
                   MAX(CASE WHEN is_edited_manually = 1 THEN 1 ELSE 0 END) AS any_manual
            FROM tags
            GROUP BY image_id, model_id, tag
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    collapsed_rows = 0
    for group in duplicate_groups:
        keep_id = group.keep_id
        # 残す行と同じ (image_id, model_id, tag) の兄弟行を取得する
        siblings = bind.execute(
            sa.text(
                """
                SELECT id, rejected_at, reject_reason, confidence_score
                FROM tags
                WHERE (image_id IS (SELECT image_id FROM tags WHERE id = :keep_id))
                  AND (model_id IS (SELECT model_id FROM tags WHERE id = :keep_id))
                  AND (tag = (SELECT tag FROM tags WHERE id = :keep_id))
                ORDER BY id
                """
            ).bindparams(keep_id=keep_id)
        ).fetchall()

        # soft-reject 維持: グループ内の最新 rejected_at とその reason を集約する
        rejected = [s for s in siblings if s.rejected_at is not None]
        latest_reject = max(rejected, key=lambda s: str(s.rejected_at)) if rejected else None
        # confidence は最新行 (MAX(id)) の値
        latest_confidence = siblings[-1].confidence_score

        bind.execute(
            sa.text(
                """
                UPDATE tags
                SET updated_at = :latest_ts,
                    rejected_at = :rejected_at,
                    reject_reason = :reject_reason,
                    is_edited_manually = CASE WHEN :any_manual = 1 THEN 1 ELSE is_edited_manually END,
                    confidence_score = :confidence
                WHERE id = :keep_id
                """
            ).bindparams(
                latest_ts=group.latest_ts,
                rejected_at=latest_reject.rejected_at if latest_reject else None,
                reject_reason=latest_reject.reject_reason if latest_reject else None,
                any_manual=group.any_manual,
                confidence=latest_confidence,
                keep_id=keep_id,
            )
        )
        delete_ids = [s.id for s in siblings if s.id != keep_id]
        bind.execute(
            sa.text("DELETE FROM tags WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": delete_ids},
        )
        collapsed_rows += len(delete_ids)

    # 畳み件数の記録 (Issue #1065: 畳んだ件数をログで残す)
    logger.info(
        f"tags duplicate collapse (Issue #1065): "
        f"groups={len(duplicate_groups)}, deleted_rows={collapsed_rows}"
    )

    # 2) UNIQUE インデックスを追加する
    existing_indexes = {index["name"] for index in inspector.get_indexes("tags")}
    if _UNIQUE_INDEX_NAME not in existing_indexes:
        op.create_index(
            _UNIQUE_INDEX_NAME,
            "tags",
            ["image_id", "model_id", "tag"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tags" not in set(inspector.get_table_names()):
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes("tags")}
    if _UNIQUE_INDEX_NAME in existing_indexes:
        op.drop_index(_UNIQUE_INDEX_NAME, table_name="tags")
    # 畳んだ重複行は復元できない (非可逆)
