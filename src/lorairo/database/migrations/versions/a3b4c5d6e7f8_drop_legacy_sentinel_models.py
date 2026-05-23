"""Drop legacy sentinel models and child references (ADR 0033 Decision 7).

ADR 0023 Phase 1.11 で導入された `litellm_model_id="__legacy_<id>__"` 用 sentinel
行を models テーブルから削除する。ADR 0033 で「過去 DB 互換は不要」と判断し、
履歴行として残す運用契約を撤回した。

FK 設定:
- tags / captions / scores: ondelete=SET NULL
- score_labels / ratings: ondelete=CASCADE
- model_function_associations: ondelete 未設定 (明示 DELETE 必須)
- error_records.model_name: FK ではなく文字列、`__legacy_%` で明示 DELETE

ADR 0033 Decision 7 に従い「該当行も同 migration 内で削除」を一律明示 DELETE で行う。
SET NULL 設定のテーブルも履歴ごと消す (整合性リスク排除を優先)。

Downgrade: 削除データは復元不可。downgrade は no-op (必要なら backup から手動復元)。

Revision ID: a3b4c5d6e7f8
Revises: f1b2c3d4e5f6
Create Date: 2026-05-23

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect, text

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQL LIKE では `_` が任意 1 文字にマッチするため、リテラル比較するには ESCAPE が必要。
# `mylegacy-model` 等の非 sentinel ID が誤マッチしないよう、`_` をすべて `\_` でエスケープし
# 末尾に `%` を付ける (旧形式 `__legacy_<id>__` の前方一致)。
_LEGACY_LIKE = r"\_\_legacy\_%"
_LEGACY_ESCAPE = "\\"

# 子テーブル削除順 (FK 整合性のため models DELETE 前にすべて消す)
_CHILD_DELETE_TABLES: tuple[str, ...] = (
    "tags",
    "captions",
    "scores",
    "score_labels",
    "ratings",
    "model_function_associations",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "models" not in existing_tables:
        return

    result = bind.execute(
        text("SELECT id FROM models WHERE litellm_model_id LIKE :pat ESCAPE :esc"),
        {"pat": _LEGACY_LIKE, "esc": _LEGACY_ESCAPE},
    )
    legacy_ids: list[int] = [row[0] for row in result]
    if not legacy_ids:
        print("[migration a3b4c5d6e7f8] legacy sentinel 行なし、no-op")
        return

    ids_csv = ", ".join(str(i) for i in legacy_ids)
    print(f"[migration a3b4c5d6e7f8] 対象 models.id=[{ids_csv}] ({len(legacy_ids)} 件)")

    for table in _CHILD_DELETE_TABLES:
        if table not in existing_tables:
            continue
        count = (
            bind.execute(text(f"SELECT COUNT(*) FROM {table} WHERE model_id IN ({ids_csv})")).scalar() or 0
        )
        if count:
            bind.execute(text(f"DELETE FROM {table} WHERE model_id IN ({ids_csv})"))
            print(f"[migration a3b4c5d6e7f8] {table}: {count} 行削除")

    # error_records は model_name 文字列ベース (FK なし)
    if "error_records" in existing_tables:
        er_count = (
            bind.execute(
                text("SELECT COUNT(*) FROM error_records WHERE model_name LIKE :pat ESCAPE :esc"),
                {"pat": _LEGACY_LIKE, "esc": _LEGACY_ESCAPE},
            ).scalar()
            or 0
        )
        if er_count:
            bind.execute(
                text("DELETE FROM error_records WHERE model_name LIKE :pat ESCAPE :esc"),
                {"pat": _LEGACY_LIKE, "esc": _LEGACY_ESCAPE},
            )
            print(f"[migration a3b4c5d6e7f8] error_records: {er_count} 行削除")

    bind.execute(text(f"DELETE FROM models WHERE id IN ({ids_csv})"))
    print(f"[migration a3b4c5d6e7f8] models: {len(legacy_ids)} 行削除")


def downgrade() -> None:
    """legacy sentinel データは復元不可。downgrade は no-op。

    元の状態に戻す必要がある場合は、migration 適用前の backup から手動復元する。
    ADR 0033 で「過去 DB 互換不要」と判断した結果のため、downgrade で sentinel を
    再生成する意味はない。
    """
    print(
        "[migration a3b4c5d6e7f8 downgrade] no-op: legacy sentinel データは復元不可。"
        " 必要なら backup から手動復元してください。"
    )
