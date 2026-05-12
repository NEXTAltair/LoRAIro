# Test Implementation Examples

Detailed examples for common LoRAIro test scenarios.

## Example 1: Repository Unit Test

**Scenario:** Test database repository with SQLite test database.

### Implementation

```python
import pytest
from sqlalchemy.orm import scoped_session, sessionmaker
from src.lorairo.database.db_core import create_test_engine
from src.lorairo.database.db_repository import ImageRepository
from src.lorairo.database.schema import Image, Base

@pytest.fixture(scope="function")
def test_db_engine():
    """Create test database engine."""
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def test_repository(test_db_engine):
    """Create test repository with isolated session."""
    session_factory = scoped_session(sessionmaker(bind=test_db_engine))
    repo = ImageRepository(session_factory)
    yield repo
    session_factory.remove()

@pytest.mark.unit
def test_add_image(test_repository):
    """Test adding image to repository.

    AAA Pattern:
    - Arrange: Create image object
    - Act: Add to repository
    - Assert: Verify persisted correctly
    """
    # Arrange
    image = Image(
        path="/test/image.jpg",
        phash="abc123def456",
        caption="Test image caption"
    )

    # Act
    result = test_repository.add(image)

    # Assert
    assert result.id is not None
    assert result.path == "/test/image.jpg"
    assert result.phash == "abc123def456"
    assert result.caption == "Test image caption"

@pytest.mark.unit
def test_get_by_id(test_repository):
    """Test retrieving image by ID."""
    # Arrange
    image = Image(path="/test/img.jpg", phash="xyz789")
    added = test_repository.add(image)

    # Act
    result = test_repository.get_by_id(added.id)

    # Assert
    assert result is not None
    assert result.id == added.id
    assert result.path == "/test/img.jpg"

@pytest.mark.unit
def test_get_by_id_not_found(test_repository):
    """Test retrieving non-existent image."""
    # Act
    result = test_repository.get_by_id(99999)

    # Assert
    assert result is None

@pytest.mark.unit
def test_batch_add(test_repository):
    """Test adding multiple images at once."""
    # Arrange
    images = [
        Image(path=f"/test/img{i}.jpg", phash=f"hash{i}")
        for i in range(10)
    ]

    # Act
    results = test_repository.batch_add(images)

    # Assert
    assert len(results) == 10
    assert all(img.id is not None for img in results)
    assert [img.path for img in results] == [f"/test/img{i}.jpg" for i in range(10)]
```

## Example 2: Service Unit Test with Mocks

**Scenario:** Test service layer with mocked dependencies.

### Implementation

```python
from unittest.mock import Mock, MagicMock, patch
from src.lorairo.services.image_processing_service import ImageProcessingService
from src.lorairo.database.schema import Image

@pytest.fixture
def mock_repository():
    """Create mock repository."""
    repo = Mock(spec=ImageRepository)

    # Setup return values
    repo.get_all.return_value = [
        Image(id=1, path="/img1.jpg", phash="hash1"),
        Image(id=2, path="/img2.jpg", phash="hash2"),
    ]

    repo.get_by_id.side_effect = lambda id: Image(id=id, path=f"/img{id}.jpg")

    repo.add.side_effect = lambda img: Image(id=1, **img.__dict__)

    return repo

@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = {
        "max_workers": 4,
        "batch_size": 100,
        "cache_enabled": True
    }
    return config

@pytest.mark.unit
def test_process_batch(mock_repository, mock_config):
    """Test batch processing service."""
    # Arrange
    service = ImageProcessingService(mock_repository, mock_config)
    image_paths = ["/img1.jpg", "/img2.jpg", "/img3.jpg"]

    # Act
    results = service.process_batch(image_paths)

    # Assert
    assert len(results) == 3
    assert mock_repository.add.call_count == 3

    # Verify correct arguments
    calls = mock_repository.add.call_args_list
    assert calls[0][0][0].path == "/img1.jpg"

@pytest.mark.unit
def test_process_with_error_handling(mock_repository, mock_config):
    """Test service handles errors gracefully."""
    # Arrange
    service = ImageProcessingService(mock_repository, mock_config)
    mock_repository.add.side_effect = ValueError("Database error")

    # Act & Assert
    with pytest.raises(ValueError, match="Database error"):
        service.process_batch(["/img1.jpg"])

@pytest.mark.unit
@patch('src.lorairo.services.image_processing_service.logger')
def test_processing_logs_progress(mock_logger, mock_repository, mock_config):
    """Test that processing logs progress."""
    # Arrange
    service = ImageProcessingService(mock_repository, mock_config)

    # Act
    service.process_batch(["/img1.jpg", "/img2.jpg"])

    # Assert
    assert mock_logger.info.called
    assert "Processing batch" in str(mock_logger.info.call_args)
```

## Example 3: Integration Test

**Scenario:** Test complete workflow across multiple components.

### Implementation

```python
@pytest.fixture(scope="function")
def integration_repository(test_db_engine):
    """Repository for integration testing."""
    session_factory = scoped_session(sessionmaker(bind=test_db_engine))
    repo = ImageRepository(session_factory)
    yield repo
    session_factory.remove()

@pytest.fixture
def integration_service(integration_repository):
    """Service with real repository."""
    config = {"max_workers": 2, "batch_size": 10}
    return ImageProcessingService(integration_repository, config)

@pytest.mark.integration
def test_full_image_workflow(integration_repository, integration_service):
    """Test complete image processing workflow.

    Workflow:
    1. Add images to database
    2. Process images via service
    3. Search for processed images
    4. Update image metadata
    5. Verify final state
    """
    # Step 1: Add images
    images = [
        Image(path=f"/test/img{i}.jpg", phash=f"hash{i}")
        for i in range(5)
    ]
    added = integration_repository.batch_add(images)
    assert len(added) == 5

    # Step 2: Process images
    results = integration_service.process_batch([img.path for img in added])
    assert len(results) == 5

    # Step 3: Search
    from src.lorairo.database.search_criteria import SearchCriteria
    criteria = SearchCriteria(min_score=0.0)
    search_results = integration_repository.search(criteria)
    assert len(search_results) >= 5

    # Step 4: Update
    search_results[0].score = 0.95
    search_results[0].caption = "Updated caption"
    updated = integration_repository.update(search_results[0])
    assert updated.score == 0.95
    assert updated.caption == "Updated caption"

    # Step 5: Verify final state
    final_image = integration_repository.get_by_id(search_results[0].id)
    assert final_image.score == 0.95
    assert final_image.caption == "Updated caption"

@pytest.mark.integration
def test_transaction_rollback(integration_repository):
    """Test that failed transactions roll back properly."""
    # Arrange
    image = Image(path="/test/img.jpg", phash="hash")
    added = integration_repository.add(image)

    # Act - Force error during update
    try:
        added.path = None  # Invalid value
        integration_repository.update(added)
    except Exception:
        pass

    # Assert - Original data unchanged
    original = integration_repository.get_by_id(added.id)
    assert original.path == "/test/img.jpg"
```

## Example 4: GUI Widget Test

**Scenario:** Test PySide6 widget with user interactions.

### Implementation

```python
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.lorairo.gui.widgets.thumbnail_widget import ThumbnailWidget

@pytest.fixture(scope="session")
def qapp():
    """Qt application fixture (session scope)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def thumbnail_widget(qtbot, qapp):
    """Create thumbnail widget for testing."""
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    return widget

@pytest.mark.gui
def test_widget_initialization(thumbnail_widget):
    """Test widget initializes correctly."""
    assert thumbnail_widget.isVisible()
    assert thumbnail_widget.windowTitle() == "Thumbnails"
    assert thumbnail_widget._images == []

@pytest.mark.gui
def test_load_images(qtbot, thumbnail_widget):
    """Test loading images into widget."""
    # Arrange
    image_paths = [f"/test/img{i}.jpg" for i in range(5)]

    # Act
    with qtbot.waitSignal(thumbnail_widget.images_loaded, timeout=1000):
        thumbnail_widget.load_images(image_paths)

    # Assert
    assert len(thumbnail_widget._images) == 5
    assert thumbnail_widget._ui.countLabel.text() == "5 images"

@pytest.mark.gui
def test_image_selection(qtbot, thumbnail_widget):
    """Test image selection emits signal."""
    # Arrange
    thumbnail_widget.load_images(["/img1.jpg", "/img2.jpg"])

    # Act
    with qtbot.waitSignal(thumbnail_widget.image_selected, timeout=1000) as blocker:
        thumbnail_widget.select_image(0)

    # Assert
    assert blocker.signal_triggered
    assert blocker.args[0] == "/img1.jpg"

@pytest.mark.gui
def test_button_click_interaction(qtbot, thumbnail_widget):
    """Test button click triggers action."""
    # Arrange
    thumbnail_widget.load_images(["/img1.jpg"])

    # Act
    qtbot.mouseClick(thumbnail_widget._ui.refreshButton, Qt.LeftButton)

    # Assert
    # Button click should trigger refresh
    assert thumbnail_widget._refresh_count == 1

@pytest.mark.gui
def test_keyboard_navigation(qtbot, thumbnail_widget):
    """Test keyboard navigation between thumbnails."""
    # Arrange
    thumbnail_widget.load_images(["/img1.jpg", "/img2.jpg", "/img3.jpg"])
    thumbnail_widget.select_image(0)

    # Act - Press Down arrow
    qtbot.keyClick(thumbnail_widget, Qt.Key_Down)

    # Assert
    assert thumbnail_widget._selected_index == 1

@pytest.mark.gui
def test_context_menu(qtbot, thumbnail_widget):
    """Test right-click context menu."""
    # Arrange
    thumbnail_widget.load_images(["/img1.jpg"])

    # Act - Right click on thumbnail
    thumbnail_item = thumbnail_widget._ui.thumbnailList.item(0)
    qtbot.mouseClick(
        thumbnail_widget._ui.thumbnailList.viewport(),
        Qt.RightButton,
        pos=thumbnail_widget._ui.thumbnailList.visualItemRect(thumbnail_item).center()
    )

    # Assert
    # Context menu should appear
    assert thumbnail_widget._context_menu.isVisible()
```

## Example 5: Widget Communication Test

**Scenario:** Test direct widget-to-widget communication.

### Implementation

```python
from src.lorairo.gui.widgets.thumbnail_widget import ThumbnailWidget
from src.lorairo.gui.widgets.details_widget import ImageDetailsWidget

@pytest.mark.gui
def test_thumbnail_to_details_communication(qtbot):
    """Test thumbnail widget sends data to details widget."""
    # Arrange
    thumbnail = ThumbnailWidget()
    details = ImageDetailsWidget()

    qtbot.addWidget(thumbnail)
    qtbot.addWidget(details)

    # Connect widgets
    details.connect_to_thumbnail_widget(thumbnail)

    # Load test data
    test_metadata = {
        "id": 1,
        "path": "/test/img1.jpg",
        "caption": "Test caption",
        "tags": ["tag1", "tag2"]
    }
    thumbnail.load_metadata([test_metadata])

    # Act - Select thumbnail
    with qtbot.waitSignal(thumbnail.image_metadata_selected, timeout=1000):
        thumbnail.select_image(0)

    # Assert - Details widget received data
    assert details._current_metadata is not None
    assert details._current_metadata["path"] == "/test/img1.jpg"
    assert details._ui.captionLabel.text() == "Test caption"

@pytest.mark.gui
def test_bidirectional_widget_communication(qtbot):
    """Test bidirectional communication between widgets."""
    # Arrange
    filter_widget = SearchFilterWidget()
    result_widget = ResultListWidget()

    qtbot.addWidget(filter_widget)
    qtbot.addWidget(result_widget)

    # Connect: Filter → Results
    result_widget.connect_to_filter(filter_widget)

    # Act - Change filter
    with qtbot.waitSignal(filter_widget.filter_changed, timeout=1000):
        filter_widget._ui.queryInput.setText("test query")

    # Assert - Results widget updated
    assert result_widget._current_filter["query"] == "test query"

    # Act - Results widget requests filter update
    with qtbot.waitSignal(result_widget.filter_update_requested, timeout=1000):
        result_widget.request_filter_change({"min_score": 0.8})

    # Assert - Filter widget updated
    assert filter_widget._ui.scoreInput.value() == 0.8
```

## Example 6: Async Worker Test

**Scenario:** Test async worker execution with QThreadPool.

### Implementation

```python
from src.lorairo.gui.workers.annotation_worker import AnnotationWorker
from PySide6.QtCore import QThreadPool

@pytest.mark.gui
def test_annotation_worker_success(qtbot):
    """Test successful annotation worker execution."""
    # Arrange
    worker = AnnotationWorker(image_id=1, model="gpt-4o")
    thread_pool = QThreadPool.globalInstance()

    # Act & Assert - Wait for signals
    with qtbot.waitSignal(worker.signals.started, timeout=1000):
        with qtbot.waitSignal(worker.signals.finished, timeout=10000) as blocker:
            thread_pool.start(worker)

    # Verify result
    results = blocker.args[0]
    assert results is not None
    assert "caption" in results
    assert "tags" in results

@pytest.mark.gui
def test_annotation_worker_error(qtbot):
    """Test annotation worker error handling."""
    # Arrange
    worker = AnnotationWorker(image_id=999, model="invalid-model")
    thread_pool = QThreadPool.globalInstance()

    # Act & Assert - Wait for error signal
    with qtbot.waitSignal(worker.signals.error, timeout=10000) as blocker:
        thread_pool.start(worker)

    # Verify error message
    error_msg = blocker.args[0]
    assert "invalid-model" in error_msg.lower() or "not found" in error_msg.lower()

@pytest.mark.gui
def test_worker_progress_updates(qtbot):
    """Test worker progress signal emissions."""
    # Arrange
    worker = AnnotationWorker(image_id=1, model="gpt-4o")
    thread_pool = QThreadPool.globalInstance()
    progress_values = []

    def on_progress(current, total):
        progress_values.append((current, total))

    worker.signals.progress.connect(on_progress)

    # Act
    with qtbot.waitSignal(worker.signals.finished, timeout=10000):
        thread_pool.start(worker)

    # Assert
    assert len(progress_values) > 0
    assert all(current <= total for current, total in progress_values)
```

## Example 7: Parameterized Tests

**Scenario:** Test same logic with multiple input variations.

### Implementation

```python
@pytest.mark.parametrize("score,expected", [
    (0.0, "Low"),
    (0.3, "Medium"),
    (0.7, "High"),
    (1.0, "Excellent"),
])
@pytest.mark.unit
def test_score_classification(score, expected):
    """Test score classification with different values."""
    from src.lorairo.scoring import classify_score

    result = classify_score(score)
    assert result == expected

@pytest.mark.parametrize("image_count", [1, 10, 100, 1000])
@pytest.mark.integration
def test_batch_processing_scalability(integration_repository, image_count):
    """Test batch processing with varying image counts."""
    # Arrange
    images = [
        Image(path=f"/img{i}.jpg", phash=f"hash{i}")
        for i in range(image_count)
    ]

    # Act
    results = integration_repository.batch_add(images)

    # Assert
    assert len(results) == image_count
    assert all(img.id is not None for img in results)

@pytest.mark.parametrize("invalid_input", [
    None,
    "",
    "/nonexistent/path.jpg",
    "/test/../../../etc/passwd",
])
@pytest.mark.unit
def test_path_validation_rejects_invalid(invalid_input):
    """Test path validation with invalid inputs."""
    from src.lorairo.validation import validate_image_path

    with pytest.raises(ValueError):
        validate_image_path(invalid_input)
```

## Coverage Best Practices

**Run coverage:**
```bash
# Generate HTML report
uv run pytest --cov=src/lorairo --cov-report=html

# Generate XML for CI
uv run pytest --cov=src/lorairo --cov-report=xml

# Show missing lines
uv run pytest --cov=src/lorairo --cov-report=term-missing
```

**Interpret results:**
```
src/lorairo/database/db_repository.py    95%   12-15
src/lorairo/services/image_service.py     87%   45, 78-82
src/lorairo/gui/widgets/thumbnail.py      72%   BELOW TARGET
```

**Improve coverage:**
1. Identify uncovered lines from report
2. Add tests for edge cases
3. Test error handling paths
4. Cover all code branches (if/else, try/except)
