"""Add Kohya-ss dataset tables.

Issue #1404: Kohya-ss 学習データセットを版・フォルダ・学習テキストとして取り込み、
同じ形で書き出すためのテーブルを追加する。
- datasets / dataset_versions / dataset_folders / dataset_folder_images
- dataset_learning_texts (フォルダごとの学習テキスト。画像直下の tags には書かない)
- training_configs (学習設定の元の中身と正規化したもの)

設計書: docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-06
"""

import datetime
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at_column() -> sa.Column[datetime.datetime]:
    """created_at 列を作る (テーブルごとに別インスタンスが必要)。"""
    return sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    """Upgrade: データセット関連の 6 テーブルを作成する。"""
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        _created_at_column(),
    )
    op.create_index("ix_datasets_name", "datasets", ["name"], unique=True)

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "parent_version_id",
            sa.Integer(),
            sa.ForeignKey("dataset_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        _created_at_column(),
        sa.UniqueConstraint("dataset_id", "name", name="uix_dataset_versions_dataset_name"),
    )

    op.create_table(
        "dataset_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dir_name", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("num_repeats", sa.Integer(), nullable=False),
        sa.Column("trigger_word", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("version_id", "dir_name", name="uix_dataset_folders_version_dir"),
    )

    op.create_table(
        "dataset_folder_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "folder_id",
            sa.Integer(),
            sa.ForeignKey("dataset_folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_stem", sa.String(), nullable=False),
        sa.UniqueConstraint("folder_id", "file_stem", name="uix_dataset_folder_images_folder_stem"),
    )
    op.create_index("ix_dataset_folder_images_image_id", "dataset_folder_images", ["image_id"])

    op.create_table(
        "dataset_learning_texts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "folder_image_id",
            sa.Integer(),
            sa.ForeignKey("dataset_folder_images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extension", sa.String(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("elements_json", sa.Text(), nullable=False),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default="0"),
        sa.UniqueConstraint("folder_image_id", "extension", name="uix_dataset_learning_texts_image_ext"),
    )

    op.create_table(
        "training_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("dataset_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_file_name", sa.String(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("normalized_json", sa.Text(), nullable=False),
        sa.Column("unmapped_json", sa.Text(), nullable=False),
        sa.Column("target_script", sa.String(), nullable=True),
        sa.Column("output_name", sa.String(), nullable=True),
        sa.Column("base_model", sa.String(), nullable=True),
        sa.Column("resolution", sa.String(), nullable=True),
        sa.Column("network_dim", sa.Integer(), nullable=True),
        sa.Column("network_alpha", sa.Float(), nullable=True),
        sa.Column("learning_rate", sa.Float(), nullable=True),
        _created_at_column(),
    )


def downgrade() -> None:
    """Downgrade: データセット関連の 6 テーブルを依存の逆順で削除する。"""
    op.drop_table("training_configs")
    op.drop_table("dataset_learning_texts")
    op.drop_index("ix_dataset_folder_images_image_id", table_name="dataset_folder_images")
    op.drop_table("dataset_folder_images")
    op.drop_table("dataset_folders")
    op.drop_table("dataset_versions")
    op.drop_index("ix_datasets_name", table_name="datasets")
    op.drop_table("datasets")
