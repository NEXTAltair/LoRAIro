# LoRAIro Technical Specification

**For detailed technical implementation:**
- **Technology Stack**: `mcp__serena__read_memory technical-stack`
- **Implementation Details**: `mcp__serena__read_memory current-project-status`

## Technology Stack

### Core Technologies

**Python 3.12+**: Primary development language with modern type hints and AI/ML ecosystem

**PySide6**: Qt for Python GUI framework with cross-platform support

**Database**: SQLite with SQLAlchemy ORM and Alembic migrations

**Package Management**: uv for dependency resolution and virtual environment management

**Current implementation details maintained in Serena memory.**

### AI Integration

**For detailed AI integration:**
- **AI Architecture**: `mcp__serena__read_memory ai-integration`
- **Provider Configuration**: `mcp__serena__read_memory current-project-status`

**Supported Providers**: OpenAI GPT-4, Anthropic Claude, Google Gemini, Local ML models

**Key Integration**: 
- **WorkerService** → **AnnotationWorker** → **image-annotator-lib**
- Multi-provider unified interface via local package integration
- Local packages: image-annotator-lib, genai-tag-db-tools

**Current implementation details maintained in Serena memory.**

### Development Tools

**Development Tools Details**: `mcp__serena__read_memory development-tools`

**Code Quality**: Ruff (linter/formatter), mypy (type checking)

**Testing**: pytest with coverage analysis and Qt GUI testing

**Logging**: Loguru for structured logging with configuration in `src/lorairo/utils/log.py`

**Current implementation details maintained in Serena memory.**

## MCP Integration and Agent Roles

**MCP Integration Details**: `mcp__serena__read_memory mcp-integration`

**Development Agents**: cipher (orchestrator), serena (codebase/memory management)

**Working Memory**: `.serena/memories/` for development knowledge management

**Development-only tools that enhance the coding workflow.**

## Development Environment

**Environment Setup Details**: `mcp__serena__read_memory development-environment`

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

**Current implementation details maintained in Serena memory.**

## Database Design

**Database Design Details**: `mcp__serena__read_memory database-design`

### Schema Architecture

**Core Tables**: Images, Annotations, Quality Scores with appropriate foreign key relationships

**Key Features**:
- SQLite with SQLAlchemy ORM and Alembic migrations
- UTC timezone standardization for consistent datetime handling
- Performance indexes for optimal query execution
- CASCADE deletion for referential integrity

**Migration Management**: Alembic with auto-generated migrations and rollback support

**Current implementation details maintained in Serena memory.**

## Code Architecture

**Code Architecture Details**: `mcp__serena__read_memory code-architecture`

### Design Patterns

**Key Patterns**:
- **Repository Pattern**: Data access abstraction with SQLAlchemy implementation
- **Service Layer Pattern**: 2-tier architecture (Business Logic + GUI Services)
- **Factory Pattern**: AI provider creation and management
- **Dependency Injection**: Service container with layered architecture

### Error Handling Strategy

**Custom Exception Hierarchy**: LoRAIroException base with specialized error types (Configuration, Database, ImageProcessing, AIProvider)

**Error Handling Patterns**: Context managers for consistent error handling and recovery

### Type System

**Type Definitions**: TypedDict for structured data (ImageMetadata, AnnotationResult, QualityScore)

**Protocol Definitions**: Runtime-checkable protocols for interface compliance

**Current implementation details maintained in Serena memory.**
## Performance Optimization

**Performance Details**: `mcp__serena__read_memory performance-optimization`

**Key Features**:
- **Memory Management**: Image processing optimization with resource monitoring
- **Database Performance**: Connection pooling and query optimization
- **Batch Processing**: 100-image batches with 5-minute target for 1000 images
- **Asynchronous Processing**: Background task management with QThreadPool

**Current implementation details maintained in Serena memory.**

## Security Considerations

**Security Details**: `mcp__serena__read_memory security-considerations`

**Key Features**:
- **API Key Management**: Environment variable storage with masked logging
- **Input Validation**: File path validation and image content verification
- **Configuration Security**: Plain-text storage for personal development use

**Current implementation details maintained in Serena memory.**

## Deployment Considerations

**Deployment Details**: `mcp__serena__read_memory deployment-considerations`

**Build and Distribution**: Application packaging with pyproject.toml and environment configuration

**Environment Setup**: Production configuration with resource limits and logging

**Current implementation details maintained in Serena memory.**

## Implementation Details

**For comprehensive technical implementation information:**
- **Architecture Patterns**: `mcp__serena__read_memory architecture-patterns`
- **Performance Specifications**: `mcp__serena__read_memory performance-specs`  
- **Security Implementation**: `mcp__serena__read_memory security-implementation`
- **Database Schemas**: `mcp__serena__read_memory database-schemas`
- **Configuration Management**: `mcp__serena__read_memory configuration-management`

**All detailed technical information is maintained in Serena memory for current reference.**

This simplified technical specification provides essential implementation guidance while maintaining comprehensive details in dynamic memory storage.
