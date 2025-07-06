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

```bash
# Automatic OS detection setup (recommended)
./scripts/setup.sh

# Manual environment specification
UV_PROJECT_ENVIRONMENT=.venv_linux uv sync --dev     # Linux
$env:UV_PROJECT_ENVIRONMENT=".venv_windows"; uv sync --dev  # Windows

# Traditional single environment
uv sync --dev

# Add new dependencies
uv add package-name

# Add development dependencies
uv add --dev package-name
```

### Running the Application

#### Cross-Platform Execution

```bash
# Windows Environment
$env:UV_PROJECT_ENVIRONMENT = ".venv_windows"; uv run lorairo

# Linux Environment  
UV_PROJECT_ENVIRONMENT=.venv_linux uv run lorairo

# Using Makefile (all platforms)
make run-gui

# Traditional single environment
uv run lorairo

# Alternative module execution
uv run python -m lorairo.main
```

### Development Tools
```bash
# Run tests
pytest

# Run specific test categories
pytest -m unit        # Unit tests only
pytest -m integration # Integration tests only
pytest -m gui         # GUI tests only (headless in dev container)

# For GUI tests in cross-platform environments (headless in Linux/container)

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
- Core: `src/lorairo/database/db_core.py` - Database initialization and core utilities

**Service Layer:**
- `ImageProcessingService` (`src/lorairo/services/image_processing_service.py`) - Image processing workflows
- `ConfigurationService` (`src/lorairo/services/configuration_service.py`) - Application configuration
- `AnnotationService` (`src/lorairo/services/annotation_service.py`) - AI annotation coordination

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
- Designer files in `src/lorairo/gui/designer/` (auto-generated UI code)
- Widget implementations in `src/lorairo/gui/widgets/`
- Window controllers in `src/lorairo/gui/window/`

**Storage:**
- `FileSystemManager` (`src/lorairo/storage/file_system.py`) - File operations and directory management
- Images stored with associated .txt/.caption files for annotations
- Database tracks image metadata, annotations, and processing status

**Quality Assessment:**
- Scoring modules in `src/lorairo/score_module/` provide image quality assessment
- CLIP aesthetic scoring, MUSIQ quality metrics, reward function scoring

### Key Design Patterns

**Repository Pattern:** Database access abstracted through repository layer
**Service Layer:** Business logic separated from GUI and data access
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
- `.cursor/rules/module_rules/module-annotator.mdc` - AI annotation module guidelines
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

## Problem-Solving Methodology

**Multiple Solution Analysis:**
Before implementing any solution, always:

1. **Enumerate All Possible Approaches** - List every conceivable solution method
2. **Evaluate Each Option** - Assess pros/cons, complexity, maintainability, and trade-offs
3. **Select Optimal Solution** - Choose the approach that best balances effectiveness, simplicity, and long-term sustainability
4. **Document Decision Rationale** - Record why the chosen solution was selected over alternatives

**Example Solution Categories:**
- **Direct Implementation** - Modify target code directly
- **Abstraction Layer** - Add intermediate interfaces/wrappers
- **Configuration Changes** - Adjust settings/parameters
- **Test Modifications** - Update test expectations/setup
- **Library/Tool Substitution** - Replace problematic dependencies
- **Architecture Refactoring** - Restructure component relationships
- **Mock/Stub Strategies** - Isolate external dependencies in tests

**Decision Criteria:**
- Maintenance burden and complexity
- Performance and resource impact
- Code readability and debugging ease
- Compatibility with existing architecture
- Risk of introducing new issues
- Time investment vs. benefit ratio

### Documentation References for Code Changes

**Before making changes, always reference:**
- `docs/architecture.md` - System architecture and component relationships
- `docs/product_requirement_docs.md` - Product requirements and user stories
- `docs/technical.md` - Technical specifications and implementation details
- `tasks/` directory - Active development tasks and plans

**When updating code, ensure documentation alignment:**
- Update architecture diagrams if component relationships change
- Modify technical specifications if implementation patterns change
- Update product requirements if functionality scope changes
- Keep task documentation current with development progress

## Troubleshooting



### Test Discovery Issues

If VS Code cannot discover tests in local packages:
- Ensure no conflicting `.venv` directories exist in local packages
- Check Python interpreter is set to appropriate environment (`.venv_linux/bin/python` or `.venv_windows/Scripts/python.exe`)
- Verify `uv sync --dev` has been run successfully

### Cross-Platform Development Environment

**Environment Isolation:**
- Windows environment: `.venv_windows` - Windows-specific dependencies and binaries
- Linux environment: `.venv_linux` - Linux-specific dependencies and binaries  
- Independent GUI operation support for both environments

**Development Workflow:**
```bash
# Setup using unified script (automatic OS detection)
./scripts/setup.sh

# Linux/Container environment - development and testing
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest

# Windows environment - execution and GUI verification
$env:UV_PROJECT_ENVIRONMENT = ".venv_windows"; uv run lorairo

# Unified execution using Makefile
make run-gui  # Automatically selects appropriate environment
```

**GUI Testing Notes:**
- Linux environment: Headless execution (pytest-qt + QT_QPA_PLATFORM=offscreen)
- Windows environment: Native GUI window display
- Cross-platform test compatibility guaranteed