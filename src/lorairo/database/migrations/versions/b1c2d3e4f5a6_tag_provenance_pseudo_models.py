"""model_id NULL のタグ行に出所 (擬似モデル) を持たせる

ADR 0111: `tags.model_id` が NULL の行は、手入力・関連ファイル (.txt) 取り込み・画像処理の
自動タグを区別できなかった。擬似モデル `SIDECAR_IMPORT` / `IMAGE_PROCESSING` を追加し、
既存の NULL 行を次の順で振り分ける (データ移行のみ。スキーマは変えず、NOT NULL 化もしない)。

1. tag = 'upscaled' かつ existing = False → IMAGE_PROCESSING
2. is_edited_manually = True → MANUAL_EDIT
3. それ以外で existing = True → SIDECAR_IMPORT
4. 残りは NULL のまま

移行先に同じ (image_id, model_id, tag) の行が既にある NULL 行 (uq_tags_image_model_tag に
反する行) は移さず NULL のまま残す。同じ (image_id, tag) の NULL 行が複数あるときは
id が最小の 1 行だけを移す。いずれも行は削除しない。

Revision ID: b1c2d3e4f5a6
Revises: f8a9b0c1d2e3
Create Date: 2026-11-19
"""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# schema.py の定数と同期 (migration は実行時のアプリ定数に依存させない)
_MANUAL_EDIT = ("MANUAL_EDIT", "__manual_edit__")
_SIDECAR_IMPORT = ("SIDECAR_IMPORT", "__sidecar_import__")
_IMAGE_PROCESSING = ("IMAGE_PROCESSING", "__image_processing__")
_PSEUDO_PROVIDER = "user"
_UPSCALED_TAG = "upscaled"

_tags = sa.table(
    "tags",
    sa.column("id", sa.Integer),
    sa.column("image_id", sa.Integer),
    sa.column("model_id", sa.Integer),
    sa.column("tag", sa.String),
    sa.column("existing", sa.Boolean),
    sa.column("is_edited_manually", sa.Boolean),
)
_models = sa.table("models", sa.column("id", sa.Integer), sa.column("litellm_model_id", sa.String))

_TagCondition = Callable[[sa.FromClause], sa.ColumnElement[bool]]


def _not_manual(t: sa.FromClause) -> sa.ColumnElement[bool]:
    """手入力でない (is_edited_manually が False または NULL)。"""
    return sa.func.coalesce(t.c.is_edited_manually, sa.false()) == sa.false()


# 3 つの条件は互いに排他にする。衝突で移せなかった手動の行が、後の取り込みの
# 振り分けに拾われて SIDECAR_IMPORT になる誤分類を防ぐため。
def _upscaled_condition(t: sa.FromClause) -> sa.ColumnElement[bool]:
    """画像処理が付けた `upscaled` (取り込み元ファイルに無かったタグ)。"""
    return sa.and_(t.c.tag == _UPSCALED_TAG, t.c.existing == sa.false(), _not_manual(t))


def _manual_condition(t: sa.FromClause) -> sa.ColumnElement[bool]:
    """手入力のタグ。"""
    return t.c.is_edited_manually == sa.true()


def _sidecar_condition(t: sa.FromClause) -> sa.ColumnElement[bool]:
    """取り込み元ファイルにあったタグ (関連ファイル .txt 取り込み)。"""
    return sa.and_(t.c.existing == sa.true(), _not_manual(t))


def _get_or_create_pseudo_model(connection: sa.engine.Connection, name: str, litellm_model_id: str) -> int:
    """擬似モデル行の ID を返す。無ければ作る (model_types には関連付けない)。"""
    model_id = connection.execute(
        sa.text("SELECT id FROM models WHERE litellm_model_id = :litellm_model_id"),
        {"litellm_model_id": litellm_model_id},
    ).scalar_one_or_none()
    if model_id is not None:
        return int(model_id)
    connection.execute(
        sa.text(
            "INSERT INTO models (name, provider, litellm_model_id, requires_api_key) "
            "VALUES (:name, :provider, :litellm_model_id, 0)"
        ),
        {"name": name, "provider": _PSEUDO_PROVIDER, "litellm_model_id": litellm_model_id},
    )
    return int(
        connection.execute(
            sa.text("SELECT id FROM models WHERE litellm_model_id = :litellm_model_id"),
            {"litellm_model_id": litellm_model_id},
        ).scalar_one()
    )


def _assign_null_rows(connection: sa.engine.Connection, condition: _TagCondition, model_id: int) -> None:
    """条件に合う model_id NULL の行を、1 文の UPDATE で擬似モデルへ移す。

    updated_at は変えない (移行は利用者の変更ではないため)。
    """
    dup = _tags.alias("dup")
    first = _tags.alias("first")
    already_assigned = sa.exists().where(
        dup.c.image_id == _tags.c.image_id,
        dup.c.model_id == model_id,
        dup.c.tag == _tags.c.tag,
    )
    first_null_row_id = (
        sa.select(sa.func.min(first.c.id))
        .where(
            first.c.image_id == _tags.c.image_id,
            first.c.tag == _tags.c.tag,
            first.c.model_id.is_(None),
            condition(first),
        )
        .scalar_subquery()
    )
    connection.execute(
        sa.update(_tags)
        .where(
            _tags.c.model_id.is_(None),
            condition(_tags),
            ~already_assigned,
            _tags.c.id == first_null_row_id,
        )
        .values(model_id=model_id)
    )


def upgrade() -> None:
    """Upgrade: 擬似モデルを用意し、model_id NULL のタグ行を出所ごとに移す。"""
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if not {"tags", "models"} <= tables:
        return

    image_processing_id = _get_or_create_pseudo_model(connection, *_IMAGE_PROCESSING)
    manual_edit_id = _get_or_create_pseudo_model(connection, *_MANUAL_EDIT)
    sidecar_import_id = _get_or_create_pseudo_model(connection, *_SIDECAR_IMPORT)

    _assign_null_rows(connection, _upscaled_condition, image_processing_id)
    _assign_null_rows(connection, _manual_condition, manual_edit_id)
    _assign_null_rows(connection, _sidecar_condition, sidecar_import_id)


def downgrade() -> None:
    """Downgrade: SIDECAR_IMPORT / IMAGE_PROCESSING のタグ行を model_id NULL に戻す。

    MANUAL_EDIT のタグ行は戻さない。移行前から MANUAL_EDIT だった行 (GUI の手動編集) と
    区別できず、旧版も MANUAL_EDIT のタグ行をそのまま扱えるため。擬似モデル行自体は残す。
    """
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if not {"tags", "models"} <= tables:
        return
    reverted_model_ids = sa.select(_models.c.id).where(
        _models.c.litellm_model_id.in_([_SIDECAR_IMPORT[1], _IMAGE_PROCESSING[1]])
    )
    connection.execute(
        sa.update(_tags).where(_tags.c.model_id.in_(reverted_model_ids)).values(model_id=None)
    )
