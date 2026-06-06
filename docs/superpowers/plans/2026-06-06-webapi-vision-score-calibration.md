# WebAPI/Vision LLM スコア表示尺度修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WebAPI/Vision LLM が返す 0-10 スケールのスコア (`openai/o1: 7.5` 等) が `10.0` に張り付くバグを修正し、aesthetic scorer より低い重みで表示スコア平均に組み込む。

**Architecture:** `score_scaler.py` に `"/" in model` でWebAPI モデルを識別する関数と `display_weight_for()` を追加。`calibrate_to_display` の未知モデル fallback を分岐させ、WebAPI には identity (`_clamp_display(raw)`) を適用。`_derive_display_score` を weighted average に変更。

**Tech Stack:** Python 3.13, SQLAlchemy ORM, pytest, `src/lorairo/domain/score_scaler.py`, `src/lorairo/database/repository/image.py`

---

## 背景・制約

- `WebApiAnnotator._format_predictions` は常に `scores = {"overall": float_score}` を生成し、`BASE_PROMPT` が LLM に 1.00–10.00 スケールを指定するため、WebAPI スコアは 0-10 スケール
- 現在の未知モデル fallback: `raw * 10 → clamp(0-10)` → `7.5 * 10 = 75 → 10.0` (バグ)
- **識別方針**: `"/" in model_name` = LiteLLM `provider/model` 形式 (Phase 1.10+)。旧形式名 (`claude-3-5-sonnet-20240620` 等、スラッシュなし) は識別不能で引き続き fallback。これは許容済み
- DB は read-time derived なのでコード修正のみで即正常化（再保存不要）
- `score_scaler.py` は Qt フリー・lib 依存なしの純粋ドメイン関数群の方針を維持

## ファイル構成

| ファイル | 変更内容 |
|---|---|
| `src/lorairo/domain/score_scaler.py` | ① `_is_webapi_vision_scorer` 追加、② `WEBAPI_VISION_SCORE_WEIGHT` 定数、③ `calibrate_to_display` WebAPI 分岐、④ `display_weight_for` 追加、⑤ `is_ai_scored_model` / `positive_key_for` WebAPI 対応 |
| `src/lorairo/database/repository/image.py` | `_derive_display_score` を weighted average に変更、`display_weight_for` import 追加 |
| `tests/unit/domain/test_score_scaler.py` | WebAPI モデルのテストケース追加 |
| `tests/unit/database/test_db_repository_annotations.py` | WebAPI スコア混在時の weighted average テスト追加 |

---

## Task 1: `score_scaler.py` — WebAPI 識別 + calibration 修正

**Files:**
- Modify: `src/lorairo/domain/score_scaler.py`

### 追加・変更するコードの概要

`_is_webapi_vision_scorer`、`WEBAPI_VISION_SCORE_WEIGHT`、`display_weight_for` を追加。
`calibrate_to_display`・`is_ai_scored_model`・`positive_key_for` を WebAPI 対応に変更。

- [ ] **Step 1: `test_score_scaler.py` に WebAPI 向け failing test を追記**

```python
# tests/unit/domain/test_score_scaler.py の末尾に追加

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
    from lorairo.domain.score_scaler import WEBAPI_VISION_SCORE_WEIGHT, display_weight_for

    assert display_weight_for("openai/o1") == pytest.approx(WEBAPI_VISION_SCORE_WEIGHT)
    assert display_weight_for("anthropic/claude-3-5-sonnet-20241022") == pytest.approx(
        WEBAPI_VISION_SCORE_WEIGHT
    )


@pytest.mark.unit
def test_display_weight_for_local_scorer_is_one() -> None:
    """ローカル ML scorer (aesthetic 系) の重みは 1.0。"""
    from lorairo.domain.score_scaler import display_weight_for

    assert display_weight_for("aesthetic_shadow_v1") == pytest.approx(1.0)
    assert display_weight_for("cafe_aesthetic") == pytest.approx(1.0)
    assert display_weight_for("WaifuAesthetic") == pytest.approx(1.0)
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py -k "webapi or display_weight" -v
```

期待: `ImportError` または `AssertionError` で FAIL

- [ ] **Step 3: `score_scaler.py` に変更を実装**

`src/lorairo/domain/score_scaler.py` を開き、以下を追加・変更する。

**① module-level に定数追加** (既存の `DISPLAY_MAX` 定義の直後):

```python
WEBAPI_VISION_SCORE_WEIGHT: float = 0.5
"""WebAPI Vision LLM スコアの表示平均重み。
aesthetic scorer (重み 1.0) より信頼度が低いため割り引く。"""
```

**② `_AI_SCORE_SPEC` dict の直後に識別関数追加**:

```python
def _is_webapi_vision_scorer(model: str) -> bool:
    """LiteLLM ``provider/model`` 形式 (slash あり) を WebAPI Vision scorer と判定する。

    Phase 1.10 以降に登録されたモデルは常に slash を持つ。旧形式名
    (``claude-3-5-sonnet-20240620`` 等、slash なし) は識別対象外で
    未知モデル fallback になる — これは許容された制限。
    """
    return "/" in model
```

**③ `is_ai_scored_model` を変更**:

```python
def is_ai_scored_model(model: str) -> bool:
    """``model`` が AI 数値スコア (表示尺度変換対象) を出すモデルか判定する。"""
    return model in _AI_SCORE_SPEC or _is_webapi_vision_scorer(model)
```

**④ `positive_key_for` を変更**:

```python
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
```

**⑤ `calibrate_to_display` の fallback 分岐を変更** (既存 `spec is None` のブロック):

```python
    if spec is None:
        if _is_webapi_vision_scorer(model):
            # WebAPI Vision LLM は BASE_PROMPT で 0-10 スケールを返す → identity + clamp
            return _clamp_display(raw)
        # 完全未知モデル: range 不明のため 0-1 を仮定した線形 0-10 マッピング。
        return _clamp_display(raw * DISPLAY_MAX)
```

**⑥ `display_weight_for` 関数を追加** (`known_models` の前):

```python
def display_weight_for(model: str) -> float:
    """``model`` の表示スコア平均における重みを返す。

    WebAPI Vision LLM は aesthetic scorer より判定信頼度が低いため
    ``WEBAPI_VISION_SCORE_WEIGHT`` (< 1.0) で割り引く。
    既知の aesthetic scorer および未知モデルは重み 1.0。
    """
    if _is_webapi_vision_scorer(model):
        return WEBAPI_VISION_SCORE_WEIGHT
    return 1.0
```

- [ ] **Step 4: テストがパスすることを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py -v
```

期待: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/domain/score_scaler.py tests/unit/domain/test_score_scaler.py
git commit -m "fix: WebAPI Vision LLM スコア calibration identity + display_weight_for (#644)"
```

---

## Task 2: `image.py` — `_derive_display_score` を weighted average に変更

**Files:**
- Modify: `src/lorairo/database/repository/image.py`
- Test: `tests/unit/database/test_db_repository_annotations.py`

- [ ] **Step 1: `test_db_repository_annotations.py` に WebAPI 混在テストを追記**

`TestDeriveDisplayScore` クラスの末尾（`test_legacy_two_rows_same_model_uses_latest` の後）に追加:

```python
    @pytest.mark.unit
    def test_webapi_score_identity_and_weighted(self):
        """WebAPI モデル (slash 形式) のスコアは identity 変換かつ重み 0.5 で組み込まれる。"""
        from lorairo.domain.score_scaler import WEBAPI_VISION_SCORE_WEIGHT

        image = Mock(spec=Image)
        image.scores = [
            # WebAPI モデル: 生値 7.5 → calibrate → 7.5 (identity), weight=0.5
            _score_row(7.5, "openai/o1", is_manual=False, created_at=datetime(2025, 1, 1), model_id=10),
        ]
        assert ImageRepository._derive_display_score(image) == pytest.approx(7.5)

    @pytest.mark.unit
    def test_webapi_mixed_with_aesthetic_weighted_average(self):
        """aesthetic scorer と WebAPI スコアが混在する場合は weighted average になる。

        cafe_aesthetic: 0.5 → calibrate → 6.0, weight=1.0
        openai/o1: 8.0 → calibrate → 8.0, weight=0.5
        weighted avg = (6.0 * 1.0 + 8.0 * 0.5) / (1.0 + 0.5) = (6.0 + 4.0) / 1.5 = 10.0 / 1.5 ≈ 6.667
        """
        image = Mock(spec=Image)
        image.scores = [
            _score_row(0.5, "cafe_aesthetic", is_manual=False, created_at=datetime(2025, 1, 1), model_id=1),
            _score_row(8.0, "openai/o1", is_manual=False, created_at=datetime(2025, 1, 1), model_id=10),
        ]
        expected = (6.0 * 1.0 + 8.0 * 0.5) / (1.0 + 0.5)
        assert ImageRepository._derive_display_score(image) == pytest.approx(expected)

    @pytest.mark.unit
    def test_webapi_score_clamps_to_display_range(self):
        """WebAPI スコアが 10 超でも clamp される。"""
        image = Mock(spec=Image)
        image.scores = [
            _score_row(12.0, "openai/gpt-4o", is_manual=False, created_at=datetime(2025, 1, 1), model_id=10),
        ]
        assert ImageRepository._derive_display_score(image) == pytest.approx(10.0)
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/database/test_db_repository_annotations.py::TestDeriveDisplayScore -v
```

期待: 新規 3 テストのうち `test_webapi_score_identity_and_weighted` が FAIL (7.5 ではなく 10.0 が返る)、他 2 つも FAIL

- [ ] **Step 3: `image.py` の import と `_derive_display_score` を変更**

**import 行の変更** (ファイル先頭付近):

現在:
```python
from ...domain.score_scaler import calibrate_to_display
```

変更後:
```python
from ...domain.score_scaler import calibrate_to_display, display_weight_for
```

**`_derive_display_score` の `display_values` 以降のロジック変更**:

現在:
```python
        display_values: list[float] = []
        for score_row in latest_by_model.values():
            model_name = score_row.model.name if score_row.model else ""
            display_values.append(calibrate_to_display(model_name, float(score_row.score)))

        if not display_values:
            return 0.0
        return sum(display_values) / len(display_values)
```

変更後:
```python
        weighted_sum: float = 0.0
        total_weight: float = 0.0
        for score_row in latest_by_model.values():
            model_name = score_row.model.name if score_row.model else ""
            value = calibrate_to_display(model_name, float(score_row.score))
            weight = display_weight_for(model_name)
            weighted_sum += value * weight
            total_weight += weight

        if total_weight == 0.0:
            return 0.0
        return weighted_sum / total_weight
```

- [ ] **Step 4: 新規テストと既存テストが全てパスすることを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/database/test_db_repository_annotations.py::TestDeriveDisplayScore -v
```

期待:
- 既存テスト: 全 PASS (aesthetic scorer のみ = weight 1.0 なので平均値は変わらない)
- 新規テスト: 全 PASS

- [ ] **Step 5: ドメイン全体テストでリグレッションがないか確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/ tests/unit/database/ -v
```

期待: 全 PASS

- [ ] **Step 6: コミット**

```bash
git add src/lorairo/database/repository/image.py \
        tests/unit/database/test_db_repository_annotations.py
git commit -m "fix: _derive_display_score を WebAPI スコア weighted average に変更 (#644)"
```

---

## Task 3: `annotation_save_service.py` — WebAPI モデルの positive key 保存を明示化

**Files:**
- Modify: `src/lorairo/services/annotation_save_service.py`

> **背景:** 現在 `is_ai_scored_model("openai/o1")` → False のため、WebAPI scores の全キーを保存する経路に入る。Task 1 の修正で `is_ai_scored_model("openai/o1")` → True になるため、`_append_scores` が "overall" キーのみを保存する経路に切り替わる。DB に入る値は同じだが、経路の一貫性を確保する。

- [ ] **Step 1: `_append_scores` の動作確認テストを追記**

`tests/unit/services/` 以下にすでに `_append_scores` を直接テストするファイルがある場合はそこへ、なければ `test_annotation_save_service.py` の既存テストクラスへ追加する。

```bash
cd /workspaces/LoRAIro
find tests/ -name "*annotation_save*" -o -name "*save_service*" 2>/dev/null
```

見つかったファイル（例: `tests/unit/services/test_annotation_save_service.py`）に追記:

```python
@pytest.mark.unit
def test_append_scores_webapi_saves_overall_key(annotation_save_service_fixture):
    """WebAPI モデル (slash 形式) は 'overall' key のみを保存する。"""
    result: AnnotationsDict = {
        "scores": [], "score_labels": [], "tags": [], "captions": [], "ratings": []
    }
    # WebAPI モデルは scores = {"overall": 8.0} で来る
    annotation_save_service_fixture._append_scores(
        model_id=99,
        scores={"overall": 8.0},
        model_name="openai/o1",
        result=result,
    )
    assert len(result["scores"]) == 1
    assert result["scores"][0]["score"] == pytest.approx(8.0)
    assert result["scores"][0]["model_id"] == 99
```

> **注:** fixture の名前は対象ファイルの既存 fixture に合わせること。もし `_append_scores` が private で直接テストが困難な場合は Step 1 をスキップし Step 2 へ進む。

- [ ] **Step 2: CI-equivalent filter を実行してリグレッションなしを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

期待: 全 PASS

- [ ] **Step 3: コミット**

```bash
git add tests/unit/services/test_annotation_save_service.py
git commit -m "test: WebAPI annotation_save_service _append_scores overall key 保存確認 (#644)"
```

---

## Task 4: `MAPPING_VERSION` を bump して drift-guard を更新

**Files:**
- Modify: `src/lorairo/domain/score_scaler.py`

> `calibrate_to_display` のマッピングロジックを変更したため `MAPPING_VERSION` を bump する (モジュール docstring の規約)。

- [ ] **Step 1: `MAPPING_VERSION` を変更**

`src/lorairo/domain/score_scaler.py` の先頭付近:

現在:
```python
MAPPING_VERSION: str = "score-scaler-v1"
```

変更後:
```python
MAPPING_VERSION: str = "score-scaler-v2"
```

- [ ] **Step 2: `test_mapping_version_is_set` が引き続き PASS することを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py::test_mapping_version_is_set -v
```

期待: PASS

- [ ] **Step 3: 全テストを CI-equivalent filter で実行**

```bash
cd /workspaces/LoRAIro
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

期待: 全 PASS

- [ ] **Step 4: コミット**

```bash
git add src/lorairo/domain/score_scaler.py
git commit -m "chore: MAPPING_VERSION を score-scaler-v2 へ bump (#644)"
```

---

## 制限事項 (ドキュメント)

本修正で対応できる範囲とできない範囲:

| 状況 | 結果 |
|---|---|
| `openai/o1` (slash あり、新形式) | ✅ `7.5 → 7.5` に正常化 |
| `anthropic/claude-3-5-sonnet-20241022` (slash あり) | ✅ 正常化 |
| `claude-3-5-sonnet-20240620` (slash なし、旧形式) | ❌ 引き続き `7.5 → 10.0` (Phase 1.10 以前の登録行) |
| ローカル ML scorer (`aesthetic_shadow_v1` 等) | ✅ 従来の knot 補間を維持 |

旧形式名の行 (~180 行) は再アノテーション (モデル再選択 → 新形式 ID で保存) によって正常化される。

---

## 動作確認チェックリスト

実装完了後に手動で確認:

1. `main_dataset_20250707_001` で `image_id 18254` (`model=openai/o1, score=7.5`) の表示スコアが `7.5` になっていること
2. aesthetic scorer のみを持つ画像の `score_value` が変わっていないこと (既存テスト保護)
3. aesthetic scorer + WebAPI 混在画像の `score_value` が weighted average になっていること
