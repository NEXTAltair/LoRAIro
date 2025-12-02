# AnnotationWorker 実装乖離修正計画

**作成日**: 2025-12-02
**ステータス**: ✅ 実装完了

---

## 問題の特定

### 問題1: Phase1 実装が計画v2と乖離

**計画の意図** (メモリー `annotator_result_save_fix_plan_v2_2025_12_01`):
- `_build_phash_mapping()` を削除
- ライブラリが返したpHashを `find_duplicate_image_by_phash()` で直接DB照会
- pHash再計算リスク回避

**実際の実装** (`src/lorairo/gui/workers/annotation_worker.py`):
- `_build_phash_mapping()` が存在 (lines 208-256)
- `calculate_phash(path_obj)` でローカル再計算
- `_save_results_to_database()` が `phash_mapping.get(phash)` を使用 (lines 258-297)

**影響**:
- ライブラリとLoRAIroのpHashアルゴリズム差異で不整合が再発するリスク
- 計画の「ライブラリ側のpHashを唯一の真実にする」方針を満たせない

### 問題2: db_manager が必須なのに None 防御なし

**現状**:
```python
def __init__(
    self,
    ...,
    db_manager: "ImageDatabaseManager | None" = None,
):
    self.db_manager = db_manager
```

**使用箇所**:
- `_build_phash_mapping()` line 233: `self.db_manager.get_image_id_by_filepath()`
- `_save_results_to_database()` line 289: `self.db_manager.repository.save_annotations()`

**影響**:
- `db_manager=None` でインスタンス化すると AttributeError
- テストやユニット実行で意図しない落ち方

---

## 修正方針

### 修正1: _build_phash_mapping() の削除とDB照会への変更

**変更内容**:
1. `_build_phash_mapping()` メソッドを完全削除
2. `execute()` メソッドから `_build_phash_mapping()` 呼び出しを削除
3. `_save_results_to_database()` シグネチャから `phash_mapping` 引数を削除
4. `_save_results_to_database()` 内で `find_duplicate_image_by_phash(phash)` を直接呼び出し

**修正後のフロー**:
```
image-annotator-lib 返却: PHashAnnotationResults (phash → model_name → UnifiedResult)
    ↓
AnnotationWorker._save_results_to_database(results)
    ↓ phash を抽出
find_duplicate_image_by_phash(phash)
    ↓ DB照会: SELECT id FROM images WHERE phash = ?
image_id 取得
    ↓
save_annotations(image_id, annotations)
```

### 修正2: db_manager 必須化（推奨: 必須引数化）

**修正内容**:
```python
def __init__(
    self,
    annotation_logic: AnnotationLogic,
    image_paths: list[str],
    models: list[str],
    db_manager: "ImageDatabaseManager",  # | None 削除
):
```

**理由**:
- より明示的
- 型チェッカーが保証
- 呼び出し側で誤用を防げる

---

## 実装ステップ

### Step 1: _build_phash_mapping() 削除
- **ファイル**: `src/lorairo/gui/workers/annotation_worker.py`
- **削除対象**: lines 208-256 全体

### Step 2: execute() メソッド修正
- `_build_phash_mapping()` 呼び出し削除
- `valid_image_paths` を `self.image_paths` に戻す
- `_save_results_to_database()` 呼び出しから `phash_mapping` 引数削除

### Step 3: _save_results_to_database() 修正
- シグネチャから `phash_mapping` 引数削除
- `phash_mapping.get(phash)` を `find_duplicate_image_by_phash(phash)` に変更

### Step 4: __init__ メソッド修正
- `db_manager` を必須引数に変更（`| None` 削除）
- docstring の説明を「必須: DB保存・エラー記録用」に更新

---

## 影響範囲

### 変更対象ファイル
1. `src/lorairo/gui/workers/annotation_worker.py`:
   - `_build_phash_mapping()` 削除
   - `execute()` 修正
   - `_save_results_to_database()` 修正
   - `__init__` 修正

### 呼び出し側の確認
**確認必要**: `AnnotationWorker` のインスタンス化箇所で `db_manager` 引数が渡されているか確認

**予想される箇所**:
- `src/lorairo/gui/services/worker_service.py`
- `src/lorairo/gui/window/main_window.py`
- テストコード

---

## 検証計画

### Unit Tests 修正
**対象**: `tests/unit/gui/workers/test_annotation_worker.py`

**修正内容**:
1. `_build_phash_mapping()` テストを削除
2. `_save_results_to_database()` テストでモック設定変更:
   - `phash_mapping` 引数削除
   - `find_duplicate_image_by_phash()` モック追加
3. `__init__` テストで `db_manager=None` パターン削除

### Integration Tests
**検証項目**:
1. アノテーション実行 → DB保存 → GUI表示の完全フロー
2. pHash不一致時の挙動（該当画像スキップ、ログ出力）
3. 部分的失敗時の動作（一部モデルのみ成功）

---

## 成功基準

- ✅ `_build_phash_mapping()` が完全削除される
- ✅ `_save_results_to_database()` が `find_duplicate_image_by_phash()` を使用
- ✅ pHash再計算リスクが排除される
- ✅ `db_manager` が必須引数になる
- ✅ 型チェック（mypy）が通る
- ✅ 既存テストが修正され、すべて成功する
- ✅ アノテーション実行時、結果がDBに保存される
- ✅ GUIにスコアが正しく表示される

---

## 実装結果

### 変更ファイル
1. **`src/lorairo/gui/workers/annotation_worker.py`**:
   - `_build_phash_mapping()` メソッド削除（48行削除）
   - `execute()` メソッド修正（pHash再計算処理削除）
   - `_save_results_to_database()` 修正（`find_duplicate_image_by_phash()` 使用）
   - `__init__` 修正（`db_manager` 必須引数化）

2. **`tests/unit/gui/workers/test_annotation_worker.py`**:
   - 全テストで `db_manager` をモック引数として追加
   - `phash_list=None` に期待値変更
   - pHash計算モック削除

### テスト結果

#### ユニットテスト (annotation_worker)
- **5件全て成功** ✅
- `test_initialization_with_annotation_logic` ✅
- `test_execute_success_single_model` ✅
- `test_execute_success_multiple_models` ✅
- `test_execute_model_error_partial_success` ✅
- `test_execute_all_models_fail` ✅

#### 全ワーカーユニットテスト
- **32件全て成功** ✅

#### 統合テスト (worker integration)
- **8件全て成功** ✅
- `test_database_worker_registration_error_recording` ✅
- `test_database_worker_thumbnail_load_error_recording` ✅  
- `test_search_error_creates_error_record` ✅
- `test_error_count_increases_from_zero` ✅
- `test_multiple_workers_error_recording` ✅
- `test_annotation_worker_saves_results_to_database` ✅
- `test_annotation_worker_error_recording` ✅
- `test_annotation_worker_partial_success` ✅

#### コード品質
- ✅ 型チェック (mypy): 全てクリア
- ✅ コードフォーマット (ruff format): 全てクリア
- ✅ リント (ruff check): 全てクリア（未使用変数 `_score_name` 対応済み）
- ⚠️ 複雑度警告: `_convert_to_annotations_dict` (11 > 10) - 非ブロッキング

### 成功基準の達成
- ✅ `_build_phash_mapping()` が完全削除される
- ✅ `_save_results_to_database()` が `find_duplicate_image_by_phash()` を使用
- ✅ pHash再計算リスクが排除される
- ✅ `db_manager` が必須引数になる
- ✅ 既存テストが修正され、すべて成功する

## 関連メモリー

- `annotator_result_save_fix_plan_v2_2025_12_01` - 元の計画v2
- `annotator_result_save_fix_implementation_completion_2025_12_01` - 実装完了記録（乖離発生）
- `database-design-decisions` - DB設計方針

---

**実装完了日**: 2025-12-02
