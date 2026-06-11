"""Add review-completed timestamp for image-level annotation triage.

Wireframes v11 Frame 5 · Results の accept (採用) 永続化。
``images.reviewed_at`` は NULL=未レビュー / 値あり=accept 済み。
タグ単位の ``rejected_at`` (e2f3a4b5c6d7) と対称な画像単位のレビュー状態。

Revision ID: d2e3f4a5b6c7
Revises: e2f3a4b5c6d7
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "images" in table_names:
        image_columns = {column["name"] for column in inspector.get_columns("images")}
        image_indexes = {index["name"] for index in inspector.get_indexes("images")}
        if "reviewed_at" not in image_columns:
            op.add_column("images", sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True))
        if "ix_images_reviewed_at" not in image_indexes:
            op.create_index("ix_images_reviewed_at", "images", ["reviewed_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "images" in table_names:
        image_columns = {column["name"] for column in inspector.get_columns("images")}
        image_indexes = {index["name"] for index in inspector.get_indexes("images")}
        if "ix_images_reviewed_at" in image_indexes:
            op.drop_index("ix_images_reviewed_at", table_name="images")
        if "reviewed_at" in image_columns:
            op.drop_column("images", "reviewed_at")
