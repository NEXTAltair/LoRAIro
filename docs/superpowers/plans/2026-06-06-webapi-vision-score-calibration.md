# WebAPI/Vision LLM スコア表示尺度修正 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WebAPI/Vision LLM が返す 0-10 スケールのスコア(`openai/o1: 7.5` など)が `10.0` に張り付くバグを修正する。あわせて、aesthetic scorer より低い重みで表示スコア平均へ組み込む。

**Architecture:** `score_scaler.py` に、`"/" in model` で WebAPI モデルを識別する関数と `display_weight_for()` を追加する。`calibrate_to_display` の未知モデル向けフォールバックを分岐させ、WebAPI には恒等変換(`_clamp_display(raw)`)を適用する。さらに `_derive_display_score` を加重平均へ変更する。

**Tech Stack:** Python 3.13、SQLAlchemy ORM、pytest、`src/lorairo/domain/score_scaler.py`、`src/lorairo/database/repository/image.py`

---

## 背景と制約

- `WebApiAnnotator._format_predictions` は常に `scores = {"overall": float_score}` を生成する。`BASE_PROMPT` が LLM に 1.00–10.00 スケールを指定するため、WebAPI スコアは 0-10 スケールとなる。
- 現在の未知モデル向けフォールバックは `raw * 10` を 0-10 へクランプする処理である。そのため、`7.5 * 10 = 75` が `10.0` に張り付くバグが発生している。
- **識別方針:** `"/" in model_name` を LiteLLM の `provider/model` 形式(Phase 1.10 以降)とみなす。旧形式名(`claude-3-5-sonnet-20240620` など、スラッシュなし)は識別できないため、引き続きフォールバック対象とする。この制限は許容済みである。
- DB の表示スコアは読み込み時に導出(read-time derived)されるため、コード修正のみで即座に正常化する。再保存は不要である。
- `score_scaler.py` は Qt 非依存かつ外部ライブラリ非依存の純粋なドメイン関数群として維持する。

## ファイル構成

| ファイル | 変更内容 |
|---|---|
| `src/lorairo/domain/score_scaler.py` | 1. `_is_webapi_vision_scorer` の追加、2. `WEBAPI_VISION_SCORE_WEIGHT` 定数の追加、3. `calibrate_to_display` の WebAPI 分岐追加、4. `display_weight_for` の追加、5. `is_ai_scored_model` と `positive_key_for` の WebAPI 対応 |
| `src/lorairo/database/repository/image.py` | `_derive_display_score` の加重平均化、`display_weight_for` のインポート追加 |
| `tests/unit/domain/test_score_scaler.py` | WebAPI モデルのテストケース追加 |
| `tests/unit/database/test_db_repository_annotations.py` | WebAPI スコア混在時の加重平均テスト追加 |

---

## Task 1: `score_scaler.py` — WebAPI 識別とキャリブレーション修正

**Files:**
- Modify: `src/lorairo/domain/score_scaler.py`

### 追加・変更するコードの概要

`_is_webapi_vision_scorer`、`WEBAPI_VISION_SCORE_WEIGHT`、`display_weight_for` を追加する。あわせて、`calibrate_to_display`、`is_ai_scored_model`、`positive_key_for` を WebAPI 対応へ変更する。

- [ ] **Step 1: `test_score_scaler.py` に WebAPI 向けの失敗するテストを追記する**

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

- [ ] **Step 2: テストが失敗することを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py -k "webapi or display_weight" -v
```

期待結果: `ImportError` または `AssertionError` で失敗する。

- [ ] **Step 3: `score_scaler.py` に変更を実装する**

`src/lorairo/domain/score_scaler.py` を開き、以下の 6 点を追加・変更する。

**1. モジュールレベル定数の追加**(既存の `DISPLAY_MAX` 定義の直後)

```python
WEBAPI_VISION_SCORE_WEIGHT: float = 0.5
"""WebAPI Vision LLM スコアの表示平均重み。
aesthetic scorer (重み 1.0) より信頼度が低いため割り引く。"""
```

**2. 識別関数の追加**(`_AI_SCORE_SPEC` 辞書の直後)

```python
def _is_webapi_vision_scorer(model: str) -> bool:
    """LiteLLM ``provider/model`` 形式 (slash あり) を WebAPI Vision scorer と判定する。

    Phase 1.10 以降に登録されたモデルは常に slash を持つ。旧形式名
    (``claude-3-5-sonnet-20240620`` 等、slash なし) は識別対象外で
    未知モデル fallback になる — これは許容された制限。
    """
    return "/" in model
```

**3. `is_ai_scored_model` の変更**

```python
def is_ai_scored_model(model: str) -> bool:
    """``model`` が AI 数値スコア (表示尺度変換対象) を出すモデルか判定する。"""
    return model in _AI_SCORE_SPEC or _is_webapi_vision_scorer(model)
```

**4. `positive_key_for` の変更**

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

**5. `calibrate_to_display` のフォールバック分岐の変更**(既存 `spec is None` のブロック)

```python
    if spec is None:
        if _is_webapi_vision_scorer(model):
            # WebAPI Vision LLM は BASE_PROMPT で 0-10 スケールを返す → identity + clamp
            return _clamp_display(raw)
        # 完全未知モデル: range 不明のため 0-1 を仮定した線形 0-10 マッピング。
        return _clamp_display(raw * DISPLAY_MAX)
```

**6. `display_weight_for` 関数の追加**(`known_models` の前)

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

- [ ] **Step 4: テストが通ることを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py -v
```

期待結果: 全テストが通る。

- [ ] **Step 5: コミットする**

```bash
git add src/lorairo/domain/score_scaler.py tests/unit/domain/test_score_scaler.py
git commit -m "fix: WebAPI Vision LLM スコア calibration identity + display_weight_for (#644)"
```

---

## Task 2: `image.py` — `_derive_display_score` を加重平均へ変更

**Files:**
- Modify: `src/lorairo/database/repository/image.py`
- Test: `tests/unit/database/test_db_repository_annotations.py`

- [ ] **Step 1: `test_db_repository_annotations.py` に WebAPI 混在テストを追記する**

`TestDeriveDisplayScore` クラスの末尾(`test_legacy_two_rows_same_model_uses_latest` の後)に以下を追加する。

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

- [ ] **Step 2: テストが失敗することを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/database/test_db_repository_annotations.py::TestDeriveDisplayScore -v
```

期待結果: 新規 3 テストのうち `test_webapi_score_identity_and_weighted` は `7.5` ではなく `10.0` が返り失敗する。他の 2 テストも失敗する。

- [ ] **Step 3: `image.py` のインポートと `_derive_display_score` を変更する**

**インポート行の変更**(ファイル先頭付近)

変更前:
```python
from ...domain.score_scaler import calibrate_to_display
```

変更後:
```python
from ...domain.score_scaler import calibrate_to_display, display_weight_for
```

**`_derive_display_score` の `display_values` 以降のロジック変更**

変更前:
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

- [ ] **Step 4: 新規テストと既存テストがすべて通ることを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/database/test_db_repository_annotations.py::TestDeriveDisplayScore -v
```

期待結果:
- 既存テストはすべて通る(aesthetic scorer のみであれば重みが 1.0 のため平均値は変わらない)。
- 新規テストもすべて通る。

- [ ] **Step 5: ドメイン全体のテストでリグレッションがないことを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/ tests/unit/database/ -v
```

期待結果: 全テストが通る。

- [ ] **Step 6: コミットする**

```bash
git add src/lorairo/database/repository/image.py \
        tests/unit/database/test_db_repository_annotations.py
git commit -m "fix: _derive_display_score を WebAPI スコア weighted average に変更 (#644)"
```

---

## Task 3: `annotation_save_service.py` — WebAPI モデルの positive key 保存を明示化

**Files:**
- Modify: `src/lorairo/services/annotation_save_service.py`

> **背景:** 現状では `is_ai_scored_model("openai/o1")` が `False` を返すため、WebAPI スコアの全キーを保存する経路に入る。Task 1 の修正により `is_ai_scored_model("openai/o1")` が `True` になると、`_append_scores` は `"overall"` キーのみを保存する経路へ切り替わる。DB に保存される値は変わらないが、処理経路の一貫性を確保できる。

- [ ] **Step 1: `_append_scores` の動作確認テストを追記する**

`tests/unit/services/` 配下に `_append_scores` を直接テストする既存ファイルがある場合はそこへ追記する。見つからない場合は `test_annotation_save_service.py` の既存テストクラスへ追加する。

```bash
cd /workspaces/LoRAIro
find tests/ -name "*annotation_save*" -o -name "*save_service*" 2>/dev/null
```

見つかったファイル(例: `tests/unit/services/test_annotation_save_service.py`)に以下を追記する。

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

> **注:** フィクスチャ名は対象ファイルの既存フィクスチャに合わせる。`_append_scores` がプライベートメソッドで直接テストが困難な場合は、Step 1 をスキップして Step 2 へ進む。

- [ ] **Step 2: CI 相当フィルタでリグレッションがないことを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

期待結果: 全テストが通る。

- [ ] **Step 3: コミットする**

```bash
git add tests/unit/services/test_annotation_save_service.py
git commit -m "test: WebAPI annotation_save_service _append_scores overall key 保存確認 (#644)"
```

---

## Task 4: `MAPPING_VERSION` を更新して drift-guard を反映

**Files:**
- Modify: `src/lorairo/domain/score_scaler.py`

> `calibrate_to_display` のマッピングロジックを変更したため、モジュール docstring の規約に従って `MAPPING_VERSION` を更新する。

- [ ] **Step 1: `MAPPING_VERSION` を変更する**

`src/lorairo/domain/score_scaler.py` の先頭付近を以下のように変更する。

変更前:
```python
MAPPING_VERSION: str = "score-scaler-v1"
```

変更後:
```python
MAPPING_VERSION: str = "score-scaler-v2"
```

- [ ] **Step 2: `test_mapping_version_is_set` が引き続き通ることを確認する**

```bash
cd /workspaces/LoRAIro
uv run pytest tests/unit/domain/test_score_scaler.py::test_mapping_version_is_set -v
```

期待結果: テストが通る。

- [ ] **Step 3: CI 相当フィルタで全テストを実行する**

```bash
cd /workspaces/LoRAIro
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q
```

期待結果: 全テストが通る。

- [ ] **Step 4: コミットする**

```bash
git add src/lorairo/domain/score_scaler.py
git commit -m "chore: MAPPING_VERSION を score-scaler-v2 へ bump (#644)"
```

---

## 制限事項

本修正で対応できる範囲と対応できない範囲を以下に示す。

| 状況 | 結果 |
|---|---|
| `openai/o1`(スラッシュあり、新形式) | ✅ `7.5` がそのまま `7.5` に正常化される |
| `anthropic/claude-3-5-sonnet-20241022`(スラッシュあり) | ✅ 正常化される |
| `claude-3-5-sonnet-20240620`(スラッシュなし、旧形式) | ❌ 引き続き `7.5` が `10.0` になる(Phase 1.10 以前の登録行) |
| ローカル ML scorer(`aesthetic_shadow_v1` など) | ✅ 従来のノット補間を維持する |

旧形式名の行(約 180 行)は、モデルを再選択して再アノテーションし、新形式 ID で保存し直すことで正常化される。

---

## 動作確認チェックリスト

実装完了後に、以下の項目を手動で確認する。

1. `main_dataset_20250707_001` の `image_id 18254`(`model=openai/o1, score=7.5`)で、表示スコアが `7.5` になっていること。
2. aesthetic scorer のみを持つ画像の `score_value` が変わっていないこと(既存テストで保護)。
3. aesthetic scorer と WebAPI が混在する画像の `score_value` が加重平均になっていること。
