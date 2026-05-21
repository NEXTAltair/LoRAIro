"""Add score_labels table for canonical scorer categorical labels

Issue #281 (ADR 0027): image-annotator-lib ADR 0002 で導入された
``UnifiedAnnotationResult.score_labels`` field を DB に永続化するため、
``score_labels`` テーブルを新規追加する。

aesthetic_shadow_v1/v2 / cafe_aesthetic 等の canonical scorer が返す
categorical label (例: "very aesthetic", "aesthetic", "displeasing",
"not_aesthetic") を、数値 ``Score`` テーブルとは独立に保持する。

詳細は docs/decisions/0027-score-labels-db-storage.md を参照。

Revision ID: a7b8c9d0e1f2
Revises: e3f4a5b6c7d8
Create Date: 2026-05-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade: score_labels テーブルを追加する。"""
    inspector = inspect(op.get_bind())

    # create_all() used to run before Alembic on project DB open. If that already
    # created score_labels while alembic_version stayed old, make this migration
    # converge instead of failing with "table already exists".
    if not inspector.has_table("score_labels"):
        op.create_table(
            "score_labels",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "image_id",
                sa.Integer(),
                sa.ForeignKey("images.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "model_id",
                sa.Integer(),
                sa.ForeignKey("models.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("is_edited_manually", sa.Boolean(), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    indexes = {index["name"] for index in inspector.get_indexes("score_labels")}
    if "ix_score_labels_image_id" not in indexes:
        op.create_index("ix_score_labels_image_id", "score_labels", ["image_id"])


def downgrade() -> None:
    """Downgrade: score_labels テーブルを削除する。"""
    op.drop_index("ix_score_labels_image_id", table_name="score_labels")
    op.drop_table("score_labels")
