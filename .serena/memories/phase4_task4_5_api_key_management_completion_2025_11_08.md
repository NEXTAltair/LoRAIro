# Phase 4-5 APIキー管理統合完了記録

**日付**: 2025-11-08  
**フェーズ**: Phase 4-5 (APIキー管理統合)  
**実装方針**: 引数ベース方式（api_keysパラメータ）  
**コミットハッシュ**: 4f35b97

---

## 実装概要

### アプローチ決定プロセス

#### 調査結果
1. **現状の問題点**:
   - 環境変数方式（`os.environ`）でグローバル状態を汚染
   - テスト困難（環境変数のクリーンアップ必要）
   - スレッドセーフではない

2. **image-annotator-lib API仕様**:
   - `annotate(api_keys=dict[str, str])` をサポート
   - 引数 > 環境変数 の優先順位
   - 実装ファイル: `api.py` (line 359)
   - ラッパー関数: `__init__.py` (line 58) - **バグ修正が必要だった**

3. **評価した選択肢**:
   - **Approach A**: 環境変数（現状維持）- グローバル状態汚染が問題
   - **Approach B**: 引数ベース（推奨）✅ - クリーン、テスタブル、スレッドセーフ
   - **Approach C**: ハイブリッド - 過剰設計（YAGNI違反）
   - **Approach D**: Vault/AWS Secrets Manager - 大規模過ぎる（デスクトップアプリには不要）

4. **最終決定**: **Approach B (引数ベース方式)** を採用
   - YAGNI準拠
   - image-annotator-lib設計意図に合致
   - 明示的データフロー
   - テスト容易性

---

## 実装詳細

### 1. AnnotatorLibraryAdapter修正

**ファイル**: `src/lorairo/services/annotator_library_adapter.py`

#### 削除した機能
```python
# ❌ 削除: 環境変数設定方式
def _set_api_keys_to_env(self) -> None:
    os.environ["OPENAI_API_KEY"] = openai_key
    # ...
```

#### 追加した機能
```python
# ✅ 追加: APIキー辞書構築
def _prepare_api_keys(self) -> dict[str, str]:
    """ConfigServiceからAPIキーを取得し辞書構築"""
    api_keys = {
        "openai": self.config_service.get_setting("api", "openai_key", ""),
        "anthropic": self.config_service.get_setting("api", "claude_key", ""),
        "google": self.config_service.get_setting("api", "google_key", ""),
    }
    # 空のキーを除外
    api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}
    return api_keys

# ✅ 追加: ログ用キーマスキング
def _mask_key(self, key: str) -> str:
    """APIキーをマスキング（例: sk-ab***cd）"""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"
```

#### annotate()メソッド変更
```python
# Before (Phase 4-1)
def annotate(...):
    self._set_api_keys_to_env()  # グローバル環境変数設定
    results = annotate(images_list, model_name_list, phash_list)

# After (Phase 4-5)
def annotate(...):
    api_keys = self._prepare_api_keys()  # 辞書構築
    results = annotate(
        images_list=images,
        model_name_list=model_names,
        phash_list=phash_list,
        api_keys=api_keys  # 明示的に引数として渡す
    )
```

---

### 2. image-annotator-lib バグ修正

**問題**: `__init__.py` のラッパー関数が `api_keys` パラメータを転送していない

**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/__init__.py`

#### 修正内容
```python
# Before
def annotate(
    images_list: list[Image.Image],
    model_name_list: list[str],
    phash_list: list[str] | None = None
) -> PHashAnnotationResults:
    return _cached_annotate(images_list, model_name_list, phash_list)

# After
def annotate(
    images_list: list[Image.Image],
    model_name_list: list[str],
    phash_list: list[str] | None = None,
    api_keys: dict[str, str] | None = None,  # 追加
) -> PHashAnnotationResults:
    """
    Args:
        api_keys: WebAPIモデル用のAPIキー辞書（オプション）。
                 例: {"openai": "sk-...", "anthropic": "sk-ant-..."}
                 指定された場合、環境変数より優先されます。
    """
    return _cached_annotate(images_list, model_name_list, phash_list, api_keys)
```

**理由**: `api.py` の実装は `api_keys` をサポートしているが、`__init__.py` のラッパーが転送していなかった

---

### 3. テスト更新

**ファイル**: `tests/unit/services/test_annotator_library_adapter.py`

#### 削除したテスト
- `test_set_api_keys_to_env()` - 環境変数設定テスト
- `test_set_api_keys_to_env_empty_keys()` - 空キー処理テスト

#### 追加したテスト
```python
def test_prepare_api_keys_all_keys(self, adapter):
    """全キー設定済みの場合"""
    api_keys = adapter._prepare_api_keys()
    assert api_keys == {
        "openai": "test-openai-key",
        "anthropic": "test-claude-key",
        "google": "test-google-key",
    }

def test_prepare_api_keys_empty_keys(self):
    """空キー除外確認"""
    # 空文字列・空白のみのキーは除外される
    assert api_keys == {"openai": "sk-test-key"}

def test_prepare_api_keys_no_keys(self):
    """全キーが空の場合"""
    assert api_keys == {}

def test_mask_key(self, adapter):
    """キーマスキング確認"""
    assert adapter._mask_key("sk-test-openai-key-12345") == "sk-t***2345"
    assert adapter._mask_key("short") == "***"
    assert adapter._mask_key("") == "***"
```

#### 更新したテスト
```python
def test_annotate_success(self, mock_annotate, adapter):
    """api_keysパラメータが正しく渡されることを確認"""
    mock_annotate.assert_called_once_with(
        images_list=[test_image],
        model_name_list=["gpt-4o"],
        phash_list=["test_phash"],
        api_keys={  # 引数として渡されることを検証
            "openai": "test-openai-key",
            "anthropic": "test-claude-key",
            "google": "test-google-key",
        },
    )
```

---

## テスト結果

### テスト実行
```bash
# AnnotatorLibraryAdapter
uv run pytest tests/unit/services/test_annotator_library_adapter.py
✅ 10/10 tests passed

# AnnotationService
uv run pytest tests/unit/services/test_annotation_service.py
✅ 11/11 tests passed

# AnnotationWorker
uv run pytest tests/unit/gui/workers/test_annotation_worker.py
✅ 14/14 tests passed

# Total
✅ 35/35 tests passed
```

### 型チェック
```bash
uv run mypy src/lorairo/services/annotator_library_adapter.py
✅ Success: no issues found
```

---

## セキュリティ対策

### 1. APIキーマスキング
```python
def _mask_key(self, key: str) -> str:
    """8文字以上: sk-ab***cd 形式、8文字未満: ***"""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"
```

**ログ出力例**:
```
DEBUG - APIキー準備完了: ['openai', 'anthropic'] (masked: {'openai': 'sk-t***2345', 'anthropic': 'sk-a***7890'})
```

### 2. 空キー検証
```python
# 空文字列・空白のみを除外
api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}
```

### 3. 既存セキュリティ（継続利用）
- `ConfigurationService._mask_api_key()` - 設定取得時のマスキング
- `.gitignore` によるconfig/lorairo.toml除外
- ファイルパーミッション（ユーザーのみ読み書き）

---

## アーキテクチャ改善

### Before (Phase 4-1)
```
AnnotatorLibraryAdapter
  ↓ _set_api_keys_to_env()
os.environ (グローバル状態)
  ↓ 環境変数読み取り
image-annotator-lib
```

**問題点**:
- ❌ グローバル環境変数汚染
- ❌ テスト間で環境変数が残る
- ❌ スレッドセーフではない
- ❌ 暗黙的なデータフロー

### After (Phase 4-5)
```
AnnotatorLibraryAdapter
  ↓ _prepare_api_keys()
api_keys: dict[str, str]
  ↓ annotate(api_keys=...)
image-annotator-lib
```

**改善点**:
- ✅ グローバル状態なし
- ✅ 明示的なデータフロー
- ✅ テスト容易（モック注入簡単）
- ✅ スレッドセーフ
- ✅ YAGNI準拠

---

## Phase 4 全体進捗

```
Phase 4: image-annotator-lib統合

✅ Phase 4-1: AnnotatorLibraryAdapter実装
   - Commit: 5e07aec
   - 完了日: 2025-11-06

✅ Phase 4-2: ModelSyncService統合
   - Phase 4-3と同時実装
   - ServiceContainer.model_sync_service修正

✅ Phase 4-3: AnnotationService実装
   - Commit: 9661bd4
   - 完了日: 2025-11-06

✅ Phase 4-4: AnnotationWorker実装
   - Commit: 2c79726
   - 完了日: 2025-11-07

✅ Phase 4-5: APIキー管理統合 ← 本タスク
   - Commit: 4f35b97
   - 完了日: 2025-11-08

⏳ Phase 4-6: 統合テスト・検証
   - 未実施
```

---

## 学んだ教訓

### 1. サブモジュールのバグ発見
- **問題**: `__init__.py` のラッパー関数が新パラメータを転送していなかった
- **解決**: 型チェックエラーから発見し、即座に修正
- **教訓**: ラッパー関数は全パラメータを転送すること

### 2. YAGNI原則の重要性
- **選択肢**: Vault/AWS Secrets Managerなど企業向けソリューション
- **判断**: デスクトップアプリには過剰 → シンプルな引数渡しを採用
- **教訓**: ユースケースに合った適切な複雑度を選択

### 3. 明示的 > 暗黙的
- **Before**: 環境変数（暗黙的、グローバル状態）
- **After**: 引数渡し（明示的、ローカルスコープ）
- **教訓**: 明示的なデータフローはバグを減らし、保守性を向上させる

---

## 技術的決定の記録

### 決定1: Pydantic Settingsを使わない
- **理由**: 現状の`ConfigurationService`で十分（YAGNI）
- **将来**: 必要になったら導入を検討

### 決定2: ローカル`_mask_key()`を実装
- **理由**: `ConfigurationService._mask_api_key()`は設定値専用
- **代替**: 独自のシンプルなマスキング実装
- **形式**: `sk-ab***cd` (先頭4文字 + *** + 末尾4文字)

### 決定3: 空キー除外ロジック
```python
api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}
```
- **理由**: 空文字列や空白のみのキーは無効
- **効果**: image-annotator-libのエラーを事前防止

---

## 次のステップ (Phase 4-6)

### 手動検証
1. 実際のAPIキーで各プロバイダーをテスト
   - OpenAI (gpt-4o)
   - Anthropic (claude-sonnet)
   - Google (gemini-2.5-flash)

2. ログ確認
   - APIキーがマスキングされていること
   - 環境変数が設定されていないこと

3. 複数モデル同時実行
   - スレッドセーフ性の確認

### 統合テスト
1. MainWindow → AnnotationService → AnnotatorLibraryAdapter の完全フロー
2. バッチ処理の動作確認
3. エラーハンドリングの検証

---

## 関連リソース

### 実装ファイル
- `src/lorairo/services/annotator_library_adapter.py`
- `local_packages/image-annotator-lib/src/image_annotator_lib/__init__.py`
- `local_packages/image-annotator-lib/src/image_annotator_lib/api.py`

### テストファイル
- `tests/unit/services/test_annotator_library_adapter.py`
- `tests/unit/services/test_annotation_service.py`
- `tests/unit/gui/workers/test_annotation_worker.py`

### 設計資料
- Memory: `phase4_task4_5_api_key_design_investigation_2025_11_08` (調査記録)
- Memory: `lorairo_annotator_integration_plan_2025` (全体計画)

---

## まとめ

Phase 4-5では、APIキー管理を**環境変数方式から引数ベース方式**に移行しました。

**主要な成果**:
1. ✅ グローバル状態汚染の排除
2. ✅ テスト容易性の向上
3. ✅ スレッドセーフ性の確保
4. ✅ 明示的なデータフローの実現
5. ✅ YAGNI原則の遵守

**テスト結果**: 35/35 tests passed ✅  
**型チェック**: mypy passed ✅  
**セキュリティ**: APIキーマスキング実装済み ✅

この実装により、Phase 4の主要タスクが完了し、Phase 4-6（統合テスト・検証）に進む準備が整いました。
