"""Add reject_reason to tag and caption annotations (Issue #1003).

無効化 / 除外 / 置換の soft-reject 種別を DB に永続化するための ``reject_reason``
列を tags / captions に追加する。既存の ``rejected_at`` 非 NULL 行は現状 reload 後に
全て打ち消し線 (= 無効化相当) で表示されるため、見た目を変えないよう初期値
``'not_needed'`` で backfill する。``rejected_at IS NULL`` の行は ``reject_reason`` も
NULL のまま (採用中)。

Revision ID: f6a7b8c9d0e1
Revises: 9c1d2e3f4a5b
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "9c1d2e3f4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 既存 rejected_at 非 NULL 行の backfill 値 (schema.REJECT_REASON_NOT_NEEDED と一致)。
_BACKFILL_REASON = "not_needed"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    for table in ("tags", "captions"):
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "reject_reason" not in columns:
            op.add_column(table, sa.Column("reject_reason", sa.String(), nullable=True))
            # 見た目不変のため、既存 soft-reject 行を無効化 (not_needed) として backfill する。
            op.execute(
                sa.text(
                    f"UPDATE {table} SET reject_reason = :reason "
                    "WHERE rejected_at IS NOT NULL AND reject_reason IS NULL"
                ).bindparams(reason=_BACKFILL_REASON)
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    for table in ("captions", "tags"):
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "reject_reason" in columns:
            op.drop_column(table, "reject_reason")
