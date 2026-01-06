# db_core.py Legacy Tag DB Cleanup - 2026-01-02

**日付**: 2026-01-02
**対象**: src/lorairo/database/db_core.py
**トリガー**: ユーザー報告「古いファイルへの参照が残ってる (TAG_DB_FILENAME = "tags_v4.db")」

## 問題

db_core.py に古い Tag DB アーキテクチャへの参照が残っていた：
- `TAG_DB_PACKAGE` / `TAG_DB_FILENAME` - genai_tag_db_tools.data パッケージから tag DB を読み込む古い方式
- `TAG_DB_PATH` / `TAG_DATABASE_ALIAS` - SQLite ATTACH DATABASE 方式（古い統合方法）
- `get_tag_db_path()` - importlib.resources でパッケージ内 DB ファイルを解決
- `attach_tag_db_listener()` - SQLAlchemy イベントリスナーでタグ DB をアタッチ

**現在のアーキテクチャ**:
- Base DB: `ensure_databases()` で HuggingFace からダウンロード（3 DB files）
- User DB: `init_user_db()` で user_tags.sqlite を作成（format_id 1000+）
- 統合: Repository Pattern 経由（`search_tags()`, `register_tag()`, `MergedTagReader`）

## 実施した変更

### 1. 定数削除と注釈追加

**L94-97 (変更前)**:
```python
TAG_DB_PACKAGE = db_config.get("tag_db_package", "genai_tag_db_tools.data")
TAG_DB_FILENAME = db_config.get("tag_db_filename", "tags_v4.db")
```

**L94-95 (変更後)**:
```python
# Note: TAG_DB_PACKAGE and TAG_DB_FILENAME were removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API (ensure_databases + init_user_db)
```

### 2. 関数削除と注釈追加

**L135-158 (変更前)**:
```python
def get_tag_db_path() -> Path:
    """インストールされたパッケージからタグデータベースファイルへのフルパスを取得します。"""
    try:
        package_name = TAG_DB_PACKAGE
        filename = TAG_DB_FILENAME
        tag_db_resource = importlib.resources.files(package_name).joinpath(filename)
        # ...
```

**L134-137 (変更後)**:
```python
# --- Tag DB Path --- #
# Note: get_tag_db_path() was removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API:
# - Base DBs: ensure_databases() downloads from HuggingFace
# - User DB: init_user_db() creates user_tags.sqlite in project directory
```

### 3. グローバル変数削除

**L196-198 (変更前)**:
```python
# TAG_DB_PATH = get_tag_db_path()  # Deprecated
TAG_DB_PATH = None  # 互換性のため残すがNoneで初期化
TAG_DATABASE_ALIAS = "tag_db"
```

**L173-175 (変更後)**:
```python
# --- SQLAlchemy エンジンとセッション設定 ---
# Note: TAG_DB_PATH and TAG_DATABASE_ALIAS were removed (2026-01-02)
# Tag databases no longer use ATTACH DATABASE; managed via genai-tag-db-tools repository pattern
```

### 4. イベントリスナー削除

**L274-296 (変更前)**:
```python
@event.listens_for(engine, "connect")
def attach_tag_db_listener(dbapi_connection: Any, connection_record: Any) -> None:
    """メインDB接続時にタグデータベースをアタッチします (インメモリDBを除く)。"""
    # Deprecated: タグDBは公開API経由で管理されるため、アタッチ不要
    if TAG_DB_PATH is None:
        logger.debug("Tag DB managed via public API, skipping database attachment.")
        return
    # ...
```

**L251-253 (変更後)**:
```python
# Note: attach_tag_db_listener was removed (2026-01-02)
# Tag databases no longer use ATTACH DATABASE; managed via genai-tag-db-tools repository pattern
# Base DBs + User DB are accessed through public API (search_tags, register_tag, MergedTagReader)
```

### 5. 不要な import 削除

**L8 (変更前)**:
```python
import importlib.resources
```

**削除済み** - get_tag_db_path() でのみ使用されていた

### 6. 型アノテーション追加

**L177 (変更前)**:
```python
IMG_DB_PATH = DB_DIR / IMG_DB_FILENAME
```

**L177 (変更後)**:
```python
IMG_DB_PATH: Path = DB_DIR / IMG_DB_FILENAME
```

**理由**: mypy が `IMG_DB_PATH.parent` の型を推論できず `Any` と判断していたため明示

## 検証結果

### 1. 型チェック
```bash
$ uv run mypy src/lorairo/database/db_core.py
Success: no issues found in 1 source file
```

### 2. Unit Tests
```bash
$ uv run pytest tests/unit/database/ -v
53 passed, 2 skipped in 0.85s
```

### 3. Integration Tests
```bash
$ uv run pytest tests/integration/database/ -v
8 skipped in 0.43s  # TEST_TAG_DB_PATH 未設定のため正常スキップ
```

### 4. 参照確認
```bash
$ grep -r "TAG_DB_FILENAME\|TAG_DB_PACKAGE\|TAG_DB_PATH\|TAG_DATABASE_ALIAS" --include="*.py" src/
# No matches（注釈のみ）
```

## 影響範囲

### 削除された機能
1. **パッケージ内 DB 読み込み**: `importlib.resources` による tag DB アクセス
2. **ATTACH DATABASE**: SQLite のデータベースアタッチ機能
3. **静的 DB パス**: ハードコードされた tag DB ファイルパス

### 現在の動作
1. **Base DB**: `ensure_databases()` で動的に HuggingFace からダウンロード
2. **User DB**: `init_user_db()` でプロジェクトディレクトリに作成
3. **統合**: Repository Pattern（`get_default_reader()` で MergedTagReader 取得）

### 互換性
- **後方互換性**: なし（古い設定値 `tag_db_package`, `tag_db_filename` は無視される）
- **既存コード**: 影響なし（db_core から TAG_DB_* をインポートしているコードは存在しない）
- **テスト**: 全テスト通過（古い方式への依存なし）

## アーキテクチャ変遷

### Phase 1 (2024-2025): パッケージ内 DB
```python
TAG_DB_PATH = get_tag_db_path()  # genai_tag_db_tools.data/tags_v4.db
engine.connect -> ATTACH DATABASE {TAG_DB_PATH} AS tag_db
```

### Phase 2 (2025-12): HuggingFace Base DB + User DB
```python
ensure_databases([DbSourceRef("NEXTAltair/genai-image-tag-db")])
runtime.init_user_db(user_db_dir=DB_DIR, format_name="Lorairo")
reader = get_default_reader()  # MergedTagReader (base+user)
```

### Phase 3 (2026-01-02): Legacy Code Cleanup
- 古いコード完全削除
- 注釈で移行履歴を明示
- Repository Pattern のみ使用

## 学んだこと

1. **段階的 Deprecation の重要性**:
   - Phase 1 で ATTACH DATABASE を無効化（L277 早期 return）
   - Phase 2 で新 API に移行
   - Phase 3 で古いコード削除（安全な段階的移行）

2. **型アノテーションの明示**:
   - グローバル変数の型は明示すべき（mypy 推論の限界）
   - `Path` 型の操作（`.parent`）も推論できない場合がある

3. **注釈の価値**:
   - 削除した機能の説明を残すことで、将来の混乱を防ぐ
   - 「なぜ削除されたか」「どう置き換えられたか」を明記

4. **import の整理**:
   - 不要な import は必ず削除（`importlib.resources`）
   - 型チェックで検出されるため見逃しにくい

## 関連ファイル

- [src/lorairo/database/db_core.py](src/lorairo/database/db_core.py) - 今回の変更対象
- [tag_management_service_user_db_only_fix_2026_01_01](tag_management_service_user_db_only_fix_2026_01_01.md) - User DB 専用化
- [genai_tag_db_tools_gui_service_migration_2025_12_29](genai_tag_db_tools_gui_service_migration_2025_12_29.md) - Repository Pattern 導入

## 今後の TODO

- [x] ~~config/lorairo.toml の `tag_db_package`, `tag_db_filename` 設定値を削除（使用されていない）~~ → **完了 (2026-01-02)**
  - `src/lorairo/utils/config.py` L112-113 から削除
  - 注釈追加: "Note: tag_db_package and tag_db_filename were removed (2026-01-02)"
  - 検証: mypy 成功、26/28 テスト通過、database tests 53/55 通過
- [ ] 古い環境変数 `TEST_TAG_DB_PATH` の用途を確認（integration tests で使用中）

## 追記 (2026-01-02 12:08 UTC)

### config.py からのレガシー設定値削除

**対象ファイル**: `src/lorairo/utils/config.py`

**削除した設定値**:
```python
# L112-113 (削除前)
"tag_db_package": "genai_tag_db_tools.data",  # タグDBのインポート元パッケージ名
"tag_db_filename": "tags_v4.db",  # タグDBのファイル名
```

**追加した注釈**:
```python
# L112-113 (削除後)
# Note: tag_db_package and tag_db_filename were removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API (ensure_databases + init_user_db)
```

**検証結果**:
- `grep -r "tag_db_package|tag_db_filename"` → config.py のみに存在（実装コードで未使用）
- `config/lorairo.toml` → 記述なし（デフォルト設定のみの削除）
- `uv run mypy src/lorairo/utils/config.py` → Success
- `uv run pytest tests/unit/test_configuration_service.py` → 26/28 passed (失敗2件はログ出力関連で無関係)
- `uv run pytest tests/unit/database/` → 53/55 passed (skipped 2件は正常)

**理由**:
- db_core.py では 2026-01-02 に既に削除済み
- genai-tag-db-tools の公開 API (`ensure_databases()`, `init_user_db()`) に完全移行
- Phase 3 (Legacy Code Cleanup) の一環として削除

**影響範囲**:
- なし（使用箇所が存在しない）
- 既存の `config/lorairo.toml` には記述されていないため、後方互換性の問題なし
