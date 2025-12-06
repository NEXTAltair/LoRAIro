# Issue #6: Duplicate Exclusion Logic - Implementation Plan

**作成日**: 2025-11-29
**担当フェーズ**: Planning Phase
**ステータス**: Ready for Implementation

## 1. Requirements Analysis

### Success Criteria
1. **機能完全性**: `SearchConditions.exclude_duplicates = True` 時、同一phashを持つ画像グループから任意の1枚のみを返す
2. **型安全性**: 完全な型ヒント（no `Any` type、no `type: ignore`）
3. **性能**: 大規模データセット（10,000+画像）でも応答時間 < 500ms
4. **後方互換性**: `exclude_duplicates = False` 時は既存動作を維持
5. **テストカバレッジ**: 75%以上（LoRAIro基準）

### Edge Cases to Handle
1. **空リスト**: `images = []` → そのまま空リストを返す
2. **重複なし**: 全画像が異なるphash → 全画像をそのまま返す
3. **全て重複**: 全画像が同一phash → 1枚のみ返す
4. **単一画像**: `len(images) == 1` → そのまま返す
5. **phash欠落**: `image["phash"]` が None or 空文字列 → WARNING ログ + 除外せず保持
6. **部分重複**: 一部グループのみ重複 → 重複グループから1枚ずつ選択

### Performance Considerations
- **アルゴリズム計算量**: O(n) - 1回のループでグループ化完了
- **メモリ使用量**: O(n) - phash → first image のマッピング
- **既存パターン踏襲**: `_filter_by_aspect_ratio()` と同様のin-memoryフィルタリング
- **データベース負荷**: ゼロ（frontend filteringのため）

---

## 2. Implementation Design

### Algorithm: Phash-Based Duplicate Filtering

```python
# 重複除外アルゴリズム（疑似コード）
def _filter_by_duplicate_exclusion(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    phashベースの重複除外フィルター
    
    ロジック:
    1. phash → 最初に出現した画像のマッピングを作成
    2. 各phashグループから任意の1枚（最初の画像）を選択
    3. 出現順序を保持したまま結果を返す
    """
    seen_phashes: dict[str, dict[str, Any]] = {}  # phash → first image
    filtered_images: list[dict[str, Any]] = []
    
    for image in images:
        phash = image.get("phash")
        
        # Edge case: phash欠落
        if not phash:
            logger.warning(f"phashが欠落している画像をスキップします: image_id={image.get('id')}")
            continue
        
        # 初出のphashなら追加
        if phash not in seen_phashes:
            seen_phashes[phash] = image
            filtered_images.append(image)
    
    return filtered_images
```

### Code Changes: `SearchCriteriaProcessor._apply_simple_frontend_filters()`

**File**: `src/lorairo/services/search_criteria_processor.py`

**Before (lines 228-231)**:
```python
# 重複除外フィルター（将来実装用プレースホルダー）
if conditions.exclude_duplicates:
    # FIXME: Issue #6参照 - 重複除外ロジック実装
    pass
```

**After**:
```python
# 重複除外フィルター
if conditions.exclude_duplicates:
    filtered_images = self._filter_by_duplicate_exclusion(filtered_images)
```

### Helper Methods

**新規メソッド**: `_filter_by_duplicate_exclusion()`

**Location**: `src/lorairo/services/search_criteria_processor.py` (line 291の直後に追加)

**Signature**:
```python
def _filter_by_duplicate_exclusion(
    self, images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    phashベースの重複除外フィルタリング
    
    同一phashを持つ画像グループから任意の1枚のみを保持します。
    "Keep Strategy"は各グループの最初に出現した画像です。
    
    Args:
        images: 画像データリスト
    
    Returns:
        list: 重複除外済み画像リスト
    
    Notes:
        - phashがNone/空文字列の画像はWARNINGログを出力してスキップ
        - 出現順序を保持（最初に見つかった画像を保持）
        - O(n)の計算量で効率的に処理
    """
```

---

## 3. Code Quality

### Type Hints and Type Safety
- **戻り値型**: `list[dict[str, Any]]` （既存パターンと一貫性）
- **パラメータ型**: `images: list[dict[str, Any]]`
- **内部変数型**:
  - `seen_phashes: dict[str, dict[str, Any]]`
  - `filtered_images: list[dict[str, Any]]`
  - `phash: str | None` （dict.get()の戻り値型）
- **型チェック**: `phash` の None/空文字列チェックで型安全性確保

### Error Handling Strategy
1. **phash欠落時**: WARNING ログ + スキップ（例外raise不要）
2. **空リスト**: そのまま返す（エラーではない）
3. **予期しない例外**: 上位層（`_apply_simple_frontend_filters`）のtry-exceptでキャッチ

### Logging Approach
| Level | Condition | Message Example |
|-------|-----------|-----------------|
| **DEBUG** | フィルター開始/完了 | `"重複除外フィルター完了: {len(images)} -> {len(filtered_images)}件（{duplicate_count}件の重複を除外）"` |
| **WARNING** | phash欠落 | `"phashが欠落している画像をスキップします: image_id={image.get('id')}"` |
| **INFO** | （なし） | - |
| **ERROR** | （なし - 上位でキャッチ） | - |

### Code Readability and Maintainability
- **変数名**: `seen_phashes` （意味明確）
- **コメント**: 日本語でロジック説明
- **docstring**: Google-styleで完全記述
- **既存パターン踏襲**: `_filter_by_aspect_ratio()` と同様の構造

---

## 4. Testing Strategy

### Unit Tests

**File**: `tests/unit/services/test_search_criteria_processor.py`

**Test Cases**:

1. **基本動作テスト**:
```python
def test_filter_by_duplicate_exclusion_basic(self, processor):
    """重複除外フィルタリング基本テスト"""
    images = [
        {"id": 1, "phash": "abc123"},
        {"id": 2, "phash": "abc123"},  # 重複
        {"id": 3, "phash": "def456"},
        {"id": 4, "phash": "def456"},  # 重複
    ]
    result = processor._filter_by_duplicate_exclusion(images)
    
    assert len(result) == 2
    assert result[0]["id"] == 1  # 最初の"abc123"
    assert result[1]["id"] == 3  # 最初の"def456"
```

2. **Edge Case Tests**:
```python
def test_filter_by_duplicate_exclusion_empty_list(self, processor):
    """空リストテスト"""
    result = processor._filter_by_duplicate_exclusion([])
    assert result == []

def test_filter_by_duplicate_exclusion_no_duplicates(self, processor):
    """重複なしテスト"""
    images = [
        {"id": 1, "phash": "abc123"},
        {"id": 2, "phash": "def456"},
        {"id": 3, "phash": "ghi789"},
    ]
    result = processor._filter_by_duplicate_exclusion(images)
    assert len(result) == 3

def test_filter_by_duplicate_exclusion_all_duplicates(self, processor):
    """全て同一phashテスト"""
    images = [
        {"id": 1, "phash": "abc123"},
        {"id": 2, "phash": "abc123"},
        {"id": 3, "phash": "abc123"},
    ]
    result = processor._filter_by_duplicate_exclusion(images)
    assert len(result) == 1
    assert result[0]["id"] == 1

def test_filter_by_duplicate_exclusion_single_image(self, processor):
    """単一画像テスト"""
    images = [{"id": 1, "phash": "abc123"}]
    result = processor._filter_by_duplicate_exclusion(images)
    assert len(result) == 1

def test_filter_by_duplicate_exclusion_missing_phash(self, processor):
    """phash欠落テスト"""
    images = [
        {"id": 1, "phash": "abc123"},
        {"id": 2, "phash": None},  # phash欠落
        {"id": 3, "phash": ""},    # 空文字列
        {"id": 4, "phash": "def456"},
    ]
    result = processor._filter_by_duplicate_exclusion(images)
    
    # phash有効な画像のみ残る
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 4
```

3. **Integration Test（既存テストへの追加）**:
```python
def test_execute_search_with_filters_with_duplicate_exclusion(self, processor, mock_db_manager):
    """重複除外フィルター統合テスト"""
    mock_images = [
        {"id": 1, "phash": "abc123", "width": 1024, "height": 1024},
        {"id": 2, "phash": "abc123", "width": 1024, "height": 1024},  # 重複
        {"id": 3, "phash": "def456", "width": 1920, "height": 1080},
    ]
    mock_db_manager.get_images_by_filter.return_value = (mock_images, 3)
    
    conditions = SearchConditions(
        search_type="tags",
        keywords=["test"],
        tag_logic="and",
        exclude_duplicates=True
    )
    
    results, count = processor.execute_search_with_filters(conditions)
    
    assert count == 2  # 重複除外後
    assert len(results) == 2
    assert results[0]["id"] == 1
    assert results[1]["id"] == 3
```

4. **Performance Test**:
```python
def test_filter_by_duplicate_exclusion_performance(self, processor):
    """大規模データセット性能テスト"""
    import time
    
    # 10,000画像（50%重複）
    images = []
    for i in range(10000):
        images.append({
            "id": i,
            "phash": f"phash_{i // 2}"  # 2画像ごとに重複
        })
    
    start = time.time()
    result = processor._filter_by_duplicate_exclusion(images)
    elapsed = time.time() - start
    
    assert len(result) == 5000  # 50%除外
    assert elapsed < 0.5  # 500ms以内
```

### Test Coverage Target
- **Line Coverage**: 100% for new `_filter_by_duplicate_exclusion()` method
- **Branch Coverage**: 100% (all if branches covered)
- **Overall Service Coverage**: 75%+ (LoRAIro standard)

---

## 5. Implementation Steps

### Step 1: 重複除外メソッドの実装
1. `src/lorairo/services/search_criteria_processor.py` の `_filter_by_date_range()` メソッド直後（line 348付近）に `_filter_by_duplicate_exclusion()` を追加
2. 完全な型ヒント・docstring・ロジックを実装
3. DEBUG/WARNING レベルのログ出力を追加

**実装内容**:
```python
def _filter_by_duplicate_exclusion(
    self, images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    phashベースの重複除外フィルタリング
    
    同一phashを持つ画像グループから任意の1枚のみを保持します。
    "Keep Strategy"は各グループの最初に出現した画像です。
    
    Args:
        images: 画像データリスト
    
    Returns:
        list: 重複除外済み画像リスト
    """
    try:
        if not images:
            return []
        
        seen_phashes: dict[str, dict[str, Any]] = {}
        filtered_images: list[dict[str, Any]] = []
        skipped_count = 0
        
        for image in images:
            phash = image.get("phash")
            
            # phash欠落チェック
            if not phash:
                logger.warning(
                    f"phashが欠落している画像をスキップします: image_id={image.get('id')}"
                )
                skipped_count += 1
                continue
            
            # 初出のphashのみ保持
            if phash not in seen_phashes:
                seen_phashes[phash] = image
                filtered_images.append(image)
        
        duplicate_count = len(images) - len(filtered_images) - skipped_count
        logger.debug(
            f"重複除外フィルター完了: {len(images)} -> {len(filtered_images)}件"
            f"（{duplicate_count}件の重複を除外、{skipped_count}件をスキップ）"
        )
        
        return filtered_images
    
    except Exception as e:
        logger.error(f"重複除外フィルター中にエラー: {e}", exc_info=True)
        return images  # エラー時は元のリストを返す
```

### Step 2: フロントエンドフィルター統合
1. `_apply_simple_frontend_filters()` メソッド（line 228-231）の FIXME プレースホルダーを削除
2. `self._filter_by_duplicate_exclusion(filtered_images)` 呼び出しを追加

**変更箇所**:
```python
# 重複除外フィルター
if conditions.exclude_duplicates:
    filtered_images = self._filter_by_duplicate_exclusion(filtered_images)
```

### Step 3: ユニットテストの実装
1. `tests/unit/services/test_search_criteria_processor.py` に以下のテストを追加:
   - `test_filter_by_duplicate_exclusion_basic`
   - `test_filter_by_duplicate_exclusion_empty_list`
   - `test_filter_by_duplicate_exclusion_no_duplicates`
   - `test_filter_by_duplicate_exclusion_all_duplicates`
   - `test_filter_by_duplicate_exclusion_single_image`
   - `test_filter_by_duplicate_exclusion_missing_phash`
   - `test_filter_by_duplicate_exclusion_partial_duplicates`

2. 既存の統合テストに重複除外ケースを追加:
   - `test_execute_search_with_filters_with_duplicate_exclusion`

### Step 4: テスト実行と検証
1. ユニットテスト実行:
   ```bash
   cd /workspaces/LoRAIro
   uv run pytest tests/unit/services/test_search_criteria_processor.py::TestSearchCriteriaProcessor::test_filter_by_duplicate_exclusion_* -v
   ```

2. カバレッジ確認:
   ```bash
   uv run pytest tests/unit/services/test_search_criteria_processor.py --cov=src/lorairo/services/search_criteria_processor --cov-report=term-missing
   ```

3. 全テスト実行（リグレッション確認）:
   ```bash
   uv run pytest tests/unit/services/test_search_criteria_processor.py -v
   ```

### Step 5: Ruffフォーマット適用
```bash
cd /workspaces/LoRAIro
uv run ruff format src/lorairo/services/search_criteria_processor.py tests/unit/services/test_search_criteria_processor.py
uv run ruff check src/lorairo/services/search_criteria_processor.py tests/unit/services/test_search_criteria_processor.py --fix
```

### Step 6: 性能テスト（Optional）
1. 大規模データセット（10,000+ 画像）での性能テスト実行
2. 応答時間 < 500ms を確認

### Step 7: ドキュメント更新（不要）
- YAGNI原則により、コード内docstringのみで十分
- 追加のREADMEやドキュメントは作成しない

---

## 6. Definition of Done

### Checklist
- [ ] `_filter_by_duplicate_exclusion()` メソッド実装完了
- [ ] `_apply_simple_frontend_filters()` 統合完了
- [ ] ユニットテスト7件以上実装完了
- [ ] テストカバレッジ 75%以上達成
- [ ] 全テストパス（既存 + 新規）
- [ ] Ruffフォーマット適用済み
- [ ] Ruff lintエラーゼロ
- [ ] 型ヒント完全（no `Any` in method signature、no `type: ignore`）
- [ ] ログ出力適切（DEBUG/WARNING）
- [ ] エッジケース全処理済み
- [ ] 性能要件満たす（< 500ms）

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| phash欠落データ | Medium | Low | WARNING ログ + スキップ処理 |
| 性能劣化（大規模） | Low | Medium | O(n)アルゴリズム + 性能テスト |
| 既存機能破壊 | Low | High | 統合テスト + `exclude_duplicates=False` 時の後方互換性確保 |
| 型安全性問題 | Low | Medium | 完全な型ヒント + mypyチェック |

---

## 8. Related Issues and Context

- **Issue #4**: Rating/Score update機能（完了） - 参考実装パターン
- **Issue #5**: ModelSyncService実装（完了） - 参考テストパターン
- **SearchConditions**: `exclude_duplicates` フィールド追加済み（line 31）
- **ImageRepository**: `find_duplicate_image_by_phash()` 既存メソッド（参考用）

---

## 9. Implementation Notes

### 既存パターンとの一貫性
- **フィルターメソッド命名**: `_filter_by_*` パターン踏襲
- **ログフォーマット**: 既存の `"{操作}完了: {before} -> {after}件"` 形式
- **エラーハンドリング**: 既存の `try-except` + `return images` パターン
- **docstring**: Google-style（既存と同一）

### 技術的決定
- **Keep Strategy**: "任意の1枚" = 最初に出現した画像（実装シンプル、順序保証）
- **phash欠落処理**: WARNING + スキップ（ERROR raiseせず、寛容な処理）
- **データ構造**: `dict[str, dict[str, Any]]` - シンプルで効率的
- **ログレベル**: DEBUG（通常動作）、WARNING（異常データ）

### 制約と前提
- **Database Schema**: `Image.phash` は `NOT NULL` かつ `indexed`
- **Frontend Filtering**: データベースクエリ後のin-memory処理
- **No DB Changes**: スキーマ変更不要
- **No New Dependencies**: 標準ライブラリのみ使用

---

**Plan Status**: ✅ Ready for `/implement` Phase
**Estimated Implementation Time**: 2-3 hours (including tests)
