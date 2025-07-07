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
AnnotationService → AnnotationWorker → ai_annotator.py → image-annotator-lib
```

**Key Components**
- **AnnotationService** (`src/lorairo/services/annotation_service.py`): Business logic coordination
- **AnnotationWorker**: Threaded processing for UI responsiveness
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

**Implementation Requirements**
```python
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

This technical specification provides comprehensive guidance for developing, maintaining, and deploying the LoRAIro application with focus on performance, security, and maintainability.