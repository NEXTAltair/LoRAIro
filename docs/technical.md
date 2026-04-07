# LoRAIro Technical Specification

## Technology Stack

### Core Technologies

**Python 3.12+**: Primary development language with modern type hints and AI/ML ecosystem

**PySide6**: Qt for Python GUI framework with cross-platform support

**Database**: SQLite with SQLAlchemy ORM and Alembic migrations

**Package Management**: uv for dependency resolution and virtual environment management

### AI Integration

**Supported Providers**: OpenAI GPT-4, Anthropic Claude, Google Gemini, Local ML models

**Key Integration**:
- **WorkerService** → **AnnotationWorker** → **image-annotator-lib**
- Multi-provider unified interface via local package integration
- Local packages: image-annotator-lib, genai-tag-db-tools

See `docs/integrations.md` for detailed integration patterns.

### Development Tools

**Code Quality**: Ruff (linter/formatter), mypy (type checking)

**Testing**: pytest with coverage analysis and Qt GUI testing

**Logging**: Loguru for structured logging with configuration in `src/lorairo/utils/log.py`

## Development Tooling

**Development Agents**: OpenClaw (long-term memory via Notion)

**Documentation**: `docs/decisions/` for design decisions, `docs/plans/` for planning records
**Long-Term Memory**: Notion LTM via OpenClaw

**Development-only tools that enhance the coding workflow.**

## Development Environment

### System Requirements
- **OS**: Windows 10/11, macOS 10.15+, Linux (Ubuntu 20.04+)
- **Hardware**: 8GB RAM minimum (16GB recommended), 10GB storage, optional GPU for local ML models
- **Python**: 3.12 or higher with virtual environment support

### Setup
```bash
git clone --recurse-submodules https://github.com/user/LoRAIro.git
uv sync --dev
```

### Configuration
- **Main Config**: `config/lorairo.toml` - Application settings, API keys, logging
- **Environment Variables**: API keys for OpenAI, Anthropic, Google providers

## Database Design

### Schema Architecture

**Core Tables**: Images, Annotations, Quality Scores with appropriate foreign key relationships

**Key Features**:
- SQLite with SQLAlchemy ORM and Alembic migrations
- UTC timezone standardization for consistent datetime handling
- Performance indexes for optimal query execution
- CASCADE deletion for referential integrity

**Migration Management**: Alembic with auto-generated migrations and rollback support

See `docs/decisions/0002-database-schema-decisions.md` for design decisions (no UNIQUE constraints, no FK to external tag DB).

## Code Architecture

### Design Patterns

**Key Patterns**:
- **Repository Pattern**: Data access abstraction with SQLAlchemy implementation
- **Service Layer Pattern**: 2-tier architecture (Business Logic + GUI Services)
- **Factory Pattern**: AI provider creation and management
- **Dependency Injection**: Service container with layered architecture

See `docs/decisions/` for rationale behind each pattern choice.

### Error Handling Strategy

**Custom Exception Hierarchy**: LoRAIroException base with specialized error types (Configuration, Database, ImageProcessing, AIProvider)

**Error Handling Patterns**: Context managers for consistent error handling and recovery

### Type System

**Type Definitions**: TypedDict for structured data (ImageMetadata, AnnotationResult, QualityScore)

**Protocol Definitions**: Runtime-checkable protocols for interface compliance

## Performance Optimization

**Key Features**:
- **Memory Management**: Image processing optimization with resource monitoring
- **Database Performance**: Connection pooling and query optimization
- **Batch Processing**: 100-image batches with 5-minute target for 1000 images
- **Asynchronous Processing**: Background task management with QThreadPool

See `docs/decisions/0010-torch-import-design.md` for ML library lazy import decisions.

## Security Considerations

**Key Features**:
- **API Key Management**: Environment variable storage with masked logging
- **Input Validation**: File path validation and image content verification
- **Configuration Security**: Plain-text storage for personal development use

See `.claude/rules/security.md` for security guidelines.

## Deployment Considerations

**Build and Distribution**: Application packaging with pyproject.toml and environment configuration

**Environment Setup**: Production configuration with resource limits and logging
