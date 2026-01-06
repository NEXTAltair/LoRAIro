# テスト戦略とベストプラクティス

## 概要

LoRAIroは3層テスト戦略を採用し、75%+のコードカバレッジを維持しています。

**Test Levels:**
- **Unit Tests**: ビジネスロジック、Qt-freeサービス
- **Integration Tests**: GUI services, データベース統合
- **BDD E2E Tests**: エンドツーエンドワークフロー

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
├── bdd/                     # BDD E2E tests
│   ├── features/            # Gherkin feature files
│   └── steps/               # Step implementations
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
```

**Run specific markers:**
```bash
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests only
uv run pytest -m "not slow"        # Exclude slow tests
```

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

## BDD E2Eテスト

### フィーチャーファイル

**File**: `tests/bdd/features/annotation_workflow.feature`

```gherkin
Feature: Image Annotation Workflow

  Scenario: Annotate single image with OpenAI
    Given I have a project with 1 image
    And OpenAI API is configured
    When I select the image
    And I click "Annotate"
    Then I should see a caption
    And I should see tags
    And the annotation should be saved to database

  Scenario: Batch annotate multiple images
    Given I have a project with 10 images
    And OpenAI API is configured
    When I select all images
    And I click "Batch Annotate"
    Then I should see progress updates
    And all 10 images should have captions
```

### ステップ実装

**File**: `tests/bdd/steps/annotation_steps.py`

```python
from pytest_bdd import given, when, then, scenarios

scenarios('annotation_workflow.feature')

@given('I have a project with 1 image')
def project_with_image(test_project, sample_image):
    test_project.add_image(sample_image)

@when('I select the image')
def select_image(main_window):
    main_window.image_list.select_first()

@when('I click "Annotate"')
def click_annotate(main_window, qtbot):
    with qtbot.waitSignal(main_window.annotation_complete):
        main_window.annotate_button.click()

@then('I should see a caption')
def verify_caption(main_window):
    assert main_window.caption_display.text() != ""
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

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - Development overview
- [docs/services.md](services.md) - Service layer architecture
- [docs/integrations.md](integrations.md) - External package integration
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/)
- [pytest documentation](https://docs.pytest.org/)
