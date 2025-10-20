# LoRAIro Development Guidelines

## Project-Specific Guidelines

### Key Principles
- **Do what has been asked; nothing more, nothing less**
- **NEVER create files unless absolutely necessary**
- **ALWAYS prefer editing existing files to creating new ones**
- **NEVER proactively create documentation files unless explicitly requested**

### Architecture Constraints
- **Repository Pattern**: All database access must go through repository layer
- **Service Layer**: Business logic belongs in service classes, not GUI components
- **Worker Pattern**: Long-running operations must use Qt QRunnable/QThreadPool
- **State Management**: Use DatasetStateManager for centralized application state

### Local Package Integration
- **genai-tag-db-tools**: Tag database management (tags_v3.db integration)
- **image-annotator-lib**: Multi-provider AI annotation (OpenAI, Anthropic, Google, Local)
- **Editable mode**: Both packages installed via uv.sources for development

## Code Organization Patterns

### Database Layer
```python
# Always use repository pattern
class ImageRepository:
    def get_images_by_criteria(self, criteria: SearchCriteria) -> list[Image]:
        # Proper transaction management
        # Type-safe SQLAlchemy operations
        pass

# Business logic in service layer
class ImageProcessingService:
    def __init__(self, repository: ImageRepository):
        self.repository = repository
    
    def process_batch(self, images: list[Path]) -> BatchResult:
        # Service orchestrates repository calls
        pass
```

### GUI Components
```python
# Qt signal/slot pattern for communication
class ThumbnailWidget(QWidget):
    image_selected = Signal(str)  # Use typed signals
    
    def handle_click(self):
        # Emit signals for cross-component communication
        self.image_selected.emit(image_path)

# Background workers for long operations
class DatabaseWorker(LoRAIroWorkerBase):
    def run(self):
        # Heavy operations in background thread
        # Report progress via signals
        pass
```

### Configuration Management
```python
# Type-safe configuration loading
@dataclass
class DatabaseConfig:
    database_dir: str
    connection_timeout: int

config = ConfigurationService.get_database_config()
```

## AI Integration Patterns

### Multi-Provider Support
```python
# Use image-annotator-lib for AI operations
from image_annotator_lib import annotate, list_available_annotators

# Unified interface across providers
results = annotate(
    images=image_paths,
    model_names=["gpt-4o", "claude-3-5-sonnet"],
    config=annotation_config
)
```

### Tag Management
```python
# Use genai-tag-db-tools for tag operations
from genai_tag_db_tools.services.tag_search import initialize_tag_searcher

tag_searcher = initialize_tag_searcher()
cleaned_tags = tag_searcher.clean_tags(raw_tags)
```

## Error Handling Standards

### Service Layer Errors
```python
# Custom exceptions for domain errors
class AnnotationError(Exception):
    def __init__(self, model_name: str, error_details: str):
        self.model_name = model_name
        self.error_details = error_details
        super().__init__(f"Annotation failed for {model_name}: {error_details}")

# Graceful degradation with partial results
def process_images(images: list[Path]) -> ProcessingResult:
    successful = []
    errors = []
    
    for image in images:
        try:
            result = process_single_image(image)
            successful.append(result)
        except Exception as e:
            errors.append((image, str(e)))
            logger.error(f"Failed to process {image}: {e}")
    
    return ProcessingResult(successful=successful, errors=errors)
```

### GUI Error Feedback
```python
# User-friendly error messages
def show_error_message(parent: QWidget, operation: str, error: Exception):
    QMessageBox.warning(
        parent,
        f"{operation} Failed",
        f"An error occurred during {operation}:\n{str(error)}\n\nPlease check the logs for details."
    )
```

## Performance Guidelines

### Database Operations
```python
# Efficient batch operations
def register_images_batch(self, image_paths: list[Path]) -> BatchResult:
    with self.session_factory() as session:
        # Bulk insert for performance
        images = [Image(path=path, phash=calculate_phash(path)) for path in image_paths]
        session.add_all(images)
        session.commit()
        return BatchResult(processed=len(images))
```

### Memory Management
```python
# Streaming for large datasets
def process_large_dataset(dataset_path: Path) -> Iterator[ProcessedImage]:
    for image_path in dataset_path.glob("**/*.jpg"):
        # Process one at a time to avoid memory issues
        yield process_single_image(image_path)
```

### GUI Responsiveness
```python
# Background processing with progress reporting
class BatchProcessor(LoRAIroWorkerBase):
    progress_updated = Signal(int, int)  # current, total
    
    def run(self):
        for i, item in enumerate(items):
            if self.is_cancelled:
                break
            process_item(item)
            self.progress_updated.emit(i + 1, len(items))
```

## Testing Patterns

### Repository Testing
```python
# Use test database for repository tests
@pytest.fixture
def test_repository():
    engine = create_test_engine()
    repository = ImageRepository(engine)
    return repository

def test_image_search(test_repository):
    # Test with known data
    criteria = SearchCriteria(tags=["landscape"])
    results = test_repository.search_images(criteria)
    assert len(results) > 0
```

### Service Testing
```python
# Mock repository for service tests
def test_processing_service():
    mock_repo = Mock(spec=ImageRepository)
    service = ImageProcessingService(mock_repo)
    
    result = service.process_batch([Path("test.jpg")])
    
    mock_repo.save_processed_image.assert_called_once()
```

### GUI Testing
```python
# Use pytest-qt for GUI tests
def test_thumbnail_widget(qtbot):
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    
    with qtbot.waitSignal(widget.image_selected) as blocker:
        qtbot.mouseClick(widget, Qt.LeftButton)
    
    assert blocker.args[0] == expected_image_path
```

## Deployment Considerations

### Cross-Platform Compatibility
- **Environment management**: Unified `.venv` directory with devcontainer volume mount
- **GUI compatibility**: QT_QPA_PLATFORM handling for headless environments
- **Path handling**: Use `pathlib.Path` for cross-platform file operations

### Configuration Management
- **Environment variables**: Support for deployment-specific overrides
- **TOML configuration**: Human-readable configuration files
- **Default values**: Sensible defaults for all configuration options

### Logging Strategy
- **Structured logging**: Use Loguru for consistent log formatting
- **Log levels**: Configurable verbosity for different deployment scenarios
- **File rotation**: Automatic log file management to prevent disk space issues