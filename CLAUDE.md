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

**Project Directory Structure:**
```
lorairo_data/
├── main_dataset_20250707_001/          # Main project (English name)
│   ├── image_database.db               # SQLite database with all metadata
│   └── image_dataset/
│       ├── original_images/
│       │   └── 2024/10/08/source_dir/  # Date-based organization
│       ├── 1024/                       # Target resolution directories
│       │   └── 2024/10/08/source_dir/
│       └── batch_request_jsonl/        # OpenAI Batch API files
├── 猫画像_20250707_002/                # Japanese project name
│   ├── image_database.db
│   └── image_dataset/
└── extracted_nsfw_20250708_001/        # Extracted subset project
    ├── image_database.db               # Contains only extracted data
    └── image_dataset/
```

**Use Cases:**
- **Unified Management**: All images in one main database for search and analysis
- **Project Extraction**: Create focused datasets (e.g., "NSFW only", "High quality only")
- **HuggingFace Publishing**: Export curated projects to HuggingFace datasets
- **Multi-language Support**: Unicode project names (Japanese, English, mixed)

## Development Workflow Integration

### 🎯 **Command-Based Development Process**

**Modern development workflow using specialized commands and agents:**

1. **Analysis Phase**: Use `/check-existing` for understanding current functionality
2. **Planning Phase**: Use `/plan` for strategic design and architecture
3. **Implementation Phase**: Use `/implement` for code development
4. **Validation Phase**: Use `/test` for quality assurance and testing

### 🧰 **Agent-Driven Task Execution**

**Specialized Agents Automatically Used by Commands:**

- **[`investigation`](.claude/agents/investigation.md)**: Codebase analysis and semantic search
  - Symbol-level search and dependency analysis
  - Architecture pattern identification
  - Code relationship mapping

- **[`library-research`](.claude/agents/library-research.md)**: Technology research and evaluation
  - Real-time documentation retrieval
  - Compatibility assessment
  - Implementation pattern research

- **[`solutions`](.claude/agents/solutions.md)**: Multi-approach problem solving
  - Solution strategy generation
  - Risk-benefit analysis
  - Implementation trade-off evaluation

- **[`code-formatter`](.claude/agents/code-formatter.md)**: Code quality maintenance
  - Ruff-based formatting and linting
  - Code structure optimization
  - Quality standard enforcement

### 📋 **Development Guidelines**

**Command Usage Pattern:**
- Use commands as primary development interface
- Commands automatically delegate to appropriate specialized agents
- Agents leverage MCP tools for efficient task execution
- Context and quality maintained through integrated workflow

**Quality Standards:**
- Follow `.cursor/rules/` guidelines for development standards
- Use command-integrated quality checks and validation
- Apply established coding conventions and patterns
- Execute comprehensive testing through `/test` command

**Modern Principles:**
- Command-based workflow for structured development
- Agent delegation for specialized task execution
- MCP tool optimization for maximum efficiency
- Integrated quality assurance and testing

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

### Modern Context Management

**Before making changes, always reference:**
- Start with `/check-existing` to understand current functionality
- Use `/plan` to analyze requirements and design approach
- Reference `docs/product_requirement_docs.md` for requirements
- Check `docs/architecture.md` for system design principles
- Review `docs/technical.md` for implementation patterns

**When updating code, ensure workflow adherence:**
- Follow the `/check-existing` → `/plan` → `/implement` → `/test` workflow
- Use agents automatically through commands for specialized tasks
- Maintain code quality through integrated formatting and validation
- Document significant changes and architectural decisions

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
uv run pytest

# Windows environment - execution and GUI verification
$env:UV_PROJECT_ENVIRONMENT = ".venv_windows"; uv run lorairo

# Unified execution using Makefile
make run-gui  # Automatically selects appropriate environment
```

**GUI Testing Notes:**
- Linux environment: Headless execution (pytest-qt + QT_QPA_PLATFORM=offscreen)
- Windows environment: Native GUI window display
- Cross-platform test compatibility guaranteed

## Command & Agent Development Workflow

### 🚀 **Command-Based Development Structure**

**Primary Development Commands:**
- 🔍 **[/check-existing](.claude/commands/check-existing.md)**: Analyze existing functionality and codebase
- 📋 **[/plan](.claude/commands/plan.md)**: Strategic planning and architecture design
- ⚙️ **[/implement](.claude/commands/implement.md)**: Code implementation and development
- 🧪 **[/test](.claude/commands/test.md)**: Testing and quality validation

### 🤖 **Specialized Agent Integration**

**Agents Automatically Used by Commands:**
- **[investigation](.claude/agents/investigation.md)**: Codebase analysis and semantic search
- **[library-research](.claude/agents/library-research.md)**: Technology research and evaluation
- **[solutions](.claude/agents/solutions.md)**: Multi-approach problem solving
- **[code-formatter](.claude/agents/code-formatter.md)**: Code quality and formatting

**Workflow Integration:**
- Commands leverage agents for specialized task execution
- MCP tools provide enhanced functionality (Serena, Context7)
- Automatic delegation ensures efficient development process
- Quality standards maintained through integrated validation

### 📚 **Development Guidelines**

**Development Workflow Pattern:**
1. **Analysis Phase**: Use `/check-existing` for existing functionality review
2. **Planning Phase**: Use `/plan` for strategic design and architecture
3. **Implementation Phase**: Use `/implement` for code development
4. **Validation Phase**: Use `/test` for quality assurance

**Command Usage:**
```bash
# Primary development workflow
/check-existing <functionality-to-analyze>
/plan <feature-or-improvement-description>
/implement <implementation-target>
/test <testing-focus>

# Agents are automatically invoked by commands
# investigation: Codebase analysis and semantic search
# library-research: Technology evaluation and documentation
# solutions: Multi-approach problem solving
# code-formatter: Code quality and formatting
```

### 🔗 **Quick Navigation**

| Purpose | Tool/Location | Description |
|---------|---------------|-------------|
| **Analysis** | [/check-existing](.claude/commands/check-existing.md) | Existing functionality review |
| **Planning** | [/plan](.claude/commands/plan.md) | Strategic design and implementation planning |
| **Implementation** | [/implement](.claude/commands/implement.md) | Code development and quality assurance |
| **Testing** | [/test](.claude/commands/test.md) | Validation and testing workflows |
| **Specialized Agents** | [.claude/agents/](/.claude/agents/) | Task-specific automation tools |
| **Requirements** | [docs/product_requirement_docs.md](docs/product_requirement_docs.md) | What to build |
| **Architecture** | [docs/architecture.md](docs/architecture.md) | How to build it |
| **Technical Details** | [docs/technical.md](docs/technical.md) | Implementation specifics |

### ⚙️ Configuration Quick Reference (2025/07/07)

**ConfigurationService Settings:**
```toml
[api]                    # Plain-text storage, log masking
openai_key = ""         # Auto-exclude models if missing
claude_key = ""
google_key = ""

[directories]           # Project structure design
database_dir = ""       # Empty = auto-generate project_name_YYYYMMDD_NNN
database_base_dir = "lorairo_data"  # Base directory for project creation
export_dir = ""         # Annotation results export (.txt/.caption)
batch_results_dir = ""  # OpenAI Batch API results (JSONL)

[huggingface]           # Plain-text storage
hf_username = ""
repo_name = ""
token = ""

[log]                   # Logging configuration
level = "INFO"
file_path = ""
```

**💡 Development Workflow:** Use `/check-existing` → `/plan` → `/implement` → `/test` for structured development. Commands automatically use specialized agents for optimal task execution and quality assurance.
