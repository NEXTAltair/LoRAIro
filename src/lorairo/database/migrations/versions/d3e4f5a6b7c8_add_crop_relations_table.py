"""Add crop_relations table for crop parent-child relations

Revision ID: d3e4f5a6b7c8
Revises: c9d0e1f2a3b4
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crop_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "parent_image_id",
            sa.Integer(),
            sa.ForeignKey("images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_image_id",
            sa.Integer(),
            sa.ForeignKey("images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("child_image_id", name="uix_crop_relations_child"),
    )
    op.create_index(
        "ix_crop_relations_parent_image_id",
        "crop_relations",
        ["parent_image_id"],
    )


def downgrade() -> None:  # pragma: no cover
    op.drop_index("ix_crop_relations_parent_image_id", table_name="crop_relations")
    op.drop_table("crop_relations")
