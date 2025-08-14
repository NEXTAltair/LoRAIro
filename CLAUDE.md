# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Instructions
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## Development Commands

### Environment Setup

#### Cross-Platform Environment Management

This project supports Windows/Linux environments with independent virtual environments to manage platform-specific dependencies properly.

## Project Architecture

### Core Components

**Main Application Flow:**
- Entry point: `src/lorairo/main.py` - Initializes Qt application and main window
- Main Window: `src/lorairo/gui/window/main_window.py` - Primary GUI orchestrator
- Configuration: `config/lorairo.toml` - Application settings and parameters

**Data Layer:**
- Database: SQLite-based image metadata storage with SQLAlchemy ORM
- Schema: `src/lorairo/database/schema.py` - Database models
- Repository: `src/lorairo/database/db_repository.py` - Data access layer
- Manager: `src/lorairo/database/db_manager.py` - High-level database operations
- Core: `src/lorairo/database/db_core.py` - Database initialization and core utilities

**Service Layer:**
- `ImageProcessingService` (`src/lorairo/services/image_processing_service.py`) - Image processing workflows
- `ConfigurationService` (`src/lorairo/services/configuration_service.py`) - Application configuration
- `AnnotationService` (`src/lorairo/services/annotation_service.py`) - AI annotation coordination (deprecated)

**GUI Services & Workers:**
- `WorkerService` (`src/lorairo/gui/services/worker_service.py`) - Qt-based asynchronous task coordination
- `WorkerManager` (`src/lorairo/gui/workers/manager.py`) - QThreadPool-based worker execution
- Specialized workers in `src/lorairo/gui/workers/`: DatabaseRegistration, Annotation, Search, Thumbnail

**AI Integration (Local Packages):**
- **image-annotator-lib**: Multi-provider AI annotation (OpenAI, Anthropic, Google, Local models)
  - Integration: `src/lorairo/annotations/ai_annotator.py`
  - Functions: `get_available_annotator_models()`, `call_annotate_library()`
  - Returns: `PHashAnnotationResults` with structured data
- **genai-tag-db-tools**: Tag database management and cleaning utilities
  - Integration: `src/lorairo/annotations/cleanup_txt.py`
  - Database: Tag taxonomy (tags_v3.db)
  - Function: `initialize_tag_searcher()` for tag normalization

**GUI Architecture:**
- Built with PySide6 (Qt for Python)
- **Main Window**: `src/lorairo/gui/window/main_workspace_window.py` - Workflow-centered 3-panel design
- Designer files in `src/lorairo/gui/designer/` (auto-generated UI code)
- Widget implementations in `src/lorairo/gui/widgets/`
- State management in `src/lorairo/gui/state/` (DatasetStateManager)
- Asynchronous workers in `src/lorairo/gui/workers/` (Qt QRunnable/QThreadPool)

**Storage:**
- `FileSystemManager` (`src/lorairo/storage/file_system.py`) - File operations and directory management
- **Project Structure**: `lorairo_data/project_name_YYYYMMDD_NNN/` format with support for Unicode project names
- **Database Design**: One SQLite database per project for data isolation and extraction workflows
- **Directory Layout**: Each project contains `image_database.db` and `image_dataset/` with date-based subdirectories
- Images stored with associated .txt/.caption files for annotations in `image_dataset/original_images/`
- Processed images stored in resolution-specific directories (`image_dataset/1024/`, etc.)

**Quality Assessment:**
- Scoring modules in `src/lorairo/score_module/` provide image quality assessment
- CLIP aesthetic scoring, MUSIQ quality metrics, reward function scoring

### Key Design Patterns

**Repository Pattern:** Database access abstracted through repository layer
**Service Layer:** Business logic separated from GUI and data access
**Worker Pattern:** Asynchronous operations using Qt QRunnable/QThreadPool
**State Management:** Centralized state with DatasetStateManager
**Dependency Injection:** Services injected into GUI components
**Configuration-Driven:** Settings externalized to TOML configuration files

### Local Dependencies
This project uses two local submodules managed via uv.sources:
- `local_packages/genai-tag-db-tools` - Tag database management utilities
  - **Integration**: Direct Python import in `src/lorairo/annotations/cleanup_txt.py`
  - **Function**: `initialize_tag_searcher()` for tag cleaning and normalization
  - **Database**: Contains tags_v3.db with tag taxonomy
  - **Usage**: Database path resolved via `src/lorairo/database/db_core.py`
- `local_packages/image-annotator-lib` - Core AI annotation functionality
  - **Integration**: Direct Python import in `src/lorairo/annotations/ai_annotator.py`
  - **Functions**: `annotate()`, `list_available_annotators()`
  - **Data Types**: `PHashAnnotationResults` for structured results
  - **Providers**: OpenAI, Anthropic, Google, Local ML models

The local packages are installed in editable mode and automatically linked during `uv sync`.

**Current Implementation Status:**
- ✅ **Active**: Modern implementation in `src/lorairo/` directory
- ⚠️ **Legacy**: Old implementation in `src/` (pending cleanup)
- ✅ **Integrated**: Both local packages fully operational
- 🔄 **Migration**: Transitioning from legacy to modern architecture

### Important File Types
- `.caption` files - AI-generated image captions
- `.txt` files - Tag annotations for training
- `.toml` files - Configuration (main: `config/lorairo.toml`)
- `.ui` files - Qt Designer interface definitions

### Development Notes

**Code Style:**
- Uses Ruff for linting and formatting (line length: 108)
- Type hints required for all functions
- Modern Python types preferred (list/dict over typing.List/Dict)
- Path operations use pathlib, not os

**Testing:**
- pytest-based with coverage reporting (minimum 75%)
- Test resources in `tests/resources/`
- Separate unit, integration, and GUI test categories
- GUI tests run headless in Linux/container using QT_QPA_PLATFORM=offscreen
- Windows environment supports native GUI windows
- Linux environment includes EGL libraries for Qt offscreen rendering

**Database:**
- Uses Alembic for migrations
- SQLite for local development
- Schema evolution tracked in `src/lorairo/database/migrations/`

**Logging:**
- Loguru for structured logging
- Configuration in `config/lorairo.toml` [log] section
- Log level configurable (DEBUG, INFO, WARNING, ERROR)
- Logs stored in `logs/` directory

**AI Models:**
- Supports GPT-4, Claude, Gemini for annotation
- Model selection configurable via settings
- Batch processing support for large datasets
- Quality scoring with aesthetic and technical metrics

**Project Structure:** `lorairo_data/project_name_YYYYMMDD_NNN/` with SQLite database and organized image directories. Supports Unicode project names and subset extraction workflows.

## Development Workflow

### Command-Based Development Process

**Standard workflow pattern:**
1. **Analysis**: `/check-existing` for understanding current functionality
2. **Planning**: `/plan` for strategic design and architecture  
3. **Implementation**: `/implement` for code development
4. **Validation**: `/test` for quality assurance and testing

### MCP Integration (cipher+serena)

**Operation Selection:**
- **Fast operations** (1-3s): Direct serena for search, memory, basic editing
- **Complex analysis** (10-30s): Cipher aggregator for multi-tool integration
- **Fallback**: Direct operations when cipher timeouts occur

**Quality Standards:**
- Follow `.cursor/rules/` development guidelines
- Use Ruff formatting (line length: 108)
- Maintain 75%+ test coverage
- Apply modern Python types (list/dict over typing.List/Dict)

## Problem-Solving Approach

**Solution Analysis:**
1. **Enumerate approaches** - List multiple solution methods
2. **Evaluate trade-offs** - Assess complexity, maintainability, performance
3. **Select optimal solution** - Balance effectiveness and sustainability
4. **Document decisions** - Record rationale for choices

**Reference documents:** `docs/architecture.md` for design principles, `docs/technical.md` for implementation patterns.

## Troubleshooting

### Environment Issues
- **Test Discovery**: Ensure no conflicting `.venv` directories in local packages, verify `uv sync --dev`
- **Cross-Platform**: Use `.venv_linux` for development/testing, `.venv_windows` for execution
- **Setup**: Run `./scripts/setup.sh` for automatic OS detection

### MCP Issues
- **Cipher timeout**: Break operations into stages, fallback to direct serena
- **Connection errors**: Use direct serena operations + WebSearch
- **Performance**: Direct serena (1-3s) for simple ops, cipher (10-30s) for complex analysis

## Quick Reference

### Commands
- **[/check-existing](.claude/commands/check-existing.md)**: Analyze existing functionality
- **[/plan](.claude/commands/plan.md)**: Strategic planning and design
- **[/implement](.claude/commands/implement.md)**: Code development
- **[/test](.claude/commands/test.md)**: Testing and validation

### Agents (automatically used by commands)
- **[investigation](.claude/agents/investigation.md)**: Codebase analysis
- **[library-research](.claude/agents/library-research.md)**: Technology research  
- **[solutions](.claude/agents/solutions.md)**: Multi-approach problem solving
- **[code-formatter](.claude/agents/code-formatter.md)**: Code quality

### Documentation
- **[docs/architecture.md](docs/architecture.md)**: System design principles
- **[docs/technical.md](docs/technical.md)**: Implementation specifications

### Configuration

**Basic config/lorairo.toml structure:**
```toml
[api]
openai_key = ""
claude_key = ""
google_key = ""

[directories]
database_base_dir = "lorairo_data"

[log]
level = "INFO"
```

