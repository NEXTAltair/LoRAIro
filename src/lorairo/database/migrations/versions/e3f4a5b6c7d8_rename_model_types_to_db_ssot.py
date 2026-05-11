"""rename model_types: tagger -> tags, score -> scores, captioner -> caption

Issue #243: 既存 migration (a860e469d0c4 / fda27f4584ec) の終端状態と本番 DB の
SSoT 値が乖離していた。事実上の SSoT は `tags` / `scores` / `caption` / `upscaler` /
`multimodal` で、`model_sync_service._map_library_model_type_to_db()` もこれに
合わせて修正された。本 migration で migration 履歴側を本番 SSoT に追従させる:

- `tagger` → `tags`
- `score` → `scores`
- `captioner` → `caption`

旧名で登録されていた DB (新規 dev DB 等) はこの migration で正規化される。
既に正規化済みの本番 DB (旧 sync 経路で `tags`/`scores`/`caption` に手動 UPDATE 済み)
では `UPDATE ... WHERE name = 'tagger'` 等の WHERE 句が 0 行ヒットするため no-op。

Revision ID: e3f4a5b6c7d8
Revises: d8e9f0a1b2c3
Create Date: 2026-05-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 旧 (migration 履歴上の値) → 新 (本番 SSoT 値) の対応
_RENAMES: tuple[tuple[str, str], ...] = (
    ("tagger", "tags"),
    ("score", "scores"),
    ("captioner", "caption"),
)


def upgrade() -> None:
    """model_types テーブルの旧名を本番 SSoT 値に rename する (該当行のみ更新)。"""
    for old, new in _RENAMES:
        # 既に新 SSoT 値の行があれば旧名行は重複になるため、先に旧名行を削除して
        # 新名行が存在しないケースのみ rename する。UNIQUE 制約違反を回避。
        op.execute(
            f"DELETE FROM model_types WHERE name = '{old}' "
            f"AND EXISTS (SELECT 1 FROM model_types WHERE name = '{new}')"
        )
        op.execute(f"UPDATE model_types SET name = '{new}' WHERE name = '{old}'")


def downgrade() -> None:
    """旧名に戻す (ベストエフォート)。"""
    for old, new in _RENAMES:
        op.execute(
            f"DELETE FROM model_types WHERE name = '{new}' "
            f"AND EXISTS (SELECT 1 FROM model_types WHERE name = '{old}')"
        )
        op.execute(f"UPDATE model_types SET name = '{old}' WHERE name = '{new}'")
