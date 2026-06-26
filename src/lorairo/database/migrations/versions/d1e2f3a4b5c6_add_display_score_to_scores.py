"""add display_score to scores

Revision ID: d1e2f3a4b5c6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-06 00:00:00.000000

Issue #626: Score.score は生値 (aesthetic_shadow は 0-1 確率など) だが、
UI フィルタは 0-10 表示スコアで指定する。表示スコアを DB に永続化して
フィルタの O(1) 比較を可能にする。

バックフィル戦略:
- is_edited_manually=True  → display_score = score (手動編集値は既に 0-10)
- WebAPI モデル (model.name に "/" 含む) → identity + clamp (0-10 で来る)
- aesthetic_shadow_v1/v2  → 区分線形補間 knots
- cafe_aesthetic          → 区分線形補間 knots
- WaifuAesthetic          → linear 0-1 → 0-10
- ImprovedAesthetic        → identity clamp (AVA 1-10)
- それ以外 (未知 model)   → raw * 10 clamp (0-1 仮定 fallback)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as _sa_inspect
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# 移行専用の calibration ロジック (score_scaler.py から独立コピー)
# migration は将来のコード変更の影響を受けないよう inline で保持する。
# ---------------------------------------------------------------------------

_KNOTS: dict[str, tuple[tuple[float, float], ...]] = {
    "aesthetic_shadow_v1": ((0.0, 0.0), (0.27, 3.0), (0.45, 8.0), (0.71, 9.0), (1.0, 10.0)),
    "aesthetic_shadow_v2": ((0.0, 0.0), (0.27, 3.0), (0.45, 8.0), (0.71, 9.0), (1.0, 10.0)),
    "cafe_aesthetic": ((0.0, 0.0), (0.5, 6.0), (1.0, 8.0)),
    "WaifuAesthetic": ((0.0, 0.0), (1.0, 10.0)),
    "ImprovedAesthetic": ((0.0, 0.0), (1.0, 1.0), (10.0, 10.0)),
}


def _clamp(v: float) -> float:
    return max(0.0, min(10.0, v))


def _piecewise(knots: tuple[tuple[float, float], ...], raw: float) -> float:
    """区分線形補間。knots は raw 昇順・display 単調非減少を前提とする。"""
    first_raw, first_disp = knots[0]
    if raw <= first_raw:
        return first_disp
    last_raw, last_disp = knots[-1]
    if raw >= last_raw:
        return last_disp
    for i in range(len(knots) - 1):
        x0, y0 = knots[i]
        x1, y1 = knots[i + 1]
        if x0 <= raw <= x1:
            if x1 == x0:
                return y1
            return y0 + (raw - x0) / (x1 - x0) * (y1 - y0)
    return last_disp


def _calibrate(model_name: str | None, raw: float, is_manually_edited: bool) -> float:
    """raw スコアを 0-10 表示スコアへ変換する (migration 用 inline 実装)。"""
    if is_manually_edited:
        # 手動編集値は save 時に既に 0-10 スケールで格納されている
        return _clamp(raw)

    if model_name is None:
        return _clamp(raw * 10.0)

    knots = _KNOTS.get(model_name)
    if knots is not None:
        return _clamp(_piecewise(knots, raw))

    # WebAPI Vision LLM: LiteLLM provider/model 形式 (slash あり) → identity + clamp
    if "/" in model_name:
        return _clamp(raw)

    # 完全未知モデル: 0-1 仮定 fallback
    return _clamp(raw * 10.0)


# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn = op.get_bind()

    # scores テーブルが存在しない最小スキーマ (一部マイグレーションテストの stale DB) は no-op
    if "scores" not in _sa_inspect(conn).get_table_names():
        return

    op.add_column("scores", sa.Column("display_score", sa.Float(), nullable=True))

    # 既存行を取得してバックフィル
    rows = conn.execute(
        text(
            "SELECT s.id, s.score, s.is_edited_manually, m.name"
            " FROM scores s LEFT JOIN models m ON s.model_id = m.id"
        )
    ).fetchall()

    for row in rows:
        score_id, raw_score, is_edited, model_name = row
        display = _calibrate(model_name, float(raw_score), bool(is_edited))
        conn.execute(
            text("UPDATE scores SET display_score = :ds WHERE id = :sid"),
            {"ds": display, "sid": score_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "scores" not in _sa_inspect(conn).get_table_names():
        return
    op.drop_column("scores", "display_score")
