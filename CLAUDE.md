# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Instructions
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## Virtual Environment Rules (CRITICAL)

**ALWAYS use the project root virtual environment:**
- Virtual environment location: `/workspaces/LoRAIro/.venv`
- NEVER execute `uv run` from local package directories (`local_packages/*/`)
- ALWAYS execute `uv run` from project root (`/workspaces/LoRAIro/`)
- Local packages share the project root `.venv` (editable install via `uv sync`)

**Examples:**
```bash
# ✅ CORRECT: From project root
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/tests/

# ❌ WRONG: From local package directory (creates separate .venv)
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
uv run pytest tests/
```

## Development Commands

### Environment Setup

```bash
# Initial setup
uv sync                    # Install dependencies
uv sync --dev              # Install with dev dependencies
./scripts/setup.sh         # Run setup script (includes submodules)

# UI Generation (required after .ui file changes)
uv run python scripts/generate_ui.py
```

### Running the Application

```bash
uv run lorairo            # Start GUI application
make run-gui              # Alternative via Makefile
```

### Testing

```bash
# Run all tests
uv run pytest
make test

# Run specific test categories
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests (headless)

# Run single test file
uv run pytest tests/unit/path/to/test_file.py

# With coverage
uv run pytest --cov=src --cov-report=xml
```

### Code Quality

```bash
# Linting and formatting
make format                # Format with Ruff
make mypy                  # Type checking
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix

# Type checking
uv run mypy -p lorairo
```

### Database Migrations

```bash
# Located in src/lorairo/database/migrations/
alembic upgrade head       # Apply migrations
alembic revision --autogenerate -m "description"  # Generate migration
```

### Documentation

```bash
make docs                  # Build Sphinx documentation
make docs-serve            # Serve docs locally on port 8000
make docs-publish          # Publish to gh-pages
```

### Cleanup

```bash
make clean                 # Remove build artifacts and caches
```

#### Cross-Platform Environment Management

This project supports Windows/Linux environments with independent virtual environments to manage platform-specific dependencies properly.

## Project Architecture

### Core Components

**Main Application Flow:**
- Entry point: `src/lorairo/main.py` - Initializes Qt application and main window
- Main Window: `src/lorairo/gui/window/main_window.py` - Primary GUI orchestrator (5段階初期化、SearchFilterService統合完了)
- Configuration: `config/lorairo.toml` - Application settings and parameters

**Data Layer:**
- Database: SQLite-based image metadata storage with SQLAlchemy ORM
- Schema: `src/lorairo/database/schema.py` - Database models
- Repository: `src/lorairo/database/db_repository.py` - Data access layer
- Manager: `src/lorairo/database/db_manager.py` - High-level database operations
- Core: `src/lorairo/database/db_core.py` - Database initialization and core utilities

**Service Layer (2-Tier Architecture):**
- **Business Logic Services** (`src/lorairo/services/`):
  - `ImageProcessingService` - Image processing workflows
  - `ConfigurationService` - Application configuration
  - `AnnotationService` - AI annotation coordination (deprecated)
  - `SearchCriteriaProcessor` - Search and filtering business logic
  - `ModelFilterService` - AI model management and filtering
- **GUI Services** (`src/lorairo/gui/services/`):
  - `WorkerService` - Qt-based asynchronous task coordination
  - `SearchFilterService` - GUI-focused search and filter operations (MainWindow統合完了)

**Workers & Async Processing:**
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
- Modern Python types preferred (list/dict over typing.List/Dict, use `| None` instead of `Optional`)
- Path operations use pathlib, not os
- **NO `# type: ignore` or `# noqa` comments** - fix the underlying issue instead
- Avoid `Any` type; use specific types or explain with comment
- Class names should be specific nouns (e.g., `ModelLoad` not `Loader`)
- Half-width characters only in code/comments (no full-width alphanumerics/symbols)

**Error Handling:**
- Catch specific expected errors only (FileNotFoundError, ValueError, etc.)
- Avoid broad `Exception` catching; let unexpected errors propagate
- Include clear error messages that aid debugging
- Don't layer unnecessary try-except blocks

**Documentation Requirements:**
- Google-style docstrings for all functions/methods (Args, Returns, Raises)
- Module-level comments explaining purpose and dependencies
- Implementation comments in Japanese for clarity
- Use Todo Tree tags (TODO, FIXME, OPTIMIZE, BUG, HACK, XXX) when changing code
- Update related docs when changing code

**Testing:**
- pytest-based with coverage reporting (minimum 75%)
- Test resources in `tests/resources/`
- Test levels: unit (tests/unit/), integration (tests/integration/), BDD E2E (tests/bdd/)
- GUI tests run headless in Linux/container using QT_QPA_PLATFORM=offscreen
- Windows environment supports native GUI windows
- Avoid mocks in unit tests; use only for external dependencies (filesystem, network, APIs)

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

### MCP-Based Development Approach

This project uses a dual-MCP strategy for efficient development:

- **Serena MCP** (fast, 1-3s): Code reading, symbol search, memory operations, basic editing
- **Cipher MCP** (complex, 10-30s): Library research, design pattern analysis, implementation execution

**Memory Strategy:**
- Machine memory: `.serena/memories/` (managed by Serena)
- Human planning: `tasks/` (managed by Cipher)
- Design/specs: `docs/` (managed by Cipher)

### Command-Based Development Process

**Standard workflow pattern:**
1. **Analysis**: `/check-existing` for understanding current functionality
2. **Planning**: `/plan` for strategic design and architecture
3. **Implementation**: `/implement` for code development
4. **Validation**: `/test` for quality assurance and testing

**Process Rules:**
- Always read related code before making changes
- Reference past design knowledge before planning
- Follow established LoRAIro architectural patterns
- Update related docs when changing code

### Claude Skills

LoRAIroの開発パターンとMCP操作は **Claude Skills** で自動化されています。

**MCP Operations Skills** (`.claude/skills/`):
- `mcp-serena-fast-ops`: 高速コード操作（1-3秒）- Symbol検索、Memory操作、基本編集
- `mcp-cipher-complex-analysis`: 複雑分析（10-30秒）- ライブラリ研究、設計パターン検索
- `mcp-memory-first-development`: 2重メモリ戦略 - Serena短期 + Cipher長期記憶

**LoRAIro Development Skills**:
- `lorairo-repository-pattern`: SQLAlchemyリポジトリパターン実装ガイド
- `lorairo-qt-widget`: PySide6ウィジェット実装（Signal/Slot、Direct Widget Communication）
- `lorairo-test-generator`: pytest+pytest-qtテスト生成（75%+ カバレッジ）

**Note**: Skills are automatically invoked by Claude based on task context. 詳細は各SkillのSKILL.mdを参照。

### Hook System（自動実行）

**セキュリティ・品質管理:**
- **Grep拒否Hook**: `git grep --function-context <pattern>`強制使用
- **Bash検証Hook**: 実行前セキュリティチェック・コマンド最適化提案
- **設定場所**: `.claude/settings.local.json`
- **自動動作**: PreToolUse/PostToolUseで透明に実行

**Hook機能:**
- コード検索の統一化（gitトラッキング対象のみ、関数コンテキスト付き）
- 危険コマンドの事前ブロック
- 開発ベストプラクティスの自動適用

**Quality Standards:**
- Follow `.cursor/rules/` development guidelines
- Use Ruff formatting (line length: 108)
- Maintain 75%+ test coverage
- Apply modern Python types (list/dict over typing.List/Dict)


## Problem-Solving Approach

**Design Principles:**
- **YAGNI (You Aren't Gonna Need It)**: Only implement what's needed now, not "might need later"
- **Readability First**: Code should be clear and understandable
- **Single Responsibility**: Each component should have one clear purpose

**Solution Analysis:**
1. **Enumerate approaches** - List multiple solution methods (minimum 3 options)
2. **Evaluate trade-offs** - Assess complexity, maintainability, performance
3. **Select optimal solution** - Balance effectiveness and sustainability
4. **Document decisions** - Record rationale for choices

**When to Ask User:**
- If violating defined principles is unavoidable, stop and explain why
- If stuck after 3+ solution attempts, explain situation and ask for guidance
- If requirements are ambiguous or multiple valid approaches exist
- If design changes affect established architecture

**Reference documents:** `docs/architecture.md` for design principles, `docs/technical.md` for implementation patterns.

## Troubleshooting

### Environment Issues
- **Test Discovery**: Ensure no conflicting `.venv` directories in local packages, verify `uv sync --dev`
- **Virtual Environment**: The project uses `.venv` directory (managed by devcontainer volume mount)
- **Setup**: Run `./scripts/setup.sh` for dependency installation

### MCP Issues
- **Cipher timeout**: Break operations into stages, fallback to direct serena
- **Connection errors**: Use direct serena operations + WebSearch
- **Performance**: Direct serena (1-3s) for simple ops, cipher (10-30s) for complex analysis

### UI Generation Issues
- **SearchFilterService Configuration Error**: If you see "SearchFilterService が設定されていません" error, the issue is missing Qt Designer UI file generation
- **Missing filterSearchPanel Widget**: MainWindow fails to create filterSearchPanel because _ui.py files are missing
- **Import Errors from designer**: `from ...MainWindow_ui import Ui_MainWindow` fails because UI files weren't generated
- **Solution**: Run `uv run python scripts/generate_ui.py` to generate all missing UI files
- **Prevention**: Always run UI generation after modifying .ui files or when setting up development environment
- **Verification**: Script should report 100% success rate and verify MainWindow_ui.py contains filterSearchPanel creation

## Quick Reference

### Commands（MCP統合スラッシュコマンド）
- **`/check-existing`**: 既存機能の詳細分析（serena経由）
- **`/plan`**: 戦略的設計・計画立案（cipher+serena統合）
- **`/implement`**: コード開発実装（段階的実行）
- **`/test`**: 品質保証・テスト実行

### Agents（コマンド内で自動使用）
- **investigation**: コードベース調査・分析（serena semantic search活用）
- **library-research**: 技術研究（cipher+context7経由）
- **solutions**: 多角的問題解決・アプローチ評価
- **code-formatter**: コード品質管理（Ruff統合）

### Skills
- **`.claude/skills/`**: 6つのSkills（MCP操作 + LoRAIro開発パターン）
- 詳細は各SkillのSKILL.mdを参照

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

