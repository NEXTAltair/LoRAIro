"""Add image_filename_aliases table for duplicate skip tracking

Revision ID: b2f3a4c5d6e7
Revises: 8a994488196e
Create Date: 2026-03-17 18:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f3a4c5d6e7"
down_revision: str | None = "8a994488196e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_filename_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "image_id",
            sa.Integer(),
            sa.ForeignKey("images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stem", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("stem", name="uix_alias_stem"),
    )
    op.create_index(
        "ix_image_filename_aliases_stem",
        "image_filename_aliases",
        ["stem"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_filename_aliases_stem", table_name="image_filename_aliases")
    op.drop_table("image_filename_aliases")
