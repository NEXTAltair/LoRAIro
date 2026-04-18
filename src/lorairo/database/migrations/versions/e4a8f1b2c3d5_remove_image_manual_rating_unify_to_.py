"""Remove Image.manual_rating column and unify to Rating table (MANUAL_EDIT model)

Issue #119: manual_rating の書き込み先と読み込み先が異なるテーブルを使っており
フィルタが常に空を返すバグを修正する。Score テーブルパターンに統一し
Image.manual_rating カラムを廃止して Rating(MANUAL_EDIT) テーブルに一元化する。

詳細は docs/decisions/0015-manual-rating-storage-unification.md を参照。

Revision ID: e4a8f1b2c3d5
Revises: 469833dd8bda
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a8f1b2c3d5"
down_revision: str | None = "b2f3a4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade: Image.manual_rating 値を Rating テーブルへ移行してカラムを削除する。"""
    connection = op.get_bind()

    # 1. MANUAL_EDIT モデルを取得または作成
    row = connection.execute(
        sa.text("SELECT id FROM models WHERE name = 'MANUAL_EDIT'")
    ).scalar_one_or_none()

    if row is None:
        connection.execute(sa.text("INSERT INTO models (name, provider) VALUES ('MANUAL_EDIT', 'user')"))
        manual_edit_id = connection.execute(
            sa.text("SELECT id FROM models WHERE name = 'MANUAL_EDIT'")
        ).scalar_one()
    else:
        manual_edit_id = row

    # 2. 既存の Image.manual_rating 値を Rating テーブルへ移行
    connection.execute(
        sa.text("""
            INSERT INTO ratings (image_id, model_id, raw_rating_value, normalized_rating)
            SELECT id, :mid, manual_rating, manual_rating
            FROM images
            WHERE manual_rating IS NOT NULL
        """),
        {"mid": manual_edit_id},
    )

    # 3. images テーブルから manual_rating カラムを削除 (SQLite は batch_alter_table 必須)
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_column("manual_rating")


def downgrade() -> None:
    """Downgrade: manual_rating カラムを復元して MANUAL_EDIT Rating を書き戻す。"""
    # 1. カラムを復元
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("manual_rating", sa.String(), nullable=True))

    # 2. MANUAL_EDIT Rating の最新値を Image.manual_rating に書き戻し
    connection = op.get_bind()
    connection.execute(
        sa.text("""
            UPDATE images
            SET manual_rating = (
                SELECT r.normalized_rating
                FROM ratings r
                JOIN models m ON r.model_id = m.id
                WHERE r.image_id = images.id
                  AND m.name = 'MANUAL_EDIT'
                ORDER BY r.created_at DESC
                LIMIT 1
            )
        """)
    )

    # 3. 移行した MANUAL_EDIT Rating レコードを削除
    connection.execute(
        sa.text("""
            DELETE FROM ratings
            WHERE model_id IN (SELECT id FROM models WHERE name = 'MANUAL_EDIT')
        """)
    )
