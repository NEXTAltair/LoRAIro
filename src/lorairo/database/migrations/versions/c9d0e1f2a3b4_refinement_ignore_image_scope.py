"""refinement_ignores に画像スコープ (image_id) を追加する (Issue #1053)。

「この理由を無視」はワンクリック操作なのに (tag, reason_code) 単位で全画像・恒久に
効いていた。nullable な image_id 列を追加してスコープ選択式にする:

- ``image_id IS NULL`` = 全画像 (既存行はそのまま全画像扱い)
- ``image_id`` あり = その画像限定 (画像削除時は CASCADE で削除)

一意性は旧 UNIQUE(tag, reason_code) を落とし、部分 UNIQUE インデックス2本に分ける
(SQLite の UNIQUE は NULL を別値扱いするため、全画像スコープの重複を単一の複合
UNIQUE では防げない):

- ``uq_refinement_ignores_global``: (tag, reason_code) WHERE image_id IS NULL
- ``uq_refinement_ignores_image``: (tag, reason_code, image_id) WHERE image_id IS NOT NULL

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-02
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_UNIQUE = "uix_refinement_ignore_tag_reason"
_GLOBAL_INDEX = "uq_refinement_ignores_global"
_IMAGE_INDEX = "uq_refinement_ignores_image"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refinement_ignores" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("refinement_ignores")}
    if "image_id" not in columns:
        # SQLite は制約変更にテーブル再作成が要るため batch モードで行う。
        # 旧 UNIQUE(tag, reason_code) はここで落とす (部分 UNIQUE インデックスへ移行)。
        with op.batch_alter_table("refinement_ignores") as batch_op:
            batch_op.add_column(sa.Column("image_id", sa.Integer(), nullable=True))
            try:
                batch_op.drop_constraint(_OLD_UNIQUE, type_="unique")
            except ValueError:
                # 縮約テスト schema 等で旧制約が無い場合はそのまま進む
                logger.info("old unique constraint not found; skipped dropping")
            batch_op.create_foreign_key(
                "fk_refinement_ignores_image_id",
                "images",
                ["image_id"],
                ["id"],
                ondelete="CASCADE",
            )

    existing_indexes = {index["name"] for index in inspector.get_indexes("refinement_ignores")}
    if _GLOBAL_INDEX not in existing_indexes:
        op.create_index(
            _GLOBAL_INDEX,
            "refinement_ignores",
            ["tag", "reason_code"],
            unique=True,
            sqlite_where=sa.text("image_id IS NULL"),
        )
    if _IMAGE_INDEX not in existing_indexes:
        op.create_index(
            _IMAGE_INDEX,
            "refinement_ignores",
            ["tag", "reason_code", "image_id"],
            unique=True,
            sqlite_where=sa.text("image_id IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refinement_ignores" not in set(inspector.get_table_names()):
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes("refinement_ignores")}
    if _GLOBAL_INDEX in existing_indexes:
        op.drop_index(_GLOBAL_INDEX, table_name="refinement_ignores")
    if _IMAGE_INDEX in existing_indexes:
        op.drop_index(_IMAGE_INDEX, table_name="refinement_ignores")
    # 画像限定スコープの行は旧 schema では表現できないため削除する (非可逆)
    op.execute(sa.text("DELETE FROM refinement_ignores WHERE image_id IS NOT NULL"))
    with op.batch_alter_table("refinement_ignores") as batch_op:
        batch_op.drop_column("image_id")
        batch_op.create_unique_constraint(_OLD_UNIQUE, ["tag", "reason_code"])
