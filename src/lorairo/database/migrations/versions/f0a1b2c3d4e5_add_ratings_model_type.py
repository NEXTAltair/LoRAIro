"""Add ratings model type

Revision ID: f0a1b2c3d4e5
Revises: a7b8c9d0e1f2
Create Date: 2026-05-22

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ensure the canonical `ratings` model type exists."""
    inspector = inspect(op.get_bind())
    if not inspector.has_table("model_types"):
        return

    op.execute(
        """
        INSERT INTO model_types (name)
        SELECT 'ratings'
        WHERE NOT EXISTS (
            SELECT 1 FROM model_types WHERE name = 'ratings'
        )
        """
    )


def downgrade() -> None:
    """Remove the `ratings` model type and its associations."""
    inspector = inspect(op.get_bind())
    if not inspector.has_table("model_types"):
        return

    if inspector.has_table("model_function_associations"):
        op.execute(
            """
            DELETE FROM model_function_associations
            WHERE type_id IN (
                SELECT id FROM model_types WHERE name = 'ratings'
            )
            """
        )
    op.execute("DELETE FROM model_types WHERE name = 'ratings'")
