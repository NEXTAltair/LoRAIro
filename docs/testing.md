---
type: Guide
title: テスト戦略とベストプラクティス
status: Accepted
timestamp: 2026-05-21
tags: [process, validation]
---
# テスト戦略とベストプラクティス

## 概要

LoRAIroは3層テスト戦略を採用し、75%+のコードカバレッジを維持しています。

**Test Levels:**
- **Unit Tests**: ビジネスロジック、Qt-freeサービス
- **Integration Tests**: GUI services, データベース統合
- **BDD Tests**: 振る舞い仕様テスト（E2Eに限らずService層以上に適用）

**Runtime validation policy:** ADR 0026 により、CI で実行する E2E は deterministic な fixture / fake backend ベースに限定します。実 API key、ローカルモデル download、実推論を伴う検証は、通常 CI ではなくローカルの on-demand runtime validation として扱います。

## Tier 1: Smoke (実機モデル軽量 E2E)

Tier 1 は image-annotator-lib の `tests/runtime_validation/` に集約した、実モデル download と実推論を伴うローカル専用 smoke layer です。LoRAIro 側には実モデル test を置かず、Makefile target で iam-lib の runtime validation を間接実行します。

```bash
make test-runtime-local
```

この target は `local_packages/image-annotator-lib` で `downloads_and_runs_model` marker の 5 model smoke を実行し、ONNX / Transformers / Tensorflow / Pipeline / CLIP の base class を 1 model ずつ通します。初回は約 3.5GB の model download と 20 分程度の実行時間を想定し、cache 後は数分程度です。

ADR 0026 / iam-lib ADR 0001 amended (2026-05-18) により、この validation は CI に含めません。GitHub Actions workflow、`workflow_dispatch`、`schedule`、CI cache、repo secret を追加しないでください。

## Tier 2: Real WebAPI integration

Tier 2 は image-annotator-lib の `tests/runtime_validation/test_real_webapi_runtime.py` に集約した、実 provider API key で実 WebAPI request を送るローカル専用 validation です。LoRAIro 側には実 WebAPI test を置かず、LoRAIro の実運用 config 経路で API key を読み込む runner から iam-lib の runtime validation を間接実行します。

```bash
make test-runtime-webapi
```

この target は `ConfigurationService` 経由で `config/lorairo.toml` の `[api]` セクションを読み、subprocess 環境変数として iam-lib test に渡します。

| LoRAIro config key | child env var | Provider |
|---|---|---|
| `openai_key` | `OPENAI_API_KEY` | OpenAI |
| `claude_key` | `ANTHROPIC_API_KEY` | Anthropic |
| `google_key` | `GEMINI_API_KEY` | Google |
| `openrouter_key` | `OPENROUTER_API_KEY` | OpenRouter |

API key 値は stdout / log に出しません。runner は provider ごとの configured / missing のみを表示します。未設定 provider は iam-lib 側で `pytest.skip` されます。

対象モデルは Google / OpenAI / Anthropic / OpenRouter の各 1 model です。#274 が未解決の間、`OPENAI_API_KEY` が設定された環境では OpenAI case が fail する可能性があります。その failure は #274 の再現として扱い、#278 では skip / xfail しません。

ADR 0026 / iam-lib ADR 0001 amended (2026-05-18) により、この validation も CI に含めません。GitHub Actions workflow、`workflow_dispatch`、`schedule`、repo secret を追加しないでください。

**Testing Framework:**
- pytest (test runner)
- pytest-qt (Qt GUI testing)
- pytest-cov (coverage reporting)

## テスト構造

### ディレクトリ構成

```
tests/
├── unit/                    # Unit tests (Qt-free)
│   ├── services/            # Business logic services
│   ├── database/            # Database layer
│   └── annotations/         # Annotation logic
├── integration/             # Integration tests
│   ├── gui/                 # GUI services + widgets
│   │   ├── services/        # GUI services
│   │   └── widgets/         # Qt widgets
│   └── database/            # DB integration
├── bdd/                     # BDD振る舞い仕様テスト
│   ├── conftest.py          # bddマーカー自動付与
│   ├── features/            # Gherkin featureファイル
│   └── steps/               # ステップ定義（test_*.py）
├── resources/               # Test resources
│   ├── images/              # Sample images
│   ├── configs/             # Test configurations
│   └── databases/           # Test databases
└── conftest.py              # Shared fixtures
```

### テストマーカー

```python
import pytest

# Unit test
@pytest.mark.unit
def test_service_logic():
    pass

# Integration test
@pytest.mark.integration
def test_database_integration():
    pass

# GUI test
@pytest.mark.gui
def test_widget_interaction(qtbot):
    pass

# Slow test
@pytest.mark.slow
def test_batch_processing():
    pass

# Deterministic E2E test for CI
@pytest.mark.integration
@pytest.mark.e2e
def test_cli_workflow_with_fake_backend():
    pass

# On-demand real API validation, excluded from normal CI
@pytest.mark.calls_real_webapi
@pytest.mark.webapi
def test_provider_contract_with_real_webapi():
    pass
```

**Run specific markers:**
```bash
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests only
uv run pytest -m e2e               # Deterministic E2E tests
uv run pytest -m "not slow"        # Exclude slow tests
uv run pytest -m calls_real_webapi # On-demand real API validation
```

`e2e` は実外部依存を使うという意味ではありません。CI で安定実行できる E2E を表します。実 API key を使うテストには `calls_real_webapi`、実モデル download / 実推論を使うテストには `downloads_and_runs_model` を付け、通常 CI から除外します。

## pytest-qtベストプラクティス

### Signalベースのアサーション

#### ✅ RECOMMENDED: qtbot.waitSignal()

```python
def test_signal_emission(qtbot):
    widget = MyWidget()

    # Wait for signal with timeout
    with qtbot.waitSignal(widget.data_loaded, timeout=1000) as blocker:
        widget.load_data()

    # Assert signal arguments
    assert blocker.args[0] == expected_data
```

**Benefits:**
- Automatic timeout handling
- Clear test failure messages
- No manual event processing

#### ❌ AVOID: Manual processEvents()

```python
# ❌ BAD: Manual event loop processing
def test_signal_bad(qtbot):
    widget = MyWidget()
    widget.load_data()

    # Fragile, timing-dependent
    QCoreApplication.processEvents()
    qtbot.wait(100)  # Arbitrary delay

    assert widget.data_ready  # May fail randomly
```

### UI状態変更

#### ✅ RECOMMENDED: qtbot.waitUntil()

```python
def test_ui_update(qtbot):
    widget = MyWidget()
    widget.start_processing()

    # Wait for UI state change
    qtbot.waitUntil(
        lambda: widget.status_label.text() == "Complete",
        timeout=2000
    )

    assert widget.is_finished()
```

**Benefits:**
- Condition-based waiting
- Automatic polling
- Clear timeout errors

#### ❌ AVOID: Fixed-time wait

```python
# ❌ BAD: Fixed delay without condition
def test_ui_bad(qtbot):
    widget = MyWidget()
    widget.start_processing()

    qtbot.wait(500)  # May be too short or too long

    assert widget.status_label.text() == "Complete"  # Flaky
```

### QMessageBoxモック

#### ✅ RECOMMENDED: monkeypatch

```python
def test_confirmation_dialog(qtbot, monkeypatch):
    widget = MyWidget()

    # Mock QMessageBox.question
    monkeypatch.setattr(
        QMessageBox,
        'question',
        lambda *args: QMessageBox.Yes
    )

    # Trigger action that shows dialog
    widget.delete_item()

    # Assert action completed
    assert widget.item_count == 0
```

**Common mocks:**
```python
# Information dialog
monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)

# Warning dialog
monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)

# Critical error dialog
monkeypatch.setattr(QMessageBox, 'critical', lambda *args: None)

# Question dialog (Yes/No)
monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
```

### ウィジェット操作

#### クリック操作

```python
def test_button_click(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)  # Ensure cleanup

    # Wait for signal on button click
    with qtbot.waitSignal(widget.button.clicked):
        qtbot.mouseClick(widget.button, Qt.LeftButton)

    assert widget.action_performed
```

#### キーボード入力

```python
def test_text_input(qtbot):
    widget = MyLineEdit()
    qtbot.addWidget(widget)

    # Type text
    qtbot.keyClicks(widget, "test input")

    assert widget.text() == "test input"
```

#### キーシーケンス

```python
def test_shortcut(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)

    # Trigger keyboard shortcut
    with qtbot.waitSignal(widget.save_triggered):
        qtbot.keyClick(widget, Qt.Key_S, Qt.ControlModifier)
```

### 非同期・スレッドテスト

#### ワーカースレッドSignal

```python
def test_worker_completion(qtbot):
    service = WorkerService()

    # Wait for worker completion signal
    with qtbot.waitSignal(service.work_finished, timeout=5000) as blocker:
        service.start_work()

    # Verify result
    result = blocker.args[0]
    assert result.success
```

#### 複数Signal

```python
def test_multi_step_process(qtbot):
    widget = MyWidget()

    # Wait for multiple signals in sequence
    with qtbot.waitSignal(widget.step1_done):
        widget.start()

    with qtbot.waitSignal(widget.step2_done):
        pass  # step2 auto-starts

    with qtbot.waitSignal(widget.all_complete):
        pass  # step3 auto-starts

    assert widget.final_result is not None
```

### ヘッドレステスト

**Linux/Container Environment:**

```bash
# Set headless mode
export QT_QPA_PLATFORM=offscreen

# Run GUI tests
uv run pytest -m gui
```

**Windows Environment:**
- GUI tests run with native windows (optional headless via Xvfb)

**pytest configuration:**
```python
# conftest.py
import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_qt_environment():
    """Ensure Qt runs in offscreen mode in CI/containers"""
    if not os.environ.get('DISPLAY'):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
```

## ユニットテスト

### ビジネスロジックサービス

#### テストパターン

```python
import pytest
from src.lorairo.services.tag_management_service import TagManagementService

@pytest.mark.unit
def test_tag_service_get_unknown_tags(tmp_path):
    # Setup: Initialize service with temp DB
    service = TagManagementService(user_db_dir=tmp_path)

    # Exercise: Call method
    tags = service.get_unknown_tags()

    # Verify: Assert expected behavior
    assert isinstance(tags, list)
    assert all(tag.type_name == "unknown" for tag in tags)
```

**Principles:**
- ❌ **No Qt dependencies** in unit tests
- ❌ **No GUI mocks** (test business logic directly)
- ✅ **Test pure functions** and service methods
- ✅ **Use tmp_path fixture** for file operations

### データベース層

#### リポジトリテスト

```python
@pytest.mark.unit
def test_image_repository_add(tmp_path):
    # Create temporary database
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(db_path)

    # Create repository
    repo = ImageRepository(session_factory)

    # Add image
    image = ImageModel(
        file_path="/path/to/image.jpg",
        phash="abc123",
        width=1024,
        height=768
    )
    repo.add(image)

    # Verify
    retrieved = repo.get_by_phash("abc123")
    assert retrieved.file_path == "/path/to/image.jpg"
```

**Database Fixtures:**
```python
@pytest.fixture
def test_db(tmp_path):
    """Create temporary test database"""
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(db_path)

    # Run migrations
    alembic_upgrade(db_path)

    yield session_factory

    # Cleanup (automatic via tmp_path)
```

### 外部依存のモック

#### ✅ WHEN TO MOCK

**External APIs:**
```python
@patch('requests.post')
def test_api_call(mock_post):
    mock_post.return_value.json.return_value = {"result": "success"}

    service = ExternalAPIService()
    result = service.call_api()

    assert result == "success"
```

**Filesystem Operations** (when testing error handling):
```python
@patch('pathlib.Path.exists')
def test_file_not_found(mock_exists):
    mock_exists.return_value = False

    service = FileService()
    with pytest.raises(FileNotFoundError):
        service.load_file("missing.txt")
```

#### ❌ WHEN NOT TO MOCK

**Database operations** (use real SQLite in tmp_path):
```python
# ✅ GOOD: Real database in temp location
def test_database_query(tmp_path):
    db = create_database(tmp_path / "test.db")
    result = db.query(...)
    assert result is not None
```

**Pure functions**:
```python
# ✅ GOOD: No mocks needed for pure logic
def test_calculate_total():
    result = calculate_total([10, 20, 30])
    assert result == 60
```

## 統合テスト

### GUIサービス

#### サービス・ウィジェット統合

```python
@pytest.mark.integration
@pytest.mark.gui
def test_search_filter_service_integration(qtbot):
    # Create service + widget
    service = SearchFilterService()
    widget = SearchWidget(service)
    qtbot.addWidget(widget)

    # Connect signals
    results_received = False
    def on_results(results):
        nonlocal results_received
        results_received = True

    service.search_completed.connect(on_results)

    # Trigger search
    with qtbot.waitSignal(service.search_completed, timeout=2000):
        widget.search_button.click()

    assert results_received
```

### データベース統合

#### 複数テーブル操作

```python
@pytest.mark.integration
def test_image_with_annotations(test_db):
    repo = ImageRepository(test_db)
    annotation_repo = AnnotationRepository(test_db)

    # Create image
    image = ImageModel(file_path="/test.jpg", phash="abc")
    repo.add(image)

    # Add annotation
    annotation = AnnotationModel(
        image_id=image.id,
        caption="Test caption",
        tags=["tag1", "tag2"]
    )
    annotation_repo.add(annotation)

    # Verify relationship
    retrieved_image = repo.get_with_annotations(image.id)
    assert len(retrieved_image.annotations) == 1
    assert retrieved_image.annotations[0].caption == "Test caption"
```

### 外部パッケージ統合

#### genai-tag-db-tools

```python
@pytest.mark.integration
def test_tag_registration_integration(tmp_path):
    # Initialize User DB
    from genai_tag_db_tools.db.core import init_user_db
    init_user_db(user_db_dir=tmp_path)

    # Use TagManagementService
    service = TagManagementService(user_db_dir=tmp_path)

    # Register tag
    tag_id = service.register_tag("test_tag", type_name="general")

    # Verify
    tags = service.get_all_tags()
    assert any(tag.tag_name == "test_tag" for tag in tags)
```

#### image-annotator-lib

```python
@pytest.mark.integration
@pytest.mark.slow
def test_annotation_integration(monkeypatch):
    # Mock API call (avoid real API costs)
    mock_result = AnnotationResult(
        caption="Test caption",
        tags=["tag1"],
        confidence=0.9
    )
    monkeypatch.setattr(
        'image_annotator_lib.annotate',
        lambda *args, **kwargs: mock_result
    )

    # Use AnnotatorLibraryAdapter
    adapter = AnnotatorLibraryAdapter(config_service)
    result = adapter.annotate("test_image.jpg", provider="openai")

    assert result.caption == "Test caption"
```

## カバレッジ要件

### 目標: 75%+

**Measured by:**
```bash
uv run pytest --cov=src --cov-report=xml --cov-report=term
```

**Coverage Report:**
```
Name                                 Stmts   Miss  Cover
--------------------------------------------------------
src/lorairo/services/...               150     20    87%
src/lorairo/database/...               200     40    80%
src/lorairo/gui/services/...           100     30    70%  # Below target
--------------------------------------------------------
TOTAL                                 1500    300    80%
```

### カバレッジ除外

**Exclude from coverage:**
```python
# pragma: no cover

# Main entry points
if __name__ == "__main__":  # pragma: no cover
    main()

# Abstract methods
def abstract_method(self):
    raise NotImplementedError  # pragma: no cover

# Type checking blocks
if TYPE_CHECKING:  # pragma: no cover
    from typing import Protocol
```

### カバレッジ改善

**Priority areas:**
1. **Below 75%**: Add missing tests immediately
2. **75-85%**: Add tests for edge cases
3. **85%+**: Focus on integration tests

**Coverage analysis:**
```bash
# Generate HTML coverage report
uv run pytest --cov=src --cov-report=html

# Open in browser
open htmlcov/index.html
```

## テストフィクスチャ

### 共通フィクスチャ

#### データベースフィクスチャ

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db(tmp_path):
    """Create temporary SQLite database"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Create tables
    Base.metadata.create_all(engine)

    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory

@pytest.fixture
def populated_db(test_db):
    """Database with test data"""
    session = test_db()

    # Add test data
    session.add(ImageModel(file_path="/test1.jpg", phash="abc"))
    session.add(ImageModel(file_path="/test2.jpg", phash="def"))
    session.commit()

    return test_db
```

#### 設定フィクスチャ

```python
@pytest.fixture
def test_config(tmp_path):
    """Test configuration service"""
    config_path = tmp_path / "test_config.toml"
    config_path.write_text("""
[api]
openai_key = "test-key"

[directories]
database_base_dir = "test_data"
    """)

    return ConfigurationService(config_path=config_path)
```

#### Qtフィクスチャ

```python
@pytest.fixture
def main_window(qtbot):
    """MainWindow instance for testing"""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window
```

## BDD振る舞い仕様テスト

BDDはE2Eに限定せず「振る舞い仕様の表現形式」としてService層以上に適用する。
ツールは **pytest-bdd (>=8.1)**。適用レイヤーの判断基準（◎ ユーザー向けフロー / ○ Service層 / △ Repository CRUD / ✕ 内部ロジック）は `.claude/rules/testing.md` の「BDD テスト」セクションを参照。

### 実装済みシナリオ

| Feature | 内容 |
|---------|------|
| `database_management.feature` | 画像登録、アノテーション保存、検索（タグ/キャプション/日付/NSFW/手動編集/レーティング） |
| `export_filter_required.feature` | `DatasetExportService.export_with_criteria()` の criteria/image_ids 分岐 |
| `logging.feature` | ログレベル制御、モジュール固有レベル、例外ログ記録 |

### ディレクトリ構成

```
tests/bdd/
├── conftest.py     # tests/bdd 配下に @pytest.mark.bdd を自動付与
├── features/       # Gherkin .feature ファイル（日本語Gherkin可）
└── steps/          # test_<feature名>.py — ステップ定義
```

### フィーチャーファイル例

**File**: `tests/bdd/features/database_management.feature`

```gherkin
Feature: 画像データベース管理機能

  Background:
    Given データベースが初期化されている
    And モデルが登録されている

  Scenario: オリジナル画像の登録
    Given テスト用の画像ファイル "file01.webp" が存在する
    When 画像を登録する
    Then 画像メタデータがデータベースに保存される
    And 画像のUUIDが生成される
```

先頭に `# language: ja` を置くと Gherkin キーワード自体も日本語化できる（`機能`/`シナリオ`/`前提`/`もし`/`ならば`/`かつ`）。`export_filter_required.feature` がその例。

### ステップ実装パターン

**File**: `tests/bdd/steps/test_database_management.py`

```python
from pathlib import Path
from pytest_bdd import given, when, then, scenarios, parsers

# feature パスは __file__ 基準で絶対解決（cwd 依存を避ける）
_FEATURE_FILE = Path(__file__).parent.parent / "features" / "database_management.feature"
scenarios(str(_FEATURE_FILE))  # feature 内の全シナリオを一括登録

@given("データベースが初期化されている")
def given_db_initialized(test_db_manager):  # conftest.py の fixture を注入
    assert test_db_manager is not None

@when("画像を登録する")
def when_register_image(test_db_manager, fs_manager, test_image_path):
    # 実装は Service/Repository を呼ぶだけに留める
    ...
```

### pytest-bdd の使い方

#### scenarios() でシナリオを登録

`scenarios(str(_FEATURE_FILE))` をステップファイル先頭に 1 行書けば feature 内の全シナリオがテスト関数に変換される。LoRAIro では個別の `@scenario()` デコレータは使わず、常に `scenarios()` 一括登録を使う。

#### given / when / then と target_fixture

- `@given` = 事前条件、`@when` = 操作、`@then` = 検証。
- ステップ間で値を引き継ぐには `target_fixture` を使う。戻り値が同名の fixture として後続ステップに渡る。
- 既存の pytest fixture は `given`/`when`/`then` の引数名で直接注入できる。

```python
@given(parsers.parse("there are {start:d} cucumbers"), target_fixture="cucumbers")
def given_cucumbers(start):
    return {"start": start, "eat": 0}  # → 後続ステップが引数 cucumbers で受け取る

@when(parsers.parse("I eat {eat:d} cucumbers"))
def eat_cucumbers(cucumbers, eat):
    cucumbers["eat"] += eat
```

`target_fixture` は既存 fixture の上書きにも使える（特定シナリオだけ値を差し替えたいとき）。

#### ステップ引数のパース

| パーサ | 用途 |
|--------|------|
| `parsers.parse("... {n:d} ...")` | 基本。`{name:d}` `{name:f}` で型変換。まずこれを使う |
| `parsers.cfparse(..., extra_types={...})` | カスタム型が必要なとき |
| `parsers.re(r"...(?P<n>\d+)...")`, `converters={...}` | 正規表現が必要なとき |

#### Background / Scenario Outline / datatable

- **Background**: 各シナリオ実行前に共通の `Given` を流す。複数シナリオで重複する前提をまとめる。
- **Scenario Outline + Examples**: `<変数>` プレースホルダと `Examples` テーブルでデータ駆動。`Examples` ブロックにタグを付ければ `pytest -m <tag>` で絞り込める。
- **datatable**: ステップ直下の表は `datatable` 引数で `list[list[str]]` として受け取る（`database_management.feature` の「以下の画像とアノテーションが登録されている:」が該当）。

### LoRAIro でのベストプラクティス

- **`scenarios()` 一括登録を徹底** — `@scenario()` 個別指定は使わない。
- **feature パスは `__file__` 基準で解決** — `Path(__file__).parent.parent / "features" / ...`。
- **ステップ間状態は `target_fixture` か Context クラスで持ち回す** — モジュールグローバル変数で共有しない（並列実行・テスト間汚染の温床）。`database_management.py` の `SearchContext` が Context クラスの例。
- **ステップ実装は薄く** — `given`/`when`/`then` は Service/Repository を呼ぶだけ。ビジネスロジックをステップに書かない。
- **既存 pytest fixture を再利用** — DB マネージャや `FileSystemManager` は `conftest.py` の fixture を引数で注入する。
- **`bdd` マーカーは自動付与** — `tests/bdd/conftest.py` の `pytest_collection_modifyitems` が付与する。手動で `@pytest.mark.bdd` を書かない。
- **粒度を守る** — Repository 層の単純 CRUD に BDD を広げない（Gherkin が冗長になる）。`.claude/rules/testing.md` の適用表に従う。
- **タグの扱い** — feature 内タグは既定で pytest マーカーになる。`skip` 等のカスタム挙動は `conftest.py` の `pytest_bdd_apply_tag` で実装する。
- **未実装ステップの検出** — `uv run pytest --generate-missing --feature tests/bdd/features tests/bdd/steps/` で feature にあって未実装のステップを洗い出せる。

### テスト実行

```bash
uv run pytest -m bdd              # BDDテスト全体
uv run pytest tests/bdd/ -v       # ディレクトリ指定
```

## パフォーマンステスト

### ベンチマークテスト

```python
import pytest

@pytest.mark.benchmark
def test_database_query_performance(benchmark, populated_db):
    repo = ImageRepository(populated_db)

    # Benchmark query
    result = benchmark(repo.search, filters={"tags": "test"})

    assert len(result) > 0
```

**Run benchmarks:**
```bash
uv run pytest -m benchmark --benchmark-only
```

### 負荷テスト

```python
@pytest.mark.slow
def test_batch_annotation_1000_images(test_project):
    # Create 1000 test images
    images = [f"image_{i}.jpg" for i in range(1000)]
    test_project.add_images(images)

    # Measure batch processing time
    import time
    start = time.time()

    service = BatchProcessor()
    service.process_all(images)

    duration = time.time() - start

    # Assert reasonable performance
    assert duration < 300  # Under 5 minutes
```

## 継続的インテグレーション

### GitHub Actionsワークフロー

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --dev

      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: |
          uv run pytest --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

## トラブルシューティング

### よくある問題

#### 不安定なテスト

**Symptom:** Test passes sometimes, fails sometimes

**Causes:**
- Fixed-time `qtbot.wait()` instead of condition-based `waitUntil()`
- Race conditions in async/threaded code
- Shared state between tests

**Solution:**
```python
# ❌ FLAKY
qtbot.wait(100)  # May not be enough

# ✅ ROBUST
qtbot.waitUntil(lambda: widget.is_ready(), timeout=1000)
```

#### Qtクリーンアップ警告

**Symptom:** `QObject::~QObject: Timers cannot be stopped from another thread`

**Cause:** Widget not properly cleaned up

**Solution:**
```python
@pytest.fixture
def widget(qtbot):
    w = MyWidget()
    qtbot.addWidget(w)  # Ensures cleanup
    return w
```

#### データベースロック

**Symptom:** `database is locked`

**Cause:** Multiple sessions accessing same SQLite DB

**Solution:**
```python
# Use separate DB for each test
@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4()}.db"
    # ...
```

## テストリファクタリング Phase 2: マーカー自動付与（2026-02-10）

### 実装内容

**pytest マーカー自動付与フック** - conftest.py に実装

```python
# tests/unit/conftest.py の例
def pytest_collection_modifyitems(config, items):
    """tests/unit 配下のテストに @pytest.mark.unit を自動付与"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
```

**マーカー適用結果**:
- ✅ unit: 1,025 テスト
- ✅ integration: 226 テスト
- ✅ gui: 622 テスト
- ✅ bdd: 29 テスト（database_management 10 + logging 19）

### 利点

1. **安全性**: テストファイルの直接編集を回避
2. **保守性**: マーカー定義が conftest.py に一元化
3. **拡張性**: 新規テストが自動的にマーカーを取得
4. **層別管理**: 各層（unit/integration/gui/bdd）が独立したフィクスチャを管理

### 次のステップ

**Phase 4 - pytest-qt 改善**:
- qtbot.wait() → qtbot.waitUntil() への移行
- 25 箇所の固定待機を条件待機に変更
- 推定 1-2 秒のテスト実行時間削減

**実行方法**:
```bash
python3 scripts/migrate_to_waituntil.py --dir tests/ --analyze
python3 scripts/migrate_to_waituntil.py --dir tests/ --suggest
```

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - Development overview
- [docs/services.md](services.md) - Service layer architecture
- [docs/integrations.md](integrations.md) - External package integration
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/)
- [pytest documentation](https://docs.pytest.org/)
