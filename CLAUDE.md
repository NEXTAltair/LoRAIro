# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install all dependencies including dev group and local packages
uv sync --dev

# Add new dependencies
uv add package-name

# Add development dependencies
uv add --dev package-name
```

### Running the Application
```bash
# Main command
lorairo

# Alternative module execution
python -m lorairo.main
```

### Development Tools
```bash
# Run tests
pytest

# Run linting and formatting
ruff check
ruff format

# Run type checking
mypy src/

# Run database migrations
alembic upgrade head

# Generate new migration
alembic revision --autogenerate -m "description"
```

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

**Service Layer:**
- `ImageProcessingService` - Handles image resizing, format conversion, cropping
- `ConfigurationService` - Manages application configuration
- `AnnotationService` - Coordinates AI-powered image annotation

**AI Integration:**
- Supports multiple AI providers: GPT-4, Claude, Gemini via respective APIs
- Annotation modules in `src/lorairo/annotations/` handle caption and tag generation
- Scoring modules in `src/lorairo/score_module/` provide image quality assessment

**GUI Architecture:**
- Built with PySide6 (Qt for Python)
- Designer files in `src/lorairo/gui/designer/` (auto-generated UI code)
- Widget implementations in `src/lorairo/gui/widgets/`
- Window controllers in `src/lorairo/gui/window/`

**Storage:**
- `FileSystemManager` - Handles file operations and directory management
- Images stored with associated .txt files for captions/tags
- Database tracks image metadata, annotations, and processing status

### Key Design Patterns

**Repository Pattern:** Database access abstracted through repository layer
**Service Layer:** Business logic separated from GUI and data access
**Dependency Injection:** Services injected into GUI components
**Configuration-Driven:** Settings externalized to TOML configuration files

### Local Dependencies
This project uses two local submodules:
- `local_packages/genai-tag-db-tools` - Tag database management utilities
- `local_packages/image-annotator-lib` - Core image annotation functionality

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

**Database:**
- Uses Alembic for migrations
- SQLite for local development
- Schema evolution tracked in `src/lorairo/database/migrations/`

**Logging:**
- Loguru for structured logging
- Configuration in `config/lorairo.toml` [log] section
- Log level configurable (DEBUG, INFO, WARNING, ERROR)