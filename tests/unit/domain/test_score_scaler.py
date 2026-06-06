"""score_scaler の表示尺度変換 (0-10) ユニットテスト (Issue #626)。"""

from itertools import pairwise

import pytest

from lorairo.domain import score_scaler
from lorairo.domain.score_scaler import (
    DISPLAY_MAX,
    DISPLAY_MIN,
    MAPPING_VERSION,
    WEBAPI_VISION_SCORE_WEIGHT,
    calibrate_to_display,
    display_weight_for,
    is_ai_scored_model,
    positive_key_for,
    select_positive_score,
)


@pytest.mark.unit
def test_mapping_version_is_set() -> None:
    assert isinstance(MAPPING_VERSION, str)
    assert MAPPING_VERSION


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "expected_key"),
    [
        ("aesthetic_shadow_v1", "hq"),
        ("aesthetic_shadow_v2", "hq"),
        ("cafe_aesthetic", "aesthetic"),
        ("WaifuAesthetic", "aesthetic"),
        ("ImprovedAesthetic", "aesthetic"),
    ],
)
def test_positive_key_for_known_models(model: str, expected_key: str) -> None:
    assert positive_key_for(model) == expected_key
    assert is_ai_scored_model(model) is True


@pytest.mark.unit
def test_positive_key_for_unknown_model_returns_none() -> None:
    assert positive_key_for("gpt-4o") is None
    assert is_ai_scored_model("gpt-4o") is False


@pytest.mark.unit
def test_select_positive_score_picks_positive_key() -> None:
    # shadow は hq を採用、lq は無視する
    assert select_positive_score("aesthetic_shadow_v1", {"hq": 0.8, "lq": 0.2}) == 0.8
    # cafe は aesthetic を採用
    assert select_positive_score("cafe_aesthetic", {"aesthetic": 0.6, "not_aesthetic": 0.4}) == 0.6


@pytest.mark.unit
def test_select_positive_score_missing_key_returns_none() -> None:
    assert select_positive_score("aesthetic_shadow_v1", {"lq": 0.2}) is None
    assert select_positive_score("unknown_model", {"aesthetic": 0.5}) is None


# ===== shadow (hq) calibration knot 値 =====


@pytest.mark.unit
@pytest.mark.parametrize("model", ["aesthetic_shadow_v1", "aesthetic_shadow_v2"])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.0, 0.0),
        (0.27, 3.0),
        (0.45, 8.0),
        (0.71, 9.0),
        (1.0, 10.0),
    ],
)
def test_shadow_knot_values(model: str, raw: float, expected: float) -> None:
    assert calibrate_to_display(model, raw) == pytest.approx(expected)


@pytest.mark.unit
def test_shadow_interpolated_midpoint() -> None:
    # 0.27 → 3.0, 0.45 → 8.0 の中間 (0.36) は線形補間で 5.5
    result = calibrate_to_display("aesthetic_shadow_v1", 0.36)
    assert result == pytest.approx(5.5)


# ===== cafe (aesthetic) calibration knot 値 =====


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.0, 0.0),
        (0.5, 6.0),
        (1.0, 8.0),
    ],
)
def test_cafe_knot_values(raw: float, expected: float) -> None:
    assert calibrate_to_display("cafe_aesthetic", raw) == pytest.approx(expected)


@pytest.mark.unit
def test_cafe_interpolated_value() -> None:
    # 0.5 → 6.0, 1.0 → 8.0、0.85 は ratio 0.7 で 7.4
    assert calibrate_to_display("cafe_aesthetic", 0.85) == pytest.approx(7.4)


# ===== waifu (sigmoid 0-1) =====


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.0, 0.0),
        (0.5, 5.0),
        (1.0, 10.0),
    ],
)
def test_waifu_linear_times_ten(raw: float, expected: float) -> None:
    assert calibrate_to_display("WaifuAesthetic", raw) == pytest.approx(expected)


# ===== improved (MOS 1-10 → clamp) =====


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1.0, 1.0),
        (5.5, 5.5),
        (10.0, 10.0),
    ],
)
def test_improved_identity_within_range(raw: float, expected: float) -> None:
    assert calibrate_to_display("ImprovedAesthetic", raw) == pytest.approx(expected)


@pytest.mark.unit
def test_improved_clamps_out_of_range() -> None:
    assert calibrate_to_display("ImprovedAesthetic", -2.0) == pytest.approx(0.0)
    assert calibrate_to_display("ImprovedAesthetic", 15.0) == pytest.approx(10.0)


# ===== 未知 model フォールバック =====


@pytest.mark.unit
def test_unknown_model_linear_fallback() -> None:
    # range 不明のため 0-1 を仮定した線形 0-10
    assert calibrate_to_display("gpt-4o", 0.0) == pytest.approx(0.0)
    assert calibrate_to_display("gpt-4o", 0.5) == pytest.approx(5.0)
    assert calibrate_to_display("gpt-4o", 1.0) == pytest.approx(10.0)


@pytest.mark.unit
def test_unknown_model_clamps() -> None:
    assert calibrate_to_display("gpt-4o", -1.0) == pytest.approx(0.0)
    assert calibrate_to_display("gpt-4o", 2.0) == pytest.approx(10.0)


# ===== 連続性・単調性・範囲 (全 known model) =====


@pytest.mark.unit
@pytest.mark.parametrize("model", sorted(score_scaler.known_models()))
def test_output_within_display_range(model: str) -> None:
    low, high = score_scaler.value_range_for(model)  # type: ignore[misc]
    # range を超える raw も含めてサンプリングし全て 0-10 に収まることを確認
    samples = [low - 1.0, low, (low + high) / 2.0, high, high + 1.0]
    for raw in samples:
        out = calibrate_to_display(model, raw)
        assert DISPLAY_MIN <= out <= DISPLAY_MAX


@pytest.mark.unit
@pytest.mark.parametrize("model", sorted(score_scaler.known_models()))
def test_monotonic_non_decreasing(model: str) -> None:
    low, high = score_scaler.value_range_for(model)  # type: ignore[misc]
    span = high - low
    raws = [low + span * i / 50.0 for i in range(51)]
    outs = [calibrate_to_display(model, r) for r in raws]
    for prev, cur in pairwise(outs):
        assert cur >= prev - 1e-9


@pytest.mark.unit
@pytest.mark.parametrize("model", sorted(score_scaler.known_models()))
def test_continuous_no_large_jumps(model: str) -> None:
    """微小な raw 変化に対して出力が連続 (大きな段差がない) ことを確認する。"""
    low, high = score_scaler.value_range_for(model)  # type: ignore[misc]
    span = high - low
    step = span / 200.0
    raws = [low + step * i for i in range(201)]
    outs = [calibrate_to_display(model, r) for r in raws]
    for prev, cur in pairwise(outs):
        # 1 step での変化は 1.0 表示点未満 (区分線形なので滑らか)
        assert abs(cur - prev) < 1.0


# ===== drift-guard: LoRAIro _AI_SCORE_SPEC ⇄ lib score_scales (iam-lib#144) =====


@pytest.mark.unit
def test_spec_matches_lib_score_scales() -> None:
    """LoRAIro ``_AI_SCORE_SPEC`` の range / positive_key が lib の SSoT と一致するか検証する。

    iam-lib#144 で各 scorer は ``SCORE_SCALE`` (range / higher_is_better) を宣言する。LoRAIro は
    自前テーブルで derived-view 変換するため、両者が drift すると尺度がずれる
    (WaifuAesthetic の値域 1-10↔0-1 取り違えが典型例)。

    ``tests/conftest.py`` が ``image_annotator_lib.model_class`` を torch ロード回避のため
    MagicMock 化するので、本テストは別プロセスで実 scorer クラスの ``SCORE_SCALE`` を JSON
    出力させて照合する。実 lib を import できない環境 (submodule 未取得等) では graceful skip する。
    """
    import json
    import subprocess
    import sys

    probe = (
        "import json\n"
        "from image_annotator_lib.model_class.pipeline_scorers import AestheticShadow, CafePredictor\n"
        "from image_annotator_lib.model_class.scorer_clip import ImprovedAesthetic, WaifuAesthetic\n"
        "classes = {\n"
        "    'aesthetic_shadow_v1': AestheticShadow,\n"
        "    'aesthetic_shadow_v2': AestheticShadow,\n"
        "    'cafe_aesthetic': CafePredictor,\n"
        "    'WaifuAesthetic': WaifuAesthetic,\n"
        "    'ImprovedAesthetic': ImprovedAesthetic,\n"
        "}\n"
        "out = {\n"
        "    name: {k: [list(s.range), s.higher_is_better] for k, s in cls.SCORE_SCALE.items()}\n"
        "    for name, cls in classes.items()\n"
        "}\n"
        "print('SCORE_SCALES_JSON=' + json.dumps(out))\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        pytest.skip(f"real image_annotator_lib unavailable: {result.stderr[-300:]}")

    marker = "SCORE_SCALES_JSON="
    payload = next(
        (line[len(marker) :] for line in result.stdout.splitlines() if line.startswith(marker)),
        None,
    )
    assert payload is not None, f"probe output missing JSON marker: {result.stdout[-300:]}"
    lib_specs = json.loads(payload)

    for model, scale_map in lib_specs.items():
        positive_keys = [key for key, (_range, higher) in scale_map.items() if higher]
        key = positive_key_for(model)
        assert key in positive_keys, f"{model}: positive key {key!r} not in lib {positive_keys}"
        lib_range = tuple(scale_map[key][0])
        assert score_scaler.value_range_for(model) == lib_range, (
            f"{model}: LoRAIro range {score_scaler.value_range_for(model)} != lib {lib_range}"
        )


# ===== WebAPI / Vision LLM scorer =====


@pytest.mark.unit
def test_webapi_slash_model_identity() -> None:
    """WebAPI モデル (slash 形式) は 0-10 を identity で返す。"""
    assert calibrate_to_display("openai/o1", 7.5) == pytest.approx(7.5)
    assert calibrate_to_display("anthropic/claude-3-5-sonnet-20241022", 8.0) == pytest.approx(8.0)
    assert calibrate_to_display("openai/gpt-4o", 0.0) == pytest.approx(0.0)
    assert calibrate_to_display("openai/gpt-4o", 10.0) == pytest.approx(10.0)


@pytest.mark.unit
def test_webapi_slash_model_clamps() -> None:
    """WebAPI モデルが 0-10 範囲外を返した場合はクランプする。"""
    assert calibrate_to_display("openai/o1", -1.0) == pytest.approx(0.0)
    assert calibrate_to_display("openai/o1", 11.0) == pytest.approx(10.0)


@pytest.mark.unit
def test_non_slash_unknown_model_still_uses_linear_fallback() -> None:
    """スラッシュなし未知モデルは従来どおり 0-1 仮定の線形 fallback。"""
    assert calibrate_to_display("some_local_model", 0.5) == pytest.approx(5.0)
    assert calibrate_to_display("some_local_model", 1.0) == pytest.approx(10.0)


@pytest.mark.unit
def test_is_ai_scored_model_webapi() -> None:
    """slash 形式の WebAPI モデルは is_ai_scored_model が True。"""
    assert is_ai_scored_model("openai/o1") is True
    assert is_ai_scored_model("anthropic/claude-3-haiku-20240307") is True
    assert is_ai_scored_model("openai/gpt-5-nano") is True


@pytest.mark.unit
def test_positive_key_for_webapi_is_overall() -> None:
    """WebAPI モデルの positive key は 'overall'。"""
    assert positive_key_for("openai/o1") == "overall"
    assert positive_key_for("anthropic/claude-3-5-sonnet-20241022") == "overall"


@pytest.mark.unit
def test_display_weight_for_webapi() -> None:
    """WebAPI モデルの表示重みは WEBAPI_VISION_SCORE_WEIGHT (< 1.0)。"""
    assert display_weight_for("openai/o1") == pytest.approx(WEBAPI_VISION_SCORE_WEIGHT)
    assert display_weight_for("anthropic/claude-3-5-sonnet-20241022") == pytest.approx(
        WEBAPI_VISION_SCORE_WEIGHT
    )


@pytest.mark.unit
def test_display_weight_for_local_scorer_is_one() -> None:
    """ローカル ML scorer (aesthetic 系) の重みは 1.0。"""
    assert display_weight_for("aesthetic_shadow_v1") == pytest.approx(1.0)
    assert display_weight_for("cafe_aesthetic") == pytest.approx(1.0)
    assert display_weight_for("WaifuAesthetic") == pytest.approx(1.0)
