"""Drop ErrorRecord.retry_count column (ADR 0033 Decision 8).

ADR 0033 Decision 8 (2026-05-23 訂正版) に従い、`error_records.retry_count`
カラムを削除する。当初は `resolved_at` も削除対象だったが、Error Log Viewer /
Error Detail Dialog の手動「解決済みマーク」UX が live のため削除対象外。

`retry_count` は「LoRAIro 側で retry 管理する」設計仮説の遺物で、現状は
`retry_count=0` 固定 INSERT のみで参照箇所が存在しない。Decision 2 で
「LoRAIro 側で自動 retry はしない」と確定したため、永続的に未使用。

Downgrade: カラムを INTEGER DEFAULT 0 NOT NULL で再追加する。過去データの
復元はできない (delete 時点で値は 0 のみだったため、復元する意味もない)。

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return any(col["name"] == column for col in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("error_records", "retry_count"):
        return
    with op.batch_alter_table("error_records") as batch_op:
        batch_op.drop_column("retry_count")


def downgrade() -> None:
    # テーブル不在 or カラムが既に存在する場合は no-op
    if not _table_exists("error_records") or _has_column("error_records", "retry_count"):
        return
    with op.batch_alter_table("error_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
