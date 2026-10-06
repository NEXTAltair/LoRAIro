"""Add latest per-image annotation review results.

Revision ID: d4e5f6a7b8c9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annotation_review_results",
        sa.Column(
            "image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("warning_threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_annotation_review_results_checked_at", "annotation_review_results", ["checked_at"])


def downgrade() -> None:
    op.drop_index("ix_annotation_review_results_checked_at", table_name="annotation_review_results")
    op.drop_table("annotation_review_results")
