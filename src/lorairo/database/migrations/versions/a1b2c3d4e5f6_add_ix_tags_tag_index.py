"""Add index ix_tags_tag on tags.tag column for LIKE search optimization

Issue #176 (E-part1): tags.tag カラムに検索インデックスを追加。
LIKE句によるタグ検索が全テーブルスキャンになるボトルネックを解消する。

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-04-24
"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tags_tag", "tags", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_tags_tag", table_name="tags")
