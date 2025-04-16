"""Add missing model type associations for pre-existing models

Revision ID: c9b242b21b87
Revises: a860e469d0c4
Create Date: 2025-04-16 17:15:24.087651

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9b242b21b87"
down_revision: str | None = "a860e469d0c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger(f"alembic.runtime.migration.{revision}")

# --- NEW_MODELS_DATA をここに再度定義 ---
NEW_MODELS_DATA = {
    "score": [
        "aesthetic_shadow_v1",
        "aesthetic_shadow_v2",
        "cafe_aesthetic",
        "ImprovedAesthetic",
        "WaifuAesthetic",
    ],
    "tagger": [
        "idolsankaku-eva02-large-tagger-v1",
        "idolsankaku-swinv2-tagger-v1",
        "Z3D-E621-Convnext",
        "wd-v1-4-convnext-tagger-v2",
        "wd-v1-4-convnextv2-tagger-v2",
        "wd-v1-4-moat-tagger-v2",
        "wd-v1-4-swinv2-tagger-v2",
        "wd-vit-tagger-v3",
        "wd-convnext-tagger-v3",
        "wd-swinv2-tagger-v3",
        "wd-vit-large-tagger-v3",
        "wd-eva02-large-tagger-v3",
        "deepdanbooru-v3-20211112-sgd-e28",
        "deepdanbooru-v4-20200814-sgd-e30",
        "deepdanbooru-v3-20200915-sgd-e30",
        "deepdanbooru-v3-20200101-sgd-e30",
        "deepdanbooru-v1-20191108-sgd-e30",
    ],
    "captioner": [
        "BLIPLargeCaptioning",
        "blip2-opt-2.7b",
        "blip2-opt-2.7b-coco",
        "blip2-opt-6.7b",
        "blip2-opt-6.7b-coco",
        "blip2-flan-t5-xl",
        "blip2-flan-t5-xl-coco",
        "blip2-flan-t5-xxl",
        "GITLargeCaptioning",
    ],
    "llm": [
        "ToriiGate-v0.3",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.5-preview",
        "optimus-alpha",
        "claude-3-7-sonnet",
        "claude-3-5-haiku",
    ],
    "upscaler": [],  # No new upscalers in the list
}


def upgrade() -> None:
    """Add missing model type associations."""
    bind = op.get_bind()
    Session = sa.orm.sessionmaker(bind=bind)
    session = Session()

    # Define table structures
    models_table = sa.table("models", sa.column("id", sa.Integer), sa.column("name", sa.String))
    model_types_table = sa.table("model_types", sa.column("id", sa.Integer), sa.column("name", sa.String))
    model_function_associations_table = sa.table(
        "model_function_associations",
        sa.column("model_id", sa.Integer),
        sa.column("type_id", sa.Integer),
    )

    try:
        # Get existing data
        model_name_to_id = {
            row.name: row.id
            for row in session.execute(sa.select(models_table.c.id, models_table.c.name)).fetchall()
        }
        type_name_to_id = {
            row.name: row.id
            for row in session.execute(
                sa.select(model_types_table.c.id, model_types_table.c.name)
            ).fetchall()
        }
        existing_associations = {
            (row.model_id, row.type_id)
            for row in session.execute(
                sa.select(
                    model_function_associations_table.c.model_id,
                    model_function_associations_table.c.type_id,
                )
            ).fetchall()
        }
        log.info(f"Found {len(existing_associations)} existing associations.")

        missing_associations_to_insert = []

        for type_name, model_list in NEW_MODELS_DATA.items():
            if type_name not in type_name_to_id:
                log.warning(f"定義されたタイプ '{type_name}' が DB に存在しません。スキップします。")
                continue
            target_type_id = type_name_to_id[type_name]

            for model_name in model_list:
                if model_name not in model_name_to_id:
                    log.warning(f"定義されたモデル '{model_name}' が DB に存在しません。スキップします。")
                    continue
                target_model_id = model_name_to_id[model_name]

                # Check if this association is missing
                if (target_model_id, target_type_id) not in existing_associations:
                    missing_associations_to_insert.append(
                        {"model_id": target_model_id, "type_id": target_type_id}
                    )
                    # Add to existing_associations set to handle models listed multiple times (if any)
                    existing_associations.add((target_model_id, target_type_id))

        if missing_associations_to_insert:
            log.info(f"Found {len(missing_associations_to_insert)} missing associations to insert.")
            op.bulk_insert(model_function_associations_table, missing_associations_to_insert)
            log.info("Inserted missing associations.")
        else:
            log.info("不足している関連付けは見つかりませんでした。")

        # session.commit() # bulk_insert は通常自動コミット (接続モードによる)
    except Exception as e:
        # session.rollback() # rollback も接続モードによる
        log.error(f"不足している関連付けの追加中にエラーが発生しました: {e}", exc_info=True)
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Downgrade: Reverting this specific data addition is complex, so we pass."""
    # It's hard to know exactly which associations were added by *this* script.
    # A simple approach is to do nothing, or log a message.
    log.warning("Downgrade for 'Add missing model type associations' is not implemented automatically.")
    pass
