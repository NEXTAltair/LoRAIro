# `pytest` および `pytest-qt` リファレンス

LoRAIro における `pytest` と `pytest-qt` を使ったテスト開発の完全リファレンスである。

## `pytest` コア API

### テストの自動検出

`pytest` は次の命名規則に従ってテストを自動検出する。

```python
# ファイル名
test_*.py           # test_repository.py
*_test.py           # repository_test.py

# 関数名
def test_*():      # test_add_image()
def *_test():      # 非推奨

# クラス名
class Test*:       # TestImageRepository
```

**明示的なテストマーカー付与:**

```python
# テストとして明示する (通常は不要)
@pytest.mark.test
def my_test_function():
    pass
```

### テストの実行

**コマンドラインオプション:**

```bash
# 全テストを実行
pytest

# 指定ファイルを実行
pytest tests/test_repository.py

# 指定テスト関数を実行
pytest tests/test_repository.py::test_add_image

# 名前パターンに一致するテストを実行
pytest -k "test_add"

# 詳細出力
pytest -v

# 最初の失敗で停止
pytest -x

# 前回失敗したテストのみ再実行
pytest --lf

# 失敗時にローカル変数を表示
pytest -l

# 並列実行
pytest -n auto    # pytest-xdist が必要
```

### マーカー

**組み込みマーカー:**

```python
@pytest.mark.skip(reason="Not implemented yet")
def test_feature():
    pass

@pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
def test_unix_feature():
    pass

@pytest.mark.xfail(reason="Known bug #123")
def test_buggy_feature():
    pass

@pytest.mark.parametrize("input,expected", [(1, 2), (2, 4)])
def test_double(input, expected):
    assert input * 2 == expected
```

**カスタムマーカー(LoRAIro):**

```python
# pytest.ini または pyproject.toml に定義する
markers =
    unit: Unit tests
    integration: Integration tests
    gui: GUI tests
    slow: Slow running tests

# 使用例
@pytest.mark.unit
def test_calculation():
    pass

# マーカーを指定して実行
pytest -m unit
pytest -m "unit and not slow"
pytest -m "integration or gui"
```

### フィクスチャ

**フィクスチャのスコープ:**

```python
# function スコープ (既定) - テスト関数ごとに実行
@pytest.fixture
def temp_data():
    return {"key": "value"}

# class スコープ - テストクラスごとに 1 回実行
@pytest.fixture(scope="class")
def database():
    db = Database()
    yield db
    db.close()

# module スコープ - モジュールごとに 1 回実行
@pytest.fixture(scope="module")
def app_config():
    return load_config()

# session スコープ - テストセッション全体で 1 回実行
@pytest.fixture(scope="session")
def test_data_dir():
    return Path(__file__).parent / "resources"
```

**フィクスチャパターン:**

```python
# セットアップと後片付け
@pytest.fixture
def resource():
    # セットアップ
    r = acquire_resource()
    yield r
    # 後片付け
    r.cleanup()

# パラメーター化フィクスチャ
@pytest.fixture(params=[1, 2, 3])
def number(request):
    return request.param

# フィクスチャ間の依存
@pytest.fixture
def db_connection():
    return DatabaseConnection()

@pytest.fixture
def repository(db_connection):
    return Repository(db_connection)

# 自動適用フィクスチャ
@pytest.fixture(autouse=True)
def reset_state():
    global_state.reset()
```

### アサーション

**基本アサーション:**

```python
# 等価比較
assert x == y
assert x != y

# 同一性比較
assert x is y
assert x is not None

# 大小比較
assert x > y
assert x >= y
assert x < y
assert x <= y

# 所属判定
assert x in collection
assert x not in collection

# 真偽判定
assert condition
assert not condition

# 型チェック
assert isinstance(x, MyClass)
```

**例外アサーション:**

```python
# 特定の例外が送出されることを検証
with pytest.raises(ValueError):
    function_that_raises()

# 例外メッセージを正規表現で検証
with pytest.raises(ValueError, match="invalid value"):
    function_that_raises()

# 例外オブジェクトを取得して検証
with pytest.raises(ValueError) as exc_info:
    function_that_raises()

assert "invalid" in str(exc_info.value)
```

**近似比較:**

```python
from pytest import approx

# 浮動小数点数の比較
assert 0.1 + 0.2 == approx(0.3)

# 許容誤差を指定した比較
assert 10.0 == approx(10.1, abs=0.2)
assert 10.0 == approx(10.1, rel=0.01)  # 相対誤差 1%

# シーケンスの比較
assert [1.0, 2.0] == approx([1.001, 2.001], abs=0.01)
```

### パラメーター化

**基本のパラメーター化:**

```python
@pytest.mark.parametrize("test_input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiply_by_two(test_input, expected):
    assert test_input * 2 == expected
```

**複数パラメーターの組み合わせ:**

```python
@pytest.mark.parametrize("x", [1, 2])
@pytest.mark.parametrize("y", [3, 4])
def test_combinations(x, y):
    # (1,3), (1,4), (2,3), (2,4) の 4 パターンが生成される
    assert x < y
```

**パラメーター化フィクスチャ:**

```python
@pytest.fixture(params=["sqlite", "postgresql"])
def database_type(request):
    return request.param

def test_database_operations(database_type):
    # 各データベース種別ごとに 1 回ずつ実行される
    db = create_database(database_type)
    assert db.connect()
```

**テスト ID のカスタマイズ:**

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
], ids=["single", "double"])
def test_values(input, expected):
    pass

# 出力例: test_values[single], test_values[double]
```

## `pytest-qt` API

### `qtbot` フィクスチャ

**ウィジェット管理:**

```python
def test_widget(qtbot):
    widget = MyWidget()

    # qtbot に登録して確実に後片付けする
    qtbot.addWidget(widget)

    # ウィジェットが qtbot の管理下に入る
    assert widget.isVisible()
```

### シグナルテスト

**シグナル待機:**

```python
def test_signal_emission(qtbot, widget):
    # 特定シグナルの発火を待機する
    with qtbot.waitSignal(widget.data_changed, timeout=1000) as blocker:
        widget.update_data("new value")

    # シグナルが発火されたことを確認する
    assert blocker.signal_triggered

    # シグナル引数を検証する
    assert blocker.args == ("new value",)
```

**複数シグナルの待機:**

```python
def test_multiple_signals(qtbot, widget):
    # すべてのシグナルが発火するまで待機する
    with qtbot.waitSignals([widget.signal1, widget.signal2], timeout=2000):
        widget.trigger_both()

    # いずれかのシグナルが発火するまで待機する
    with qtbot.waitSignal([widget.signal1, widget.signal2], timeout=2000):
        widget.trigger_either()
```

**シグナル未発火の検証:**

```python
def test_no_signal_emitted(qtbot, widget):
    # シグナルが発火しないことを検証する
    with qtbot.assertNotEmitted(widget.data_changed, wait=100):
        widget.no_op_action()
```

### ユーザー操作のシミュレーション

**マウスイベント:**

```python
def test_button_click(qtbot, widget):
    from PySide6.QtCore import Qt

    # クリック
    qtbot.mouseClick(widget.button, Qt.LeftButton)

    # ダブルクリック
    qtbot.mouseDClick(widget.button, Qt.LeftButton)

    # 座標指定クリック
    qtbot.mouseClick(
        widget.button,
        Qt.LeftButton,
        pos=QPoint(10, 10)
    )

    # 押下と解放
    qtbot.mousePress(widget.button, Qt.LeftButton)
    qtbot.mouseRelease(widget.button, Qt.LeftButton)

    # マウス移動
    qtbot.mouseMove(widget, pos=QPoint(50, 50))
```

**キーボードイベント:**

```python
def test_keyboard_input(qtbot, widget):
    from PySide6.QtCore import Qt

    # 文字列入力
    qtbot.keyClicks(widget.text_input, "Hello World")

    # 単一キー押下
    qtbot.keyClick(widget, Qt.Key_Return)

    # 修飾キー付き押下
    qtbot.keyClick(widget, Qt.Key_C, Qt.ControlModifier)

    # 修飾キー付き文字列入力
    qtbot.keyClicks(widget, "Test", Qt.ControlModifier)

    # キー押下と解放
    qtbot.keyPress(widget, Qt.Key_Shift)
    qtbot.keyRelease(widget, Qt.Key_Shift)
```

**待機関数:**

```python
def test_with_delays(qtbot, widget):
    # 条件を満たすまで待機
    def check_state():
        return widget.is_ready()

    qtbot.waitUntil(check_state, timeout=5000)

    # 固定時間待機
    qtbot.wait(100)  # ミリ秒

    # ウィンドウ表示まで待機
    qtbot.waitForWindowShown(widget)

    # ウィンドウ描画完了まで待機
    qtbot.waitExposed(widget)
```

### 例外ハンドリング

**スロット内例外の捕捉:**

```python
def test_exception_in_slot(qtbot, widget):
    # スロット内で送出された例外を捕捉する
    with qtbot.captureExceptions() as exceptions:
        widget.trigger_buggy_slot()

    # 捕捉した例外を検証する
    assert len(exceptions) == 1
    assert isinstance(exceptions[0][1], ValueError)
```

## カバレッジ設定

**`pyproject.toml` の設定例:**

```toml
[tool.coverage.run]
source = ["src/lorairo"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/venv/*",
    "*/.venv/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
fail_under = 75
show_missing = true

[tool.coverage.html]
directory = "htmlcov"
```

**コマンドラインでのカバレッジ計測:**

```bash
# HTML レポートを生成
pytest --cov=src/lorairo --cov-report=html

# XML レポートを生成 (CI 用)
pytest --cov=src/lorairo --cov-report=xml

# 未カバー行を端末へ出力
pytest --cov=src/lorairo --cov-report=term-missing

# 複数レポートを同時出力
pytest --cov=src/lorairo --cov-report=html --cov-report=xml

# 基準値を下回った場合に失敗させる
pytest --cov=src/lorairo --cov-fail-under=75
```

## `conftest.py` パターン

**プロジェクトルートの `conftest.py`:**

```python
# /workspaces/LoRAIro/tests/conftest.py
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication

# セッションスコープのフィクスチャ
@pytest.fixture(scope="session")
def test_resources_dir():
    """Path to test resources directory."""
    return Path(__file__).parent / "resources"

@pytest.fixture(scope="session")
def qapp():
    """Qt application for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # app.quit() は Qt 側で処理されるため不要

# マーカー登録
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "gui: GUI tests")
    config.addinivalue_line("markers", "slow: Slow running tests")

# カスタムフック
def pytest_collection_modifyitems(items):
    """Modify test collection."""
    for item in items:
        # GUI テストへ自動的に gui マーカーを付与する
        if "qtbot" in item.fixturenames:
            item.add_marker(pytest.mark.gui)
```

**モジュール固有の `conftest.py`:**

```python
# tests/database/conftest.py
import pytest
from sqlalchemy.orm import scoped_session, sessionmaker
from src.lorairo.database.db_core import create_test_engine
from src.lorairo.database.schema import Base

@pytest.fixture(scope="function")
def test_db_engine():
    """Test database engine."""
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def db_session(test_db_engine):
    """Database session for tests."""
    Session = scoped_session(sessionmaker(bind=test_db_engine))
    session = Session()
    yield session
    session.rollback()
    Session.remove()
```

## LoRAIro のテストユーティリティ

**共通テストフィクスチャ:**

```python
# tests/conftest.py (LoRAIro 固有)

@pytest.fixture
def sample_image(test_resources_dir):
    """Sample image file."""
    return test_resources_dir / "sample.jpg"

@pytest.fixture
def sample_images(test_resources_dir):
    """Multiple sample images."""
    return [
        test_resources_dir / f"sample{i}.jpg"
        for i in range(1, 6)
    ]

@pytest.fixture
def mock_annotation_result():
    """Mock annotation API result."""
    return {
        "caption": "A beautiful landscape",
        "tags": ["landscape", "nature", "outdoor"],
        "confidence": 0.95
    }

@pytest.fixture(autouse=True)
def reset_loguru():
    """Reset loguru logger between tests."""
    from loguru import logger
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    yield
    logger.remove()
```

**ヘルパー関数:**

```python
# tests/helpers.py

from typing import List
from src.lorairo.database.schema import Image

def create_test_images(count: int, **kwargs) -> List[Image]:
    """Create test image objects."""
    return [
        Image(
            path=f"/test/img{i}.jpg",
            phash=f"hash{i}",
            **kwargs
        )
        for i in range(count)
    ]

def assert_image_equal(img1: Image, img2: Image, ignore_id: bool = True):
    """Assert two images are equal."""
    if not ignore_id:
        assert img1.id == img2.id
    assert img1.path == img2.path
    assert img1.phash == img2.phash
    assert img1.caption == img2.caption
```

## LoRAIro でのテスト実行

**標準テストコマンド:**

```bash
# 全テスト実行
uv run pytest

# カテゴリ別に実行
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m gui

# モジュール別に実行
uv run pytest tests/database/
uv run pytest tests/gui/widgets/

# カバレッジ付きで実行
uv run pytest --cov=src/lorairo --cov-report=html

# 詳細出力
uv run pytest -v

# print 出力を表示
uv run pytest -s

# 並列実行 (pytest-xdist が必要)
uv run pytest -n auto
```

**CI/CD 連携:**

```bash
# CI パイプライン用テストコマンド
uv run pytest \
    -m "unit or integration" \
    --cov=src/lorairo \
    --cov-report=xml \
    --cov-report=term \
    --cov-fail-under=75 \
    --junitxml=test-results.xml \
    -v
```

## 環境変数

**`pytest` 関連の環境変数:**

```bash
# ヘッドレステスト向けに Qt プラットフォームを指定
export QT_QPA_PLATFORM=offscreen

# Qt のデバッグ出力を抑制
export QT_LOGGING_RULES="*.debug=false"

# pytest オプションの既定値
export PYTEST_ADDOPTS="--strict-markers --tb=short"

# カバレッジ計測コアの設定
export COVERAGE_CORE=sysmon
```

**LoRAIro テスト用の環境変数:**

```bash
# テストデータベースの配置先
export LORAIRO_TEST_DB_DIR=/tmp/lorairo_test_db

# 外部 API 呼び出しを無効化
export LORAIRO_MOCK_APIS=true

# テストデータディレクトリ
export LORAIRO_TEST_DATA_DIR=tests/resources
```

## 参考資料

- **pytest 公式ドキュメント**: https://docs.pytest.org/
- **pytest-qt ドキュメント**: https://pytest-qt.readthedocs.io/
- **PySide6 テストガイド**: https://doc.qt.io/qtforpython/tutorials/pretutorial/testing.html
- **Coverage.py**: https://coverage.readthedocs.io/
