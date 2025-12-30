# genai-tag-db-tools テスト修正計画（既存リファクタリング対応）

**作成日**: 2025-12-28  
**ブランチ**: `refactor/db-tools-hf`  
**状態**: Planning Phase  
**優先方針**: **コード品質優先（後方互換性は考慮しない）**

## 実装目的

**既に完了したHF標準キャッシュ移行**（`cache_dir` → `user_db_dir`パラメータ名変更）に対応するため、
テストコードを更新・修正する。レガシーテストの削除を含むクリーンアップを実施。

## 方針更新

- 後方互換は切り捨て（旧API/旧引数のテストは削除対象）
- `cache_dir`はHFライブラリ側のデフォルト機能を使用し、ユーザーDB保存先は`user_db_dir`を正式引数とする（`cache_dir`互換は不要）

## エラーカテゴリ分析

### カテゴリA: パラメータ名変更（cache_dir → user_db_dir）

**影響範囲**: 
- DbInitializationService
- DbInitWorker
- MainWindow統合テスト

**失敗テスト**: 14件
- `test_main_window_with_custom_cache_dir` (integration)
- `test_worker_initialization` (unit)
- `test_worker_successful_initialization` (unit)
- `test_worker_file_not_found_error` (unit)
- `test_worker_connection_error_with_cache` (unit)
- `test_worker_connection_error_without_cache` (unit)
- `test_service_initialization_default_cache` (unit)
- `test_service_initialization_custom_cache` (unit)
- `test_initialize_databases_async` (unit)
- `test_initialize_databases_with_token` (unit)
- `test_on_worker_progress` (unit)
- `test_on_worker_complete_success` (unit)
- `test_on_worker_complete_failure` (unit)
- `test_on_worker_error` (unit)

**原因**:
```python
# 旧API（テストで期待）
DbInitializationService(cache_dir=path, parent=window)
DbInitWorker(requests=[...], cache_dir=path)

# 新API（実装）
DbInitializationService(user_db_dir=path, parent=window)
DbInitWorker(requests=[...], user_db_dir=path)
```

**修正方針**: テストコードの引数名を `cache_dir` → `user_db_dir` に一括更新

---

### カテゴリB: GUIプレゼンター/ウィジェット変更

**影響範囲**:
- TagStatisticsPresenter
- TagStatisticsWidget
- TagStatisticsView（Pydanticモデル）

**失敗テスト**: 3件
- `test_build_usage_chart_with_data` - チャートタイトル変更
- `test_build_statistics_view_complete` - `top_tags`フィールド削除
- `test_tag_statistics_widget_update_top_tags` - ウィジェット機能削除

**原因1: チャートタイトル変更**
```python
# 旧タイトル（テスト期待値）
"Usage by Format"

# 新タイトル（実装）
"Usage Distribution (Tags by Usage Count)"
```

**原因2: TagStatisticsViewモデル変更**
```python
# 旧モデル
class TagStatisticsView(BaseModel):
    summary_text: str
    top_tags: list[str]  # ← 削除された
    distribution: DataFrame
    usage: DataFrame
    language: DataFrame

# 新モデル
class TagStatisticsView(BaseModel):
    summary_text: str
    distribution: DataFrame
    usage: DataFrame
    language: DataFrame
```

**修正方針**:
- チャートタイトル期待値の更新
- `top_tags`関連テストの削除（機能自体が削除されたため）
- ウィジェット統合テストの見直し

---

### カテゴリC: 廃止API呼び出し（TagCleaner.convert_prompt）

**影響範囲**:
- TagCleaner（utils/cleanup_str.py）

**失敗テスト**: 2件
- `test_convert_prompt_uses_tag_searcher`
- `test_convert_prompt_returns_original_when_format_missing`

**原因**:
```python
# cleanup_str.py:226
def convert_prompt(self, prompt: str, format_name: str) -> str:
    raise NotImplementedError(
        "TagCleaner.convert_prompt() is deprecated. Use core_api.convert_tags() instead."
    )
```

**修正方針**:
- レガシーテストの削除（`test_cleanup_str.py`の該当テスト）
- 新API（`core_api.convert_tags()`）のテストが既に存在することを確認

---

### カテゴリD: DB未初期化エラー

**影響範囲**:
- TagSearchService
- TagStatisticsService

**失敗テスト**: 5件
- `test_tag_search_service_emits_error_on_exception`
- `test_tag_statistics_service_get_general_stats`
- `test_tag_statistics_service_get_usage_stats`
- `test_tag_statistics_service_get_type_distribution`
- `test_tag_statistics_service_get_translation_stats`
- `test_tag_statistics_service_emits_error_on_exception`

**原因**:
サービス初期化時に`get_default_reader()`が呼ばれるが、テスト環境でDBパスが未設定。

```python
# services/tag_search.py:13
def __init__(self, ...):
    self.reader = reader or get_default_reader()  # ← RuntimeError発生
```

**修正方針**:
- テストでモックReaderを明示的に注入
- または`autouse` fixtureでDB初期化を実施

---

### カテゴリE: Pydanticモデル未定義エラー

**影響範囲**:
- PreloadedData（models.py）
- Tag（models.py）

**失敗テスト**: 2件
- `test_search_tags_filters_by_format_type_language`
- `test_search_tags_resolve_preferred_replaces_tag_and_translations`

**原因**:
```python
pydantic.errors.PydanticUserError: `PreloadedData` is not fully defined; 
you should define `Tag`, then call `PreloadedData.model_rebuild()`.
```

Pydanticモデルの前方参照問題（`Tag`モデルが`PreloadedData`より後で定義されている）。

**修正方針**:
- `Tag`モデルを`PreloadedData`より前に定義
- または`PreloadedData.model_rebuild()`を明示的に呼ぶ

---

### カテゴリF: Pydanticモデル型変更

**影響範囲**:
- GeneralStatsResult（models.py）

**失敗テスト**: 2件
- `test_general_stats_counts_aliases` - `dict`として使おうとしている
- `test_get_general_stats_file_not_found_fallback` - `model_dump()`不在

**原因**:
```python
# テストコード（旧想定）
stats = {...}  # dict型
stats["total_tags"]  # エラー: BaseModelはsubscriptableでない

# 現在の実装
stats = GeneralStatsResult(...)  # Pydanticモデル
stats.total_tags  # 正しいアクセス方法
```

**修正方針**:
- テストで`dict`アクセス → 属性アクセスに変更
- または`stats.model_dump()`でdictに変換してからアクセス

---

### カテゴリG: ユーザーDB書き込み制限

**影響範囲**:
- TagRegister（write operations）

**失敗テスト**: 1件
- `test_normalize_tags_fills_missing_fields`

**原因**:
```python
ValueError: User database not available for write operations
```

ユーザーDB未初期化状態でwrite操作を実行。

**修正方針**:
- テストで`runtime.init_user_db()`を明示的に呼ぶ
- または書き込みテスト用のfixtureでDB初期化

---

## 統合テスト判定基準（DB初期化fixtureの適用範囲）

以下の条件に該当するテストは統合テストとして扱い、DB初期化fixtureを適用：
- `runtime`や`ensure_db`を経由する処理
- DBファイルI/Oが発生する処理
- `get_default_reader()`の暗黙依存によりDB未初期化エラーが発生
- 複数レイヤー（service→db/runtime→reader）を跨ぐ処理

以下の条件に該当するテストはユニットテストとして扱い、DB初期化fixtureは不要：
- 依存をモック注入可能
- GUI/Presenter/モデル変換のみでDBアクセスなし

## 実装戦略

### フェーズ1: 機械的置換（10分）

**対象**: カテゴリA（cache_dir → user_db_dir）

```bash
# 対象ファイル
tests/gui/integration/test_main_window_initialization.py
tests/gui/unit/test_db_initialization_service.py
```

**実行内容**:
1. `cache_dir=` → `user_db_dir=` に一括置換
2. `worker.cache_dir` → `worker.user_db_dir` に一括置換
3. `service.cache_dir` → `service.user_db_dir` に一括置換

---

### フェーズ2: レガシーテスト削除（5分）

**対象**: カテゴリC（廃止API）

**実行内容**:
1. `test_cleanup_str.py`から以下を削除:
   - `test_convert_prompt_uses_tag_searcher`
   - `test_convert_prompt_returns_original_when_format_missing`
2. 新API（`core_api.convert_tags()`）のテストが存在することを確認

---

### フェーズ3: GUIテスト更新（15分）

**対象**: カテゴリB（プレゼンター/ウィジェット）

**実行内容**:
1. **test_tag_statistics_presenter.py**:
   - チャートタイトル期待値を更新: `"Usage by Format"` → `"Usage Distribution (Tags by Usage Count)"`
   - `test_build_statistics_view_complete`を修正: `top_tags`フィールドの参照を削除

2. **test_tag_statistics_widget.py**:
   - `test_tag_statistics_widget_update_top_tags`を削除（機能削除のため）

---

### フェーズ4: DB初期化テスト整備（20分）

**対象**: カテゴリD、E、F、G（DB依存テスト）

**実行内容**:
1. **統合/ユニットの切り分け**:
   - 統合判定基準に該当するテストのみDB初期化fixtureを適用
   - それ以外はモックReader注入でDB初期化を回避
2. **共通fixture作成**（`conftest.py`に追加）:
   ```python
   @pytest.fixture(autouse=True)
   def reset_runtime():
       """各テスト前後でruntimeをリセット"""
       from genai_tag_db_tools.db import runtime
       yield
       runtime.reset()
   
   @pytest.fixture
   def initialized_test_db(tmp_path):
       """テスト用DB初期化fixture"""
       from genai_tag_db_tools.db import runtime
       from genai_tag_db_tools.core_api import ensure_db
       
       user_db_dir = tmp_path / "test_cache"
       user_db_dir.mkdir()
       
       # ベースDB初期化（モックまたは実際のHF取得）
       # ... 実装 ...
       
       runtime.init_user_db(user_db_dir)
       return user_db_dir
   ```

2. **test_app_services.py修正**:
   - `TagSearchService`/`TagStatisticsService`のテストでモックReaderを注入
   - またはテストで`initialized_test_db` fixtureを使用

3. **test_tag_searcher.py修正**:
   - `PreloadedData`使用前に`Tag.model_rebuild()`を呼ぶ
   - または`models.py`で定義順を変更

4. **test_tag_statistics.py修正**:
   - `dict`アクセス → 属性アクセスに変更
   - または`result.model_dump()`でdict化

5. **test_tag_register.py修正**:
   - `initialized_test_db` fixtureを使用してユーザーDB初期化

---

## タスク分解

### Task 1: パラメータ名変更（カテゴリA）
- [ ] `test_main_window_initialization.py`: `cache_dir` → `user_db_dir` (1箇所)
- [ ] `test_db_initialization_service.py`: `cache_dir` → `user_db_dir` (40箇所以上)
- [ ] テスト実行・確認: 14件の失敗が解消されること

### Task 2: レガシーテスト削除（カテゴリC）
- [ ] `test_cleanup_str.py`: 廃止API関連テスト2件を削除
- [ ] `test_core_api.py`: `convert_tags()`のテストが存在することを確認

### Task 3: GUIテスト更新（カテゴリB）
- [ ] `test_tag_statistics_presenter.py`: チャートタイトル期待値更新
- [ ] `test_tag_statistics_presenter.py`: `top_tags`参照削除
- [ ] `test_tag_statistics_widget.py`: `update_top_tags`テスト削除
- [ ] テスト実行・確認: 3件の失敗が解消されること

### Task 4: DB初期化fixture整備（カテゴリD/E/F/G）
- [ ] 統合判定基準に従い、DB初期化が必要なテストのみfixture適用
- [ ] `conftest.py`: `reset_runtime` autouse fixture追加
- [ ] `conftest.py`: `initialized_test_db` fixture追加
- [ ] `test_app_services.py`: モックReader注入または fixture使用
- [ ] `test_tag_searcher.py`: Pydantic前方参照問題修正
- [ ] `test_tag_statistics.py`: dict → 属性アクセス修正
- [ ] `test_tag_register.py`: ユーザーDB初期化追加
- [ ] テスト実行・確認: 10件の失敗が解消されること

### Task 5: 最終検証
- [ ] 全テスト実行: `uv run pytest local_packages/genai-tag-db-tools/tests/`
- [ ] カバレッジ確認: 75%以上維持
- [ ] Ruff lint/format: 全通過確認

---

## リスク分析

### 高リスク
- **DB初期化fixture設計**: 不適切な実装だとテスト実行時間が大幅増加
  - **対策**: モックReaderを優先、実DB初期化は統合テストのみ

### 中リスク
- **Pydantic前方参照**: `model_rebuild()`の呼び出しタイミング
  - **対策**: `models.py`の定義順変更で根本解決

### 低リスク
- **機械的置換**: 単純な文字列置換ミス
  - **対策**: git diffで変更箇所を目視確認

---

## 成功基準

1. **全テスト合格**: 30件の失敗が0件に
2. **カバレッジ維持**: 75%以上を維持
3. **コード品質**: Ruff lint/format全通過
4. **実行時間**: テスト実行時間が1.5倍以内（DB初期化overhead考慮）

---

## 次ステップ

1. `/implement`コマンドで実装フェーズ開始
2. フェーズ1から順次実装
3. 各フェーズ完了後にテスト実行・確認
4. 全完了後にメモリ更新

---

## 参照ドキュメント

- `.serena/memories/genai_tag_db_tools_refactor_plan_2025_12_20.md`
- `.serena/memories/genai_tag_db_tools_hf_cache_migration_completion_2025_12_27.md`
- `local_packages/genai-tag-db-tools/tests/` - 既存テストコード
- `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/` - 実装コード
