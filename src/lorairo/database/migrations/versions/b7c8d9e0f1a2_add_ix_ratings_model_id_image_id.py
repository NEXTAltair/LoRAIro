"""Add composite index ix_ratings_model_id_image_id on ratings(model_id, image_id)

Issue #558: AIレーティングフィルタ (model_id IN (...) + GROUP BY image_id) が
ratings テーブルを model_id でスキャンしていたボトルネックを解消する。
既存の ix_ratings_image_id は維持する。

Revision ID: b7c8d9e0f1a2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-30
"""

from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_ratings_model_id_image_id", "ratings", ["model_id", "image_id"])


def downgrade() -> None:  # pragma: no cover
    op.drop_index("ix_ratings_model_id_image_id", table_name="ratings")
