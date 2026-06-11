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
    op.add_column("tags", sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("captions", sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index("ix_tags_rejected_at", "tags", ["rejected_at"])
    op.create_index("ix_captions_rejected_at", "captions", ["rejected_at"])


def downgrade() -> None:
    op.drop_index("ix_captions_rejected_at", table_name="captions")
    op.drop_index("ix_tags_rejected_at", table_name="tags")
    op.drop_column("captions", "rejected_at")
    op.drop_column("tags", "rejected_at")
