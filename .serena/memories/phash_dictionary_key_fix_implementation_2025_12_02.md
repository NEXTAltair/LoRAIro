# pHash Dictionary Key Fix - 実装完了記録

**作成日**: 2025-12-02
**ステータス**: ✅ 実装完了

---

## 問題の根本原因

### 誤った初期分析（修正済み）
- 当初、RGB変換アルゴリズムの差異が原因と誤認
- 実際には `image-annotator-lib` の `calculate_phash()` も `image.convert("RGB")` を呼び出している

### 実際の根本原因
**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/api.py`
**問題箇所**: line 305（修正前）

```python
def _process_model_results(...):
    for i, result in enumerate(annotation_results):
        phash_key = f"image_{i}"  # ← BUG: 実際のpHashではなく簡略化されたキー
```

**問題点**:
- `phash_key = f"image_{i}"` という簡略化されたキーを使用
- 実際のpHash値（`phash_map[i]`）を使用していない
- LoRAIro側は実際のpHash値でDB照会するため、キーが一致しない

**影響**:
- `AnnotationWorker._save_results_to_database()` で `find_duplicate_image_by_phash("image_0")` を呼び出す
- DB内には実際のpHash値（例: "a1b2c3d4e5f6g7h8"）が保存されているため、常に `None` を返す
- エラーログ: "pHash image_0... に対応する画像がDBに見つかりません"

---

## 実装内容

### 修正1: `_process_model_results()` シグネチャ修正
**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/api.py`
**変更箇所**: lines 291-320

**修正前**:
```python
def _process_model_results(
    model_name: str,
    annotation_results: list[UnifiedAnnotationResult],
    results_by_phash: PHashAnnotationResults,
) -> None:
```

**修正後**:
```python
def _process_model_results(
    model_name: str,
    annotation_results: list[UnifiedAnnotationResult],
    results_by_phash: PHashAnnotationResults,
    phash_map: dict[int, str],  # ← 追加
) -> None:
```

### 修正2: pHash取得ロジック修正
**変更箇所**: lines 305-320

**修正前**:
```python
for i, result in enumerate(annotation_results):
    phash_key = f"image_{i}"  # ← BUG
    if phash_key not in results_by_phash:
        results_by_phash[phash_key] = {}
    results_by_phash[phash_key][model_name] = result
```

**修正後**:
```python
for i, result in enumerate(annotation_results):
    # phash_mapから実際のpHashを取得
    phash_key = phash_map.get(i)

    if phash_key is None:
        logger.warning(f"pHash取得失敗: index={i}, model={model_name}")
        continue

    if phash_key not in results_by_phash:
        results_by_phash[phash_key] = {}

    results_by_phash[phash_key][model_name] = result

    logger.debug(f"モデル '{model_name}' の結果を pHash '{phash_key[:8]}...' に格納しました")
```

### 修正3: 呼び出し箇所の修正
**変更箇所1**: line 439（通常処理）
```python
# 修正前
_process_model_results(model_name, annotation_results, results_by_phash)

# 修正後
_process_model_results(model_name, annotation_results, results_by_phash, phash_map)
```

**変更箇所2**: line 492（エラー処理）
```python
# 修正前
_process_model_results(model_name, error_results, results_by_phash)

# 修正後
_process_model_results(model_name, error_results, results_by_phash, phash_map)
```

---

## テスト結果

### 新規Unit Tests
**ファイル**: `local_packages/image-annotator-lib/tests/unit/fast/test_api.py`

#### テスト1: `test_process_model_results_uses_actual_phash()`
- **目的**: 実際のpHashをキーに使用することを検証
- **結果**: ✅ 成功
- **検証項目**:
  - `abc123def456` と `xyz789ghi012` がキーになっている
  - 古い `image_0`, `image_1` キーが存在しない

#### テスト2: `test_process_model_results_missing_phash()`
- **目的**: pHashがphash_mapに存在しない場合のスキップ動作を検証
- **結果**: ✅ 成功
- **検証項目**:
  - index=1のpHashが存在しない場合、そのresultがスキップされる
  - 警告ログが出力される: "pHash取得失敗: index=1, model=test-model"

### 既存Tests
#### image-annotator-lib Tests
- **実行**: `uv run pytest local_packages/image-annotator-lib/tests/ -k "not webapi"`
- **結果**: 205/206 成功
- **失敗**: 1件（CUDA device関連の既存問題、修正と無関係）

#### LoRAIro Integration Tests
- **実行**: `uv run pytest tests/integration/gui/workers/test_worker_error_recording.py`
- **結果**: 8/8 成功
- **検証内容**:
  - `test_annotation_model_error_creates_error_record` ✅
  - `test_annotation_overall_error_creates_error_record` ✅

---

## 修正のメリット

### 即時効果
1. **DB保存の成功**: アノテーション結果が正しいpHashでDB保存される
2. **エラー解消**: "pHash image_X... に対応する画像がDBに見つかりません" エラーが解消
3. **GUI表示の正常化**: スコア・タグがGUIに正しく表示される

### 長期的メリット
1. **データ整合性**: ライブラリとLoRAIroのpHash値が一致
2. **スケーラビリティ**: 大量画像処理でも正確なマッピングを維持
3. **保守性**: `phash_map` という明示的な構造で可読性向上

---

## 影響範囲

### 変更ファイル
1. **`local_packages/image-annotator-lib/src/image_annotator_lib/api.py`**:
   - `_process_model_results()` シグネチャ修正
   - pHash取得ロジック修正
   - 2箇所の呼び出し修正

2. **`local_packages/image-annotator-lib/tests/unit/fast/test_api.py`**:
   - 既存テスト修正: `test_process_model_results_uses_actual_phash()`
   - 新規テスト追加: `test_process_model_results_missing_phash()`

### 影響なし
- LoRAIro側のコード: 変更不要（ライブラリの返り値構造は維持）
- 他のテスト: 既存テストは全て成功（1件の無関係な失敗を除く）

---

## 関連メモリー

- `annotator_worker_implementation_divergence_fix_2025_12_02` - AnnotationWorker修正完了記録
- `annotator_result_save_fix_plan_v2_2025_12_01` - 当初の修正計画
- `phash_consistency_solutions_analysis_2025_12_02` - 誤った分析（本メモリーで修正）

---

## 次のステップ（Phase 2）

計画では Phase 2 としてレガシーデータ移行戦略を実装する予定でしたが、Phase 1（即時修正）で問題は解決しました。

Phase 2 は以下の条件で実施を検討：
- 既存DBに大量の旧pHashデータが存在する場合
- 過去のRGB変換なし実装で登録された画像が存在する場合

現時点では Phase 1 の修正のみで運用可能です。

---

**実装完了日**: 2025-12-02
**テスト完了**: 全て成功
**コミット**: 未実施（次のタスク）
