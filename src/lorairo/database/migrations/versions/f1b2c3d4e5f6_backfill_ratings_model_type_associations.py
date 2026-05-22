"""Backfill ratings model type associations

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-22

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "f1b2c3d4e5f6"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RATING_CAPABLE_MODEL_NAMES = (
    "idolsankaku-eva02-large-tagger-v1",
    "idolsankaku-swinv2-tagger-v1",
    "Z3D-E621-Convnext",
    "anime_rating_mobilenetv3_sce_dist",
    "anime_rating_caformer_s36_plus",
    "camie_tagger_initial",
    "wd-v1-4-convnext-tagger-v2",
    "wd-v1-4-convnextv2-tagger-v2",
    "wd-v1-4-moat-tagger-v2",
    "wd-v1-4-swinv2-tagger-v2",
    "wd-vit-tagger-v3",
    "wd-convnext-tagger-v3",
    "wd-swinv2-tagger-v3",
    "wd-vit-large-tagger-v3",
    "wd-eva02-large-tagger-v3",
)


def _quoted_model_names() -> str:
    return ", ".join(f"'{name}'" for name in RATING_CAPABLE_MODEL_NAMES)


def upgrade() -> None:
    """Attach the `ratings` type to known rating-capable local models."""
    inspector = inspect(op.get_bind())
    required_tables = {"models", "model_types", "model_function_associations"}
    if not required_tables.issubset(set(inspector.get_table_names())):
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
    op.execute(
        f"""
        INSERT INTO model_function_associations (model_id, type_id)
        SELECT m.id, mt.id
        FROM models AS m
        JOIN model_types AS mt ON mt.name = 'ratings'
        WHERE m.name IN ({_quoted_model_names()})
          AND NOT EXISTS (
              SELECT 1
              FROM model_function_associations AS existing
              WHERE existing.model_id = m.id
                AND existing.type_id = mt.id
          )
        """
    )


def downgrade() -> None:
    """Leave rating associations intact on downgrade.

    This data migration cannot distinguish rows inserted here from valid
    associations created by a prior manual backfill or model resync. Preserve
    data rather than deleting potentially legitimate model capabilities.
    """
