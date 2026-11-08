"""Add generation metadata tables.

Issue #1481 / ADR 0105: 画像に埋め込まれた生成情報の原データと解析結果を分けて保存する。
- generation_metadata_sources: PNG テキストチャンク / EXIF UserComment の原データ (整形しない)
- generation_metadata: 解析結果 (1 画像 1 行、解析状態つき)

既存の行は変更しない。既存画像は未解析 (行なし) のままになる。

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade: 生成メタデータの 2 テーブルを作成する。"""
    op.create_table(
        "generation_metadata_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "image_id", "source_kind", "source_key", name="uix_generation_metadata_sources_image_kind_key"
        ),
    )

    op.create_table(
        "generation_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=True),
        sa.Column("parser_name", sa.String(), nullable=False),
        sa.Column("parser_version", sa.String(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=True),
        sa.Column("positive_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("model_hash", sa.String(), nullable=True),
        sa.Column("seed", sa.String(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("sampler", sa.String(), nullable=True),
        sa.Column("cfg_scale", sa.Float(), nullable=True),
        sa.Column("loras_json", sa.Text(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("analyzed_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("image_id", name="uix_generation_metadata_image"),
        sa.CheckConstraint(
            "status IN ('parsed', 'partial', 'unsupported', 'no_metadata', 'failed')",
            name="ck_generation_metadata_status",
        ),
    )
    op.create_index("ix_generation_metadata_tool", "generation_metadata", ["tool"])


def downgrade() -> None:
    """Downgrade: 生成メタデータの 2 テーブルを削除する。"""
    op.drop_index("ix_generation_metadata_tool", table_name="generation_metadata")
    op.drop_table("generation_metadata")
    op.drop_table("generation_metadata_sources")
