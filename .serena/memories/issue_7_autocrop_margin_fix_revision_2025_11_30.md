# Issue #7: AutoCrop Margin Logic Fix - Revision (2025-11-30)

## レビューフィードバック対応

### 指摘された問題点

1. **軸別マージン適用条件の誤り**: 両軸同時成立を要求していた
2. **テストがマージンロジックを検証できていない**: モックで実装をスキップ
3. **ドキュメントと実装の乖離**: "Axis-specific"と記載しているのに実装は両軸同時

### 修正内容

#### 1. 軸別の独立したマージン適用 (`src/lorairo/editor/autocrop.py` L362-381)

**修正前（誤った実装）:**
```python
# Apply margin only if bbox is large enough
if bbox_width > 2 * margin_x and bbox_height > 2 * margin_y:  # ❌ AND条件
    x_min = max(0, x_min + margin_x)
    y_min = max(0, y_min + margin_y)
    x_max = min(width, x_max - margin_x)
    y_max = min(height, y_max - margin_y)
    logger.debug(f"Applied margin: x={margin_x}px, y={margin_y}px")
else:
    logger.debug("...skipping margin")
```

**修正後（正しい実装）:**
```python
# Apply margin independently per axis
if bbox_width > 2 * margin_x:  # ✅ 軸ごとに独立
    x_min = max(0, x_min + margin_x)
    x_max = min(width, x_max - margin_x)
    logger.debug(f"Applied x-axis margin: {margin_x}px")
else:
    logger.debug(f"Bbox width too small for x-margin ({bbox_width} <= {2 * margin_x}), skipping x-margin")

if bbox_height > 2 * margin_y:  # ✅ 軸ごとに独立
    y_min = max(0, y_min + margin_y)
    y_max = min(height, y_max - margin_y)
    logger.debug(f"Applied y-axis margin: {margin_y}px")
else:
    logger.debug(f"Bbox height too small for y-margin ({bbox_height} <= {2 * margin_y}), skipping y-margin")
```

**設計意図の実現:**
- 横長コンテンツ（1000x3）: x軸のみマージン適用、y軸スキップ
- 縦長コンテンツ（3x1000）: y軸のみマージン適用、x軸スキップ
- 極小コンテンツ（3x3）: 両軸スキップ

#### 2. テストの全面書き直し (`tests/unit/test_autocrop.py` L390-515)

**修正前の問題:**
```python
# モックで_get_crop_areaをスキップ → マージン計算が実行されない
with patch.object(self.autocrop, "_get_crop_area") as mock_get_crop:
    mock_get_crop.return_value = (750, 750, 500, 500)
    ...
    assert result.size == (500, 500)  # 旧実装でも成立
```

**修正後:**
```python
# 実際の画像で_get_crop_areaを呼び出してマージン適用を検証
test_img = np.full((2000, 2000, 3), 0, dtype=np.uint8)
test_img[750:1250, 750:1250] = [255, 255, 255]

crop_area = self.autocrop._get_crop_area(test_img)
assert crop_area is not None

_x, _y, w, h = crop_area
# マージン適用後のサイズを検証（490-500pxの範囲）
assert 490 <= w <= 500
assert 490 <= h <= 500
```

**新規テストケース（6個）:**
1. `test_margin_calculation_based_on_bbox`: バウンディングボックス基準の検証
2. `test_margin_per_axis_non_square_bbox`: 軸ごとの異なるマージン検証
3. `test_margin_x_only_applied_wide_bbox`: x軸のみマージン適用（横長）
4. `test_margin_y_only_applied_tall_bbox`: y軸のみマージン適用（縦長）
5. `test_margin_prevents_negative_dimensions_both_axes`: 両軸スキップ
6. `test_margin_debug_logging_both_axes`: デバッグログ検証

#### 3. ドキュメント整合性確保

**`src/lorairo/editor/autocrop.py` docstring (L280-281):**
```python
# 修正前
- Safety check: Skips margin if bbox is too small (< 2 * margin)
- Axis-specific: Handles non-square bounding boxes correctly

# 修正後
- Safety check: Each axis applies margin independently (bbox_width > 2 * margin_x, bbox_height > 2 * margin_y)
- Axis-specific: Non-square bounding boxes apply margin per axis (e.g., wide bbox skips y-margin only)
```

**`docs/specs/core/image_processing.md` (L53-62):**
- 「軸ごとの独立計算」を明記
- 例を6パターンに拡充（横長・縦長の独立適用を追加）

### 品質検証結果

- ✅ **Ruff**: 全チェックパス
- ❌ **Pytest**: 循環import エラー（既存のコードベース問題、修正とは無関係）

### 変更ファイル

1. `src/lorairo/editor/autocrop.py` (L280-281, L362-381)
2. `tests/unit/test_autocrop.py` (L390-515: 全面書き直し)
3. `docs/specs/core/image_processing.md` (L53-62)

### 修正の妥当性確認

**設計原則との整合性:**
- ✅ 軸ごとの独立計算を実装
- ✅ 非正方形バウンディングボックスに正しく対応
- ✅ 負の寸法を確実に防止
- ✅ ドキュメントと実装が一致

**テストカバレッジ:**
- ✅ バウンディングボックス基準の検証
- ✅ 軸ごとの独立適用の検証
- ✅ 安全性チェックの検証
- ✅ デバッグログの検証

## 次のアクション（循環import解決後）

1. 全テスト実行: `uv run pytest tests/unit/test_autocrop.py -v`
2. 新規6テストのパス確認
3. 既存21テストのリグレッション確認
4. 軸別マージン適用の動作確認（横長・縦長コンテンツ）

## 参照

- 初回実装: `.serena/memories/issue_7_autocrop_margin_implementation_completion_2025_11_30.md`
- 計画書: `/home/vscode/.claude/plans/eventual-swimming-penguin.md`
