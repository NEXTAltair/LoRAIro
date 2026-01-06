# Plan: recursive-orbiting-leaf

**Created**: 2026-01-02 13:41:36
**Source**: plan_mode
**Original File**: recursive-orbiting-leaf.md
**Status**: planning

---

# Tag Database Initialization Migration Plan

## 概要

タグデータベース初期化処理を `genai-tag-db-tools` 側に集約し、LoRAIro側はシンプルな関数呼び出しのみに変更する。

## 調査結果サマリー

### 現状確認

1. **genai-tag-db-tools の実装**:
   - `_default_sources()` は既に3つすべて（CC4, MIT, CC0）を返す実装
   - `initialize_databases()` で `sources=None` にすると3つすべて自動ダウンロード
   - **問題**: `format_name` パラメータが `initialize_databases()` で公開されていない

2. **現在のLoRAIro実装** ([db_core.py:179-220](src/lorairo/database/db_core.py#L179-L220)):
   - CC0のみを手動でダウンロード
   - 手動で `runtime.set_base_database_paths()`, `init_engine()`, `init_user_db()` を呼び出し
   - `format_name="Lorairo"` を明示的に渡している

### ユーザー要件

1. **3つすべてのDBを使用**: CC4, MIT, CC0（デフォルト動作）
2. **format_name="Lorairo" 維持**: アプリケーション名をハードコードして渡す運用ポリシー

## 実装アプローチ

genai-tag-db-tools に `format_name` パラメータを追加し、LoRAIro側をシンプル化する。

**効果**:
- 責任分離が明確（初期化ロジックはライブラリ側）
- コード削減（35行 → 約15行）
- 保守性向上（HuggingFace URL変更時もライブラリ側のみ修正）
- 他プロジェクトでも同じパターンで使用可能
- genai-tag-db-tools への変更が必要（local packageのため影響範囲は限定的）

## 詳細実装計画

### Phase 1: genai-tag-db-tools 側の拡張

**ファイル**: `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py`

#### Step 1.1: `initialize_databases()` シグネチャ変更

**Location**: [core_api.py:84-90](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py#L84-L90)

**変更前**:
```python
def initialize_databases(
    user_db_dir: Path | str | None = None,
    sources: list[DbSourceRef] | None = None,
    token: str | None = None,
    *,
    init_user_db: bool | None = None,
) -> list[EnsureDbResult]:
```

**変更後**:
```python
def initialize_databases(
    user_db_dir: Path | str | None = None,
    sources: list[DbSourceRef] | None = None,
    token: str | None = None,
    *,
    init_user_db: bool | None = None,
    format_name: str | None = None,  # 🆕 追加
) -> list[EnsureDbResult]:
```

#### Step 1.2: Docstring更新

**Location**: [core_api.py:91-100](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py#L91-L100)

**追加内容**:
```python
"""Download base DBs (if needed) and initialize runtime.

Args:
    user_db_dir: User DB directory (user_tags.sqlite). If None, defaults to OS cache dir
        when init_user_db is True.
    sources: Optional list of DbSourceRef. If None, default sources are used.
    token: Hugging Face access token (optional).
    init_user_db: Whether to initialize the user DB. Defaults to True when user_db_dir
        is provided, otherwise False.
    format_name: Format name for user DB (e.g., "Lorairo", "MyApp").  # 🆕 追加
        If None, defaults to "tag-db".
"""
```

#### Step 1.3: `init_user_db()` 呼び出し修正

**Location**: [core_api.py:116-117](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py#L116-L117)

**変更前**:
```python
if init_user_db:
    runtime.init_user_db(cache_dir)
```

**変更後**:
```python
if init_user_db:
    runtime.init_user_db(cache_dir, format_name=format_name)
```

### Phase 2: LoRAIro側のシンプル化

**ファイル**: `src/lorairo/database/db_core.py`

#### Step 2.1: Import変更

**Location**: [db_core.py:182-185](src/lorairo/database/db_core.py#L182-L185)

**変更前**:
```python
from genai_tag_db_tools import ensure_databases
from genai_tag_db_tools.db import runtime
from genai_tag_db_tools.models import DbCacheConfig, DbSourceRef, EnsureDbRequest
```

**変更後**:
```python
from genai_tag_db_tools import initialize_databases
```

#### Step 2.2: 初期化処理の書き換え

**Location**: [db_core.py:179-213](src/lorairo/database/db_core.py#L179-L213)

**変更前（35行）**:
```python
# --- genai-tag-db-tools Database Initialization --- #
# GUI起動前にベースDB + ユーザーDBを初期化
try:
    from genai_tag_db_tools import ensure_databases
    from genai_tag_db_tools.db import runtime
    from genai_tag_db_tools.models import DbCacheConfig, DbSourceRef, EnsureDbRequest

    logger.info("Initializing genai-tag-db-tools databases...")

    # 1. ベースDBをHuggingFaceからダウンロード
    requests = [
        EnsureDbRequest(
            source=DbSourceRef(
                repo_id="NEXTAltair/genai-image-tag-db",
                filename="genai-image-tag-db-cc0.sqlite",
                revision=None,
            ),
            cache=DbCacheConfig(cache_dir=str(DB_DIR), token=None),
        )
    ]
    results = ensure_databases(requests)
    base_paths = [Path(result.db_path) for result in results]

    # 2. ベースDBパスを設定
    runtime.set_base_database_paths(base_paths)
    logger.info(f"Base tag database configured: {base_paths[0]}")

    # 3. SQLAlchemyエンジン初期化
    runtime.init_engine(base_paths[0])

    # 4. ユーザーDBをプロジェクトディレクトリに作成
    USER_TAG_DB_PATH = runtime.init_user_db(user_db_dir=DB_DIR, format_name="Lorairo")
    logger.info(f"User tag database initialized: {USER_TAG_DB_PATH}")

    logger.info("Tag database initialization complete (GUI起動準備完了)")
```

**変更後（15行、57%削減）**:
```python
# --- genai-tag-db-tools Database Initialization --- #
# GUI起動前にベースDB（3つ: CC4, MIT, CC0）+ ユーザーDBを初期化
try:
    from genai_tag_db_tools import initialize_databases

    logger.info("Initializing genai-tag-db-tools databases...")

    # ワンストップ初期化（デフォルトで3つすべてのDBをダウンロード）
    results = initialize_databases(
        user_db_dir=DB_DIR,
        format_name="Lorairo",
    )

    USER_TAG_DB_PATH = DB_DIR / "user_tags.sqlite"
    logger.info(f"Tag databases initialized: {len(results)} base DB(s) + user DB at {USER_TAG_DB_PATH}")
```

#### Step 2.3: コメント更新

**変更内容**:
- "ベースDB（3つ: CC4, MIT, CC0）" を明記
- `sources` パラメータ省略時はデフォルトで3つすべてダウンロードされることを明示

### Phase 3: テスト更新

**ファイル**: `tests/conftest.py`

#### Step 3.1: Mock更新

**Location**: [conftest.py:18-44](tests/conftest.py#L18-L44)

**変更内容**:
- `genai_tag_db_tools.ensure_databases` のモック → `genai_tag_db_tools.initialize_databases` のモックに変更
- 不要なモック削除: `set_base_database_paths`, `init_engine` は `initialize_databases` 内で呼ばれる

**変更前**:
```python
_runtime_patches = [
    unittest.mock.patch(
        "genai_tag_db_tools.ensure_databases",
        return_value=[_mock_ensure_result],
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.set_base_database_paths",
        return_value=None,
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.init_engine",
        return_value=None,
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.init_user_db",
        return_value=_MockPath("/tmp/test_user_tag_db.db"),
    ),
    # ...
]
```

**変更後**:
```python
_runtime_patches = [
    unittest.mock.patch(
        "genai_tag_db_tools.initialize_databases",
        return_value=[_mock_ensure_result],
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.get_user_session_factory",
        return_value=_mock_user_session_factory,
    ),
]
```

**理由**:
- `initialize_databases()` が `ensure_databases`, `set_base_database_paths`, `init_engine`, `init_user_db` をカプセル化
- テストでは `initialize_databases()` のモックのみで十分

### Phase 4: genai-tag-db-tools テスト追加

**ファイル**: `local_packages/genai-tag-db-tools/tests/test_core_api.py` (既存ファイル)

#### Step 4.1: format_name パラメータのテスト追加

**新規テスト**:
```python
def test_initialize_databases_with_format_name(tmp_path, monkeypatch):
    """Test initialize_databases() with custom format_name parameter."""
    # Mock HuggingFace download
    mock_download = Mock(return_value=(tmp_path / "test.db", False))
    monkeypatch.setattr("genai_tag_db_tools.io.hf_downloader.download_with_offline_fallback", mock_download)

    # Mock runtime functions
    mock_set_paths = Mock()
    mock_init_engine = Mock()
    mock_init_user = Mock(return_value=tmp_path / "user_tags.sqlite")

    monkeypatch.setattr("genai_tag_db_tools.db.runtime.set_base_database_paths", mock_set_paths)
    monkeypatch.setattr("genai_tag_db_tools.db.runtime.init_engine", mock_init_engine)
    monkeypatch.setattr("genai_tag_db_tools.db.runtime.init_user_db", mock_init_user)

    # Execute
    results = initialize_databases(
        user_db_dir=tmp_path,
        format_name="TestApp",
    )

    # Verify format_name was passed through
    mock_init_user.assert_called_once_with(tmp_path, format_name="TestApp")
    assert len(results) == 3  # Default 3 databases
```

## データフロー図

### Before（手動初期化）

```
LoRAIro (db_core.py)
  │
  ├─> ensure_databases([CC0のみ])
  ├─> runtime.set_base_database_paths([base_paths])
  ├─> runtime.init_engine(base_paths[0])
  └─> runtime.init_user_db(DB_DIR, format_name="Lorairo")
```

### After（ライブラリ関数使用）

```
LoRAIro (db_core.py)
  │
  └─> initialize_databases(
        user_db_dir=DB_DIR,
        format_name="Lorairo"
      )
        │
        ├─> ensure_databases([CC4, MIT, CC0])  # デフォルト
        ├─> set_base_database_paths([all_paths])
        ├─> init_engine(all_paths[0])
        └─> init_user_db(DB_DIR, format_name="Lorairo")
```

## 影響範囲分析

### 変更されるファイル

| ファイル | 変更内容 | 行数変化 |
|---------|---------|---------|
| `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py` | `format_name` パラメータ追加 | +3行 |
| `src/lorairo/database/db_core.py` | `initialize_databases()` 使用 | -20行 |
| `tests/conftest.py` | モック簡素化 | -15行 |
| `local_packages/genai-tag-db-tools/tests/test_core_api.py` | 新規テスト | +25行 |

**合計**: 約7行削減 + テストカバレッジ向上

### 動作の変化

| 項目 | Before | After |
|-----|--------|-------|
| ダウンロードされるDB数 | 1つ（CC0のみ） | 3つ（CC4, MIT, CC0） |
| 初回起動時間 | 短い | やや長い（3倍のダウンロード） |
| ストレージ使用量 | 小さい | 約3倍 |
| 利用可能なタグ情報 | CC0のみ | CC4 + MIT + CC0（最大） |
| `format_name` | "Lorairo" | "Lorairo"（維持） |

### 互換性

- **後方互換性**: 既存の user_tags.sqlite は引き続き使用可能
- **破壊的変更**: なし（初回起動時に追加ダウンロードのみ）

## リスクと対策

### リスク1: 初回ダウンロード時間増加

**影響**: 初回起動時に3つのDBダウンロードで時間がかかる

**対策**:
- ローディング画面にダウンロード進捗表示（既存機能で対応可能）
- オフライン環境では既存のキャッシュを使用（`download_with_offline_fallback()` で実装済み）

### リスク2: ストレージ容量増加

**影響**: 約3倍のストレージ使用量

**対策**:
- ドキュメントに必要容量を明記
- 将来的に設定で選択可能にする拡張を検討

### リスク3: genai-tag-db-tools API変更

**影響**: local package への変更が必要

**対策**:
- 変更は minimal（1パラメータ追加のみ）
- 既存の `init_user_db()` が既にサポート済み
- 後方互換性維持（`format_name=None` でデフォルト動作）

## 検証計画

### Unit Tests

1. **genai-tag-db-tools**:
   ```bash
   cd local_packages/genai-tag-db-tools
   uv run pytest tests/test_core_api.py::test_initialize_databases_with_format_name -v
   ```

2. **LoRAIro database tests**:
   ```bash
   uv run pytest tests/unit/database/ -v
   ```

### Integration Tests

1. **フル起動テスト**:
   ```bash
   # 既存のuser_tags.sqliteを削除
   rm lorairo_data/*/user_tags.sqlite

   # LoRAIro起動（3つのDBダウンロードを確認）
   uv run lorairo
   ```

2. **ログ確認**:
   - "Tag databases initialized: 3 base DB(s)" のメッセージ確認
   - `USER_TAG_DB_PATH` が正しく設定されていることを確認

### 手動検証

1. **タグ検索**:
   - CC4, MIT, CC0 それぞれのタグが検索できることを確認
   - MergedTagReader が3つすべてのDBを参照していることを確認

2. **ユーザーDB**:
   - `format_name="Lorairo"` が正しく設定されていることを確認
   - format_id=1000 予約が機能することを確認

## タイムライン

- **Phase 1** (genai-tag-db-tools拡張): 15分
- **Phase 2** (LoRAIro簡素化): 10分
- **Phase 3** (テスト更新): 10分
- **Phase 4** (テスト追加): 15分
- **検証**: 10分

**合計**: 約60分

## 次のステップ

1. ユーザー承認取得
2. `/implement` コマンドで実装開始
3. Phase 1 → Phase 2 → Phase 3 → Phase 4 の順序で実装
4. 各Phaseごとにテスト実行して検証

## 関連ドキュメント

- [db_core_legacy_tag_db_cleanup_2026_01_02.md](.serena/memories/db_core_legacy_tag_db_cleanup_2026_01_02.md) - Tag DB アーキテクチャ変遷
- [genai_tag_db_tools_gui_service_migration_2025_12_29.md](.serena/memories/genai_tag_db_tools_gui_service_migration_2025_12_29.md) - Repository Pattern導入
- [CLAUDE.md](CLAUDE.md#local-dependencies) - genai-tag-db-tools統合ガイド
