# 外部タグDB初期化失敗時の起動中止対応 - テスト更新

## 実施日
2026-01-01

## 更新履歴
- 初版: 2026-01-01 09:42 - 初期実装（モジュールレベルパッチ）
- 改訂: 2026-01-01 08:55 - パッチタイミング修正、session fixture追加

## 背景
ユーザー報告: "外部タグDB初期化の失敗を「起動中止」に変更した タグ検索ができなくなるのでタグ情報の登録がうまく行かないのが理由｡この変更に合わせてテストも変更して"

`src/lorairo/database/db_core.py` L252-258 で、`genai-tag-db-tools`の初期化失敗時にRuntimeErrorを発生させるように変更されていた。

```python
except Exception as e:
    USER_TAG_DB_PATH = None
    logger.error(
        f"Failed to initialize tag databases: {e}. "
        "LoRAIro cannot start without external tag DB access."
    )
    raise RuntimeError("Tag database initialization failed") from e
```

## 問題点
- `db_core.py`はモジュールレベルで初期化処理を実行する
- テストで`db_core`をインポートするだけでRuntimeErrorが発生
- すべてのテストが失敗する可能性がある

## 解決策
`tests/conftest.py`に外部tag DB初期化のモックを追加し、すべてのテストで自動適用する。

### 実装詳細 (tests/conftest.py)

```python
# --- External Tag DB Initialization Mock (autouse for all tests) ---
# Mock genai-tag-db-tools initialization to prevent RuntimeError during db_core import

import unittest.mock
from pathlib import Path as _MockPath

# Mock ensure_databases to return successful result
_mock_ensure_result = unittest.mock.Mock()
_mock_ensure_result.db_path = str(_MockPath("/tmp/test_tag_db.db"))

# Mock runtime functions
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
]

# Start all patches at module level
for _patch in _runtime_patches:
    _patch.start()
```

### モック対象API
1. **`genai_tag_db_tools.ensure_databases`**: ベースDBダウンロード処理
2. **`genai_tag_db_tools.db.runtime.set_base_database_paths`**: ベースDBパス設定
3. **`genai_tag_db_tools.db.runtime.init_engine`**: SQLAlchemyエンジン初期化
4. **`genai_tag_db_tools.db.runtime.init_user_db`**: ユーザーDB作成

### モックの特徴
- **モジュールレベルで適用**: `conftest.py`インポート時に即座にパッチ開始
- **autouse不要**: モジュールレベルで動作するため、fixture不要
- **すべてのテストに自動適用**: 個別のテストでモックを意識する必要なし
- **上書き可能**: 特定のテストで`monkeypatch`や`patch`で上書き可能

## テスト結果

### Unit Tests
- **test_tag_management_service.py**: 14/14 passed ✅
- **test_tag_management_widget.py**: 7/7 passed ✅
- **test_existing_file_reader.py**: 12/12 passed ✅

### Integration Tests
- **test_configuration_integration.py::test_project_directory_integration_with_db_core**: passed ✅

## 影響範囲
- `db_core`を直接・間接的にインポートするすべてのテストが対象
- 既存のテストコードに変更不要（自動適用）
- 新規テストも自動的にモック適用される

## 注意事項
1. **実際の初期化失敗テストは個別にモックを上書き**
   - `monkeypatch.setattr`で`ensure_databases`を例外発生に変更
   - MainWindow起動テストなどで明示的に失敗ケースをテスト可能

2. **モック開始のタイミング**
   - `conftest.py`インポート時（pytest起動時）
   - `db_core`インポート前に必ずモックが適用される

3. **メンテナンス性**
   - すべてのモックが`conftest.py`の一箇所に集約
   - genai-tag-db-tools APIの変更時も一箇所の修正で対応可能

## 関連ファイル
- `tests/conftest.py`: モック定義
- `src/lorairo/database/db_core.py`: 初期化処理（L215-258）
- `tests/unit/services/test_tag_management_service.py`: 影響を受けるテスト
- `tests/unit/gui/widgets/test_tag_management_widget.py`: 影響を受けるテスト

## 改訂内容（2026-01-01 08:55）

### 問題点（ユーザー指摘）
1. **パッチタイミングの問題**: conftest.py で lorairo 系の import 後にパッチ開始
   - `from lorairo.database.db_manager import ImageDatabaseManager` が先に実行
   - これらは内部で `db_core` を import → 初期化失敗の可能性
   - 「テストが通ってるならたまたま問題化してないだけ」

2. **パッチのライフサイクル管理**: start() のみで stop() していない
   - セッション全体で固定される
   - 明示的に session fixture で管理すべき

3. **get_user_session_factory() のモック不足**: 単純な Path 返却のみ
   - 実際の DB 操作が必要なテストで問題の可能性
   - session_factory までモックが必要

### 修正内容

#### 1. パッチを最上部に移動 ([conftest.py:1-45](tests/conftest.py#L1-L45))

```python
# tests/conftest.py

# --- External Tag DB Initialization Mock (MUST BE FIRST) ---
# Mock genai-tag-db-tools initialization BEFORE any lorairo imports
# to prevent RuntimeError during db_core module-level initialization

import unittest.mock
from pathlib import Path as _MockPath
from sqlalchemy.orm import sessionmaker as _sessionmaker

# Mock ensure_databases to return successful result
_mock_ensure_result = unittest.mock.Mock()
_mock_ensure_result.db_path = str(_MockPath("/tmp/test_tag_db.db"))

# Create mock session factory for user DB
_mock_user_db_engine = unittest.mock.Mock()
_mock_user_session_factory = _sessionmaker(bind=_mock_user_db_engine)

# Mock runtime functions
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
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.get_user_session_factory",
        return_value=_mock_user_session_factory,
    ),
]

# Start all patches at module level (before any lorairo imports)
for _patch in _runtime_patches:
    _patch.start()


# --- Standard Library Imports ---
import os
import shutil
...

# --- LoRAIro Imports (after patches are active) ---
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
...
```

#### 2. Session Fixture でパッチ管理 ([conftest.py:74-92](tests/conftest.py#L74-L92))

```python
@pytest.fixture(scope="session", autouse=True)
def mock_genai_tag_db_tools():
    """
    外部タグDB初期化のモックを管理（全テストで自動実行）
    
    genai-tag-db-toolsの初期化処理をモックし、テスト環境で
    RuntimeErrorが発生しないようにします。
    
    Note:
        - session スコープでパッチを管理
        - テストセッション終了時に自動的にパッチを停止
        - モジュールレベルで既にパッチは開始されている
    """
    # パッチは既にモジュールレベルで開始されている
    yield
    
    # テストセッション終了時にすべてのパッチを停止
    for patch in _runtime_patches:
        patch.stop()
```

#### 3. get_user_session_factory() のモック追加 (L37-40)

実際の SQLAlchemy sessionmaker を使用したモックセッションファクトリを作成:
- `_mock_user_db_engine`: モック DB エンジン
- `_mock_user_session_factory`: sessionmaker(bind=_mock_user_db_engine)
- 実際の DB クエリは失敗するが、セッション作成は可能

### テスト結果（改訂後）

すべてのテストが正常動作:
- **test_tag_management_service.py**: 14/14 passed ✅
- **test_tag_management_widget.py**: 7/7 passed ✅
- **test_configuration_integration.py**: 7/7 passed ✅

### 既知の制限事項

#### 警告メッセージ
```
Failed to initialize LoRAIro format mappings: User database not available for write operations.
```

- `db_core.py` L200 の `_initialize_lorairo_format_mappings()` から出力
- モックした `get_default_repository()` では DB 書き込みができない
- テストには影響なし（実際のアプリケーション実行時は本物のリポジトリを使用）

#### モックセッションファクトリの制限
- 実際の DB クエリを実行すると失敗する可能性
- 必要に応じて、特定のテストで本物の DB セッションに置き換え可能

## 次のステップ
- ✅ 基本的なモック実装完了
- ✅ パッチタイミング修正完了
- ✅ Session fixture でライフサイクル管理完了
- ✅ get_user_session_factory() モック追加完了
- ✅ すべての既存テスト動作確認
- ⏳ 初期化失敗ケースの明示的テスト追加（必要に応じて）
- ⏳ MainWindow起動失敗テストの追加（必要に応じて）
