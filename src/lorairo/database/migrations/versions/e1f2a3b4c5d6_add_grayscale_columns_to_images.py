"""Add is_grayscale_like and colorfulness_score to images

Revision ID: e1f2a3b4c5d6
Revises: c8d9e0f1a2b3
Create Date: 2026-06-05 00:00:00.000000

Issue #631 / ADR 0061: 登録パイプライン再設計の基盤として、画像の内容ベースで
カラー / グレースケール相当を区別するための 2 カラムを ``images`` に追加する。

Backfill 方針:
    既存の行は両カラムとも NULL のままにする (本 migration では全件再計算しない)。
    判定は画像内容のサンプリングを伴うため、起動時の一括 backfill はコストが高く
    UX を損なう。NULL を「未判定」として扱い、再アノテーションや別版分類など
    判定が必要になった経路で遅延 backfill する (ADR 0061 参照)。新規登録は
    ``FileSystemManager.get_image_info`` が値を埋めるため NULL にならない。
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_grayscale_like and colorfulness_score columns to images table."""
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_grayscale_like", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("colorfulness_score", sa.Float(), nullable=True))


def downgrade() -> None:  # pragma: no cover
    """Remove is_grayscale_like and colorfulness_score columns from images table."""
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_column("colorfulness_score")
        batch_op.drop_column("is_grayscale_like")
