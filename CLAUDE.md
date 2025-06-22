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

# Run specific test categories
pytest -m unit        # Unit tests only
pytest -m integration # Integration tests only
pytest -m gui         # GUI tests only

# Run linting and formatting
ruff check
ruff format

# Run type checking
mypy src/

# Run database migrations
alembic upgrade head

# Generate new migration
alembic revision --autogenerate -m "description"

# Run single test file
pytest tests/path/to/test_file.py

# Check test coverage
pytest --cov=src --cov-report=html
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
This project uses two local submodules managed via uv.sources:
- `local_packages/genai-tag-db-tools` - Tag database management utilities (entry: `tag-db`)
- `local_packages/image-annotator-lib` - Core image annotation functionality

The local packages are installed in editable mode and automatically linked during `uv sync`.

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
- Logs stored in `logs/` directory

**AI Models:**
- Supports GPT-4, Claude, Gemini for annotation
- Model selection configurable via settings
- Batch processing support for large datasets
- Quality scoring with aesthetic and technical metrics

## Rule Files and Documentation References

### .cursor Directory Structure
Claude Code should reference these files for development guidance:

**Core Development Rules:**
- `.cursor/rules/rules.mdc` - Master development workflow and architectural rules
- `.cursor/rules/coding-rules.mdc` - Coding standards, type hints, error handling, documentation requirements
- `.cursor/rules/memory.mdc` - Memory management and file-based documentation system structure

**Process-Specific Rules:**
- `.cursor/rules/plan.mdc` - Planning guidelines and templates for feature development
- `.cursor/rules/implement.mdc` - Implementation patterns and code quality standards
- `.cursor/rules/debug.mdc` - Debugging workflows and troubleshooting procedures

**Documentation and Testing:**
- `.cursor/rules/doc-lookup-rules.mdc` - Documentation reference hierarchy and update requirements
- `.cursor/rules/test_rules/testing-rules.mdc` - Test strategy and pytest configuration
- `.cursor/rules/test_rules/pytest-bdd-feature-rules.mdc` - BDD feature file guidelines
- `.cursor/rules/test_rules/pytest-bdd-step-def-rules.mdc` - BDD step definition patterns

**Module-Specific Rules:**
- `.cursor/rules/module_rules/module-annotater.mdc` - AI annotation module guidelines
- `.cursor/rules/module_rules/module-database-rules.mdc` - Database operation patterns
- `.cursor/rules/encapsulation-rules.mdc` - Encapsulation and design patterns

### .roo Directory Structure
The .roo directory contains aliases that reference .cursor rules and additional configuration:

**Rule References:**
- `.roo/rules/rules.mdc` → Reference `.cursor/rules/rules.mdc`
- `.roo/rules/memory.mdc` → Reference `.cursor/rules/memory.mdc`
- `.roo/rules-architect/plan.mdc` → Reference `.cursor/rules/plan.mdc`
- `.roo/rules-code/implement.mdc` → Reference `.cursor/rules/implement.mdc`
- `.roo/rules-debug/debug.mdc` → Reference `.cursor/rules/debug.mdc`

**Configuration:**
- `.roo/mcp.json` - MCP server configuration (not tracked in git)
- `.roo/mcp.json.example` - Template for MCP configuration
- `.roo/README.md` - Setup instructions for GitHub MCP server

### Reference Guidelines for Claude Code

**When Planning (PLAN/Architect Mode):**
1. Read `.cursor/rules/memory.mdc` for memory bank structure
2. Reference `.cursor/rules/plan.mdc` for planning guidelines
3. Check `.cursor/rules/doc-lookup-rules.mdc` for documentation hierarchy
4. Review existing documentation in `docs/` and `tasks/` directories

**When Implementing (ACT/Code Mode):**
1. Follow `.cursor/rules/coding-rules.mdc` for code quality standards
2. Use `.cursor/rules/implement.mdc` for implementation patterns
3. Reference module-specific rules for relevant components
4. Update memory bank files per `.cursor/rules/memory.mdc`

**When Debugging:**
1. Follow procedures in `.cursor/rules/debug.mdc`
2. Check for error patterns and solutions
3. Document fixes for future reference

**Documentation Updates:**
1. Always reference `.cursor/rules/doc-lookup-rules.mdc` for documentation structure
2. Update related documentation when making code changes
3. Maintain consistency across documentation files
4. Follow the hierarchical documentation reference system

**Testing:**
1. Use guidelines from `.cursor/rules/test_rules/testing-rules.mdc`
2. Follow BDD patterns for feature tests
3. Ensure coverage requirements are met

**Key Principles:**
- Reference rules before starting any development task
- Update documentation alongside code changes
- Follow established patterns and conventions
- Use the memory bank system for context retention
- Always check for existing solutions in error documentation