"""update_model_type_llm_to_multimodal

Revision ID: fda27f4584ec
Revises: 469833dd8bda
Create Date: 2025-07-29 10:20:02.695268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fda27f4584ec'
down_revision: Union[str, None] = '469833dd8bda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update ModelType name from 'llm' to 'multimodal'."""
    # Update model type name
    op.execute(
        "UPDATE model_types SET name = 'multimodal' WHERE name = 'llm'"
    )


def downgrade() -> None:
    """Revert ModelType name from 'multimodal' back to 'llm'."""
    # Revert model type name
    op.execute(
        "UPDATE model_types SET name = 'llm' WHERE name = 'multimodal'"
    )
