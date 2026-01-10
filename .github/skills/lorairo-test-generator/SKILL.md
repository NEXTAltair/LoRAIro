---
name: lorairo-test-generator
version: "1.0.0"
description: Generates pytest unit, integration, and GUI tests for LoRAIro with proper fixtures, mocks, and 75%+ coverage using pytest-qt for PySide6 testing. Use when creating test suites, implementing test patterns, or ensuring code quality with comprehensive test coverage.
allowed-tools:
  # Code exploration
  - mcp__serena__find_symbol
  - mcp__serena__search_for_pattern
  - mcp__serena__get_symbols_overview
  # Memory (test patterns)
  - mcp__serena__read_memory
  - mcp__cipher__cipher_memory_search
  # Fallback
  - Read
  - Write
  - Bash
dependencies: []
---

# Test Generation for LoRAIro

pytest+pytest-qt test generation with fixtures, mocks, and 75%+ coverage for LoRAIro project.

## When to Use

Use this skill when:
- **Creating tests**: After implementing new features
- **Improving coverage**: Increasing existing test coverage
- **Regression testing**: After refactoring code
- **GUI testing**: Implementing PySide6 widget tests

## Test Categories

### pytest Markers

**Three test levels:**
```python
# Unit tests: Single function/class, business logic
@pytest.mark.unit
def test_calculate_score():
    assert calculate_score(10, 20) == 0.5

# Integration tests: Multiple components
@pytest.mark.integration
def test_repository_service_integration():
    service = ImageProcessingService(repository)
    result = service.process_batch(images)
    assert len(result) > 0

# GUI tests: PySide6 widgets
@pytest.mark.gui
def test_widget_interaction(qtbot):
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    assert widget.isVisible()
```

### Running Tests

```bash
# All tests
uv run pytest

# By category
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m gui

# With coverage
uv run pytest --cov=src --cov-report=html
```

## Core Patterns

### 1. Unit Tests

**Repository test example:**
```python
@pytest.fixture
def test_repository(test_db_engine):
    session_factory = scoped_session(sessionmaker(bind=test_db_engine))
    repo = ImageRepository(session_factory)
    yield repo
    session_factory.remove()

@pytest.mark.unit
def test_add_image(test_repository):
    """Test image addition."""
    image = Image(path="/test/image.jpg", phash="abc123")
    result = test_repository.add(image)

    assert result.id is not None
    assert result.path == "/test/image.jpg"
```

**Service test with mocks:**
```python
@pytest.fixture
def mock_repository():
    repo = Mock(spec=ImageRepository)
    repo.get_all.return_value = [Image(id=1, path="/img1.jpg")]
    return repo

@pytest.mark.unit
def test_process_batch(mock_repository):
    service = ImageProcessingService(mock_repository)
    result = service.process_batch(["/img1.jpg"])
    assert len(result) == 1
```

### 2. Integration Tests

**Full workflow test:**
```python
@pytest.mark.integration
def test_full_workflow(test_repository):
    """Test complete workflow."""
    # Arrange
    images = [Image(path=f"/img{i}.jpg") for i in range(5)]

    # Act & Assert
    added = test_repository.batch_add(images)
    assert len(added) == 5

    results = test_repository.search(SearchCriteria(min_score=0.5))
    assert isinstance(results, list)
```

### 3. GUI Tests (pytest-qt)

**Widget test:**
```python
@pytest.fixture
def thumbnail_widget(qtbot):
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    return widget

@pytest.mark.gui
def test_signal_emission(qtbot, thumbnail_widget):
    """Test signal emission."""
    with qtbot.waitSignal(thumbnail_widget.image_selected, timeout=1000) as blocker:
        thumbnail_widget.select_image(0)

    assert blocker.args[0] == "/path/to/image.jpg"

@pytest.mark.gui
def test_button_click(qtbot, thumbnail_widget):
    """Test button interaction."""
    qtbot.mouseClick(thumbnail_widget._ui.loadButton, Qt.LeftButton)
    assert thumbnail_widget._images_loaded is True
```

### 4. Fixtures

**Common fixtures:**
```python
@pytest.fixture(scope="session")
def test_data_dir():
    return Path(__file__).parent / "resources"

@pytest.fixture
def sample_image(test_data_dir):
    return test_data_dir / "sample.jpg"

@pytest.fixture(params=[1, 5, 10])
def batch_size(request):
    """Parameterized fixture."""
    return request.param
```

## Best Practices

**DO:**
- Use AAA pattern (Arrange, Act, Assert)
- Single assertion per test
- Use fixtures for setup/teardown
- Apply appropriate pytest markers
- Maintain 75%+ code coverage

**DON'T:**
- Create dependencies between tests
- Call external APIs (use mocks)
- Hardcode paths (use `tests/resources/`)
- Use print statements (use logger or assert messages)
- Write slow unit tests (keep under 1 second)

## Coverage Requirements

```bash
# Generate coverage report
uv run pytest --cov=src --cov-report=html

# View in browser: htmlcov/index.html

# Requirements:
# - Minimum: 75%
# - Target: Unit 90%+, Integration 80%+, GUI 70%+
```

## Project Structure

```
tests/
├── conftest.py              # Shared fixtures
├── resources/               # Test data
│   ├── sample.jpg
│   └── test_config.toml
├── database/                # Database tests
│   └── test_db_repository.py
├── services/                # Service tests
│   └── test_image_processing_service.py
└── gui/                     # GUI tests
    ├── widgets/
    │   └── test_thumbnail_widget.py
    └── window/
        └── test_main_window.py
```

## Memory Integration

**Before writing tests:**
```
1. mcp__serena__read_memory("current-project-status")
2. Check for similar test patterns
3. Review existing test fixtures
```

**After writing tests:**
```
1. mcp__serena__write_memory - Record test patterns
2. mcp__cipher__cipher_extract_and_operate_memory - Store testing strategies
```

## Examples

See [examples.md](./examples.md) for detailed test implementation scenarios.

## Reference

See [reference.md](./reference.md) for complete pytest and pytest-qt API reference.
