# LoRAIro Technical Specification

## Technology Stack

### Core Technologies

#### Programming Language
- **Python 3.11+**: Primary development language
  - Modern type hints and features
  - Excellent AI/ML library ecosystem
  - Strong GUI framework support

#### GUI Framework
- **PySide6**: Qt for Python
  - Cross-platform desktop application framework
  - Rich widget set and layout management
  - Signal/slot event system
  - Designer-based UI development

**DirectoryPicker Widget Validation (2025/07/12 Enhancement)**
- **Purpose**: Prevent invalid directory selection that causes unintended batch processing
- **Validation Strategy**: Hierarchical depth limitation + file count control
- **Implementation**: Custom `validDirectorySelected` signal with pre-validation
- **Performance Constraints**:
  - Maximum directory depth: 3 levels
  - Maximum file scan limit: 10,000 files
  - Early termination on system directory detection
- **Validation Criteria**:
  - Directory must exist and be readable
  - Must contain at least 1 image file (.jpg, .png, .webp, .bmp)
  - File count must not exceed upper limit (prevents system directory selection)
  - Directory hierarchy must not exceed depth limit (prevents deep recursive scanning)
- **Signal Behavior**:
  - `textChanged`: Disabled for manual input validation
  - `validDirectorySelected`: Only emitted after successful validation
  - Trigger events: Enter key, focus loss, dialog selection, history selection

#### Database
- **SQLite**: Embedded database
  - Zero-configuration local storage
  - ACID compliance
  - File-based portability
- **SQLAlchemy**: Object-Relational Mapping
  - Declarative model definitions
  - Database abstraction layer
  - Query optimization
- **Alembic**: Database migration management
  - Version-controlled schema changes
  - Forward and backward migrations
  - Team collaboration support

#### Package Management
- **uv**: Modern Python package manager
  - Fast dependency resolution
  - Virtual environment management
  - Lock file for reproducible builds
  - Local package integration

### AI Integration

#### Supported AI Providers

**OpenAI GPT-4 Vision**
- Image analysis and captioning
- Structured output generation
- High-quality descriptions
- Rate limiting and quota management

**Anthropic Claude**
- Advanced image understanding
- Detailed analysis capabilities
- Context-aware descriptions
- Safety-focused outputs

**Google Gemini**
- Multi-modal AI processing
- Image and text integration
- Scalable API access
- Competitive pricing

**Local ML Models** (via image-annotator-lib)
- **CLIP**: Aesthetic scoring and similarity assessment
- **DeepDanbooru**: Anime/artwork tagging models
- **ONNX Runtime**: Cross-platform model inference
- **TensorFlow**: ML model execution framework
- **Transformers**: Hugging Face model integration

#### AI Integration Architecture

**Integration Flow**
```
WorkerService → AnnotationWorker → ai_annotator.py → image-annotator-lib
```

**Key Components**
- **WorkerService** (`src/lorairo/gui/services/worker_service.py`): Qt-based worker coordination
- **AnnotationWorker** (`src/lorairo/gui/workers/annotation_worker.py`): QRunnable-based asynchronous processing
- **AnnotationService** (`src/lorairo/services/annotation_service.py`): Legacy business logic (deprecated)
- **ai_annotator.py** (`src/lorairo/annotations/ai_annotator.py`): Library integration wrapper
  - `get_available_annotator_models()`: Retrieve available AI models
  - `call_annotate_library()`: Execute annotation with comprehensive error handling
  - `AiAnnotatorError`: Custom exception for library-specific errors
- **image-annotator-lib**: External library providing unified AI provider access

**Data Flow**
- Input: `list[PIL.Image]` + `list[str]` (model names) + `list[str]` (pHash values)
- Processing: Multi-provider AI annotation via unified `annotate()` function
- Output: `PHashAnnotationResults` with structured annotation data
- Storage: Results processed by AnnotationService and stored via DatabaseManager

**Current Implementation Status**
- ✅ **Fully Integrated**: image-annotator-lib for AI annotation
- ✅ **Fully Integrated**: genai-tag-db-tools for tag cleaning and database operations
- ✅ **Active**: Clean separation between legacy and current implementation
- 🔄 **In Progress**: Legacy code cleanup and documentation alignment

### Development Tools

#### Code Quality
- **Ruff**: Fast Python linter and formatter
  - Replaces multiple tools (flake8, black, isort)
  - Rust-based for performance
  - Configurable rules and formatting
- **mypy**: Static type checking
  - Type hint validation
  - Runtime error prevention
  - IDE integration support

#### Testing
- **pytest**: Testing framework
  - Fixture-based test organization
  - Parametrized testing
  - Plugin ecosystem
- **pytest-cov**: Coverage analysis
  - Line and branch coverage
  - HTML and XML reports
  - Minimum coverage enforcement
- **pytest-qt**: GUI testing
  - Qt application testing
  - Event simulation
  - Widget interaction testing

#### Logging
- **Loguru**: Modern structured logging (migrated from standard logging)
  - Simple, intuitive API
  - Colored output for development
  - File rotation and retention
  - Context management and filtering
  - Better performance than standard logging
  - Configured via `src/lorairo/utils/log.py`

## Development Environment

### System Requirements

#### Operating System
- **Windows 10/11**: Primary development platform
- **macOS 10.15+**: Supported with Qt compatibility
- **Linux**: Ubuntu 20.04+ or equivalent

#### Hardware Requirements
- **Memory**: 8GB RAM minimum, 16GB recommended
- **Storage**: 10GB available space for models and data
- **GPU**: Optional but recommended for local ML models
  - NVIDIA GPU with CUDA support
  - 4GB+ VRAM for larger models

#### Python Environment
- **Python 3.11 or higher**
- **Virtual environment support**
- **Package compilation tools** (for some dependencies)

### Environment Setup

#### Initial Setup
```bash
# Clone repository with submodules
git clone --recurse-submodules https://github.com/user/LoRAIro.git
cd LoRAIro

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create and activate virtual environment with dependencies
uv sync --dev

# Verify installation
uv run python -c "import lorairo; print('Installation successful')"
```

#### Development Dependencies
```toml
[tool.uv.dev-dependencies]
pytest = "^8.0.0"
pytest-cov = "^4.0.0"
pytest-qt = "^4.2.0"
ruff = "^0.1.0"
mypy = "^1.7.0"
pre-commit = "^3.5.0"
```

#### Local Package Integration
```toml
[tool.uv.sources]
genai-tag-db-tools = { path = "local_packages/genai-tag-db-tools", editable = true }
image-annotator-lib = { path = "local_packages/image-annotator-lib", editable = true }
```

### Configuration Management

#### Configuration Files
- **`config/lorairo.toml`**: Main application configuration
  - Database settings
  - Image processing parameters
  - Logging configuration
  - UI preferences
- **`config/annotator_config.toml`**: AI annotator configuration
  - Model definitions and parameters
  - Provider-specific settings
- **`config/available_api_models.toml`**: API model definitions
  - Supported AI provider models
  - Model capabilities and limits

#### Configuration Service
- **`src/lorairo/services/configuration_service.py`**: Configuration management
  - TOML file parsing and validation
  - Runtime configuration access
  - Settings persistence
- **`src/lorairo/utils/config.py`**: Configuration utilities
  - Configuration loading helpers
  - Default value management

### Configuration Management

#### Primary Configuration (`config/lorairo.toml`)
```toml
[app]
name = "LoRAIro"
version = "1.0.0"
debug = false

[database]
path = "Image_database/image_database.db"
pool_size = 5
echo = false

[ai_providers.openai]
api_key_env = "OPENAI_API_KEY"
model = "gpt-4-vision-preview"
timeout = 30
retry_attempts = 3
rate_limit_requests_per_minute = 10

[ai_providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"
model = "claude-3-sonnet-20240229"
timeout = 45
retry_attempts = 2

[ai_providers.google]
api_key_env = "GOOGLE_API_KEY"
model = "gemini-pro-vision"
timeout = 30
retry_attempts = 3

[logging]
level = "INFO"
format = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
rotation = "1 week"
retention = "1 month"
```

#### Environment Variables
```bash
# AI Provider API Keys
export OPENAI_API_KEY="your-openai-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export GOOGLE_API_KEY="your-google-api-key"

# Development Settings
export LORAIRO_DEBUG="true"
export LORAIRO_LOG_LEVEL="DEBUG"
```

## Database Design

### Schema Architecture

#### Core Tables

**Images Table**
```sql
CREATE TABLE images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    format TEXT,
    hash_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Annotations Table**
```sql
CREATE TABLE annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    caption TEXT,
    tags TEXT, -- JSON array
    confidence REAL,
    processing_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE
);
```

**Quality Scores Table**
```sql
CREATE TABLE quality_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    aesthetic_score REAL,
    technical_score REAL,
    overall_score REAL,
    scoring_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE
);
```

#### Indexes and Performance
```sql
-- Performance indexes
CREATE INDEX idx_images_file_path ON images(file_path);
CREATE INDEX idx_images_hash ON images(hash_value);
CREATE INDEX idx_annotations_image_id ON annotations(image_id);
CREATE INDEX idx_annotations_provider ON annotations(provider);
CREATE INDEX idx_quality_scores_image_id ON quality_scores(image_id);
```

#### Timezone Handling (2025/07/12 Standardization)

**UTC Standardization Policy**
- **Database Storage**: All `TIMESTAMP(timezone=True)` fields store timezone-aware UTC datetime objects
- **Application Processing**: All datetime parsing and comparison operations use UTC timezone consistency
- **Date String Processing**: The `_parse_datetime_str()` method in `ImageRepository` ensures:
  - Naive datetime strings are interpreted as UTC and converted to timezone-aware objects
  - Existing timezone-aware datetime objects preserve their timezone information
  - UTC timezone-aware objects are returned for database comparison compatibility
  - Invalid date formats return `None` with appropriate warning logging

**Implementation Details**
```python
# Database schema uses timezone-aware TIMESTAMP fields
created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))
updated_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC))

# Application datetime parsing ensures UTC consistency
def _parse_datetime_str(self, date_str: str | None) -> datetime | None:
    # Parses date strings and returns timezone-aware UTC datetime objects
    # Ensures compatibility with TIMESTAMP(timezone=True) database fields
```

**Benefits**
- Consistent timezone handling across all database operations
- Proper comparison operations between parsed dates and database timestamps
- Protection against timezone-related bugs in filtering and search operations
- Standardized UTC storage for international deployment compatibility

### Migration Management

#### Alembic Configuration
```python
# alembic/env.py
from sqlalchemy import engine_from_config, pool
from alembic import context
from lorairo.database.schema import Base

target_metadata = Base.metadata

def run_migrations_online():
    configuration = context.config
    configuration.set_main_option(
        "sqlalchemy.url", 
        get_database_url()
    )
    
    connectable = engine_from_config(
        configuration.get_section(configuration.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
```

#### Migration Best Practices
- Always review auto-generated migrations
- Test migrations with sample data
- Provide rollback procedures
- Document breaking changes
- Backup database before production migrations

## Code Architecture

### Design Patterns

#### Repository Pattern
```python
from abc import ABC, abstractmethod
from typing import Optional, List
from lorairo.database.schema import ImageRecord

class ImageRepositoryInterface(ABC):
    @abstractmethod
    def create(self, image_data: dict) -> ImageRecord:
        pass
    
    @abstractmethod
    def get_by_id(self, image_id: int) -> Optional[ImageRecord]:
        pass
    
    @abstractmethod
    def get_by_path(self, file_path: str) -> Optional[ImageRecord]:
        pass
    
    @abstractmethod
    def list_all(self, limit: int = 100, offset: int = 0) -> List[ImageRecord]:
        pass

class SQLAlchemyImageRepository(ImageRepositoryInterface):
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    def create(self, image_data: dict) -> ImageRecord:
        with self.session_factory() as session:
            image = ImageRecord(**image_data)
            session.add(image)
            session.commit()
            session.refresh(image)
            return image
```

#### Service Layer Pattern
```python
from typing import List, Dict, Any
from pathlib import Path
from lorairo.database.db_repository import ImageRepository
from lorairo.storage.file_system import FileSystemManager

class ImageProcessingService:
    def __init__(
        self,
        image_repository: ImageRepository,
        file_manager: FileSystemManager,
        config: dict
    ):
        self.image_repository = image_repository
        self.file_manager = file_manager
        self.config = config
        self.logger = get_logger(__name__)
    
    async def process_images(
        self, 
        image_paths: List[Path]
    ) -> List[Dict[str, Any]]:
        """Process multiple images with error handling and progress tracking."""
        results = []
        
        for i, path in enumerate(image_paths):
            try:
                result = await self._process_single_image(path)
                results.append(result)
                
                # Emit progress signal
                progress = int((i + 1) / len(image_paths) * 100)
                self.progress_updated.emit(progress)
                
            except Exception as e:
                self.logger.error(f"Failed to process {path}: {e}")
                results.append({"error": str(e), "path": str(path)})
        
        return results
```

#### Factory Pattern
```python
from typing import Protocol
from lorairo.annotations.providers.base import AIProvider

class AIProviderFactory:
    _providers = {
        "openai": "lorairo.annotations.providers.openai.OpenAIProvider",
        "anthropic": "lorairo.annotations.providers.anthropic.AnthropicProvider",
        "google": "lorairo.annotations.providers.google.GoogleProvider",
    }
    
    @classmethod
    def create_provider(cls, provider_name: str, config: dict) -> AIProvider:
        if provider_name not in cls._providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        provider_class_path = cls._providers[provider_name]
        module_path, class_name = provider_class_path.rsplit(".", 1)
        
        module = importlib.import_module(module_path)
        provider_class = getattr(module, class_name)
        
        return provider_class(config)
```

### Error Handling Strategy

#### Custom Exception Hierarchy
```python
class LoRAIroException(Exception):
    """Base exception for LoRAIro application."""
    pass

class ConfigurationError(LoRAIroException):
    """Configuration-related errors."""
    pass

class DatabaseError(LoRAIroException):
    """Database operation errors."""
    pass

class ImageProcessingError(LoRAIroException):
    """Image processing errors."""
    pass

class AIProviderError(LoRAIroException):
    """AI provider communication errors."""
    pass

class RateLimitError(AIProviderError):
    """API rate limit exceeded."""
    pass

class AuthenticationError(AIProviderError):
    """API authentication failed."""
    pass
```

#### Error Handling Pattern
```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def handle_ai_provider_errors() -> Generator[None, None, None]:
    """Context manager for consistent AI provider error handling."""
    try:
        yield
    except requests.exceptions.Timeout:
        raise AIProviderError("Request timeout - provider may be overloaded")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        elif e.response.status_code == 401:
            raise AuthenticationError("Invalid API credentials")
        else:
            raise AIProviderError(f"HTTP error: {e}")
    except Exception as e:
        raise AIProviderError(f"Unexpected error: {e}")
```

### Type System

#### Type Definitions
```python
from typing import TypedDict, Optional, List, Union, Literal
from pathlib import Path

class ImageMetadata(TypedDict):
    width: int
    height: int
    format: str
    file_size: int
    hash_value: str

class AnnotationResult(TypedDict):
    caption: Optional[str]
    tags: List[str]
    confidence: float
    processing_time: float
    provider: str
    model: str

class QualityScore(TypedDict):
    aesthetic_score: float
    technical_score: float
    overall_score: float
    scoring_model: str

AIProvider = Literal["openai", "anthropic", "google"]
ImageFormat = Literal["JPEG", "PNG", "WebP", "BMP", "TIFF"]
ProcessingStatus = Literal["pending", "processing", "completed", "failed"]
```

#### Protocol Definitions
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ImageProcessor(Protocol):
    def process_image(self, image_path: Path) -> ImageMetadata:
        """Process an image and return metadata."""
        ...

@runtime_checkable
class AnnotationProvider(Protocol):
    async def annotate_image(self, image_path: Path) -> AnnotationResult:
        """Generate annotations for an image."""
        ...

@runtime_checkable
class QualityScorer(Protocol):
    def score_image(self, image_path: Path) -> QualityScore:
        """Calculate quality scores for an image."""
        ...
```

## Performance Optimization

### Memory Management

#### Image Processing Optimization
```python
from contextlib import contextmanager
import psutil
from PIL import Image

@contextmanager
def memory_limited_processing(max_memory_mb: int = 1000):
    """Context manager to limit memory usage during processing."""
    initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
    
    try:
        yield
    finally:
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_used = current_memory - initial_memory
        
        if memory_used > max_memory_mb:
            import gc
            gc.collect()
            logger.warning(f"High memory usage detected: {memory_used:.1f}MB")

def process_large_image(image_path: Path) -> Image.Image:
    """Process large images with memory optimization."""
    with memory_limited_processing():
        # Open image with lazy loading
        with Image.open(image_path) as img:
            # Process in chunks if needed
            if img.size[0] * img.size[1] > 4000 * 4000:
                # Resize for processing
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            
            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            return img.copy()
```

#### Database Connection Pooling
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

### Asynchronous Processing

#### Hybrid Controlled Batch Processing (clarified 2025/07/06)
```python
class HybridBatchProcessor:
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.performance_target = 300  # 5 minutes for 1000 images = 300 seconds
        
    async def process_images_batch(
        self,
        image_paths: List[Path],
        progress_callback: Callable[[int], None] | None = None
    ) -> List[ProcessingResult]:
        """Process images in 100-image batches for optimal memory control."""
        total_images = len(image_paths)
        processed_count = 0
        
        for batch_start in range(0, total_images, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_images)
            batch = image_paths[batch_start:batch_end]
            
            # Batch registration and processing
            batch_results = await self._process_single_batch(batch)
            processed_count += len(batch_results)
            
            if progress_callback:
                progress = int(processed_count / total_images * 100)
                progress_callback(progress)
                
        return results

#### Policy Violation Tracking (clarified 2025/07/06)
```python
# Database schema addition for policy violation tracking
class AnnotationFailure(Base):
    __tablename__ = 'annotation_failures'
    
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey('images.id'))
    model_name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    failure_reason = Column(String, nullable=False)
    error_message = Column(Text)
    failed_at = Column(DateTime, default=datetime.utcnow)
    is_policy_violation = Column(Boolean, default=False)

# Retry policy with violation awareness
def check_policy_violations(image_ids: List[int], model_name: str) -> List[int]:
    """Check for previous policy violations and warn user."""
    violations = session.query(AnnotationFailure).filter(
        AnnotationFailure.image_id.in_(image_ids),
        AnnotationFailure.model_name == model_name,
        AnnotationFailure.is_policy_violation == True
    ).all()
    
    if violations:
        # Show warning dialog to user
        show_policy_violation_warning(violations)
    
    return [v.image_id for v in violations]
```

#### Background Task Management
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Callable, Any

class TaskManager:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: List[asyncio.Task] = []
    
    async def run_in_background(
        self, 
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Run CPU-bound task in background thread."""
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(self.executor, func, *args, **kwargs)
        self.active_tasks.append(task)
        
        try:
            result = await task
            return result
        finally:
            self.active_tasks.remove(task)
    
    async def process_batch(
        self,
        items: List[Any],
        processor: Callable,
        batch_size: int = 10
    ) -> List[Any]:
        """Process items in batches to control resource usage."""
        results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_tasks = [
                self.run_in_background(processor, item)
                for item in batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            results.extend(batch_results)
        
        return results
```

## Security Considerations

### API Key Management

#### ConfigurationService Requirements (updated 2025/07/07)

**Configuration Item Structure**
```toml
[api]
openai_key = ""          # OpenAI APIキー (平文保存)
claude_key = ""          # Anthropic Claude APIキー (平文保存)
google_key = ""          # Google Vision APIキー (平文保存)

[directories]
database_dir = ""        # プロジェクト群の親ディレクトリ（project_name/database.db + images/）
export_dir = ""          # アノテーション結果の出力先（.txt/.captionファイル等）
batch_results_dir = ""   # OpenAI Batch API結果JSONLファイルの保存先

[huggingface]
hf_username = ""         # Hugging Face ユーザー名 (平文保存)
repo_name = ""           # リポジトリ名
token = ""               # Hugging Face トークン (平文保存)

[log]
level = "INFO"           # ログレベル (DEBUG/INFO/WARNING/ERROR/CRITICAL)
file_path = ""           # ログファイルパス
```

**Directory Structure Design**
```
database_dir/
├── project_a/
│   ├── database.db      # SQLite database for project_a
│   └── images/          # Processed images for project_a
└── project_b/
    ├── database.db      # SQLite database for project_b  
    └── images/          # Processed images for project_b
```

**Functional Requirements (2025/07/06 clarifications)**
- **API Key Management**: Plain-text storage in config.toml (personal OSS development)
- **Logging Security**: API keys masked with `***` in log output
- **UI Integration**: Auto-exclude models from providers with missing API keys
- **Configuration Changes**: Immediate reflection and file persistence
- **Validation**: Path format validation, log level validation, required field checks

**Configuration Item Changes**
- `database` → `database_dir` (multi-DB file support)
- `response_file` → `batch_results_dir` (OpenAI Batch API results)
- `output` → `export_dir` (annotation results export)
- `edited_output` → removed (not used)
- `dataset` → managed under `database_dir` structure

**Architecture Design (implemented 2025/07/07)**

**Shared Configuration with Dependency Injection Pattern**
- Multiple ConfigurationService instances share the same configuration object (reference passing)
- Configuration changes are immediately reflected across all instances
- High testability through dependency injection of mock configurations
- Automatic default configuration file creation when missing

**Usage Pattern**
```python
# Master configuration service (loads file)
master_config = ConfigurationService()
shared_config = master_config.get_shared_config()

# Child services (share configuration object)
window_config = ConfigurationService(shared_config=shared_config)
processor_config = ConfigurationService(shared_config=shared_config)

# Changes propagate immediately to all instances
window_config.update_setting("api", "openai_key", "new_key")
# → processor_config also sees the change instantly
```

**Project Structure Design (updated 2025/07/07)**

**Multi-Project Database Architecture**
- Each project maintains independent SQLite database for data isolation
- Unified main database for cross-project search and analysis
- Support for project extraction workflows (subset creation)

**Directory Structure Pattern**
```
lorairo_data/
├── {project_name}_{YYYYMMDD}_{NNN}/
│   ├── image_database.db
│   └── image_dataset/
│       ├── original_images/{YYYY}/{MM}/{DD}/{source_dir}/
│       ├── {resolution}/{YYYY}/{MM}/{DD}/{source_dir}/
│       └── batch_request_jsonl/
```

**Project Name Support**
- Unicode project names supported (Japanese, mixed languages)
- Safe filename sanitization for filesystem compatibility
- Date-based versioning with 3-digit incremental numbering

**Use Cases**
- Main dataset management with comprehensive search
- Focused project extraction (quality filters, content type, tags)
- HuggingFace dataset preparation and publishing
- Research dataset curation with provenance tracking

**Implementation Requirements**
```python
def get_project_dir(base_dir_name: str, project_name: str = "project") -> Path:
    """Generate project directory with Unicode name support"""

def normalize_legacy_paths(db_path: Path) -> None:
    """Convert legacy absolute paths to relative project paths"""

def __init__(self, config_path: Path | None = None, shared_config: dict[str, Any] | None = None):
    """Initialize with optional shared configuration object for DI pattern"""
    
def _create_default_config_file(self) -> dict[str, Any]:
    """Create default configuration file when missing"""
    
def mask_api_key(key: str) -> str:
    """APIキーを***でマスキング"""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"

def get_available_providers(self) -> list[str]:
    """APIキーが設定されているプロバイダーを返す"""
    providers = []
    if self.get_setting("api", "openai_key"):
        providers.append("openai")
    if self.get_setting("api", "claude_key"):
        providers.append("anthropic")
    if self.get_setting("api", "google_key"):
        providers.append("google")
    return providers
```

### Input Validation

#### File Path Validation
```python
from pathlib import Path
import mimetypes

class FileValidator:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    @classmethod
    def validate_image_file(cls, file_path: Path) -> bool:
        """Validate image file for security and format compliance."""
        
        # Check if file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check file extension
        if file_path.suffix.lower() not in cls.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        # Check file size
        if file_path.stat().st_size > cls.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file_path.stat().st_size} bytes")
        
        # Check MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith("image/"):
            raise ValueError(f"Invalid MIME type: {mime_type}")
        
        # Validate image content
        try:
            with Image.open(file_path) as img:
                img.verify()
        except Exception as e:
            raise ValueError(f"Invalid image file: {e}")
        
        return True
```

## Deployment Considerations

### Build and Distribution

#### Application Packaging
```python
# pyproject.toml
[project]
name = "lorairo"
version = "1.0.0"
description = "AI-powered image annotation for ML datasets"
authors = [{name = "Your Name", email = "your.email@example.com"}]
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"

dependencies = [
    "PySide6>=6.6.0",
    "SQLAlchemy>=2.0.0",
    "alembic>=1.12.0",
    "Pillow>=10.0.0",
    "requests>=2.31.0",
    "loguru>=0.7.0",
    "toml>=0.10.0",
    "psutil>=5.9.0",
]

[project.scripts]
lorairo = "lorairo.main:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-qt>=4.2.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
    "pre-commit>=3.5.0",
]
```

#### Environment Configuration
```bash
# Production environment setup
export LORAIRO_ENV="production"
export LORAIRO_LOG_LEVEL="INFO"
export LORAIRO_DATABASE_PATH="/opt/lorairo/data/database.db"
export LORAIRO_CONFIG_PATH="/etc/lorairo/config.toml"

# Resource limits
export LORAIRO_MAX_MEMORY_MB="2048"
export LORAIRO_MAX_WORKERS="4"
export LORAIRO_BATCH_SIZE="10"
```

## Image Processing Module Architecture

### Module Separation Design (2025/07/14 - Completed)

#### Overview
The image processing system has been successfully refactored from a monolithic approach into modular components following clean architecture principles and dependency injection patterns.

#### Completed Module Structure

**Current Implementation (`src/lorairo/editor/`)**
- **`image_processor.py`**: ImageProcessingManager and ImageProcessor classes
  - High-level processing coordination and workflow management
  - Image resizing and color profile normalization
  - Integration point for AutoCrop and Upscaler modules
- **`autocrop.py`**: AutoCrop module (Completed 2025/07/12)
  - Singleton pattern with classmethod interface
  - Complementary color difference algorithm
  - Letterbox detection and removal
- **`upscaler.py`**: Upscaler module (Completed 2025/07/14)
  - Configuration-driven dependency injection
  - Multi-model support (RealESRGAN variants)
  - Model caching and lazy loading

#### Implementation Details

**1. ImageProcessingManager Integration**
```python
class ImageProcessingManager:
    def __init__(self, file_system_manager: FileSystemManager, target_resolution: int, 
                 preferred_resolutions: list[tuple[int, int]], config_service: ConfigurationService):
        self.upscaler = Upscaler(config_service)  # Dependency injection
        
    def process_image(self, db_stored_original_path: Path, original_has_alpha: bool, 
                     original_mode: str, upscaler: str | None = None) -> tuple[Image.Image | None, dict[str, Any]]:
        cropped_img = AutoCrop.auto_crop_image(img)  # Static method call
        upscaled_img = self.upscaler.upscale_image(converted_img, upscaler)  # Instance method
```

**2. AutoCrop Module (Singleton Pattern)**
```python
class AutoCrop:
    """Singleton pattern with complementary color difference algorithm"""
    
    @classmethod
    def auto_crop_image(cls, pil_image: Image.Image) -> Image.Image:
        """Main public interface for automatic image cropping"""
        
    def _get_crop_area(self, np_image: np.ndarray) -> tuple[int, int, int, int] | None:
        """Core complementary color analysis algorithm"""
```

**3. Upscaler Module (Dependency Injection Pattern)**
```python
class Upscaler:
    """Configuration-driven upscaler with dependency injection"""
    
    def __init__(self, config_service: ConfigurationService):
        self.config_service = config_service
        self._loaded_models: dict[str, Any] = {}  # Model caching
        
    @classmethod
    def create_default(cls) -> "Upscaler":
        """Factory method for backward compatibility"""
        
    def upscale_image(self, img: Image.Image, model_name: str, scale: float | None = None) -> Image.Image:
        """Main upscaling interface with model management"""
        """指定解像度への画像アップスケール処理"""
        
    def get_available_models(self) -> list[str]:
        """利用可能なアップスケールモデルの一覧取得"""
```

#### Database Schema Enhancements

**ProcessedImage Table Extension**
```python
class ProcessedImage(Base):
    # 既存フィールド
    upscaler_used: Mapped[str | None] = mapped_column(String)  # 使用されたアップスケーラー名
    
    # 新規追加フィールド (2025/07/12)
    crop_status: Mapped[str | None] = mapped_column(String)    # クロップ状態: None/"auto"/"approved"/"manual"
```

**Crop Status Management**
- **None**: 未処理 (新規画像、クロップ処理実行)
- **"auto"**: 自動クロップ済み (再処理対象)
- **"approved"**: 承認済みクロップ (再処理対象外)
- **"manual"**: 手動調整済みクロップ (再処理対象外)

#### Implementation Specifications

**1. Image ID Management**
- **基本原則**: 全ての処理済み画像は元画像のimage_idを基準とする
- **一意性保証**: `(image_id, width, height, filename)` による複合ユニーク制約
- **関係性維持**: 元画像削除時のカスケード削除 (`ondelete="CASCADE"`)

**2. Crop Processing Pipeline**
```python
def process_with_crop_awareness(self, image_id: int, image_path: Path) -> ProcessingResult:
    """クロップ状態を考慮した処理パイプライン"""
    
    # 1. 既存処理済み画像のクロップ状態確認
    existing_metadata = self.db_manager.get_processed_metadata(image_id)
    crop_status = existing_metadata.get('crop_status') if existing_metadata else None
    
    # 2. 承認済み画像は再処理スキップ
    if crop_status in ["approved", "manual"]:
        logger.info(f"スキップ: 承認済みクロップ (status={crop_status})")
        return existing_metadata
        
    # 3. 自動クロップ実行 (None, "auto"の場合)
    processed_image, processing_metadata = self.auto_crop.crop_image(image, crop_status)
    processing_metadata['crop_status'] = 'auto'  # 処理後のステータス設定
```

**3. Upscaler Model Management**

**Fixed Directory Approach (Simple)**
```python
class Upscaler:
    MODEL_DIRECTORY = Path("models/upscalers")
    
    def get_available_models(self) -> list[str]:
        """models/upscalers内の全モデルをリストアップ"""
        if not self.MODEL_DIRECTORY.exists():
            return []
            
        model_files = []
        for file_path in self.MODEL_DIRECTORY.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ['.pth', '.safetensors', '.pt', '.ckpt']:
                model_files.append(file_path.stem)
        
        return sorted(model_files)
```

**Spandrel Integration Specification**
```python
from spandrel import ModelLoader, UnsupportedModelError

class SpandrelUpscaler:
    def __init__(self):
        self.model_loader = ModelLoader(device="cuda" if torch.cuda.is_available() else "cpu")
        
    def load_model(self, model_path: Path) -> bool:
        """Spandrelによるモデル読み込みと互換性チェック"""
        try:
            model_descriptor = self.model_loader.load_from_file(model_path)
            logger.info(f"モデル読み込み成功: {model_path.name}")
            return True
        except UnsupportedModelError:
            logger.warning(f"Spandrel非対応モデル: {model_path.name}")
            return False
        except Exception as e:
            logger.error(f"モデル読み込みエラー: {model_path.name}, Error: {e}")
            return False
```

**Model Directory Structure**
```
models/
└── upscalers/
    ├── RealESRGAN_x4plus.pth
    ├── waifu2x_art_noise3_scale2.safetensors
    ├── ESRGAN_x4.pth
    └── model_symlink.pth -> /path/to/actual/model.pth
```

#### Performance and Resource Management

**Memory Optimization**
```python
class ResourceAwareProcessor:
    def __init__(self, max_memory_mb: int = 2048):
        self.max_memory_mb = max_memory_mb
        
    def process_with_memory_limit(self, image: Image.Image) -> Image.Image:
        """メモリ使用量を監視しながら処理実行"""
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        try:
            result = self._execute_processing(image)
            return result
        finally:
            current_memory = psutil.Process().memory_info().rss / 1024 / 1024
            if current_memory - initial_memory > self.max_memory_mb * 0.8:
                gc.collect()
                logger.warning(f"高メモリ使用量検出: {current_memory - initial_memory:.1f}MB")
```

**Batch Processing Integration**
```python
def process_batch_with_crop_status(self, image_ids: list[int]) -> list[ProcessingResult]:
    """バッチ処理でのクロップ状態考慮"""
    results = []
    
    for image_id in image_ids:
        # 承認済み画像のフィルタリング
        if self._is_approved_crop(image_id):
            logger.debug(f"スキップ: 承認済みクロップ (ID={image_id})")
            continue
            
        # 未処理・自動処理済み画像の処理実行
        result = self.process_with_crop_awareness(image_id)
        results.append(result)
        
    return results
```

#### Migration and Implementation Strategy

**Phase 1: Module Extraction**
1. `auto_crop.py` - AutoCropクラスの分離
2. `upscaler.py` - Upscalerクラスの分離
3. `processing_manager.py` - ImageProcessingManagerの更新

**Phase 2: Database Schema Migration**
```python
"""Add crop_status to processed_images table

Revision ID: add_crop_status
Revises: previous_revision
Create Date: 2025-07-12
"""

def upgrade():
    op.add_column('processed_images', 
                  sa.Column('crop_status', sa.String(), nullable=True))

def downgrade():
    op.drop_column('processed_images', 'crop_status')
```

**Phase 3: Integration Testing**
- モジュール間インターフェース検証
- クロップ状態管理ロジック検証  
- Spandrelモデル互換性テスト
- パフォーマンスベンチマーク

#### Benefits and Design Rationale

**Maintainability Improvements**
- **Single Responsibility**: 各モジュールが明確な責務を持つ
- **Testability**: 独立したユニットテストが可能
- **Reusability**: 他の処理パイプラインでの再利用性向上

**Performance Optimizations**
- **Memory Management**: モジュール単位での最適化
- **Resource Isolation**: クロップとアップスケールの独立実行
- **Batch Efficiency**: 承認済み画像のスキップによる処理時間短縮

**Extensibility**
- **Model Support**: 新しいアップスケールモデルの簡単な追加
- **Processing Options**: クロップアルゴリズムの差し替え可能
- **Workflow Customization**: 処理パイプラインの柔軟な調整

## Upscaler Resource Management Implementation Plan (2025/07/12)

### Overview
Spandrelベースのアップスケーラーインスタンス管理の実装計画。バッチ処理効率化とVRAMリソース競合回避を目的とする。

### Resource Management Strategy

#### Instance Lifecycle (Confirmed Specification)
```
1. 初回アップスケール実行 → グローバルインスタンス生成 + モデル読み込み
2. バッチ処理完了 → インスタンス維持（同モデル保持）
3. 同モデルでの別バッチ → 既存インスタンス再利用（読み込み不要）
4. 異なるモデル指定 → インスタンス破棄 → 新インスタンス生成 + 新モデル読み込み
5. アノテーション処理開始 → 強制インスタンス破棄 + VRAM解放
6. アノテーション後のアップスケール → 新インスタンス生成（前回と同モデルでも）
```

#### Design Principles
- **Single Instance Pattern**: グローバルに1つのUpscalerインスタンスのみ保持
- **Model Change Detection**: モデル名変更時のみ新規読み込み実行
- **Forced Cleanup**: アノテーション処理前の強制リソース解放
- **No Caching**: メインメモリキャッシュは実装しない（コストベネフィット不適合）

### Implementation Specification

#### Core Class Structure
```python
class Upscaler:
    """Spandrelベースの画像アップスケーラー（シングルトンパターン）"""
    
    # クラス変数（グローバル状態）
    _global_instance: "Upscaler | None" = None
    _current_model_name: str | None = None
    
    @classmethod
    def get_for_model(cls, model_name: str) -> "Upscaler":
        """指定モデル用のUpscalerインスタンス取得"""
        if cls._current_model_name != model_name:
            logger.info(f"モデル切り替え: {cls._current_model_name} → {model_name}")
            cls._cleanup_current()
            cls._global_instance = cls(model_name)
            cls._current_model_name = model_name
        return cls._global_instance
    
    @classmethod
    def force_cleanup(cls):
        """アノテーション処理前の強制解放"""
        if cls._global_instance:
            logger.info(f"VRAM解放のためUpscaler強制破棄: {cls._current_model_name}")
            cls._cleanup_current()
    
    @classmethod
    def _cleanup_current(cls):
        """現在のインスタンス解放"""
        if cls._global_instance:
            cls._global_instance._cleanup()
            cls._global_instance = None
            cls._current_model_name = None
            torch.cuda.empty_cache()  # GPU VRAM解放
```

#### Resource Management Features
- **Model Detection**: `models/upscalers/` ディレクトリ自動検出
- **VRAM Management**: `torch.cuda.empty_cache()` による明示的GPU メモリ解放
- **Error Handling**: モデル読み込み失敗時の適切なフォールバック
- **Logging**: モデル切り替えとリソース解放の詳細ログ

### Integration Points

#### Batch Processing Integration
```python
# batch_processor.py での使用例
def process_directory_batch(..., upscaler_name: str | None = None):
    """効率的なバッチ処理（共有Upscalerインスタンス使用）"""
    
    shared_upscaler = None
    if upscaler_name:
        shared_upscaler = Upscaler.get_for_model(upscaler_name)
        # ↑ バッチ全体で同一インスタンス使用
    
    for image_file in image_files:
        if shared_upscaler:
            # 既に読み込まれたモデルで高速処理
            result = shared_upscaler.upscale_image(image)
```

#### Annotation Service Integration
```python
# annotation_service.py での使用例
class AnnotationService:
    def start_annotation_batch(self, ...):
        """アノテーション処理開始（VRAM競合回避）"""
        
        # アノテーション処理前にUpscalerリソース強制解放
        Upscaler.force_cleanup()
        logger.info("アノテーション処理のためVRAM解放完了")
        
        # アノテーション実行（VRAMフル活用可能）
        results = self._execute_annotations(...)
```

### Performance Characteristics

#### Memory Usage
- **GPU VRAM**: 1モデル分のみ保持（4-6GB）
- **System RAM**: モデルファイルサイズ（64MB程度）
- **Peak Usage**: アップスケール実行時のみ

#### Processing Efficiency
- **Model Reuse**: 同一モデル連続使用時は瞬時実行（0.1秒/画像）
- **Model Switch**: モデル切り替え時のみ遅延（8-10秒）
- **Batch Optimization**: 1000枚処理で99.9%の読み込み時間削減

#### VRAM Conflict Resolution
- **Problem**: アップスケーラー（6GB）+ アノテーション（4GB）= 10GB → OOM
- **Solution**: アノテーション前強制解放 → VRAM競合回避
- **Trade-off**: アノテーション後初回アップスケールで再読み込み遅延

### Implementation Timeline

#### Phase 1: Core Module Implementation
1. `upscaler.py` - Upscalerクラス単体実装
2. `auto_crop.py` - AutoCropクラス分離
3. `processing_manager.py` - 統合処理マネージャー

#### Phase 2: Resource Management Integration  
1. グローバルインスタンス管理実装
2. 強制クリーンアップ機能実装
3. モデル切り替え検知機能実装

#### Phase 3: Service Integration
1. batch_processor.py との統合
2. annotation_service.py との統合
3. VRAM競合回避機能の実装

### Decision Rationale

#### Rejected Alternative: Memory Caching
**検討案**: メインメモリでstate_dictキャッシュ
**却下理由**:
- 実装複雑性増加（2-3日の工数）
- 効果限定的（8秒→6秒、25%改善のみ）
- メンテナンス負債（キャッシュ管理、エラーハンドリング）
- ROI不適合（小さなモデルサイズに対して過剰な最適化）

#### Selected Solution: Simple Force Cleanup
**選択理由**:
- 実装シンプル（数行のコード）
- 高い信頼性（問題が起きにくい）
- 保守性優秀（理解しやすいロジック）
- 十分な効果（VRAM競合完全回避）

This technical specification provides comprehensive guidance for developing, maintaining, and deploying the LoRAIro application with focus on performance, security, and maintainability.