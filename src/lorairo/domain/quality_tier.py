"""Unified Dataset Quality Tier mapping (ADR 0029).

scorer 由来の categorical ``score_labels`` と manual score を、LoRAIro 独自の
統一品質 tier (`masterpiece` ... `worst quality` + sentinel `no score` / `unknown`)
に正規化する。raw annotation は変更せず、derived view として計算する。

集約規約は **median + is_unanimous hybrid**:

- ``tier``: known votes の順序中央値 (tie は higher 寄り = ``sorted[len // 2]``)
- ``is_unanimous``: 全 known votes が同 tier かつ unknown vote なし

filter ロジック (out-of-scope) は ``QualityTier`` の ordinal 比較で実装する。
sentinel 値は ordinal 比較に乗らないため、filter 側で別途扱う。

新 scorer (例: ``WaifuAesthetic``) を mapping に追加する場合:

1. ``_SCORE_LABEL_TO_TIER`` に ``(model_name, label)`` 行を追加
2. mapping を変更する場合は ``MAPPING_VERSION`` を bump
3. 該当する unit test を追加 (``tests/unit/domain/test_quality_tier.py``)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

MAPPING_VERSION: str = "quality-tier-v1"
"""mapping table の version 識別子。mapping を変更する際に bump する。"""

NO_SCORE: str = "no score"
"""score 系 annotation が存在しない sentinel tier。"""

UNKNOWN: str = "unknown"
"""raw value は存在するが mapping 未定義の sentinel tier。"""

MANUAL_MODEL_NAME: str = "manual"
"""manual score の vote 出力で使う model 名 sentinel。"""


class QualityTier(IntEnum):
    """順序尺度の品質 tier。値が高いほど高品質。"""

    MASTERPIECE = 6
    BEST_QUALITY = 5
    GOOD_QUALITY = 4
    NORMAL_QUALITY = 3
    LOW_QUALITY = 2
    WORST_QUALITY = 1

    @property
    def label(self) -> str:
        """user-facing label (例: ``"best quality"``)。"""
        return _TIER_TO_LABEL[self]


_TIER_TO_LABEL: dict[QualityTier, str] = {
    QualityTier.MASTERPIECE: "masterpiece",
    QualityTier.BEST_QUALITY: "best quality",
    QualityTier.GOOD_QUALITY: "good quality",
    QualityTier.NORMAL_QUALITY: "normal quality",
    QualityTier.LOW_QUALITY: "low quality",
    QualityTier.WORST_QUALITY: "worst quality",
}

_LABEL_TO_TIER: dict[str, QualityTier] = {label: tier for tier, label in _TIER_TO_LABEL.items()}

# (model_name, raw_label) -> QualityTier
_SCORE_LABEL_TO_TIER: dict[tuple[str, str], QualityTier] = {
    ("aesthetic_shadow_v1", "very aesthetic"): QualityTier.MASTERPIECE,
    ("aesthetic_shadow_v1", "aesthetic"): QualityTier.BEST_QUALITY,
    ("aesthetic_shadow_v1", "displeasing"): QualityTier.LOW_QUALITY,
    ("aesthetic_shadow_v1", "very displeasing"): QualityTier.WORST_QUALITY,
    ("aesthetic_shadow_v2", "very aesthetic"): QualityTier.MASTERPIECE,
    ("aesthetic_shadow_v2", "aesthetic"): QualityTier.BEST_QUALITY,
    ("aesthetic_shadow_v2", "displeasing"): QualityTier.LOW_QUALITY,
    ("aesthetic_shadow_v2", "very displeasing"): QualityTier.WORST_QUALITY,
    ("cafe_aesthetic", "aesthetic"): QualityTier.GOOD_QUALITY,
    ("cafe_aesthetic", "not_aesthetic"): QualityTier.LOW_QUALITY,
}


def map_score_label_to_tier(model: str, label: str) -> QualityTier | None:
    """scorer raw label を tier に変換する。未定義は ``None``。"""
    return _SCORE_LABEL_TO_TIER.get((model, label))


def map_manual_score_to_tier(score: float) -> QualityTier | None:
    """manual score (0.00-10.00) を tier に変換する。範囲外は ``None``。

    ADR 0029 の境界仕様:

    - 9.00 ≤ score ≤ 10.00 -> masterpiece
    - 8.00 ≤ score < 9.00 -> best quality
    - 6.00 ≤ score < 8.00 -> good quality
    - 5.00 ≤ score < 6.00 -> normal quality
    - 3.00 ≤ score < 5.00 -> low quality
    - 0.00 ≤ score < 3.00 -> worst quality
    """
    if score < 0.0 or score > 10.0:
        return None
    if score >= 9.0:
        return QualityTier.MASTERPIECE
    if score >= 8.0:
        return QualityTier.BEST_QUALITY
    if score >= 6.0:
        return QualityTier.GOOD_QUALITY
    if score >= 5.0:
        return QualityTier.NORMAL_QUALITY
    if score >= 3.0:
        return QualityTier.LOW_QUALITY
    return QualityTier.WORST_QUALITY


def tier_label_to_value(label: str) -> QualityTier | None:
    """user-facing tier label を ``QualityTier`` enum に逆変換する。

    filter follow-up で ``min_tier: "good quality"`` を ordinal 比較する用途。
    sentinel (``"no score"`` / ``"unknown"``) には ordinal 値がないので ``None``。
    """
    return _LABEL_TO_TIER.get(label)


@dataclass
class _Vote:
    """compute_quality_summary 内部の vote 表現。"""

    source: str  # "score_label" | "manual_score"
    model: str  # scorer model 名、manual score は MANUAL_MODEL_NAME
    raw_label: str | None  # score_label の場合の raw label
    raw_score: float | None  # manual_score の場合の raw 数値
    tier: QualityTier | None  # None = mapping 未定義


def compute_quality_summary(
    score_labels: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> dict[str, Any]:
    """raw annotation から quality_summary を計算する (ADR 0029)。

    Args:
        score_labels: ``{"model": str, "label": str, ...}`` の list。
            通常 ``get_image_annotations`` 戻り値の ``"score_labels"`` キー。
        scores: ``{"score": float, "is_edited_manually": bool, ...}`` の list。
            ``is_edited_manually == True`` のエントリのみ manual score とみなす
            (AI scorer numeric は model 間 scale 不揃いのため tier 化しない)。

    Returns:
        次の形状の dict::

            {
                "mapping_version": str,
                "tier": str,                  # tier label or "no score" / "unknown"
                "is_unanimous": bool,
                "known_count": int,
                "unknown_count": int,
                "no_score": bool,
                "votes": list[dict],          # 各 vote の詳細
            }
    """
    votes: list[_Vote] = []

    for sl in score_labels:
        model = sl.get("model", "")
        label = sl.get("label", "")
        tier = map_score_label_to_tier(model, label)
        votes.append(_Vote(source="score_label", model=model, raw_label=label, raw_score=None, tier=tier))

    for sc in scores:
        if not sc.get("is_edited_manually"):
            continue
        raw_score = sc.get("score")
        if raw_score is None:
            continue
        score_value = float(raw_score)
        tier = map_manual_score_to_tier(score_value)
        votes.append(
            _Vote(
                source="manual_score",
                model=MANUAL_MODEL_NAME,
                raw_label=None,
                raw_score=score_value,
                tier=tier,
            )
        )

    serialized_votes = [_serialize_vote(v) for v in votes]
    known_votes = [v for v in votes if v.tier is not None]
    unknown_count = sum(1 for v in votes if v.tier is None)

    if not votes:
        return {
            "mapping_version": MAPPING_VERSION,
            "tier": NO_SCORE,
            "is_unanimous": False,
            "known_count": 0,
            "unknown_count": 0,
            "no_score": True,
            "votes": [],
        }

    if not known_votes:
        return {
            "mapping_version": MAPPING_VERSION,
            "tier": UNKNOWN,
            "is_unanimous": False,
            "known_count": 0,
            "unknown_count": unknown_count,
            "no_score": False,
            "votes": serialized_votes,
        }

    # median (tie は higher 寄り)
    sorted_tiers = sorted([v.tier for v in known_votes if v.tier is not None])
    median_tier = sorted_tiers[len(sorted_tiers) // 2]

    is_unanimous = len({v.tier for v in known_votes}) == 1 and unknown_count == 0

    return {
        "mapping_version": MAPPING_VERSION,
        "tier": median_tier.label,
        "is_unanimous": is_unanimous,
        "known_count": len(known_votes),
        "unknown_count": unknown_count,
        "no_score": False,
        "votes": serialized_votes,
    }


def _serialize_vote(v: _Vote) -> dict[str, Any]:
    """vote を JSON-safe dict に変換する。"""
    out: dict[str, Any] = {
        "model": v.model,
        "source": v.source,
        "quality_tier": v.tier.label if v.tier is not None else UNKNOWN,
    }
    if v.raw_label is not None:
        out["raw_label"] = v.raw_label
    if v.raw_score is not None:
        out["raw_score"] = v.raw_score
    return out
