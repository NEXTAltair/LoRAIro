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
├── bdd/            # BDD振る舞い仕様テスト（pytest-bdd）
│   ├── conftest.py     # bddマーカー自動付与
│   ├── features/       # Gherkin featureファイル
│   └── steps/          # ステップ定義（test_*.py）
└── resources/      # テストリソース
```

### テストマーカー
```python
@pytest.mark.unit        # ユニットテスト
@pytest.mark.integration # 統合テスト
@pytest.mark.gui         # GUIテスト
@pytest.mark.bdd         # BDDテスト（tests/bdd/配下は自動付与）
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

# BDDテストのみ
uv run pytest -m bdd

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

## BDD テスト（pytest-bdd）

BDDはE2Eに限定せず「振る舞い仕様の表現形式」としてService層以上に適用する。

### 適用レイヤー

| レイヤー | BDD の適用 | 理由 |
|---------|-----------|------|
| ユーザー向け機能フロー | ◎ | 仕様そのもの |
| Service 層の振る舞い | ○ | ビジネスルールの表現に向く |
| Repository 層の CRUD | △ | 技術的すぎて Gherkin が冗長 |
| 内部ロジック・ユーティリティ | ✕ | 通常の pytest が適切 |

### BDDシナリオを書くべきケース

- 新しいユーザー向け機能（画像登録、タグ検索等）
- Service層のビジネスルール（重複排除、バリデーション等）
- バグ修正のリグレッション防止（再現シナリオを書いてから修正）

### BDDシナリオを書かないケース

- 内部リファクタリング
- UIの見た目の調整
- Repository層の単純CRUD

### 新しいBDDテストの追加方法

1. `tests/bdd/features/` に `.feature` ファイルを作成（日本語Gherkin）
2. `tests/bdd/steps/` に `test_<feature名>.py` を作成
3. `scenarios()` で feature ファイルを参照:
   ```python
   from pathlib import Path
   from pytest_bdd import scenarios
   _FEATURE_FILE = Path(__file__).parent.parent / "features" / "<feature名>.feature"
   scenarios(str(_FEATURE_FILE))
   ```
4. `@given`, `@when`, `@then` でステップ定義を実装

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
- `tests/bdd/conftest.py`: BDDマーカー自動付与
