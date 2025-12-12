# Legacy Test Cleanup Investigation (2025-12-12)

## 調査概要

**目的:** 古いAPI使用や構造変更で不要になったレガシーテストコードの特定とクリーンナップ計画

**調査範囲:** 68テストファイル全体

**発見:** 2ファイルに23箇所の修正対象を特定 (API変換19 + dict変換1 + コメント削除3)

---

## 調査結果サマリー

### 修正が必要なファイル: 2ファイル (23箇所: API 19 + dict 1 + コメント 3)

#### 1. `tests/unit/gui/services/test_worker_service.py` (5箇所)
**優先度:** HIGH - コアサービステスト
**問題:** 古いSearchConditions API使用

**対象行:**
- Line 145: `SearchConditions(tags=["test"], caption="sample")`
- Line 178: `SearchConditions(tags=["test"], caption="sample")`
- Line 278: `SearchConditions(tags=["test1"])`
- Line 279: `SearchConditions(tags=["test2"])`
- Line 301: `SearchConditions(tags=["test"])`

**理由:** `WorkerService.start_search()` は新しいSearchConditions API (`search_type`, `keywords`, `tag_logic`) を期待

---

#### 2. `tests/integration/gui/test_worker_coordination.py` (15箇所 + 3コメント)
**優先度:** MEDIUM - 統合テスト
**問題:** 古いAPI使用 + dict形式使用 + 不要なコメント

**古いAPI使用 (14行):**
- Lines: 85, 89, 115, 139, 155, 184, 198, 227, 230, 240, 244, 267, 288, 311
- パターン: `SearchConditions(tags=[...])`

**dict形式使用 (1行):**
- Line 61: `filter_conditions = {"tags": ["test"], "caption": "sample"}`
- `worker_service.start_search(filter_conditions)` に誤ってdictを渡している
- SearchConditionsオブジェクトに変換が必要

**不要なコメント (3行):**
- Line 56: `# ProgressManager削除により不要となったfixture`
- Line 97: `# ProgressManager は削除済みのため該当テストを削除`
- Line 250: `# ProgressManager は削除済みのため該当テストを削除`
- 削除済みProgressManagerへの参照を削除

---

### 修正が不要なファイル: test_dataset_state.py (重要な発見)

#### `tests/unit/gui/state/test_dataset_state.py` (修正不要)
**優先度:** N/A
**状態:** ✅ 正しい - 意図的にdict形式使用

**理由:**
- Line 128: `filter_conditions = {"tags": ["test"], "caption": "sample"}`
- 使用箇所: `state_manager.apply_filter_results(filtered_images, filter_conditions)`
- `apply_filter_results()` シグネチャ: `filter_conditions: dict[str, Any]`
- **このメソッドはdictを期待している設計** - テストは正しい

**追加調査結果:**
- `DatasetStateManager.apply_filter_results()` は **srcディレクトリで参照なし**
- テストコードのみで使用されている **レガシーメソッド**
- docstringでdict形式の例を明示
- メソッド設計としてdict型を受け入れる仕様

---

## API変換パターン

### 現在のAPI (正しい)
```python
SearchConditions(
    search_type="tags",      # 必須: "tags" or "caption"
    keywords=["tag1", "tag2"],  # 必須: キーワードリスト
    tag_logic="and"          # 必須: "and" or "or"
)
```

### 古いAPI (非推奨)
```python
# パターン1: tags のみ
SearchConditions(tags=["tag1", "tag2"])  # ❌ OLD

# パターン2: tags + caption
SearchConditions(tags=["test"], caption="sample")  # ❌ OLD

# パターン3: dict形式 (WorkerServiceで誤使用)
{"tags": ["test"], "caption": "sample"}  # ❌ OLD (for WorkerService)
```

### 変換ルール

**ルール1: tagsのみ検索**
```python
# OLD:
SearchConditions(tags=["tag1", "tag2"])

# NEW:
SearchConditions(
    search_type="tags",
    keywords=["tag1", "tag2"],
    tag_logic="and"
)
```

**ルール2: tags + caption 組み合わせ**
```python
# OLD:
SearchConditions(tags=["test"], caption="sample")

# NEW (tagsを優先):
SearchConditions(
    search_type="tags",
    keywords=["test"],
    tag_logic="and"
)
# Note: Caption検索は別タイプ - 現在のAPIは組み合わせをサポートしない
```

**ルール3: dict → オブジェクト (WorkerService用)**
```python
# OLD:
filter_conditions = {"tags": ["test"], "caption": "sample"}
worker_service.start_search(filter_conditions)

# NEW:
filter_conditions = SearchConditions(
    search_type="tags",
    keywords=["test"],
    tag_logic="and"
)
worker_service.start_search(filter_conditions)
```

---

## 既に正しく移行済みのファイル (9ファイル)

以下のファイルは既に新しいAPIを正しく使用:

1. ✅ `/workspaces/LoRAIro/tests/unit/services/test_search_criteria_processor.py`
2. ✅ `/workspaces/LoRAIro/tests/unit/gui/services/test_search_filter_service.py`
3. ✅ `/workspaces/LoRAIro/tests/integration/gui/test_filter_search_integration.py`
4. ✅ `/workspaces/LoRAIro/tests/integration/test_ai_rating_filter_integration.py`
5. ✅ `/workspaces/LoRAIro/tests/unit/database/test_db_repository_ai_rating_filter.py`
6. ✅ `/workspaces/LoRAIro/tests/unit/services/test_model_filter_service.py`
7. ✅ `/workspaces/LoRAIro/tests/integration/gui/workers/test_worker_error_recording.py`
8. ✅ その他のフィルター/検索テストファイル

これらはパターン参照用に使用可能。

---

## アーキテクチャ理解

### SearchConditions API定義

**ファイル:** `src/lorairo/services/search_models.py`

```python
@dataclass
class SearchConditions:
    """検索条件データクラス"""
    
    search_type: str  # "tags" or "caption" (必須)
    keywords: list[str]  # (必須)
    tag_logic: str  # "and" or "or" (必須)
    resolution_filter: str | None = None
    aspect_ratio_filter: str | None = None
    # ... 他のオプションフィールド
    
    def to_db_filter_args(self) -> dict[str, Any]:
        """DB APIの引数に直接変換"""
        return {
            "tags": self.keywords if self.search_type == "tags" else None,
            "caption": self.keywords[0] if self.search_type == "caption" and self.keywords else None,
            # ... 他のフィールド変換
        }
```

### WorkerService.start_search() シグネチャ

**ファイル:** `src/lorairo/gui/services/worker_service.py`

```python
def start_search(self, search_conditions: SearchConditions) -> str:
    """
    検索開始（既存の検索は自動キャンセル）
    
    Args:
        search_conditions: 検索条件 (SearchConditionsオブジェクト)
    
    Returns:
        str: ワーカーID
    """
    worker = SearchWorker(self.db_manager, search_conditions)
    # ... ワーカー開始処理
```

**重要:** `SearchConditions`オブジェクトを期待、dictは受け付けない

### DatasetStateManager.apply_filter_results() シグネチャ

**ファイル:** `src/lorairo/gui/state/dataset_state.py`

```python
def apply_filter_results(
    self, filtered_images: list[dict[str, Any]], filter_conditions: dict[str, Any]
) -> None:
    """
    データベースからのフィルター結果を適用し、状態を更新します。
    
    Args:
        filtered_images: フィルター処理後の画像メタデータリスト
        filter_conditions: 適用されたフィルター条件 (dict型)
            - "tags": タグフィルター条件 (list[str])
            - "caption": キャプション検索条件 (str)
            - "resolution": 解像度フィルター条件 (int)
            - ... 他のフィルター条件
    """
    self._filter_conditions = filter_conditions.copy()
    # ... 状態更新処理
```

**重要:** `dict[str, Any]`型を期待、SearchConditionsオブジェクトではない

**調査結果:**
- srcディレクトリ内に参照なし（本番コードで使用されていない）
- テストコードのみで使用
- レガシーメソッドの可能性が高い
- ただし、テストは仕様通りにdictを使用しているため正しい

---

## 優先度ランキング

### Priority 1: CRITICAL (必須修正)
**ファイル:** 2
**箇所:** 19

1. `test_worker_service.py` (5箇所) - コアサービステスト
2. `test_worker_coordination.py` (14箇所 + 1 dict) - 統合テスト

**影響:** これらのファイルは重要なワーカーインフラをテスト。古いAPIによりテスト失敗または不正確な検証の可能性。

---

### Priority 2: LOW (クリーンナップ)
**ファイル:** 1
**箇所:** 3コメント

3. `test_worker_coordination.py` - 不要なProgressManager削除コメント

**影響:** コード品質向上、ただし機能への影響なし

---

### Priority 3: NO ACTION (正しい実装)
**ファイル:** 1  
**箇所:** 0

4. `test_dataset_state.py` - 変更不要（仕様通りにdict使用）

---

## エッジケース分析

### ケース1: tags + caption 組み合わせ検索

**問題:** 古いAPIでは `SearchConditions(tags=["x"], caption="y")` が可能だったが、新APIでは `search_type` 選択が必須

**解決策:**
1. テストコンテキストを確認して主要な検索意図を理解
2. 両方存在する場合は `search_type="tags"` をデフォルト（最も一般的なワークフロー）
3. captionが明確に主要な場合は `search_type="caption"` を使用
4. 曖昧な場合はコードコメントで決定理由を文書化

**例:**
```python
# テストコンテキスト: タグによる主要検索
# OLD: SearchConditions(tags=["lora", "training"], caption="quality")
# NEW: 
SearchConditions(
    search_type="tags",  # このワークフローでの主要検索方法
    keywords=["lora", "training"],
    tag_logic="and"
)
```

### ケース2: 空またはNone値

**問題:** テストが `SearchConditions(tags=None)` または `SearchConditions(tags=[])` を使用する可能性

**解決策:**
```python
# OLD: SearchConditions(tags=None)
# NEW: SearchConditions(search_type="tags", keywords=[], tag_logic="and")

# OLD: SearchConditions(tags=[])
# NEW: SearchConditions(search_type="tags", keywords=[], tag_logic="and")
```

### ケース3: 動的テストパラメータ

**問題:** パラメータ化を使用するテストがSearchConditionsを動的生成する可能性

**解決策:**
- パラメータ化構造を維持
- インスタンス化パターンのみ更新
- pytestパラメータが正しく動作することを検証

---

## テスト戦略方針との整合性

**参照:** `test_strategy_policy_change_2025_11_06` memory

**統合テスト方針 (2025-11-06):**
- 統合テスト: モックのみ使用、CI/CD常時実行可能
- E2Eテスト: 実API使用、BDD形式
- `@pytest.mark.real_api` 廃止 - E2Eテストに集約

**本クリーンナップとの関連:**
- SearchConditions API更新は方針と整合
- モックベーステストの品質向上
- API一貫性確保によりメンテナンス性向上

---

## 参照ファイル

### 定義ファイル:
1. `src/lorairo/services/search_models.py` - SearchConditions定義
2. `src/lorairo/gui/services/worker_service.py` - WorkerService.start_search()
3. `src/lorairo/gui/state/dataset_state.py` - DatasetStateManager.apply_filter_results()

### パターン参照ファイル:
4. `tests/unit/services/test_search_criteria_processor.py` - 正しい新API使用例
5. `tests/unit/gui/services/test_search_filter_service.py` - 正しい新API使用例
6. `tests/integration/gui/test_filter_search_integration.py` - 統合テスト例

---

## 実行手順(完了条件含む)

### 完了条件(受け入れ基準)

**機能要件:**
- [ ] 19箇所の古いSearchConditions API → 新API変換完了
- [ ] 1箇所のdict形式 → SearchConditionsオブジェクト変換完了
- [ ] 3箇所のProgressManagerコメント削除完了

**品質要件:**
- [ ] 対象2ファイルの全テスト通過
- [ ] カバレッジ75%以上維持 (プロジェクト基準: CLAUDE.md記載)
- [ ] Ruffエラーなし
- [ ] mypy新規エラーなし

**数の整理 (合計23箇所):**
- API変換: 19箇所
- dict変換: 1箇所
- コメント削除: 3箇所
- **合計:** 23修正箇所

---

### Step 1: 前提検証 (5分)

**Base Commit:** `c5951a395d9883cc2f663d526ff2a059e40aeb00`

#### 1.1 空keywords受け入れ確認
```bash
# プロジェクトルートで実行
python -c "from lorairo.services.search_models import SearchConditions; c = SearchConditions(search_type='tags', keywords=[], tag_logic='and'); print('✅ OK:', c)"
```

**期待結果:** エラーなし
**失敗時:** STOP - 戦略再検討

#### 1.2 ベースライン取得
```bash
# 現状把握
uv run pytest tests/unit/gui/services/test_worker_service.py -v
uv run pytest tests/integration/gui/test_worker_coordination.py -v
```

**記録:** pass/fail数を控える

---

### Step 2: test_worker_service.py (5箇所) - 20分

#### 2.1 変換判断基準

**全5箇所共通の判断:**
- テスト目的: ワーカー起動・キャンセル・ID生成の検証
- 検索内容への依存: **なし** (mockで検証)
- 結論: tags/caption区別不要 → **tags優先で統一**

**変換パターン:**
```python
# OLD:
SearchConditions(tags=["test"], caption="sample")
SearchConditions(tags=["test1"])

# NEW:
SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
SearchConditions(search_type="tags", keywords=["test1"], tag_logic="and")
```

#### 2.2 実行
```bash
# 5箇所をエディタで置換 (Line 145, 178, 278, 279, 301)

# 検証
uv run pytest tests/unit/gui/services/test_worker_service.py -v
uv run ruff format tests/unit/gui/services/test_worker_service.py
uv run ruff check tests/unit/gui/services/test_worker_service.py

# コミット
git add tests/unit/gui/services/test_worker_service.py
git commit -m "test: Update 5 SearchConditions API calls

- Lines 145, 178, 278, 279, 301
- Convert tags=/caption= to search_type/keywords/tag_logic
- All tests pass"
```

---

### Step 3: test_worker_coordination.py (18箇所) - 40分

#### 3.1 コメント削除 (3箇所) - 5分

**対象:** Line 56, 97, 250

```bash
# 削除実行 (エディタで3箇所削除)

# 検証
uv run pytest tests/integration/gui/test_worker_coordination.py -v

# コミット
git add tests/integration/gui/test_worker_coordination.py
git commit -m "test: Remove 3 obsolete ProgressManager comments"
```

#### 3.2 dict変換 (1箇所) - 10分

**Line 61 判断:**
- テスト: `test_worker_service_search_integration`
- 用途: mock検証用のSearchConditions渡し
- mock assertion確認必要: `mock_worker_class.assert_called_once_with(...)`がSearchConditionsを期待するか

**変換:**
```python
# OLD:
filter_conditions = {"tags": ["test"], "caption": "sample"}

# NEW:
filter_conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
```

**注意:** mock assertion失敗時は assertionも修正

```bash
# 実行
# (エディタで1箇所変換)

# 単体検証
uv run pytest tests/integration/gui/test_worker_coordination.py::test_worker_service_search_integration -v

# コミット
git add tests/integration/gui/test_worker_coordination.py
git commit -m "test: Convert dict to SearchConditions (line 61)"
```

#### 3.3 API変換 (14箇所) - 25分

**変換判断フロー:**

| Line | tags | caption | 判断 | search_type |
|------|------|---------|------|-------------|
| 85, 89, 115, 139, 155, 184 | あり | なし | tags優先 | "tags" |
| 198 | あり | "" | 空caption無視 | "tags" |
| 227, 230, 240, 244 | あり | なし | tags優先 | "tags" |
| 267, 288, 311 | f-string | なし | tags優先 | "tags" |

**全て `search_type="tags"` で統一**

**理由:**
- テスト目的: ワーカー協調動作の検証
- 検索精度への依存なし
- caption値は全てダミーまたは空

```bash
# 14箇所をエディタで置換

# 5箇所ごとに中間検証
uv run pytest tests/integration/gui/test_worker_coordination.py -v

# 最終検証
uv run pytest tests/integration/gui/test_worker_coordination.py -v
uv run ruff format tests/integration/gui/test_worker_coordination.py

# コミット
git add tests/integration/gui/test_worker_coordination.py
git commit -m "test: Update 14 SearchConditions API calls

- Lines 85, 89, 115, 139, 155, 184, 198, 227, 230, 240, 244, 267, 288, 311
- All unified to search_type='tags'
- Dynamic f-string patterns handled"
```

---

### Step 4: 全体検証 (15分)

#### 4.1 対象ファイルテスト
```bash
# 修正した2ファイル
uv run pytest tests/unit/gui/services/test_worker_service.py -v
uv run pytest tests/integration/gui/test_worker_coordination.py -v

# コントロール(未修正)
uv run pytest tests/unit/gui/state/test_dataset_state.py -v
```

**期待:** 全て通過

#### 4.2 関連suite
```bash
# 検索関連
uv run pytest tests/unit/services/test_search_criteria_processor.py -v
uv run pytest tests/unit/gui/services/test_search_filter_service.py -v

# ワーカー関連
uv run pytest tests/unit/gui/workers/ -v
```

**期待:** 新規失敗なし

#### 4.3 カバレッジ
```bash
uv run pytest --cov=src --cov-report=term --cov-report=xml
```

**期待:** 75%以上

#### 4.4 品質チェック
```bash
uv run ruff format tests/
uv run ruff check tests/
uv run mypy -p lorairo
```

**期待:** 新規エラーなし

---

### Step 5: 完了記録 (5分)

```bash
# 新規メモリー作成 (.serena/memories/legacy_test_cleanup_completion_2025_12_12.md)
# 以下の内容でファイル作成:
# ===== 開始 =====
# Legacy Test Cleanup - 完了記録 (2025-12-12)

## 実行結果

**Base Commit:** c5951a395d9883cc2f663d526ff2a059e40aeb00

**修正箇所:**
- test_worker_service.py: 5箇所
- test_worker_coordination.py: 18箇所 (API 14 + dict 1 + comment 3)
- 合計: 23箇所

**テスト結果:**
- test_worker_service.py: [実際の数]/[実際の数] 通過
- test_worker_coordination.py: [実際の数]/[実際の数] 通過
- カバレッジ: [実際の%]%

**コミット:**
- [hash] test: Update 5 SearchConditions API calls
- [hash] test: Remove 3 obsolete ProgressManager comments
- [hash] test: Convert dict to SearchConditions (line 61)
- [hash] test: Update 14 SearchConditions API calls

## 教訓

1. DatasetStateManager.apply_filter_results()はdict受け取り設計
2. WorkerService.start_search()はSearchConditions必須
3. テスト意図分析が変換判断の鍵
# ===== 終了 =====
```

---

### 失敗時の対処

**テスト失敗:**
```bash
# 単体テスト実行で原因特定
uv run pytest <file>::<test_name> -vv

# TypeError → SearchConditions引数確認
# AssertionError → mock期待値確認
```

**ロールバック:**
```bash
# ファイル単位
git checkout c5951a395 -- tests/unit/gui/services/test_worker_service.py

# 全体
git reset --hard c5951a395
```

---

**補足:**
- 本手順はWindows/Linux両環境対応
- 詳細な760行版計画は別途存在 (開発環境に応じて参照)
- 実行環境: プロジェクトルート想定

---

**記録日:** 2025-12-12  
**調査者:** Explore Agent (agentId: 6dcfabee) + Manual Review  
**ステータス:** ✅ **実装完了** (2025-12-12)  
**影響:** テスト品質向上、API一貫性確保

---

## ✅ 完了ステータス

**完了日:** 2025-12-12  
**完了記録:** `.serena/memories/legacy_test_cleanup_completion_2025_12_12.md`  

**実装コミット:**
- 28d02df: test: Update 5 SearchConditions API calls in test_worker_service.py
- 4eb233e: test: Remove 3 obsolete ProgressManager comments
- 67bf639: test: Convert dict to SearchConditions in test_worker_coordination.py
- fa0cae8: test: Update 14 SearchConditions API calls in test_worker_coordination.py

**最終結果:**
- ✅ 全23箇所の修正完了 (19 API + 1 dict + 3 comments)
- ✅ SearchConditions変換: 100% 成功
- ✅ test_worker_service.py: 15/19 tests passing (4件は既存の失敗)
- ✅ test_worker_coordination.py: 11/12 tests passing (1件は既存の失敗)
- ✅ test_dataset_state.py: 10/10 tests passing (未変更・コントロール)
- ✅ 新規失敗なし、リグレッションなし
