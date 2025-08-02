# LoRAIro Architecture and Code Structure

## Project Structure Overview

### Source Code Organization
```
src/lorairo/
├── main.py                    # Application entry point
├── annotations/               # AI annotation logic
├── database/                  # Data persistence layer
│   ├── schema.py             # SQLAlchemy models
│   ├── db_repository.py      # Data access layer
│   ├── db_manager.py         # High-level operations
│   ├── db_core.py            # Core database utilities
│   └── migrations/           # Alembic migration scripts
├── editor/                   # Image processing
├── gui/                      # User interface
│   ├── controllers/          # Business logic controllers
│   ├── services/             # GUI service layer
│   ├── state/               # State management
│   ├── widgets/             # Custom UI components
│   ├── window/              # Main application windows
│   └── workers/             # Asynchronous task workers
├── services/                # Business logic layer
├── storage/                 # File system operations
└── utils/                   # Shared utilities
```

### Key Architectural Components

#### Data Layer
- **Database Core** (`db_core.py`): SQLite connection management, path resolution
- **Schema** (`schema.py`): SQLAlchemy ORM models for images, annotations, metadata
- **Repository** (`db_repository.py`): Data access patterns and query abstraction
- **Manager** (`db_manager.py`): High-level database operations and transactions

#### Service Layer
- **ImageProcessingService**: Coordinates image transformation workflows
- **ConfigurationService**: Application settings and user preferences
- **AnnotationService**: AI model coordination and batch processing
- **WorkerService**: Qt-based asynchronous task management

#### GUI Layer
- **MainWorkspaceWindow**: Primary 3-panel workflow interface
- **DatasetStateManager**: Centralized application state
- **Workers**: QRunnable-based background task execution
- **Widgets**: Modular UI components (thumbnails, filters, annotations)

#### Integration Layer
- **AI Annotation**: `image-annotator-lib` integration for multi-provider AI
- **Tag Management**: `genai-tag-db-tools` integration for tag normalization

## Design Patterns

### Repository Pattern
- Abstracts database access through well-defined interfaces
- Enables testing with mock repositories
- Centralizes query logic and transaction management

### Service Layer Pattern
- Separates business logic from GUI and data access
- Provides clean APIs for complex operations
- Enables dependency injection and testing

### Worker Pattern (Qt-based)
- QRunnable/QThreadPool for background processing
- Progress reporting and cancellation support
- GUI responsiveness during long operations

### State Management
- Centralized state with DatasetStateManager
- Event-driven updates across GUI components
- Immutable state transitions where possible

## Project Directory Structure

### Data Storage Pattern
```
lorairo_data/
├── project_name_YYYYMMDD_NNN/     # Auto-generated project directories
│   ├── image_database.db          # SQLite database with metadata
│   └── image_dataset/
│       ├── original_images/        # Source images with annotations
│       │   └── YYYY/MM/DD/source_dir/  # Date-based organization
│       ├── 1024/                   # Processed images by resolution
│       └── batch_request_jsonl/    # OpenAI Batch API files
```

### Configuration Structure
- **Main Config**: `config/lorairo.toml` (application settings)
- **Local Packages**: Independent configuration for submodules
- **User Settings**: GUI preferences and workflow state

## Local Package Integration

### genai-tag-db-tools
- **Purpose**: Tag database management and normalization
- **Integration**: Direct Python import in `cleanup_txt.py`
- **Database**: Pre-built tag taxonomy (tags_v3.db)
- **Function**: `initialize_tag_searcher()` for tag cleaning

### image-annotator-lib  
- **Purpose**: Multi-provider AI annotation (OpenAI, Anthropic, Google, Local)
- **Integration**: Direct Python import in `ai_annotator.py`
- **API**: `annotate()`, `list_available_annotators()`
- **Output**: Structured `PHashAnnotationResults`

## Cross-Platform Support

### Environment Management
- **Linux Environment**: `.venv_linux` for development/testing
- **Windows Environment**: `.venv_windows` for GUI execution
- **Independent Dependencies**: Platform-specific binary management

### GUI Compatibility
- **Linux**: Headless execution (QT_QPA_PLATFORM=offscreen)
- **Windows**: Native GUI window display
- **Container**: X11 forwarding support for remote GUI

## Memory and Performance

### Database Design
- **SQLite with WAL mode**: Concurrent access support
- **Strategic indexing**: Optimized for common query patterns
- **Project isolation**: One database per project for data integrity

### Image Processing
- **Streaming processing**: Memory-efficient handling of large datasets
- **Background workers**: Non-blocking GUI operations
- **Caching strategies**: Thumbnail and metadata caching

### AI Integration
- **Batch processing**: Efficient API usage patterns
- **Model management**: Local model caching and memory optimization
- **Provider abstraction**: Unified interface across different AI services