# Repository Testing Patterns

Test strategies and pytest patterns for LoRAIro repository layer.

## Test Strategy

### Testing Pyramid for Repositories

```
        ╱──────────╲
       ╱ Integration ╲      (10%) - Full workflow tests
      ╱────────────────╲
     ╱   Repository    ╲   (90%) - Repository unit tests
    ╱────────────────────╲
```

**Focus:** Repository layer tests should be unit tests using in-memory SQLite.

### Coverage Goals
- **Repository methods:** 100% coverage (all CRUD operations)
- **Error paths:** Test all exception handling
- **Edge cases:** Empty results, null values, constraint violations
- **Transaction behavior:** Commit, rollback, savepoint

## Test Environment Setup

### conftest.py

```python
# tests/conftest.py or tests/database/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from src.lorairo.database.schema import Base
from src.lorairo.database.db_repository import ImageRepository

@pytest.fixture(scope="function")
def test_engine():
    """
    Create in-memory SQLite engine for each test.

    Scope: function - Fresh database for each test
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def session_factory(test_engine):
    """
    Create session factory for test database.

    Returns:
        scoped_session - Session factory for repository
    """
    factory = scoped_session(sessionmaker(bind=test_engine))
    yield factory
    factory.remove()

@pytest.fixture(scope="function")
def image_repository(session_factory):
    """
    Create ImageRepository instance for testing.

    Returns:
        ImageRepository - Repository instance with test session
    """
    return ImageRepository(session_factory)

@pytest.fixture
def sample_image():
    """
    Create sample Image instance (not saved to database).

    Returns:
        Image - Sample image with test data
    """
    from src.lorairo.database.schema import Image
    return Image(
        path="/test/sample.jpg",
        phash="abc123def456",
        width=1024,
        height=768,
        score=0.85
    )

@pytest.fixture
def sample_images():
    """
    Create multiple sample Image instances.

    Returns:
        list[Image] - List of sample images
    """
    from src.lorairo.database.schema import Image
    return [
        Image(path=f"/test/image_{i}.jpg", phash=f"hash{i}", score=0.5 + i * 0.1)
        for i in range(5)
    ]
```

## Basic CRUD Tests

### Test Add Operation

```python
import pytest
from src.lorairo.database.schema import Image

@pytest.mark.unit
def test_add_image(image_repository, sample_image):
    """Test adding single image"""
    # Act
    result = image_repository.add(sample_image)

    # Assert
    assert result.id is not None, "ID should be generated"
    assert result.path == sample_image.path
    assert result.phash == sample_image.phash
    assert result.score == sample_image.score

@pytest.mark.unit
def test_add_image_returns_detached_object(image_repository, sample_image):
    """Test that returned image is usable outside session"""
    result = image_repository.add(sample_image)

    # Image should be detached and all fields accessible
    assert result.id is not None
    assert result.path == "/test/sample.jpg"  # No lazy load error

@pytest.mark.unit
def test_batch_add_images(image_repository, sample_images):
    """Test adding multiple images in single transaction"""
    # Act
    results = image_repository.batch_add(sample_images)

    # Assert
    assert len(results) == len(sample_images)
    assert all(img.id is not None for img in results)
    assert all(img.path for img in results)
```

### Test Read Operations

```python
@pytest.mark.unit
def test_get_by_id_existing(image_repository, sample_image):
    """Test retrieving existing image by ID"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    result = image_repository.get_by_id(added.id)

    # Assert
    assert result is not None
    assert result.id == added.id
    assert result.path == sample_image.path

@pytest.mark.unit
def test_get_by_id_nonexistent(image_repository):
    """Test retrieving non-existent image returns None"""
    # Act
    result = image_repository.get_by_id(99999)

    # Assert
    assert result is None

@pytest.mark.unit
def test_get_all_empty(image_repository):
    """Test get_all with empty database"""
    # Act
    results = image_repository.get_all()

    # Assert
    assert results == []

@pytest.mark.unit
def test_get_all_with_limit(image_repository, sample_images):
    """Test get_all respects limit parameter"""
    # Arrange
    image_repository.batch_add(sample_images)

    # Act
    results = image_repository.get_all(limit=3)

    # Assert
    assert len(results) == 3

@pytest.mark.unit
def test_exists(image_repository, sample_image):
    """Test checking image existence"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    exists = image_repository.exists(added.id)
    not_exists = image_repository.exists(99999)

    # Assert
    assert exists is True
    assert not_exists is False
```

### Test Update Operation

```python
@pytest.mark.unit
def test_update_image(image_repository, sample_image):
    """Test updating image fields"""
    # Arrange
    added = image_repository.add(sample_image)
    original_score = added.score

    # Act
    added.score = 0.95
    updated = image_repository.update(added)

    # Assert
    assert updated.score == 0.95
    assert updated.score != original_score

    # Verify in database
    retrieved = image_repository.get_by_id(added.id)
    assert retrieved.score == 0.95

@pytest.mark.unit
def test_update_nonexistent_creates_new(image_repository, sample_image):
    """Test update with non-existent ID creates new entry (merge behavior)"""
    # Arrange
    sample_image.id = 99999  # Non-existent ID

    # Act
    result = image_repository.update(sample_image)

    # Assert
    assert result.id is not None
    # Note: Depending on merge behavior, this might create new or fail
```

### Test Delete Operation

```python
@pytest.mark.unit
def test_delete_existing(image_repository, sample_image):
    """Test deleting existing image"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    deleted = image_repository.delete(added.id)

    # Assert
    assert deleted is True
    assert image_repository.get_by_id(added.id) is None

@pytest.mark.unit
def test_delete_nonexistent(image_repository):
    """Test deleting non-existent image returns False"""
    # Act
    deleted = image_repository.delete(99999)

    # Assert
    assert deleted is False
```

## Search and Query Tests

### Test Type-Safe Search

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SearchCriteria:
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None

@pytest.mark.unit
def test_search_by_min_score(image_repository, sample_images):
    """Test searching with minimum score filter"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.7)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert all(img.score >= 0.7 for img in results)

@pytest.mark.unit
def test_search_by_score_range(image_repository, sample_images):
    """Test searching with score range"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.6, max_score=0.8)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert all(0.6 <= img.score <= 0.8 for img in results)

@pytest.mark.unit
def test_search_no_matches(image_repository, sample_images):
    """Test search with no matching results"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.99)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert results == []

@pytest.mark.unit
def test_count_matching(image_repository, sample_images):
    """Test counting matches without fetching data"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.7)

    # Act
    count = image_repository.count_matching(criteria)
    results = image_repository.search(criteria)

    # Assert
    assert count == len(results)
```

## Error Handling Tests

### Test Constraint Violations

```python
from sqlalchemy.exc import IntegrityError

@pytest.mark.unit
def test_add_duplicate_phash_fails(image_repository, sample_image):
    """Test adding image with duplicate phash raises IntegrityError"""
    # Arrange
    image_repository.add(sample_image)
    duplicate = Image(path="/different/path.jpg", phash=sample_image.phash)

    # Act & Assert
    with pytest.raises(IntegrityError):
        image_repository.add(duplicate)

@pytest.mark.unit
def test_add_safe_handles_duplicate(image_repository, sample_image):
    """Test safe add returns None on constraint violation"""
    # Arrange
    image_repository.add(sample_image)
    duplicate = Image(path="/different/path.jpg", phash=sample_image.phash)

    # Act
    result = image_repository.add_safe(duplicate)

    # Assert
    assert result is None
```

### Test Transaction Rollback

```python
@pytest.mark.unit
def test_transaction_rollback_on_error(image_repository, sample_images):
    """Test transaction rolls back entirely on error"""
    # Arrange
    # Create one valid image
    valid_image = sample_images[0]

    # Create one invalid image (will violate constraint)
    invalid_image = Image(path=None, phash="hash123")  # Null path may violate NOT NULL

    # Act & Assert
    with pytest.raises(Exception):  # Some database error
        with image_repository.session_factory() as session:
            session.add(valid_image)
            session.add(invalid_image)
            session.commit()

    # Verify rollback - valid image should NOT be in database
    all_images = image_repository.get_all()
    assert len(all_images) == 0, "Transaction should have rolled back"
```

## Transaction Tests

### Test Atomic Operations

```python
@pytest.mark.unit
def test_batch_add_is_atomic(image_repository, sample_images, monkeypatch):
    """Test batch add commits all or nothing"""
    # Arrange
    def mock_commit_fail(self):
        raise Exception("Commit failed")

    # Act & Assert
    with pytest.raises(Exception):
        with monkeypatch.context() as m:
            # Simulate commit failure
            m.setattr("sqlalchemy.orm.Session.commit", mock_commit_fail)
            image_repository.batch_add(sample_images)

    # Verify nothing was committed
    assert len(image_repository.get_all()) == 0

@pytest.mark.unit
def test_complex_operation_transactional(image_repository):
    """Test complex multi-step operation is transactional"""
    # This test would verify that operations like moving images
    # to another project are atomic (all succeed or all rollback)
    pass  # Implement based on your complex operations
```

## Performance Tests

### Test Bulk Operations

```python
@pytest.mark.unit
def test_bulk_update_performance(image_repository, sample_images):
    """Test bulk update is efficient"""
    # Arrange
    added = image_repository.batch_add(sample_images)
    score_updates = {img.id: 0.9 for img in added}

    # Act
    updated_count = image_repository.bulk_update_scores(score_updates)

    # Assert
    assert updated_count == len(score_updates)

    # Verify updates
    for img in image_repository.get_all():
        assert img.score == 0.9

@pytest.mark.unit
def test_bulk_delete(image_repository, sample_images):
    """Test bulk delete by IDs"""
    # Arrange
    added = image_repository.batch_add(sample_images)
    ids_to_delete = [img.id for img in added[:3]]

    # Act
    deleted_count = image_repository.bulk_delete_by_ids(ids_to_delete)

    # Assert
    assert deleted_count == 3
    assert len(image_repository.get_all()) == 2
```

### Test N+1 Query Prevention

```python
@pytest.mark.unit
def test_eager_loading_prevents_n_plus_1(image_repository, session_factory):
    """Test eager loading loads relations in single query"""
    from sqlalchemy import event
    from src.lorairo.database.schema import Image

    # Arrange - Add images with annotations
    with session_factory() as session:
        for i in range(5):
            image = Image(path=f"/image_{i}.jpg", phash=f"hash{i}")
            session.add(image)
            # Add related annotations if your schema has them
        session.commit()

    # Track query count
    query_count = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        query_count.append(statement)

    event.listen(test_engine, "before_cursor_execute", before_cursor_execute)

    # Act - Get images with eager loading
    images = image_repository.get_all_with_annotations()

    # Assert - Should be 1 query (or 2 max with selectinload), not N+1
    assert len(query_count) <= 2, f"Too many queries: {len(query_count)}"
```

## Test Fixtures and Helpers

### Factory Pattern for Test Data

```python
# tests/factories.py
from dataclasses import dataclass
from typing import Optional
from src.lorairo.database.schema import Image

@dataclass
class ImageFactory:
    """Factory for creating test Image instances"""

    @staticmethod
    def create(
        path: Optional[str] = None,
        phash: Optional[str] = None,
        score: Optional[float] = None,
        **kwargs
    ) -> Image:
        """Create Image with default test values"""
        return Image(
            path=path or "/test/default.jpg",
            phash=phash or "default_hash",
            score=score if score is not None else 0.75,
            **kwargs
        )

    @staticmethod
    def create_batch(count: int, **kwargs) -> list[Image]:
        """Create multiple images with unique paths"""
        return [
            ImageFactory.create(
                path=f"/test/image_{i}.jpg",
                phash=f"hash_{i}",
                **kwargs
            )
            for i in range(count)
        ]
```

### Using Factories in Tests

```python
from tests.factories import ImageFactory

@pytest.mark.unit
def test_add_with_factory(image_repository):
    """Test using factory for test data"""
    # Arrange
    image = ImageFactory.create(score=0.9)

    # Act
    result = image_repository.add(image)

    # Assert
    assert result.score == 0.9

@pytest.mark.unit
def test_batch_with_factory(image_repository):
    """Test batch operations with factory"""
    # Arrange
    images = ImageFactory.create_batch(10, score=0.8)

    # Act
    results = image_repository.batch_add(images)

    # Assert
    assert len(results) == 10
    assert all(img.score == 0.8 for img in results)
```

## Parametrized Tests

### Test Multiple Scenarios

```python
@pytest.mark.parametrize("score,expected_count", [
    (0.0, 5),   # All images
    (0.6, 4),   # Images with score >= 0.6
    (0.8, 2),   # Images with score >= 0.8
    (0.99, 0),  # No images
])
@pytest.mark.unit
def test_search_by_score_parametrized(image_repository, sample_images, score, expected_count):
    """Test search with various score thresholds"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=score)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert len(results) == expected_count

@pytest.mark.parametrize("field,value,should_raise", [
    ("path", None, True),           # NULL path should raise
    ("phash", None, True),          # NULL phash should raise
    ("score", -1.0, False),         # Negative score allowed (no constraint)
    ("width", -100, False),         # Negative width allowed (no constraint)
])
@pytest.mark.unit
def test_field_constraints(image_repository, field, value, should_raise):
    """Test database field constraints"""
    # Arrange
    image_data = {
        "path": "/test/image.jpg",
        "phash": "hash123",
        "score": 0.75,
        field: value  # Override specific field
    }
    image = Image(**image_data)

    # Act & Assert
    if should_raise:
        with pytest.raises(Exception):  # IntegrityError or other
            image_repository.add(image)
    else:
        result = image_repository.add(image)
        assert result is not None
```

## Integration Tests

### Test Full Workflow

```python
@pytest.mark.integration
def test_full_image_lifecycle(image_repository):
    """Test complete CRUD lifecycle"""
    # Create
    image = Image(path="/test/lifecycle.jpg", phash="lifecycle_hash", score=0.5)
    created = image_repository.add(image)
    assert created.id is not None

    # Read
    retrieved = image_repository.get_by_id(created.id)
    assert retrieved.path == image.path

    # Update
    retrieved.score = 0.9
    updated = image_repository.update(retrieved)
    assert updated.score == 0.9

    # Verify update persisted
    verify = image_repository.get_by_id(created.id)
    assert verify.score == 0.9

    # Delete
    deleted = image_repository.delete(created.id)
    assert deleted is True

    # Verify deletion
    assert image_repository.get_by_id(created.id) is None
```

## Coverage Best Practices

### Measure Coverage

```bash
# Run tests with coverage
uv run pytest tests/database/test_repository.py --cov=src/lorairo/database --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Coverage Goals
- **Repository methods:** 100% (all methods tested)
- **Error paths:** All exception handlers tested
- **Branch coverage:** All if/else branches tested
- **Overall:** 75%+ repository layer coverage

### Coverage Exclusions

```python
# Mark defensive code that shouldn't be covered
def defensive_check(self, value):
    if not isinstance(value, int):  # pragma: no cover
        raise TypeError("Defensive check, should never reach")
```

## Running Tests

```bash
# All repository tests
uv run pytest tests/database/test_repository.py -v

# Single test
uv run pytest tests/database/test_repository.py::test_add_image -v

# With coverage
uv run pytest tests/database/ --cov=src/lorairo/database --cov-report=term-missing

# Parallel execution
uv run pytest tests/database/ -n auto
```

## Common Pitfalls

### ❌ Sharing Sessions Between Tests
```python
# BAD: Session shared across tests
@pytest.fixture(scope="module")  # Wrong scope!
def session_factory(test_engine):
    return scoped_session(sessionmaker(bind=test_engine))
```

### ✅ Correct: Fresh Session Per Test
```python
# GOOD: Fresh session for each test
@pytest.fixture(scope="function")
def session_factory(test_engine):
    factory = scoped_session(sessionmaker(bind=test_engine))
    yield factory
    factory.remove()  # Clean up
```

### ❌ Testing Against Production Database
```python
# BAD: Using production database URL
@pytest.fixture
def test_engine():
    return create_engine("postgresql://prod_db")  # NEVER!
```

### ✅ Correct: In-Memory Test Database
```python
# GOOD: In-memory SQLite
@pytest.fixture
def test_engine():
    return create_engine("sqlite:///:memory:")
```

### ❌ Not Testing Error Paths
```python
# BAD: Only testing happy path
def test_add_image(repository, image):
    result = repository.add(image)
    assert result.id is not None
    # Missing: What if add fails?
```

### ✅ Correct: Test Error Cases
```python
# GOOD: Test both success and failure
def test_add_image_success(repository, image):
    result = repository.add(image)
    assert result.id is not None

def test_add_image_duplicate_fails(repository, image):
    repository.add(image)
    with pytest.raises(IntegrityError):
        repository.add(image)  # Duplicate phash
```
