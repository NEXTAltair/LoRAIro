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

# 正規 sentinel 形式は `__legacy_<digits>__` (ADR 0023 Phase 1.11 / Worker 側
# `_is_legacy_sentinel_model_id` と一致)。SQL `LIKE` の `_` ワイルドカードを ESCAPE で
# literal 化し、prefix と suffix の両方を pattern に含める。`<digits>` 部分は LIKE では
# 厳密に表現できないので、SELECT 後 Python 側で `.isdecimal()` post-filter する。
_LEGACY_LIKE = r"\_\_legacy\_%\_\_"
_LEGACY_ESCAPE = "\\"
_LEGACY_PREFIX = "__legacy_"
_LEGACY_SUFFIX = "__"

# 子テーブル削除順 (FK 整合性のため models DELETE 前にすべて消す)
_CHILD_DELETE_TABLES: tuple[str, ...] = (
    "tags",
    "captions",
    "scores",
    "score_labels",
    "ratings",
    "model_function_associations",
)


def _is_canonical_sentinel(model_id: str) -> bool:
    """`__legacy_<digits>__` 形式のみ canonical sentinel と判定する。

    Worker 側 `AnnotationWorker._is_legacy_sentinel_model_id` と完全に一致させる。
    LIKE pattern (prefix `\\_\\_legacy\\_%\\_\\_` + ESCAPE) で suffix `__` までは絞り込み
    済みだが、`<digits>` 部分の数字限定は SQL では厳密に表現できないため Python 側で
    検査する。例:
        `__legacy_22__`       → True
        `__legacy_foo__`      → False (middle が数字でない)
        `__legacy_22_extra__` → False (middle に `_` を含む)
    """
    if not (model_id.startswith(_LEGACY_PREFIX) and model_id.endswith(_LEGACY_SUFFIX)):
        return False
    middle = model_id[len(_LEGACY_PREFIX) : -len(_LEGACY_SUFFIX)]
    return middle.isdecimal()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "models" not in existing_tables:
        return

    candidate_rows = bind.execute(
        text("SELECT id, litellm_model_id FROM models WHERE litellm_model_id LIKE :pat ESCAPE :esc"),
        {"pat": _LEGACY_LIKE, "esc": _LEGACY_ESCAPE},
    ).fetchall()
    legacy_ids: list[int] = [row[0] for row in candidate_rows if _is_canonical_sentinel(row[1])]
    skipped = [row[1] for row in candidate_rows if not _is_canonical_sentinel(row[1])]
    if skipped:
        print(f"[migration a3b4c5d6e7f8] LIKE 候補で除外 (canonical sentinel ではない): {skipped}")
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

    # error_records は model_name 文字列ベース (FK なし)。models と同じ canonical filter
    # で `__legacy_<digits>__` のみに絞る (SELECT 後 Python post-filter で id を取得)。
    if "error_records" in existing_tables:
        er_candidates = bind.execute(
            text("SELECT id, model_name FROM error_records WHERE model_name LIKE :pat ESCAPE :esc"),
            {"pat": _LEGACY_LIKE, "esc": _LEGACY_ESCAPE},
        ).fetchall()
        er_ids = [row[0] for row in er_candidates if _is_canonical_sentinel(row[1])]
        er_skipped = [row[1] for row in er_candidates if not _is_canonical_sentinel(row[1])]
        if er_skipped:
            print(f"[migration a3b4c5d6e7f8] error_records LIKE 候補で除外: {er_skipped}")
        if er_ids:
            er_ids_csv = ", ".join(str(i) for i in er_ids)
            bind.execute(text(f"DELETE FROM error_records WHERE id IN ({er_ids_csv})"))
            print(f"[migration a3b4c5d6e7f8] error_records: {len(er_ids)} 行削除")

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
