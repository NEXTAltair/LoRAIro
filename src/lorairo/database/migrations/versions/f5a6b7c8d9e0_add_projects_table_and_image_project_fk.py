"""Add projects table and images.project_id FK

Issue #175 (ADR 0017): プロジェクトを第一級エンティティとして DB 正規化する。
- projects テーブルを新規作成
- images.project_id FK カラムを追加 (nullable=True、ON DELETE SET NULL)
- 既存データのバックフィル（DB パスからプロジェクト名を抽出）

詳細は docs/decisions/0017-project-db-normalization.md を参照。

Revision ID: f5a6b7c8d9e0
Revises: e4a8f1b2c3d5
Create Date: 2026-04-24

"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4a8f1b2c3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Upgrade: projects テーブル追加・images.project_id カラム追加・バックフィル。"""
    # Phase 1: projects テーブルを作成
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_projects_name", "projects", ["name"], unique=True)

    # Phase 2: images.project_id カラム追加（SQLite は batch_alter_table 必須）
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_images_project_id", ["project_id"])
        batch_op.create_foreign_key(
            "fk_images_project_id",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Phase 3: バックフィル（冪等性あり・インメモリDB はスキップ）
    _backfill_project(op.get_bind())


def _backfill_project(connection: sa.engine.Connection) -> None:
    """現在の DB パスからプロジェクト名を特定して projects/images を更新する。

    インメモリ DB（テスト環境）や PRAGMA 取得失敗時はスキップする。
    既に projects 行が存在する場合も冪等にスキップする。
    """
    try:
        row = connection.execute(sa.text("PRAGMA database_list")).fetchone()
    except Exception:
        logger.debug("PRAGMA database_list 失敗 — バックフィルをスキップ")
        return

    if row is None or not row[2]:
        logger.debug("DB パス未取得 — バックフィルをスキップ")
        return

    db_file: str = row[2]
    if db_file == ":memory:":
        logger.debug("インメモリ DB — バックフィルをスキップ")
        return

    # 既に projects 行が存在する場合はスキップ（冪等性保証）
    existing_count = connection.execute(sa.text("SELECT COUNT(*) FROM projects")).scalar()
    if existing_count and existing_count > 0:
        logger.info(f"projects テーブルに既存行あり ({existing_count} 件) — バックフィルをスキップ")
        return

    db_parent = Path(db_file).parent
    project_path = str(db_parent)

    # .lorairo-project メタデータから logical name を読む。
    # ディレクトリ名は "name_YYYYMMDD_HHMMSS" 形式だが、アプリが使う project_name は
    # メタデータの "name" フィールド（タイムスタンプなし）なので、一致させる必要がある。
    metadata_file = db_parent / ".lorairo-project"
    project_name = db_parent.name  # フォールバック: ディレクトリ名
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        if isinstance(metadata.get("name"), str) and metadata["name"]:
            project_name = metadata["name"]
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    connection.execute(
        sa.text("INSERT OR IGNORE INTO projects (name, path) VALUES (:name, :path)"),
        {"name": project_name, "path": project_path},
    )

    project_id = connection.execute(
        sa.text("SELECT id FROM projects WHERE name = :name"),
        {"name": project_name},
    ).scalar_one()

    connection.execute(
        sa.text("UPDATE images SET project_id = :pid WHERE project_id IS NULL"),
        {"pid": project_id},
    )

    updated_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM images WHERE project_id = :pid"),
        {"pid": project_id},
    ).scalar()
    logger.info(
        f"Backfill 完了: {updated_count} 枚の画像をプロジェクト '{project_name}'"
        f" (id={project_id}) に割り当てました"
    )


def downgrade() -> None:
    """Downgrade: images.project_id カラム削除・projects テーブル削除。"""
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_constraint("fk_images_project_id", type_="foreignkey")
        batch_op.drop_index("ix_images_project_id")
        batch_op.drop_column("project_id")

    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
