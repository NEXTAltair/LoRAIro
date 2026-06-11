"""Add soft-reject timestamps for tag and caption annotations.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "tags" in table_names:
        tag_columns = {column["name"] for column in inspector.get_columns("tags")}
        tag_indexes = {index["name"] for index in inspector.get_indexes("tags")}
        if "rejected_at" not in tag_columns:
            op.add_column("tags", sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True))
        if "ix_tags_rejected_at" not in tag_indexes:
            op.create_index("ix_tags_rejected_at", "tags", ["rejected_at"])

    if "captions" in table_names:
        caption_columns = {column["name"] for column in inspector.get_columns("captions")}
        caption_indexes = {index["name"] for index in inspector.get_indexes("captions")}
        if "rejected_at" not in caption_columns:
            op.add_column("captions", sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True))
        if "ix_captions_rejected_at" not in caption_indexes:
            op.create_index("ix_captions_rejected_at", "captions", ["rejected_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "captions" in table_names:
        caption_columns = {column["name"] for column in inspector.get_columns("captions")}
        caption_indexes = {index["name"] for index in inspector.get_indexes("captions")}
        if "ix_captions_rejected_at" in caption_indexes:
            op.drop_index("ix_captions_rejected_at", table_name="captions")
        if "rejected_at" in caption_columns:
            op.drop_column("captions", "rejected_at")

    if "tags" in table_names:
        tag_columns = {column["name"] for column in inspector.get_columns("tags")}
        tag_indexes = {index["name"] for index in inspector.get_indexes("tags")}
        if "ix_tags_rejected_at" in tag_indexes:
            op.drop_index("ix_tags_rejected_at", table_name="tags")
        if "rejected_at" in tag_columns:
            op.drop_column("tags", "rejected_at")
