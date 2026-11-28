"""プロジェクト横断の画像コピーの記録と由来の表を追加する

ADR 0112 (Issue #1661): 別プロジェクトの画像はコピーで取り込み、コピー元のプロジェクトと
画像 ID / uuid を由来として記録する。DB をまたぐ外部キーは作らない。

- `project_transfer_runs`: 取り込み 1 回分 (コピー元 1 プロジェクトにつき 1 行)
- `image_origins`: 画像ごとの由来
- `dataset_version_origins`: 版ごとの由来 (プロジェクトの統合 #1660 で使う)

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-11-28
"""

import datetime
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[datetime.datetime]:
    return sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


# 由来の表に付ける index (表名, index 名, 列)。コピー元からの逆引きと、取り込みの記録ごとの参照に使う
_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("image_origins", "ix_image_origins_source", ("source_project_name", "source_image_uuid")),
    ("image_origins", "ix_image_origins_transfer_run_id", ("transfer_run_id",)),
    (
        "dataset_version_origins",
        "ix_dataset_version_origins_source",
        ("source_project_name", "source_version_id"),
    ),
    ("dataset_version_origins", "ix_dataset_version_origins_transfer_run_id", ("transfer_run_id",)),
)


def _create_missing_indexes() -> None:
    """`_INDEXES` のうち、まだ無い index を作る。"""
    inspector = sa.inspect(op.get_bind())
    for table, name, columns in _INDEXES:
        existing = {index["name"] for index in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, list(columns))


def upgrade() -> None:
    """Upgrade: 3 つの表を作る (既にある表は作らない)。"""
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "project_transfer_runs" not in tables:
        op.create_table(
            "project_transfer_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("source_project_name", sa.String(), nullable=False),
            sa.Column("source_project_path", sa.String(), nullable=False),
            sa.Column("copied_images", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("linked_images", sa.Integer(), nullable=False, server_default="0"),
            _created_at(),
            sa.CheckConstraint(
                "kind IN ('copy_images', 'merge_project')", name="ck_project_transfer_runs_kind"
            ),
        )

    if "image_origins" not in tables:
        op.create_table(
            "image_origins",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column(
                "transfer_run_id",
                sa.Integer(),
                sa.ForeignKey("project_transfer_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("source_project_name", sa.String(), nullable=False),
            sa.Column("source_image_id", sa.Integer(), nullable=False),
            sa.Column("source_image_uuid", sa.String(), nullable=False),
            _created_at(),
            sa.UniqueConstraint(
                "image_id",
                "source_project_name",
                "source_image_uuid",
                name="uix_image_origins_image_source",
            ),
        )

    if "dataset_version_origins" not in tables:
        op.create_table(
            "dataset_version_origins",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "version_id",
                sa.Integer(),
                sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "transfer_run_id",
                sa.Integer(),
                sa.ForeignKey("project_transfer_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("source_project_name", sa.String(), nullable=False),
            sa.Column("source_dataset_name", sa.String(), nullable=False),
            sa.Column("source_version_id", sa.Integer(), nullable=False),
            sa.Column("source_version_name", sa.String(), nullable=False),
            _created_at(),
            sa.UniqueConstraint(
                "version_id",
                "source_project_name",
                "source_version_id",
                name="uix_dataset_version_origins_version_source",
            ),
        )

    _create_missing_indexes()


def downgrade() -> None:
    """Downgrade: 3 つの表を削除する (参照する側から順に)。"""
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for name in ("dataset_version_origins", "image_origins", "project_transfer_runs"):
        if name in tables:
            op.drop_table(name)
