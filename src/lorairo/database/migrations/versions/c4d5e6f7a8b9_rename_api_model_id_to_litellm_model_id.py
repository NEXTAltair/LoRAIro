"""rename api_model_id to litellm_model_id

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08

ADR 0023 line 73「``available_api_models.toml`` 由来の旧 ``api_model_id`` は本 ADR
で廃止する (互換シムを残さない)」を public API レベルで実現する一括破壊的変更
(Issue #41 / Option A)。

image-annotator-lib 側 ``AnnotatorInfo.api_model_id`` field を ``litellm_model_id``
にリネームしたことに追従し、LoRAIro DB schema の ``models.api_model_id`` カラムを
``litellm_model_id`` に同期リネームする。

実装方針:
- SQLite が ``ALTER COLUMN ... RENAME`` を直接サポートしないため、Alembic 公式
  パターンの ``batch_alter_table`` で alter_column を実行する。
- production data は upgrade 一発で自動変換される (column 名のみ変更、データは保持)。
- ロールバックは ``alembic downgrade -1`` で旧名に戻る。
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """models.api_model_id を litellm_model_id にリネームする。"""
    with op.batch_alter_table("models") as batch_op:
        batch_op.alter_column("api_model_id", new_column_name="litellm_model_id")


def downgrade() -> None:  # pragma: no cover
    """models.litellm_model_id を api_model_id に戻す (ロールバック用)。"""
    with op.batch_alter_table("models") as batch_op:
        batch_op.alter_column("litellm_model_id", new_column_name="api_model_id")
