"""add refinement_ignores table

タグ refinement リコメンドのローカル無視設定 (tag + reason_code 単位) を
永続化するテーブルを追加する (#931)。

Revision ID: 9c1d2e3f4a5b
Revises: d2e3f4a5b6c7
Create Date: 2026-06-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c1d2e3f4a5b"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create refinement_ignores table (#931)."""
    op.create_table(
        "refinement_ignores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tag", "reason_code", name="uix_refinement_ignore_tag_reason"),
    )
    op.create_index("ix_refinement_ignores_tag", "refinement_ignores", ["tag"], unique=False)


def downgrade() -> None:
    """Drop refinement_ignores table (#931)."""
    op.drop_index("ix_refinement_ignores_tag", table_name="refinement_ignores")
    op.drop_table("refinement_ignores")
