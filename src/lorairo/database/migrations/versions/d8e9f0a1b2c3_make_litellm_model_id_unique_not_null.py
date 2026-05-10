"""make litellm_model_id unique not null and demote name to non-unique display name

ADR 0023 Phase 1.11 (LoRAIro Issue #238).

image-annotator-lib Phase 1.9 / 1.10 (Issue #51, #52) のマージで registry が
"同一論理モデル × 経路違い" のエントリを完全 LiteLLM ID で並列保持するようになり、
LoRAIro `schema.Model` の旧 `name UNIQUE` 制約では同一モデル名の複数経路登録が
不可能になった。本 migration で以下を実施する:

1. 既存データの backfill (5 段階):
   - MANUAL_EDIT 行に sentinel `__manual_edit__` を設定
   - スラッシュ込み name 行 (例: `openai/gpt-4.1`) は name をそのまま
     litellm_model_id にコピーし、name/provider を最初の `/` で分離
   - スラッシュなし name + provider あり + litellm_model_id NULL → 補完
   - 残存 NULL 行は `__legacy_<id>__` sentinel で fallback
2. schema 変更 (SQLite batch_alter_table 必須):
   - name の UNIQUE 制約 drop
   - litellm_model_id を NOT NULL + UNIQUE 化

Revision ID: d8e9f0a1b2c3
Revises: c4d5e6f7a8b9
Create Date: 2026-05-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ADR 0023 Phase 1.11 sentinel (schema.MANUAL_EDIT_LITELLM_ID と同期)
_MANUAL_EDIT_NAME = "MANUAL_EDIT"
_MANUAL_EDIT_LITELLM_ID = "__manual_edit__"


def _old_models_table() -> sa.Table:
    """旧 schema (name UNIQUE, litellm_model_id nullable) を batch_alter_table の copy_from に渡すための定義。

    SQLAlchemy インライン `unique=True` で生成された UniqueConstraint は SQLite で
    anonymous (name=None) として保存されるため、reflection 経由では `drop_constraint`
    で名前指定できない。ここで明示的な制約名 `uq_models_name` を付けて copy_from に
    渡すことで、batch 内 `drop_constraint("uq_models_name", ...)` が成立する。
    """
    return sa.Table(
        "models",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("provider", sa.String),
        sa.Column("discontinued_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("litellm_model_id", sa.String),
        sa.Column("estimated_size_gb", sa.Float),
        sa.Column("requires_api_key", sa.Boolean, server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_models_name"),
    )


def _intermediate_models_table() -> sa.Table:
    """中間 schema (name UNIQUE drop 済み, litellm_model_id nullable のまま) の Table 定義。

    upgrade() で「name UNIQUE drop → data backfill → litellm_model_id UNIQUE NOT NULL 付与」
    の 2 段階で batch_alter_table を呼ぶための中間状態。
    """
    return sa.Table(
        "models",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("provider", sa.String),
        sa.Column("discontinued_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("litellm_model_id", sa.String),
        sa.Column("estimated_size_gb", sa.Float),
        sa.Column("requires_api_key", sa.Boolean, server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )


def _new_models_table() -> sa.Table:
    """新 schema (litellm_model_id UNIQUE NOT NULL, name 非 UNIQUE) を downgrade の copy_from に渡すための定義。"""
    return sa.Table(
        "models",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("provider", sa.String),
        sa.Column("discontinued_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("litellm_model_id", sa.String, nullable=False),
        sa.Column("estimated_size_gb", sa.Float),
        sa.Column("requires_api_key", sa.Boolean, server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("litellm_model_id", name="uq_models_litellm_model_id"),
    )


def upgrade() -> None:
    """既存データを backfill した上で UNIQUE 制約を name → litellm_model_id に付替える。"""
    connection = op.get_bind()

    # Step A: `name` UNIQUE 制約を data backfill より先に drop する。
    # Step 3 (slash 込み name の分離) で `name='openai/gpt-4o'` を `name='gpt-4o'` に
    # UPDATE する際、既存の `name='gpt-4o'` 行と衝突して name UNIQUE 違反になるため、
    # backfill 前に制約を外しておく必要がある。
    with op.batch_alter_table("models", copy_from=_old_models_table()) as batch_op:
        batch_op.drop_constraint("uq_models_name", type_="unique")

    # 0. 旧 sync が `name` と同値の bare 名 (`/` なし) を `litellm_model_id` に書き込んだ
    # 行を NULL に戻し、後続ステップで Phase 1.10 後の正規 LiteLLM ID で補完する。
    # (旧 `model_sync_service` は完全 ID でなく name をそのまま入れる経路があった)
    connection.execute(
        sa.text(
            "UPDATE models SET litellm_model_id = NULL "
            "WHERE litellm_model_id IS NOT NULL "
            "  AND litellm_model_id = name "
            "  AND litellm_model_id NOT LIKE '%/%'"
        )
    )

    # 1. MANUAL_EDIT 行に sentinel を設定 (UNIQUE NOT NULL 制約を満たす)
    connection.execute(
        sa.text(
            "UPDATE models SET litellm_model_id = :sentinel "
            "WHERE name = :manual_edit AND litellm_model_id IS NULL"
        ),
        {"sentinel": _MANUAL_EDIT_LITELLM_ID, "manual_edit": _MANUAL_EDIT_NAME},
    )

    # 2. スラッシュ込み name 行: name を litellm_model_id にコピー (NULL のみ)
    connection.execute(
        sa.text(
            "UPDATE models SET litellm_model_id = name WHERE name LIKE '%/%' AND litellm_model_id IS NULL"
        )
    )

    # 3. スラッシュ込み name の name/provider 分離
    # provider := name の最初の '/' 前 (lowercase 化)、name := 最初の '/' 後
    # 例: name='openrouter/openai/gpt-4o' → provider='openrouter', name='openai/gpt-4o'
    connection.execute(
        sa.text(
            "UPDATE models "
            "SET provider = lower(substr(name, 1, instr(name, '/') - 1)), "
            "    name = substr(name, instr(name, '/') + 1) "
            "WHERE name LIKE '%/%'"
        )
    )

    # 4. 既知 provider (case-insensitive) のスラッシュなし name 行を LiteLLM 規約で補完。
    # provider 値も LiteLLM 規約 (lowercase + Google → gemini マップ) に整合させる。
    # MANUAL_EDIT は手順 1 で sentinel 設定済みのため `lower(provider) IN (...)` で自然除外。
    for provider_old, provider_new in (
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("openrouter", "openrouter"),
        # LiteLLM 同梱 DB は Google モデルを `gemini/` プレフィックスで格納するため、
        # 旧 DB の `Google` は `gemini` にマップする
        ("google", "gemini"),
        ("gemini", "gemini"),
    ):
        connection.execute(
            sa.text(
                "UPDATE models "
                "SET litellm_model_id = :prefix || '/' || name, provider = :prefix "
                "WHERE litellm_model_id IS NULL AND lower(provider) = :old"
            ),
            {"prefix": provider_new, "old": provider_old},
        )

    # 5. 残存 NULL 行 (ローカル ML モデル / 不明 provider / 空文字 / `xinntao` 等) →
    # `__legacy_<id>__` sentinel で fallback。次回 registry sync で正規行が新規追加される
    # まで履歴行として保持される (推論経路には乗らない)。
    connection.execute(
        sa.text(
            "UPDATE models SET litellm_model_id = '__legacy_' || id || '__' WHERE litellm_model_id IS NULL"
        )
    )

    # 5.5. `litellm_model_id` 値の重複を解消する (UNIQUE 付与前の dedup)。
    # 旧 DB は `name UNIQUE` だったため、`name='openai/gpt-4o'` (slash 形式) と
    # `name='gpt-4o', provider='openai'` (bare 形式) が共存しうる。Step 2/4 で両行が
    # 同じ `litellm_model_id='openai/gpt-4o'` を持つと UNIQUE 制約付与時に IntegrityError
    # になる。最も古い (id 最小) 行のみ正規 ID を保持し、残りは `__legacy_<id>__` sentinel
    # に変換することで競合を解消する。既存 annotation 結果の FK は履歴行として保持される。
    connection.execute(
        sa.text(
            "UPDATE models "
            "SET litellm_model_id = '__legacy_' || id || '__' "
            "WHERE id NOT IN ("
            "    SELECT MIN(id) FROM models "
            "    WHERE litellm_model_id IS NOT NULL "
            "    GROUP BY litellm_model_id"
            ")"
        )
    )

    # Step B: data backfill 完了後、`litellm_model_id` を NOT NULL + UNIQUE 化する。
    # 中間 schema (name UNIQUE drop 済み、litellm_model_id nullable) を copy_from に渡す。
    with op.batch_alter_table("models", copy_from=_intermediate_models_table()) as batch_op:
        batch_op.alter_column(
            "litellm_model_id",
            existing_type=sa.String(),
            nullable=False,
        )
        batch_op.create_unique_constraint("uq_models_litellm_model_id", ["litellm_model_id"])


def downgrade() -> None:
    """UNIQUE 制約を litellm_model_id → name に戻す (ベストエフォート)。

    - litellm_model_id を nullable + 非 UNIQUE に戻す
    - name の UNIQUE を復元 (同名重複行があると IntegrityError、運用上手動 dedup が必要)
    - backfill した name/provider 分離値や sentinel 値の復元は行わない
    """
    with op.batch_alter_table("models", copy_from=_new_models_table()) as batch_op:
        batch_op.drop_constraint("uq_models_litellm_model_id", type_="unique")
        batch_op.alter_column(
            "litellm_model_id",
            existing_type=sa.String(),
            nullable=True,
        )
        batch_op.create_unique_constraint("uq_models_name", ["name"])
