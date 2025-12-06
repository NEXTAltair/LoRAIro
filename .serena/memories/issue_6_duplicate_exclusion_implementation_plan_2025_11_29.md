# Issue #6: 重複除外ロジック実装プラン

## 概要

`SearchConditions.exclude_duplicates` フラグが有効な場合、知覚ハッシュ(phash)を使用して重複画像を除外するフィルタリングロジックを実装します。

## 要件定義

**ユーザー要件（確認済み）:**
- **保持戦略**: 重複グループから任意の1枚を保持
- **重複判定**: phash（知覚ハッシュ）による比較
- **処理場所**: メモリ内（フロントエンド）フィルタリング

**成功基準:**
- 同一phashを持つ画像グループから1枚のみ保持
- 型安全性: 既存コードベースに合わせて `list[dict[str, Any]]` を使用（将来的なTypedDict移行は別Issue）
- phash欠落時の明確な処理方針（ログ出力 + そのまま保持 ≠ 重複除外対象外）
- 大規模データセット対応（10,000+画像で < 500ms）を性能テストで検証
- 後方互換性維持（`exclude_duplicates=False`時は影響なし）
- テストカバレッジ75%+

## 実装アプローチ

### アルゴリズム設計

**O(n)のシンプルなphashグループ化:**

```python
def _filter_by_duplicate_exclusion(
    self, images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    phashによる重複画像除外

    同一phashを持つ画像グループから最初に遭遇した画像のみを保持します。
    phash欠落画像は保持されます（警告ログ出力）。
    """
    seen_phashes: dict[str, dict[str, Any]] = {}
    filtered_images: list[dict[str, Any]] = []

    for image in images:
        phash = image.get("phash")

        if not phash:
            # phash欠落時: 警告ログ + 重複判定不可のためそのまま保持
            # 注意: これは「重複除外対象外」であり、実際には重複が残る可能性がある
            # 本来はDB登録時にphash必須化すべきだが、スキーマ上はNOT NULL制約済み
            logger.warning(
                f"phash欠落画像を検出（重複判定不可）: image_id={image.get('id')}, "
                f"path={image.get('stored_image_path', 'N/A')}"
            )
            filtered_images.append(image)
            continue

        if phash not in seen_phashes:
            seen_phashes[phash] = image
            filtered_images.append(image)
        # else: 重複のためスキップ（暗黙的）

    logger.debug(
        f"重複除外完了: {len(images)} -> {len(filtered_images)}件 "
        f"(重複除外: {len(images) - len(filtered_images)}件)"
    )
    return filtered_images
```

**統合箇所（`_apply_simple_frontend_filters()`）:**

```python
# 重複除外フィルター
if conditions.exclude_duplicates:
    filtered_images = self._filter_by_duplicate_exclusion(filtered_images)
```

### エッジケース対応

| ケース | 動作 |
|--------|------|
| 空リスト | そのまま返却 |
| 重複なし | 全画像保持 |
| 全て重複 | 1枚のみ保持 |
| 単一画像 | そのまま保持 |
| phash欠落 | 警告ログ + 保持 |
| 部分重複 | グループごとに1枚保持 |

## 実装ステップ

### Step 1: 新規メソッド実装
**ファイル**: `src/lorairo/services/search_criteria_processor.py`

- `_filter_by_duplicate_exclusion()` メソッドを追加（line 348付近）
- 既存パターン（`_filter_by_aspect_ratio`）に倣った実装
- 型ヒント完全記述
- try-exceptでエラーハンドリング
- DEBUG/WARNINGレベルログ出力

### Step 2: 既存フィルターへの統合
**ファイル**: `src/lorairo/services/search_criteria_processor.py`

- `_apply_simple_frontend_filters()` 内のFIXME（line 228-231）を削除
- 重複除外フィルター呼び出しを追加
- アスペクト比フィルターと同じパターンで統合

### Step 3: ユニットテスト実装
**ファイル**: `tests/unit/services/test_search_criteria_processor.py`

**必須テストケース（8件以上）:**

1. `test_filter_by_duplicate_exclusion_basic` - 基本的な重複除外
2. `test_filter_by_duplicate_exclusion_empty_list` - 空リスト処理
3. `test_filter_by_duplicate_exclusion_no_duplicates` - 重複なしケース
4. `test_filter_by_duplicate_exclusion_all_duplicates` - 全て重複ケース
5. `test_filter_by_duplicate_exclusion_single_image` - 単一画像
6. `test_filter_by_duplicate_exclusion_missing_phash` - phash欠落（警告ログ確認 + 保持確認）
7. `test_filter_by_duplicate_exclusion_partial_duplicates` - 部分重複
8. `test_filter_by_duplicate_exclusion_performance` - 性能テスト（10,000画像で < 500ms）

### Step 4: テスト実行・カバレッジ確認

```bash
uv run pytest tests/unit/services/test_search_criteria_processor.py -v
uv run pytest tests/unit/services/test_search_criteria_processor.py --cov=src/lorairo/services/search_criteria_processor --cov-report=term
```

- 全テスト成功確認
- カバレッジ75%+確認

### Step 5: コード品質チェック

```bash
uv run ruff format src/lorairo/services/search_criteria_processor.py tests/unit/services/test_search_criteria_processor.py
uv run ruff check src/lorairo/services/search_criteria_processor.py tests/unit/services/test_search_criteria_processor.py --fix
uv run mypy src/lorairo/services/search_criteria_processor.py
```

### Step 6: 性能テスト（必須）

**性能要件を検証するため必須ステップ:**

```python
def test_filter_by_duplicate_exclusion_performance():
    """10,000画像での性能テスト（目標: < 500ms）"""
    import time

    # テストデータ生成: 10,000画像（50%重複）
    test_images = []
    for i in range(5000):
        # 重複ペア
        phash = f"phash_{i:06d}"
        test_images.append({"id": i*2, "phash": phash, "width": 1024, "height": 1024})
        test_images.append({"id": i*2+1, "phash": phash, "width": 1024, "height": 1024})

    processor = SearchCriteriaProcessor(db_manager=Mock())

    start = time.perf_counter()
    result = processor._filter_by_duplicate_exclusion(test_images)
    elapsed = (time.perf_counter() - start) * 1000  # ms

    assert len(result) == 5000, f"Expected 5000, got {len(result)}"
    assert elapsed < 500, f"Performance requirement failed: {elapsed:.2f}ms > 500ms"

    logger.info(f"性能テスト成功: {elapsed:.2f}ms (10,000画像 -> 5,000画像)")
```

**検証基準:**
- 10,000画像処理で < 500ms
- メモリ使用量が許容範囲内（dict蓄積によるメモリリーク確認）

### Step 7: 統合テスト（Optional）

`test_execute_search_with_filters_with_duplicate_exclusion` を追加し、実際の検索フロー全体での動作確認。

## Critical Files

**実装対象:**
- `src/lorairo/services/search_criteria_processor.py` - メインロジック
- `tests/unit/services/test_search_criteria_processor.py` - ユニットテスト

**参考:**
- `src/lorairo/services/search_models.py` - `SearchConditions`定義
- `src/lorairo/database/schema.py` - `Image`モデル（phashフィールド確認）

## コード品質基準

- **型ヒント**: 完全記述（関数シグネチャ、変数）
- **エラーハンドリング**: try-except + logger.error
- **ログレベル**: DEBUG（通常）、WARNING（phash欠落）、ERROR（例外）
- **コメント**: 日本語で実装意図を明記
- **命名**: 既存パターン踏襲（`_filter_by_*`）
- **フォーマット**: Ruff（line length: 108）

## 制約条件と設計判断

**制約:**
- ✅ データベーススキーマ変更なし
- ✅ 新規依存関係なし
- ✅ 後方互換性維持
- ✅ YAGNI原則遵守（必要最小限の実装）
- ✅ 既存パターン踏襲

**設計判断の記録:**

1. **型安全性**: `list[dict[str, Any]]` を使用
   - 既存コードベース全体が `dict[str, Any]` ベースで設計されている
   - TypedDict（ImageDict等）への段階的移行は別Issueで対応
   - 現時点では既存パターンを踏襲し、一貫性を保つ

2. **phash欠落時の処理**: 警告ログ + そのまま保持
   - スキーマ上は `phash` は NOT NULL 制約だが、データ不整合の可能性を考慮
   - phash がない画像は重複判定不可のため除外対象外として扱う
   - 代替キー（ファイル名等）でのフォールバックは実装しない（YAGNI）
   - 本質的解決はDB登録時のphash必須化（別Issue）

3. **性能要件**: 必須検証項目
   - 10,000画像で < 500ms を性能テストで検証
   - O(n)アルゴリズムにより理論上達成可能
   - メモリ使用量も dict 蓄積により管理可能範囲

## 実装完了基準

- [ ] `_filter_by_duplicate_exclusion()` メソッド実装完了（phash欠落時の動作を明示的にコメント）
- [ ] `_apply_simple_frontend_filters()` 統合完了
- [ ] ユニットテスト8件以上実装・成功（性能テスト含む）
- [ ] 性能テスト成功（10,000画像で < 500ms）
- [ ] カバレッジ75%+達成
- [ ] Ruff/mypy全チェック成功
- [ ] FIXMEコメント削除

## 参考パターン

**既存実装:**
- `_filter_by_aspect_ratio()` (line 240-290) - フロントエンドフィルタリングパターン
- `_filter_by_date_range()` (line 292-348) - ログ出力・エラーハンドリング
- 既存テスト - テストケース設計パターン

---

この計画は `/implement` コマンドで直接実行可能です。
