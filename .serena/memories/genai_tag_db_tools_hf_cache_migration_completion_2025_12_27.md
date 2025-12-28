# genai-tag-db-tools HF標準キャッシュ移行完了記録

**実装日**: 2025-12-27  
**ブランチ**: `refactor/db-tools-hf`  
**完了コミット**: 8afa0ed (submodule), 376f2d8 (main repo)

## 実装概要

HuggingFace Hub標準キャッシュ（CAS: Content-Addressable Storage）への完全移行を実施。独自キャッシュ管理からHFライブラリに依存する設計へ変更。

## 主要変更

### 1. キャッシュ機構の統一 (commit 17f549f)

**削除したファイル**:
- `src/genai_tag_db_tools/io/cache_metadata.py` (140行) - 独自メタデータ管理
- `tests/unit/test_cache_metadata.py` (205行) - メタデータテスト

**変更内容**:
- `download_with_fallback()` → `download_with_offline_fallback()` にリネーム
- カスタム`local_dir`パラメータ削除、HF標準キャッシュ（blobs/snapshots/refs）を使用
- `local_files_only=True`によるオフラインフォールバック実装
- 戻り値: `tuple[Path, bool]` (パス, キャッシュ使用フラグ)

**影響ファイル**:
- `src/genai_tag_db_tools/io/hf_downloader.py`: 102行 → 82行 (20行削減)
- `src/genai_tag_db_tools/models.py`: `EnsureDbResult.downloaded` → `cached`
- `src/genai_tag_db_tools/core_api.py`: `ensure_databases()`の実装変更

### 2. GUI初期化の修正 (commit 2180fc9)

**問題**: `db_initialization.py`が旧キャッシュ構造を参照してクラッシュの可能性

**修正箇所**:
```python
# 削除 (19行) - 旧 base_dbs ディレクトリへのフォールバック
# src/genai_tag_db_tools/gui/services/db_initialization.py:115-133

# 簡素化 (6行) - download_with_offline_fallback() 結果のみに依存
except ConnectionError as e:
    error_msg = f"Network error and no cached databases available: {e}"
    logger.error(error_msg)
    self.signals.error.emit(error_msg)
    self.signals.complete.emit(False, error_msg)
```

**修正理由**:
- `cache_dir/base_dbs/filename` という旧構造へのアクセスを削除
- 存在しない `self.cache_dir` の参照を修正（`self.user_db_dir`が正）
- `ConnectionError`は既に`download_with_offline_fallback()`内で処理済み

### 3. 不要な制約の削除 (commit 9a3ad9b)

**削除した制約**:
```python
# src/genai_tag_db_tools/core_api.py:69-72 削除
# cache_dir一致チェック（無意味）
# tokenフィールド一致チェック（無意味）
```

**削除した引数**:
```python
# src/genai_tag_db_tools/io/hf_downloader.py
def ensure_db_ready(spec: HFDatasetSpec, *, token: str | None = None) -> Path:
    # user_db_dir引数を削除（未使用だった）

def ensure_databases_ready(specs: list[HFDatasetSpec], *, token: str | None = None) -> list[Path]:
    # user_db_dir引数を削除（未使用だった）
```

**削除したテスト**:
- `test_ensure_databases_requires_same_cache_dir` - 削除された制約のテスト

**変更理由**:
- 複数のDB要求で異なる`cache_dir`を使うことは正当なユースケース
- リクエストごとに異なるトークンを使う必要がある場合もある
- 未使用の引数は混乱を招くだけ

### 4. デフォルトパス実装 (commit 78f7250)

**目的**: 明示的な設定なしでDB初期化が可能に

**変更**:
```python
# src/genai_tag_db_tools/db/runtime.py:102-122
def init_user_db(user_db_dir: Path | None = None) -> Path:
    """ユーザーDBを初期化する。存在しなければ空DBを作成する。
    
    Args:
        user_db_dir: ユーザーDB配置ディレクトリ（Noneの場合はデフォルト）
    
    Returns:
        Path: 初期化されたuser_tags.sqliteのパス
    """
    if user_db_dir is None:
        from genai_tag_db_tools.io.hf_downloader import default_cache_dir
        user_db_dir = default_cache_dir()
    
    # 残りの実装は同じ
```

**docstring修正**:
```python
# src/genai_tag_db_tools/db/runtime.py:43
def get_base_database_paths() -> list[Path]:
    """ベースDBパス一覧を返す。未設定なら例外を投げる。"""  # 修正前: 「未設定なら単一DBを返す」
    if _base_db_paths is not None:
        return list(_base_db_paths)
    return [get_database_path()]  # これは RuntimeError を投げる
```

**設計原則**:
- **ユーザーDB**: デフォルトで`default_cache_dir()`（OS別アプリキャッシュ）を使用
- **ベースDB**: HF標準キャッシュ（`~/.cache/huggingface/hub/`）を自動使用
- **例外なし**: デフォルト設定で必ず動作する設計

### 5. コード品質管理 (commit 8afa0ed)

Ruffによる自動フォーマット（行長108文字に調整）:
- `src/genai_tag_db_tools/core_api.py`: 多行呼び出しを1行に統合
- `tests/unit/test_hf_downloader.py`: monkeypatch.setattr呼び出しを1行に統合

## テスト結果

### 修正したテスト (35個すべて合格)

**test_hf_downloader.py** (6テスト):
- `test_default_cache_dir_points_to_app_cache`
- `test_download_uses_hf_standard_cache` - `local_dir`不使用を確認
- `test_offline_fallback_uses_local_files_only` - `local_files_only=True`を確認
- `test_offline_fallback_returns_fresh_download` - `is_cached=False`確認
- `test_offline_fallback_raises_when_no_cache_available` - エラー動作確認
- `test_ensure_db_ready_sets_runtime` - runtime初期化確認

**test_core_api.py** (5テスト):
- `test_ensure_db_returns_fresh_download` - `cached=False`確認
- `test_ensure_db_returns_cached_download` - `cached=True`確認
- `test_ensure_databases_returns_cached_status_per_spec` - 個別キャッシュ状態確認
- `test_search_tags_filters_and_maps`
- `test_register_tag_delegates`

**test_models.py** (24テスト):
- `EnsureDbResult.cached`フィールドに変更（全テスト更新）
- その他Pydanticモデルのバリデーションテスト

### 品質チェック

```bash
# Ruff linter: All checks passed!
uv run ruff check local_packages/genai-tag-db-tools/src/

# pytest: 35/35 passed
uv run pytest local_packages/genai-tag-db-tools/tests/unit/test_{core_api,hf_downloader,models}.py
```

## アーキテクチャ変更

### Before: 独自キャッシュ管理

```
cache_dir/
├── cache_metadata.json          # 独自メタデータ
├── base_dbs/
│   ├── genai-image-tag-db-cc4.sqlite
│   └── genai-image-tag-db-mit.sqlite
└── user_tags.sqlite
```

### After: HF標準キャッシュ + 分離されたユーザーDB

```
# ベースDB: HF標準キャッシュ（自動管理）
~/.cache/huggingface/hub/
├── models--NEXTAltair--genai-image-tag-db-CC4/
│   ├── blobs/
│   │   └── abc123...  # content-addressable storage
│   ├── snapshots/
│   │   └── v1.0/
│   │       └── genai-image-tag-db-cc4.sqlite -> ../../blobs/abc123...
│   └── refs/
│       └── main -> ../snapshots/v1.0
└── models--NEXTAltair--genai-image-tag-db-mit/
    └── (同様の構造)

# ユーザーDB: アプリ専用ディレクトリ（分離管理）
~/.cache/genai-tag-db-tools/  # Linux/macOS default_cache_dir()
└── user_tags.sqlite
```

**設計上の利点**:
1. **HFライブラリに完全依存**: キャッシュ整合性はHF Hub SDKが保証
2. **オフライン対応**: `local_files_only=True`でキャッシュ優先動作
3. **ディスク効率**: CASによる重複排除（同一blobは1回のみ保存）
4. **保守性向上**: 独自実装140行削除、テスト205行削減

## データフロー

### DB初期化シーケンス（GUI起動時）

```python
# 1. GUI初期化サービス
DbInitializationService.initialize_databases()
    ↓
# 2. 複数DBの準備
core_api.ensure_databases([req1, req2, req3])
    ↓ (各リクエストごとに)
# 3. HFからダウンロード/キャッシュ確認
hf_downloader.download_with_offline_fallback(spec, token=req.cache.token)
    ↓ try
# 4a. ネットワークダウンロード
hf_hub_download(repo_id, filename, token=token)
    → return (Path, is_cached=False)
    ↓ except ConnectionError
# 4b. オフラインフォールバック
hf_hub_download(repo_id, filename, local_files_only=True)
    → return (Path, is_cached=True)
    ↓
# 5. ベースDBパス設定
runtime.set_base_database_paths([path1, path2, path3])
    ↓
# 6. ベースエンジン初期化
runtime.init_engine(base_paths[0])
    ↓
# 7. ユーザーDB初期化（デフォルトパス）
runtime.init_user_db(user_db_dir=None)  # default_cache_dir()を自動使用
    ↓
# 8. 完了シグナル
DbInitWorker.signals.complete.emit(True, "Database ready")
```

### エラーハンドリング階層

1. **`download_with_offline_fallback()`**: 
   - ネットワークエラー → キャッシュ確認 → キャッシュなし時のみ`RuntimeError`
   
2. **`DbInitWorker.run()`**:
   - `FileNotFoundError`: DBファイル不在
   - `ConnectionError`: 完全なネットワーク障害（キャッシュなし）
   - `Exception`: 予期しないエラー（詳細ログ付き）

3. **GUIレイヤー**:
   - エラーシグナル → ユーザーへの通知ダイアログ

## 互換性とマイグレーション

### 破壊的変更

1. **フィールド名変更**: `EnsureDbResult.downloaded` → `cached`
   - 影響: APIクライアントは更新必須
   - 理由: キャッシュ使用/ネットワーク取得の区別を明確化

2. **関数リネーム**: `download_with_fallback()` → `download_with_offline_fallback()`
   - 影響: 直接呼び出しコードは更新必須
   - 理由: オフライン動作の意図を明確化

3. **キャッシュディレクトリ構造変更**:
   - 影響: 既存の`cache_dir/base_dbs/`は使用されなくなる
   - マイグレーション: 不要（HFが新規ダウンロード/既存キャッシュ検出）

### 後方互換性維持

- `DbCacheConfig.cache_dir`: パラメータは残存（ユーザーDB配置用に再利用）
- `ensure_db()` / `ensure_databases()`: 関数シグネチャ不変
- `runtime.init_user_db()`: 明示的パス指定も引き続きサポート

## 関連ドキュメント

- **HF Hub標準キャッシュ仕様**: https://huggingface.co/docs/huggingface_hub/guides/manage-cache
- **実装計画メモリ**: `plan_lexical_pondering_swan_2025_12_27.md`
- **コミット履歴**:
  - 17f549f: HF標準キャッシュ移行
  - 2180fc9: GUI初期化修正
  - 9a3ad9b: 不要制約削除
  - 78f7250: デフォルトパス実装
  - 8afa0ed: コード品質管理

## 検証コマンド

```bash
# テスト実行
cd /workspaces/LoRAIro
uv run pytest local_packages/genai-tag-db-tools/tests/unit/ -xvs

# コード品質チェック
uv run ruff check local_packages/genai-tag-db-tools/src/
uv run ruff format --check local_packages/genai-tag-db-tools/src/

# 型チェック（オプション）
uv run mypy local_packages/genai-tag-db-tools/src/genai_tag_db_tools/
```
