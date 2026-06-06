"""AI 数値スコアを手動スライダーと同じ 0.0-10.0 表示尺度へ変換する純粋関数群。

AI アノテーションの数値スコアはモデルごとに値域・意味が異なる
(shadow hq/lq=独立確率, cafe aesthetic=確率, waifu=Sigmoid 0-1,
improved=AVA MOS 1-10)。これを手動スコアと同じ **0.0-10.0** 表示尺度へ
連続・単調な区分線形補間で写像する (Issue #626)。

設計方針:

1. **連続・非線形マッピング**。確率を線形品質と見なさず、Animagine 由来の
   しきい値 (lib の ``SCORE_THRESHOLDS``) を knot にした区分線形補間で
   連続 0-10 を出す。線形 ``*10`` でも 6 段階離散でもない。
2. AI scorer は ``higher_is_better=True`` の positive key 1 個だけを表示尺度の
   入力として扱う (complement の lq / not_aesthetic は表示に使わない)。
3. 既存の品質ティア badge (ADR 0029 ``quality_tier.compute_quality_summary``、
   離散 6 段階) はそのまま維持し、本モジュールは連続 display score を別途提供する。

本モジュールは ``quality_tier`` と同様に lib に依存しない LoRAIro 自前テーブルを
derived-view の SSoT とする (ADR 0029 / 0031 と同じ流儀)。``_AI_SCORE_SPEC`` の
``range`` / ``positive_key`` が lib の ``ScoreScale`` (score_scales) と一致するかは
drift-guard テストで検証する (iam-lib#144 の submodule pin 反映後に有効化)。

新 scorer を追加する場合:

1. ``_AI_SCORE_SPEC`` に行を追加 (positive_key / range / calibration knots)。
2. mapping を変更する場合は ``MAPPING_VERSION`` を bump する。
3. ``tests/unit/domain/test_score_scaler.py`` に対応する境界・連続・単調テストを追加。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

MAPPING_VERSION: str = "score-scaler-v1"
"""calibration table の version 識別子。マッピングを変更する際に bump する。"""

DISPLAY_MIN: float = 0.0
"""表示尺度の下限。手動スライダーと揃える。"""

DISPLAY_MAX: float = 10.0
"""表示尺度の上限。手動スライダーと揃える。"""

WEBAPI_VISION_SCORE_WEIGHT: float = 0.5
"""WebAPI Vision LLM スコアの表示平均重み。
aesthetic scorer (重み 1.0) より信頼度が低いため割り引く。"""


@dataclass(frozen=True)
class _AIScoreSpec:
    """1 scorer の表示尺度変換仕様。

    Attributes:
        positive_key: ``scores`` dict から表示に使う ``higher_is_better=True`` の key。
        value_range: 生値の理論値域 (min, max)。lib の ``ScoreScale.range`` と一致させる。
        knots: 生値 → 表示値 (0-10) の区分線形補間 knot 列。生値昇順かつ
            表示値が単調非減少であること。None の場合は ``value_range`` に基づく
            線形マッピングを行う (フォールバック扱いはしないが特別な calibration なし)。
    """

    positive_key: str
    value_range: tuple[float, float]
    knots: tuple[tuple[float, float], ...] | None = None


# model 名 (= iam-lib registry key) → 表示尺度変換仕様。
# model 名は image-annotator-lib の config / quality_tier._SCORE_LABEL_TO_TIER と揃える。
_AI_SCORE_SPEC: dict[str, _AIScoreSpec] = {
    # aesthetic_shadow (hq): softmax 確率 (0-1)。lib の
    # SCORE_THRESHOLDS={very aesthetic:0.71, aesthetic:0.45, displeasing:0.27} と
    # quality_tier.map_manual_score_to_tier のティア境界を knot にした区分線形補間。
    #   0.27 -> 3.0 (low/worst quality 境界)
    #   0.45 -> 8.0 (aesthetic = best quality 下端)
    #   0.71 -> 9.0 (very aesthetic = masterpiece 下端)
    "aesthetic_shadow_v1": _AIScoreSpec(
        positive_key="hq",
        value_range=(0.0, 1.0),
        knots=((0.0, 0.0), (0.27, 3.0), (0.45, 8.0), (0.71, 9.0), (1.0, 10.0)),
    ),
    "aesthetic_shadow_v2": _AIScoreSpec(
        positive_key="hq",
        value_range=(0.0, 1.0),
        knots=((0.0, 0.0), (0.27, 3.0), (0.45, 8.0), (0.71, 9.0), (1.0, 10.0)),
    ),
    # cafe_aesthetic (aesthetic): softmax 確率 (0-1)。argmax 境界 0.5 を knot にし、
    # aesthetic -> good quality の下端 6.0 を採用する。
    #   0.5 -> 6.0 (aesthetic 判定の下端 = good quality 下端)
    #   1.0 -> 8.0 (best quality 下端、過度な満点付与を避ける)
    "cafe_aesthetic": _AIScoreSpec(
        positive_key="aesthetic",
        value_range=(0.0, 1.0),
        knots=((0.0, 0.0), (0.5, 6.0), (1.0, 8.0)),
    ),
    # WaifuAesthetic (aesthetic): Sigmoid 出力 (0-1)。素直に *10 でクランプ。
    "WaifuAesthetic": _AIScoreSpec(
        positive_key="aesthetic",
        value_range=(0.0, 1.0),
        knots=((0.0, 0.0), (1.0, 10.0)),
    ),
    # ImprovedAesthetic (aesthetic): AVA MOS 1-10 regression。既に表示尺度と同じため
    # clamp のみ。1.0 -> 1.0, 10.0 -> 10.0 の恒等写像 + 範囲外クランプ。
    "ImprovedAesthetic": _AIScoreSpec(
        positive_key="aesthetic",
        value_range=(1.0, 10.0),
        knots=((0.0, 0.0), (1.0, 1.0), (10.0, 10.0)),
    ),
}


def _is_webapi_vision_scorer(model: str) -> bool:
    """LiteLLM ``provider/model`` 形式 (slash あり) を WebAPI Vision scorer と判定する。

    Phase 1.10 以降に登録されたモデルは常に slash を持つ。旧形式名
    (``claude-3-5-sonnet-20240620`` 等、slash なし) は識別対象外で
    未知モデル fallback になる — これは許容された制限。
    """
    return "/" in model


def is_ai_scored_model(model: str) -> bool:
    """``model`` が AI 数値スコア (表示尺度変換対象) を出すモデルか判定する。"""
    return model in _AI_SCORE_SPEC or _is_webapi_vision_scorer(model)


def positive_key_for(model: str) -> str | None:
    """``model`` の positive key (``higher_is_better=True`` の scores key) を返す。

    WebAPI Vision LLM は常に ``"overall"`` キーで単一スコアを返す。
    未知モデル (旧形式 slash なし等) は ``None``。
    """
    spec = _AI_SCORE_SPEC.get(model)
    if spec is not None:
        return spec.positive_key
    if _is_webapi_vision_scorer(model):
        return "overall"
    return None


def select_positive_score(model: str, scores: dict[str, float]) -> float | None:
    """``scores`` から ``model`` の positive key に対応する生値を取り出す。

    Args:
        model: scorer model 名。
        scores: scorer が出力した ``{key: raw_value}`` 辞書。

    Returns:
        positive key の生値。positive key が不明、または ``scores`` に存在しなければ
        ``None``。
    """
    key = positive_key_for(model)
    if key is None:
        return None
    value = scores.get(key)
    return float(value) if value is not None else None


def _clamp_display(value: float) -> float:
    """表示尺度 (0-10) の範囲にクランプする。"""
    return max(DISPLAY_MIN, min(DISPLAY_MAX, value))


def _interpolate(knots: tuple[tuple[float, float], ...], raw: float) -> float:
    """生値 ``raw`` を knot 列で区分線形補間する。

    ``knots`` は生値昇順・表示値単調非減少を前提とする。範囲外は端点で saturate する。
    """
    first_raw, first_disp = knots[0]
    if raw <= first_raw:
        return first_disp
    last_raw, last_disp = knots[-1]
    if raw >= last_raw:
        return last_disp

    for (x0, y0), (x1, y1) in pairwise(knots):
        if x0 <= raw <= x1:
            if x1 == x0:
                return y1
            ratio = (raw - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    # 到達しないはずだが安全側に末端を返す。
    return last_disp


def calibrate_to_display(model: str, raw: float) -> float:
    """scorer の生値 ``raw`` を 0.0-10.0 の連続表示スコアへ変換する。

    変換は連続・単調・区分線形。各モデルの knot は ``_AI_SCORE_SPEC`` を参照
    (根拠は module / テーブル docstring に記載)。未知 model は ``value_range`` 不明の
    ため 0-1 を仮定した線形マッピングをフォールバックとして行う。

    Args:
        model: scorer model 名 (iam-lib registry key)。
        raw: scorer が出力した positive key の生値。

    Returns:
        0.0-10.0 にクランプされた連続表示スコア。
    """
    spec = _AI_SCORE_SPEC.get(model)
    if spec is None:
        if _is_webapi_vision_scorer(model):
            # WebAPI Vision LLM は BASE_PROMPT で 0-10 スケールを返す → identity + clamp
            return _clamp_display(raw)
        # 完全未知モデル: range 不明のため 0-1 を仮定した線形 0-10 マッピング。
        return _clamp_display(raw * DISPLAY_MAX)

    if spec.knots is not None:
        return _clamp_display(_interpolate(spec.knots, raw))

    # knots 未指定: value_range に基づく線形マッピング。
    low, high = spec.value_range
    if high == low:
        return DISPLAY_MIN
    ratio = (raw - low) / (high - low)
    return _clamp_display(ratio * DISPLAY_MAX)


def display_weight_for(model: str) -> float:
    """``model`` の表示スコア平均における重みを返す。

    WebAPI Vision LLM は aesthetic scorer より判定信頼度が低いため
    ``WEBAPI_VISION_SCORE_WEIGHT`` (< 1.0) で割り引く。
    既知の aesthetic scorer および未知モデルは重み 1.0。
    """
    if _is_webapi_vision_scorer(model):
        return WEBAPI_VISION_SCORE_WEIGHT
    return 1.0


def value_range_for(model: str) -> tuple[float, float] | None:
    """``model`` の生値理論値域を返す。drift-guard テスト用。未知 model は ``None``。"""
    spec = _AI_SCORE_SPEC.get(model)
    return spec.value_range if spec is not None else None


def known_models() -> frozenset[str]:
    """表示尺度変換が定義済みの model 名集合を返す。drift-guard テスト用。"""
    return frozenset(_AI_SCORE_SPEC.keys())
