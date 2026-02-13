# Plan: jazzy-greeting-willow

**Created**: 2026-02-11 04:37:40
**Source**: plan_mode
**Original File**: jazzy-greeting-willow.md
**Status**: planning

---

# スコアラモデルのスコア抽出修正計画

## Context

スコアラモデル（AestheticShadow, CafePredictor, ImprovedAesthetic等）の実行結果で、数値スコアがDBに保存されず、サマリーダイアログにも「タグ1」としか表示されない問題を修正する。

**根本原因**: ライブラリの旧形式 `AnnotationResult` dict には `scores` キーが存在せず、スコアデータは `formatted_output` に埋もれている。`_convert_to_annotations_dict()` は `formatted_output` を見ていないため、スコアが失われる。

## モデルタイプ別の結果形式

| モデルタイプ | 結果型 | `formatted_output` | `scores`キー |
|---|---|---|---|
| Pipeline (AestheticShadow) | dict | `{"hq": 0.9, "lq": 0.1}` | **なし** |
| Pipeline (CafePredictor) | dict | `0.67` (float) | **なし** |
| CLIP (ImprovedAesthetic) | dict | `UnifiedAnnotationResult(scores={"aesthetic": 5.2})` | **なし** |
| WebAPI (GPT, Claude) | Pydantic model | N/A | **あり** ✓ |

## 実装計画

### Step 1: `_extract_scores_from_formatted_output` 追加

**ファイル**: `src/lorairo/gui/workers/annotation_worker.py`
**位置**: `_extract_field()` の直後（line 449付近）

新規 staticmethod を追加。`formatted_output` の型に応じてスコア辞書を返す:

```python
@staticmethod
def _extract_scores_from_formatted_output(formatted_output: Any) -> dict[str, float] | None:
```

- `UnifiedAnnotationResult` (CLIP) → `.scores` フィールド使用
- `dict` with `"hq"` key (AestheticShadow) → `{"aesthetic": hq値}`
- `float`/`int` (CafePredictor) → `{"aesthetic": float値}`
- その他 → `None`

### Step 2: `_convert_to_annotations_dict` のスコア抽出修正

**ファイル**: 同上
**位置**: line 569付近（`_append_scores` 呼び出し箇所）

変更前:
```python
self._append_scores(self._extract_field(unified_result, "scores"), model.id, result)
```

変更後:
```python
scores = self._extract_field(unified_result, "scores")
if not scores:
    formatted_output = self._extract_field(unified_result, "formatted_output")
    scores = self._extract_scores_from_formatted_output(formatted_output)
self._append_scores(scores, model.id, result)
```

### Step 3: テスト追加

**ファイル**: `tests/unit/gui/workers/test_annotation_worker.py`
**位置**: `TestExtractField` クラスの後

2つのテストクラスを追加:

1. **`TestExtractScoresFromFormattedOutput`** (9テスト)
   - None入力、UnifiedAnnotationResult、dict(hq)、float、未知dict等

2. **`TestConvertToAnnotationsDict`** (6テスト)
   - AestheticShadow: dict `{"hq": 0.9}` → score=0.9 + tag="very aesthetic"
   - CafePredictor: float `0.67` → score=0.67 + tag="cafe_score_6"
   - CLIP scorer: `UnifiedAnnotationResult(scores={"aesthetic": 5.2})` → score=5.2
   - WebAPI (既存パス確認): `scores={"aesthetic": 0.87}` → score=0.87
   - formatted_output=None: score=0件
   - エラーモデル: スキップ確認

## 並列実行戦略 (Subagent Teams)

```
┌─────────────────────┐  ┌─────────────────────┐
│  Agent A: Core Fix  │  │  Agent B: Tests     │
│  (annotation_worker)│  │  (test_annotation_  │
│                     │  │   worker)           │
│  1. 新メソッド追加   │  │  1. TestExtract...  │
│  2. 変換ロジック修正 │  │  2. TestConvert...  │
│  3. format確認      │  │  3. フィクスチャ準備 │
└────────┬────────────┘  └────────┬────────────┘
         │                        │
         └──────────┬─────────────┘
                    ▼
         ┌─────────────────────┐
         │  Agent C: Verify    │
         │  (sequential)       │
         │                     │
         │  1. pytest実行      │
         │  2. ruff/format確認 │
         │  3. 全体テスト回帰  │
         └─────────────────────┘
```

- **Agent A + B**: 並列実行（異なるファイルを編集、競合なし）
- **Agent C**: A+B完了後に順次実行

## 変更しないファイル

- `annotation_summary_dialog.py` - `_build_image_summary()` は既に `annotations_dict["scores"]` を読んでいるため修正不要
- `image-annotator-lib/` - ライブラリ側は変更しない（LoRAIro側で吸収）

## 検証方法

```bash
# 単体テスト
uv run pytest tests/unit/gui/workers/test_annotation_worker.py -v --timeout=10 --timeout-method=thread

# ダイアログテスト（回帰確認）
uv run pytest tests/unit/gui/widgets/test_annotation_summary_dialog.py -v --timeout=10 --timeout-method=thread

# フォーマット
make format
```
