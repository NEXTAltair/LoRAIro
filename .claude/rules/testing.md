# Testing Rules

LoRAIroプロジェクトにおけるテスト要件とベストプラクティス。

## カバレッジ要件

- **最小カバレッジ**: 75%以上を維持
- **新機能**: 対応するテストを必ず作成
- **バグ修正**: リグレッションテストを追加

## テスト構造

### ディレクトリ構成
```
tests/
├── unit/           # ユニットテスト（外部依存はモック）
├── integration/    # 統合テスト（内部コンポーネント結合）
├── gui/            # GUIテスト（pytest-qt）
├── bdd/            # BDD E2Eテスト
└── resources/      # テストリソース
```

### テストマーカー
```python
@pytest.mark.unit        # ユニットテスト
@pytest.mark.integration # 統合テスト
@pytest.mark.gui         # GUIテスト
@pytest.mark.slow        # 時間のかかるテスト
```

## pytest-qtベストプラクティス

### シグナル待機
```python
# 正しい: waitSignalでタイムアウト付き待機
with qtbot.waitSignal(widget.completed, timeout=5000):
    widget.start_operation()

# 禁止: 固定時間待機
qtbot.wait(1000)  # 避ける
```

### UI状態待機
```python
# 正しい: waitUntilで条件待機
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=5000)

# 禁止: processEventsの直接呼び出し
QCoreApplication.processEvents()  # 避ける
```

### ダイアログモック
```python
# QMessageBoxは必ずモック
def test_delete_confirmation(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args: QMessageBox.Yes
    )
    widget.delete_item()
```

## モック戦略

### モック対象
- 外部API（OpenAI, Anthropic, Google）
- ファイルシステム操作（大量ファイル処理）
- ネットワーク通信
- 時間依存処理

### モック非対象
- 内部サービス間の連携（統合テストで検証）
- データベース操作（テストDBを使用）
- Qt Signal/Slot（実際の動作を検証）

```python
# 外部APIのモック例
@pytest.fixture
def mock_openai(monkeypatch):
    def mock_complete(*args, **kwargs):
        return MockResponse(content="mocked response")
    monkeypatch.setattr(openai.ChatCompletion, "create", mock_complete)
```

## テスト実行

### 基本コマンド
```bash
# 全テスト実行
uv run pytest

# ユニットテストのみ
uv run pytest -m unit

# カバレッジ付き
uv run pytest --cov=src --cov-report=html

# 特定ファイル
uv run pytest tests/unit/path/to/test_file.py
```

### GUI テスト環境
```bash
# Linux/Container: ヘッドレス実行
QT_QPA_PLATFORM=offscreen uv run pytest -m gui

# Windows: ネイティブウィンドウ
uv run pytest -m gui
```

## テスト命名規則

```python
# ファイル名: test_<module_name>.py
# 関数名: test_<機能>_<条件>_<期待結果>

def test_search_with_empty_query_returns_all_items():
    ...

def test_delete_image_when_not_found_raises_error():
    ...
```

## フィクスチャ管理

### スコープの使い分け
```python
@pytest.fixture(scope="session")  # 全テストで1回
def database():
    ...

@pytest.fixture(scope="function")  # 各テストで毎回
def clean_state():
    ...
```

### conftest.py配置
- `tests/conftest.py`: 共通フィクスチャ
- `tests/unit/conftest.py`: ユニットテスト専用
- `tests/integration/conftest.py`: 統合テスト専用
