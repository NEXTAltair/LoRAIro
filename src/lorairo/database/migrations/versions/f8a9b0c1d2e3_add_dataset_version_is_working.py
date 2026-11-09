"""Add is_working to dataset_versions for in-app working version editing.

Issue #1486 / ADR 0098: LoRAIro 内で版を編集して確定する「作業中の版」を
`dataset_versions.is_working` で表す。取り込み済み・確定済みの版は `False` (既定値) で
後から書き換えず、未確定の作業中の版だけ `True` にして編集・破棄・確定を許可する。

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade: dataset_versions に is_working 列を追加する。"""
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "dataset_versions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("dataset_versions")}
        if "is_working" not in columns:
            op.add_column(
                "dataset_versions",
                sa.Column("is_working", sa.Boolean(), nullable=False, server_default="0"),
            )


def downgrade() -> None:
    """Downgrade: dataset_versions から is_working 列を削除する。"""
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "dataset_versions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("dataset_versions")}
        if "is_working" in columns:
            op.drop_column("dataset_versions", "is_working")
