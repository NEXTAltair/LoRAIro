# pytest and pytest-qt Reference

Complete reference for pytest and pytest-qt testing in LoRAIro.

## pytest Core API

### Test Discovery

**pytest automatically discovers tests following these rules:**

```python
# File names
test_*.py           # test_repository.py
*_test.py           # repository_test.py

# Function names
def test_*():      # test_add_image()
def *_test():      # Not recommended

# Class names
class Test*:       # TestImageRepository
```

**Explicit test marking:**
```python
# Mark as test (not usually needed)
@pytest.mark.test
def my_test_function():
    pass
```

### Test Execution

**Command-line options:**
```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_repository.py

# Run specific test
pytest tests/test_repository.py::test_add_image

# Run tests matching pattern
pytest -k "test_add"

# Run with verbose output
pytest -v

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf

# Show local variables on failure
pytest -l

# Parallel execution
pytest -n auto    # Requires pytest-xdist
```

### Markers

**Built-in markers:**
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

**Custom markers (LoRAIro):**
```python
# Define in pytest.ini or pyproject.toml
markers =
    unit: Unit tests
    integration: Integration tests
    gui: GUI tests
    slow: Slow running tests

# Usage
@pytest.mark.unit
def test_calculation():
    pass

# Run specific markers
pytest -m unit
pytest -m "unit and not slow"
pytest -m "integration or gui"
```

### Fixtures

**Fixture scopes:**
```python
# Function scope (default) - Run for each test
@pytest.fixture
def temp_data():
    return {"key": "value"}

# Class scope - Run once per test class
@pytest.fixture(scope="class")
def database():
    db = Database()
    yield db
    db.close()

# Module scope - Run once per module
@pytest.fixture(scope="module")
def app_config():
    return load_config()

# Session scope - Run once per test session
@pytest.fixture(scope="session")
def test_data_dir():
    return Path(__file__).parent / "resources"
```

**Fixture patterns:**
```python
# Setup/teardown
@pytest.fixture
def resource():
    # Setup
    r = acquire_resource()
    yield r
    # Teardown
    r.cleanup()

# Parameterized fixture
@pytest.fixture(params=[1, 2, 3])
def number(request):
    return request.param

# Fixture dependency
@pytest.fixture
def db_connection():
    return DatabaseConnection()

@pytest.fixture
def repository(db_connection):
    return Repository(db_connection)

# Auto-use fixture
@pytest.fixture(autouse=True)
def reset_state():
    global_state.reset()
```

### Assertions

**Basic assertions:**
```python
# Equality
assert x == y
assert x != y

# Identity
assert x is y
assert x is not None

# Comparison
assert x > y
assert x >= y
assert x < y
assert x <= y

# Membership
assert x in collection
assert x not in collection

# Boolean
assert condition
assert not condition

# Type checking
assert isinstance(x, MyClass)
```

**Exception assertions:**
```python
# Assert raises specific exception
with pytest.raises(ValueError):
    function_that_raises()

# Check exception message
with pytest.raises(ValueError, match="invalid value"):
    function_that_raises()

# Access exception object
with pytest.raises(ValueError) as exc_info:
    function_that_raises()

assert "invalid" in str(exc_info.value)
```

**Approximate comparisons:**
```python
from pytest import approx

# Float comparison
assert 0.1 + 0.2 == approx(0.3)

# With tolerance
assert 10.0 == approx(10.1, abs=0.2)
assert 10.0 == approx(10.1, rel=0.01)  # 1% relative

# Sequences
assert [1.0, 2.0] == approx([1.001, 2.001], abs=0.01)
```

### Parametrization

**Basic parametrization:**
```python
@pytest.mark.parametrize("test_input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiply_by_two(test_input, expected):
    assert test_input * 2 == expected
```

**Multiple parameters:**
```python
@pytest.mark.parametrize("x", [1, 2])
@pytest.mark.parametrize("y", [3, 4])
def test_combinations(x, y):
    # Creates 4 tests: (1,3), (1,4), (2,3), (2,4)
    assert x < y
```

**Parametrized fixtures:**
```python
@pytest.fixture(params=["sqlite", "postgresql"])
def database_type(request):
    return request.param

def test_database_operations(database_type):
    # Runs once for each database type
    db = create_database(database_type)
    assert db.connect()
```

**ID customization:**
```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
], ids=["single", "double"])
def test_values(input, expected):
    pass

# Output: test_values[single], test_values[double]
```

## pytest-qt API

### qtbot Fixture

**Widget management:**
```python
def test_widget(qtbot):
    widget = MyWidget()

    # Add widget (ensures proper cleanup)
    qtbot.addWidget(widget)

    # Widget is now managed by qtbot
    assert widget.isVisible()
```

### Signal Testing

**Wait for signal:**
```python
def test_signal_emission(qtbot, widget):
    # Wait for specific signal
    with qtbot.waitSignal(widget.data_changed, timeout=1000) as blocker:
        widget.update_data("new value")

    # Check signal was emitted
    assert blocker.signal_triggered

    # Access signal arguments
    assert blocker.args == ("new value",)
```

**Wait for multiple signals:**
```python
def test_multiple_signals(qtbot, widget):
    # Wait for all signals
    with qtbot.waitSignals([widget.signal1, widget.signal2], timeout=2000):
        widget.trigger_both()

    # Wait for any signal
    with qtbot.waitSignal([widget.signal1, widget.signal2], timeout=2000):
        widget.trigger_either()
```

**Signal blocking:**
```python
def test_no_signal_emitted(qtbot, widget):
    # Ensure signal is NOT emitted
    with qtbot.assertNotEmitted(widget.data_changed, wait=100):
        widget.no_op_action()
```

### User Interaction Simulation

**Mouse events:**
```python
def test_button_click(qtbot, widget):
    from PySide6.QtCore import Qt

    # Simple click
    qtbot.mouseClick(widget.button, Qt.LeftButton)

    # Double click
    qtbot.mouseDClick(widget.button, Qt.LeftButton)

    # Click at specific position
    qtbot.mouseClick(
        widget.button,
        Qt.LeftButton,
        pos=QPoint(10, 10)
    )

    # Mouse press/release
    qtbot.mousePress(widget.button, Qt.LeftButton)
    qtbot.mouseRelease(widget.button, Qt.LeftButton)

    # Mouse move
    qtbot.mouseMove(widget, pos=QPoint(50, 50))
```

**Keyboard events:**
```python
def test_keyboard_input(qtbot, widget):
    from PySide6.QtCore import Qt

    # Type text
    qtbot.keyClicks(widget.text_input, "Hello World")

    # Single key press
    qtbot.keyClick(widget, Qt.Key_Return)

    # Key press with modifiers
    qtbot.keyClick(widget, Qt.Key_C, Qt.ControlModifier)

    # Multiple keys
    qtbot.keyClicks(widget, "Test", Qt.ControlModifier)

    # Key press/release
    qtbot.keyPress(widget, Qt.Key_Shift)
    qtbot.keyRelease(widget, Qt.Key_Shift)
```

**Wait functions:**
```python
def test_with_delays(qtbot, widget):
    # Wait for condition
    def check_state():
        return widget.is_ready()

    qtbot.waitUntil(check_state, timeout=5000)

    # Wait fixed time
    qtbot.wait(100)  # milliseconds

    # Wait for window shown
    qtbot.waitForWindowShown(widget)

    # Wait for window exposed
    qtbot.waitExposed(widget)
```

### Exception Handling

**Exception capturing:**
```python
def test_exception_in_slot(qtbot, widget):
    # Capture exceptions from slots
    with qtbot.captureExceptions() as exceptions:
        widget.trigger_buggy_slot()

    # Check exceptions
    assert len(exceptions) == 1
    assert isinstance(exceptions[0][1], ValueError)
```

## Coverage Configuration

**pyproject.toml configuration:**
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

**Command-line coverage:**
```bash
# Generate HTML report
pytest --cov=src/lorairo --cov-report=html

# Generate XML (for CI)
pytest --cov=src/lorairo --cov-report=xml

# Terminal output with missing lines
pytest --cov=src/lorairo --cov-report=term-missing

# Combine reports
pytest --cov=src/lorairo --cov-report=html --cov-report=xml

# Fail if coverage below threshold
pytest --cov=src/lorairo --cov-fail-under=75
```

## conftest.py Patterns

**Project root conftest.py:**
```python
# /workspaces/LoRAIro/tests/conftest.py
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication

# Session-scoped fixtures
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
    # app.quit() not needed - handled by Qt

# Markers registration
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "gui: GUI tests")
    config.addinivalue_line("markers", "slow: Slow running tests")

# Custom hooks
def pytest_collection_modifyitems(items):
    """Modify test collection."""
    for item in items:
        # Auto-mark GUI tests
        if "qtbot" in item.fixturenames:
            item.add_marker(pytest.mark.gui)
```

**Module-specific conftest.py:**
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

## LoRAIro Test Utilities

**Common test fixtures:**
```python
# tests/conftest.py (LoRAIro specific)

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

**Helper functions:**
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

## Running Tests in LoRAIro

**Standard test commands:**
```bash
# All tests
uv run pytest

# By category
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m gui

# Specific module
uv run pytest tests/database/
uv run pytest tests/gui/widgets/

# With coverage
uv run pytest --cov=src/lorairo --cov-report=html

# Verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Parallel execution (requires pytest-xdist)
uv run pytest -n auto
```

**CI/CD integration:**
```bash
# CI pipeline test command
uv run pytest \
    -m "unit or integration" \
    --cov=src/lorairo \
    --cov-report=xml \
    --cov-report=term \
    --cov-fail-under=75 \
    --junitxml=test-results.xml \
    -v
```

## Environment Variables

**pytest environment variables:**
```bash
# Set Qt platform for headless testing
export QT_QPA_PLATFORM=offscreen

# Disable Qt debug output
export QT_LOGGING_RULES="*.debug=false"

# pytest options
export PYTEST_ADDOPTS="--strict-markers --tb=short"

# Coverage options
export COVERAGE_CORE=sysmon
```

**LoRAIro test environment:**
```bash
# Test database location
export LORAIRO_TEST_DB_DIR=/tmp/lorairo_test_db

# Disable external API calls
export LORAIRO_MOCK_APIS=true

# Test data directory
export LORAIRO_TEST_DATA_DIR=tests/resources
```

## Additional Resources

- **pytest docs**: https://docs.pytest.org/
- **pytest-qt docs**: https://pytest-qt.readthedocs.io/
- **PySide6 testing**: https://doc.qt.io/qtforpython/tutorials/pretutorial/testing.html
- **Coverage.py**: https://coverage.readthedocs.io/
