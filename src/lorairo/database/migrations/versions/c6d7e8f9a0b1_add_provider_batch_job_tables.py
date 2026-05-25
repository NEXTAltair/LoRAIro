"""Add provider batch job tables (ADR 0038).

Revision ID: c6d7e8f9a0b1
Revises: b4c5d6e7f8a9
Create Date: 2026-05-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_batch_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_job_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider_status", sa.String(), nullable=True),
        sa.Column("endpoint", sa.String(), nullable=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("canceled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expired_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("imported_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("input_artifact_path", sa.String(), nullable=True),
        sa.Column("output_artifact_path", sa.String(), nullable=True),
        sa.Column("error_artifact_path", sa.String(), nullable=True),
        sa.Column("raw_provider_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_provider_batch_jobs_provider", "provider_batch_jobs", ["provider"])
    op.create_index("ix_provider_batch_jobs_status", "provider_batch_jobs", ["status"])
    op.create_index("ix_provider_batch_jobs_created_at", "provider_batch_jobs", ["created_at"])
    op.create_index(
        "uq_provider_batch_jobs_provider_job",
        "provider_batch_jobs",
        ["provider", "provider_job_id"],
        unique=True,
        sqlite_where=sa.text("provider_job_id IS NOT NULL"),
    )

    op.create_table(
        "provider_batch_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("provider_batch_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("custom_id", sa.String(), nullable=False),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="SET NULL")),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("raw_request", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("job_id", "custom_id", name="uix_provider_batch_items_job_custom_id"),
    )
    op.create_index("ix_provider_batch_items_job_id", "provider_batch_items", ["job_id"])
    op.create_index("ix_provider_batch_items_status", "provider_batch_items", ["status"])
    op.create_index("ix_provider_batch_items_image_id", "provider_batch_items", ["image_id"])
    op.create_index("ix_provider_batch_items_model_id", "provider_batch_items", ["model_id"])

    op.create_table(
        "provider_batch_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("provider_batch_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("local_path", sa.String(), nullable=False),
        sa.Column("provider_file_id", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "job_id",
            "artifact_type",
            "local_path",
            name="uix_provider_batch_artifacts_job_type_path",
        ),
    )
    op.create_index("ix_provider_batch_artifacts_job_id", "provider_batch_artifacts", ["job_id"])
    op.create_index("ix_provider_batch_artifacts_type", "provider_batch_artifacts", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_provider_batch_artifacts_type", table_name="provider_batch_artifacts")
    op.drop_index("ix_provider_batch_artifacts_job_id", table_name="provider_batch_artifacts")
    op.drop_table("provider_batch_artifacts")

    op.drop_index("ix_provider_batch_items_model_id", table_name="provider_batch_items")
    op.drop_index("ix_provider_batch_items_image_id", table_name="provider_batch_items")
    op.drop_index("ix_provider_batch_items_status", table_name="provider_batch_items")
    op.drop_index("ix_provider_batch_items_job_id", table_name="provider_batch_items")
    op.drop_table("provider_batch_items")

    op.drop_index("uq_provider_batch_jobs_provider_job", table_name="provider_batch_jobs")
    op.drop_index("ix_provider_batch_jobs_created_at", table_name="provider_batch_jobs")
    op.drop_index("ix_provider_batch_jobs_status", table_name="provider_batch_jobs")
    op.drop_index("ix_provider_batch_jobs_provider", table_name="provider_batch_jobs")
    op.drop_table("provider_batch_jobs")
