"""Normalize annotation outcome error_type values

Issue #599 changes WebAPI annotation outcome routing from exception-name
prefixes to structured iam-lib error_code strings. Existing unresolved
refusal rows must be normalized so the send-before filter remains code-only.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | None = None
depends_on: str | None = None


def _error_records_exists() -> bool:
    bind = op.get_bind()
    return "error_records" in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _error_records_exists():
        return
    op.execute(
        """
        UPDATE error_records
        SET error_type = 'SAFETY_REFUSAL'
        WHERE operation_type = 'annotation'
          AND error_type = 'SafetyRefusalError'
        """
    )
    op.execute(
        """
        UPDATE error_records
        SET error_type = 'CONTENT_POLICY_REFUSAL'
        WHERE operation_type = 'annotation'
          AND error_type = 'ContentPolicyRefusalError'
        """
    )


def downgrade() -> None:
    if not _error_records_exists():
        return
    op.execute(
        """
        UPDATE error_records
        SET error_type = 'SafetyRefusalError'
        WHERE operation_type = 'annotation'
          AND error_type = 'SAFETY_REFUSAL'
        """
    )
    op.execute(
        """
        UPDATE error_records
        SET error_type = 'ContentPolicyRefusalError'
        WHERE operation_type = 'annotation'
          AND error_type = 'CONTENT_POLICY_REFUSAL'
        """
    )
