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

Two-tier service architecture separating Qt-free business logic from Qt-dependent GUI services:

- **Business Logic Services** (`src/lorairo/services/`, 22 services):
  - Core services: `ServiceContainer` (DI), `ConfigurationService`, `TagManagementService`
  - Processing: `ImageProcessingService`, `DataTransformService`, `BatchProcessor`
  - Model management: `ModelFilterService`, `ModelSelectionService`, `ModelSyncService`
  - **Pattern**: Qt-free, reusable across CLI/GUI/API contexts

- **GUI Services** (`src/lorairo/gui/services/`, 7 services):
  - Coordination: `WorkerService`, `SearchFilterService`, `PipelineControlService`
  - State: `ProgressStateService`, `ResultHandlerService`
  - **Pattern**: Qt-dependent, Signal-based communication with widgets

- **Qt-Free Core Pattern**: Core services have no Qt dependencies; GUI wrappers use composition pattern
- **Complete catalog**: See [docs/services.md](docs/services.md) for all 29 services with responsibilities

**Workers & Async Processing:**
- `WorkerManager` (`src/lorairo/gui/workers/manager.py`) - QThreadPool-based worker execution
- Specialized workers in `src/lorairo/gui/workers/`: DatabaseRegistration, Annotation, Search, Thumbnail

**AI Integration (Local Packages):**
- **image-annotator-lib**: Multi-provider AI annotation (OpenAI, Anthropic, Google, Local models)
  - Integration: `src/lorairo/annotations/annotator_adapter.py`, `src/lorairo/annotations/annotation_logic.py`
  - Service: `src/lorairo/services/annotator_library_adapter.py`
  - Returns: `PHashAnnotationResults` with structured data
- **genai-tag-db-tools**: Tag database management and cleaning utilities
  - Integration: `src/lorairo/database/db_repository.py` (primary), `src/lorairo/services/tag_management_service.py`
  - Database: User DB (auto-created) + Base DB (3 DB files from HuggingFace)
  - Public APIs: `search_tags()`, `register_tag()`, `MergedTagReader`

**GUI Architecture:**
- Built with PySide6 (Qt for Python)
- **Main Window**: `src/lorairo/gui/window/main_window.py` - Primary GUI orchestrator (688 lines, 5-stage initialization)
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
  - **Integration**: `src/lorairo/database/db_repository.py` (primary entry point)
  - **Public APIs**: `search_tags()`, `register_tag()` for external tag DB
  - **Database**: User DB (auto-created) + Base DB (3 DB files from HuggingFace)
  - **Services**: `TagManagementService` for user DB operations (user tags only)
  - **User DB Strategy**: format_id 1000+ reservation, auto-init at startup
- `local_packages/image-annotator-lib` - Core AI annotation functionality
  - **Integration**: `src/lorairo/annotations/annotator_adapter.py`, `annotation_logic.py`
  - **Service Adapter**: `src/lorairo/services/annotator_library_adapter.py`
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
  - **FIXME**: Issues requiring future implementation (reference GitHub Issue numbers, e.g., `FIXME: Issue #1参照 - description`)
  - **PENDING**: Issues awaiting external decisions or requirements clarification (include detailed context: reason, trigger condition, related issues)
- Update related docs when changing code

**Testing:**
- pytest-based with coverage reporting (minimum 75%)
- Test resources in `tests/resources/`
- Test levels: unit (tests/unit/), integration (tests/integration/), BDD E2E (tests/bdd/)
- GUI tests run headless in Linux/container using QT_QPA_PLATFORM=offscreen
- Windows environment supports native GUI windows
- Avoid mocks in unit tests; use only for external dependencies (filesystem, network, APIs)
- **pytest-qt Best Practices**:
  - Use `qtbot.waitSignal(timeout=XXX)` for signal-based assertions
  - Use `qtbot.waitUntil(lambda, timeout=XXX)` for UI state changes
  - Always mock `QMessageBox` with `monkeypatch`
  - Avoid `QCoreApplication.processEvents()` direct calls
  - Avoid `qtbot.wait(fixed_time)` without condition checks
  - See [docs/testing.md](docs/testing.md) for comprehensive patterns

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

### Key Architecture Features (Recent Updates)

**Tag Management System (Phase 2 & 2.5, Dec 2025):**
- **External Tag DB Integration**: Public API integration (`search_tags()`, `register_tag()`)
- **User DB Strategy**: Auto-created user database with format_id 1000+ reservation (collision avoidance)
- **Tag Registration**: Search → Register → Retry pattern with format_name="Lorairo", type_name="unknown"
- **Incomplete Tag Management**: Batch update of unknown type tags via `update_tags_type_batch()`
- **User DB Only Policy**: `TagManagementService` operates on user DB exclusively (not merged with base DB)
- **Coverage**: 97% on Phase 2.5 code, 75%+ overall

**Qt-Free Core Pattern (Dec 2025):**
- **Design**: Composition over inheritance for service wrappers
- **Core Services**: Qt-free business logic (e.g., `TagRegisterService`)
- **GUI Wrappers**: Qt-dependent wrappers with Signal support (e.g., `GuiTagRegisterService`)
- **Benefit**: Enables CLI tools without Qt dependencies while GUI has full Signal integration

**MainWindow 5-Stage Initialization (Nov 2025):**
- **Size Reduction**: 1,645 lines → 688 lines (58.2% reduction)
- **Pattern**: Phase-based initialization with event delegation via Service helpers
- **Integration**: SearchFilterService fully integrated, HybridAnnotationController removed

**Database Architecture:**
- **User DB**: Auto-initialized at startup (`init_user_db()`), format_id 1000+
- **Base DB**: Optional 3 DB files from HuggingFace with curated tag taxonomy
- **Design**: User DB works standalone; base DB is enhancement, not requirement

## Development Workflow

### MCP-Based Development Approach

This project uses a dual-MCP strategy for efficient development:

- **Serena MCP** (fast, 1-3s): Code reading, symbol search, memory operations, basic editing
- **Cipher MCP** (complex, 10-30s): Library research, design pattern analysis, implementation execution

**Memory Strategy:**
- Machine memory: `.serena/memories/` (managed by Serena)
- Plan Mode plans: `.claude/plans/` → Auto-synced to Serena Memory via PostToolUse hook
- Design/specs: `docs/` (architecture, services, integrations, testing)
- **Obsolete**: `tasks/` directory (removed 2025-11-06, use Plan Mode + Serena Memory instead)

### Command-Based Development Process

**Standard workflow pattern:**
1. **Analysis**: `/check-existing` for understanding current functionality
2. **Planning**: `/planning` for strategic design and architecture
3. **Implementation**: `/implement` for code development
4. **Validation**: `/test` for quality assurance and testing

**Process Rules:**
- Always read related code before making changes
- Reference past design knowledge before planning
- Follow established LoRAIro architectural patterns
- Update related docs when changing code

### Git Worktree for Parallel Development

**When to use git worktree:**
- Working on multiple branches simultaneously without switching contexts
- Long-running tasks that require keeping main branch accessible
- Testing changes across different branches without stashing
- Separating unrelated feature development (e.g., MainWindow separation while keeping annotator integration branch ready)

**Creating a worktree:**
```bash
# Create new branch in worktree
git worktree add ../LoRAIro-feature-name -b feature/branch-name

# Use existing branch in worktree
git worktree add ../LoRAIro-feature-name feature/existing-branch

# List all worktrees
git worktree list

# Remove worktree
git worktree remove ../LoRAIro-feature-name
```

**Setup requirements:**
Each worktree needs independent environment setup:
```bash
cd ../LoRAIro-feature-name
uv sync --dev              # Install dependencies in worktree
uv run python scripts/generate_ui.py  # Generate UI files if needed
```

**Claude Code support:**
- Claude Code officially supports git worktree sessions
- Each worktree is treated as an independent workspace
- Documentation: https://docs.claude.com/en/docs/claude-code/common-workflows#using-git-worktrees

**Best practices:**
- Keep worktrees in parent directory (e.g., `../LoRAIro-feature-name`)
- Use descriptive worktree directory names matching branch purpose
- Clean up worktrees after merging branches (`git worktree remove`)
- Run `uv sync` in each worktree to maintain consistent dependencies

### Claude Skills

LoRAIroの開発パターンとMCP操作は **Claude Skills** で自動化されています。

**MCP Operations Skills** (`.github/skills/`):
- `mcp-serena-fast-ops`: 高速コード操作（1-3秒）- Symbol検索、Memory操作、基本編集
- `mcp-cipher-complex-analysis`: 複雑分析（10-30秒）- ライブラリ研究、設計パターン検索
- `mcp-memory-first-development`: 2重メモリ戦略 - Serena短期 + Cipher長期記憶

**LoRAIro Development Skills**:
- `lorairo-repository-pattern`: SQLAlchemyリポジトリパターン実装ガイド
- `lorairo-qt-widget`: PySide6ウィジェット実装（Signal/Slot、Direct Widget Communication）
- `lorairo-test-generator`: pytest+pytest-qtテスト生成（75%+ カバレッジ）

**Note**: Skills are automatically invoked by Claude based on task context. 詳細は各SkillのSKILL.mdを参照。

#### Claude Code 2.1.0 Optimizations (2026-01-10)

LoRAIroは Claude Code 2.1.0 の新機能を最大限活用するよう最適化されています：

**Skills Enhancement**:
- 全6個のSkillに `version: "1.0.0"` と `dependencies: []` フィールド追加
- Hot-reload有効化: Skill変更時にClaude Code再起動不要

**Agent Parallel Execution** ⚡:
- Investigation、Library-research、Solutions agentが `context: fork` で並列実行
- Code-formatter agentは `context: main` で順次実行（ファイル変更のため）
- `/planning` コマンド実行時間: **30-50%高速化**（90-150秒 → 30-50秒）

**Hook Optimization**:
- ExitPlanMode hookに `once: true` 設定追加
- Plan Mode終了時のSerena Memory同期が1回のみ実行（重複防止）

**Permission Management**:
- 冗長なPlan Mode許可削除（Claude Code 2.1.0では暗黙的）
- Gitコマンド統合: `Bash(git *)` でワイルドカード対応
- Timeout統合: `Bash(timeout * uv run pytest:*)` など
- 許可エントリ数: 94 → 75 (20%削減)

**Language Configuration**:
- `language: "japanese"` 設定追加
- Claude Code応答が日本語で統一、LoRAIroドキュメントとの整合性確保

**Rollback**: 各最適化は `.github/skills.backup`、`.claude/agents.backup`、`.claude/settings.local.json.backup` からロールバック可能

**Memory**: 実装詳細は `.serena/memories/claude_code_2_1_0_optimization_completion_2026_01_10` 参照

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
- **`/planning`**: 戦略的設計・計画立案（cipher+serena統合）
- **`/implement`**: コード開発実装（段階的実行）
- **`/test`**: 品質保証・テスト実行（引数なし: クイックチェック、引数あり: 包括的テスト）
- **`/sync-plan`**: Plan Mode の計画を手動で Serena Memory に同期

### Plan Mode vs /planning Command

Claude Code のネイティブ Plan Mode と custom `/planning` コマンドの使い分け：

**Plan Mode** (Quick Task Planning):
- **用途**: 単一機能の実装、即座の実行タスク
- **所要時間**: 5-10分
- **出力**: `.claude/plans/` → Serena Memory（自動同期）
- **Memory**: Serena のみ（プロジェクト固有）
- **特徴**:
  - Claude Code UI でネイティブサポート
  - PostToolUse hook で自動的に Serena Memory に同期
  - 他の Agent から `.serena/memories/plan_*` として参照可能

**/planning Command** (Comprehensive Design):
- **用途**: 複雑なアーキテクチャ決定、複数フェーズ機能
- **所要時間**: 20-40分
- **出力**: Cipher Memory（設計パターン） + Serena Memory（現在状況）
- **Memory**: Serena + Cipher（クロスプロジェクト知識）
- **特徴**:
  - Investigation + Library Research + Solutions agents 統合
  - 複数アプローチ検討とトレードオフ分析
  - 設計知識を Cipher に永続化（再利用可能）

**選択ガイドライン**:
- シンプルな機能追加 → **Plan Mode**
- アーキテクチャ変更を伴う実装 → **/planning**
- 過去に似た実装がある → まず `/check-existing`、その後 Plan Mode
- 技術選定が必要 → **/planning** (Library Research を含む)

### Agents（コマンド内で自動使用）
- **investigation**: コードベース調査・分析（serena semantic search活用）
- **library-research**: 技術研究（cipher+context7経由）
- **solutions**: 多角的問題解決・アプローチ評価
- **code-formatter**: コード品質管理（Ruff統合）

### Skills
- **`.github/skills/`**: 6つのSkills（MCP操作 + LoRAIro開発パターン）
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

## Documentation Maintenance

### Layered Documentation Strategy

LoRAIroは3層ドキュメント構造を採用し、設計変更への耐性を確保しています：

**Layer 1: CLAUDE.md** (このファイル)
- **Purpose**: AI agent orientation + workflow guidance
- **Update frequency**: Quarterly or on major architecture changes
- **Contents**: Core principles, workflows, architecture patterns overview
- **Stable**: 設計原則、開発ワークフロー、問題解決アプローチ

**Layer 2: docs/*.md** (Technical Specifications)
- **Purpose**: Detailed architecture and API documentation
- **Update frequency**: On feature completion or pattern changes
- **Contents**:
  - [docs/services.md](docs/services.md) - Complete service catalog (29 services)
  - [docs/integrations.md](docs/integrations.md) - External package integration patterns
  - [docs/testing.md](docs/testing.md) - Testing strategies and best practices
  - [docs/architecture.md](docs/architecture.md) - System design principles
  - [docs/technical.md](docs/technical.md) - Implementation specifications
- **Volatile**: サービスリスト、統合詳細、APIシグネチャ

**Layer 3: Code** (Source of Truth)
- **Purpose**: Always accurate implementation details
- **Update frequency**: Real-time (on every commit)
- **Contents**: Python docstrings, type hints, module comments
- **Always current**: コードそのものが真実の情報源

### When to Update

**CLAUDE.md (this file):**
- Quarterly review for obsolete patterns
- Major architecture changes (e.g., new design patterns)
- Workflow updates (e.g., new commands, hooks)
- Critical path changes (entry points, main components)

**docs/*.md files:**
- Feature completion: Update services.md if new service added
- Integration changes: Update integrations.md if external package API changed
- Testing strategy: Update testing.md if new patterns adopted
- Architecture evolution: Update architecture.md for design decisions

**Code docstrings:**
- Every function/method implementation
- Every class definition
- Every module creation

### Update Checklist

**On Feature Completion:**
- [ ] Memory files auto-updated (Plan Mode PostToolUse hook)
- [ ] Update docs/services.md if new service added
- [ ] Update docs/integrations.md if integration changed
- [ ] Update docs/testing.md if new test pattern used
- [ ] Run validation script (if available): `python scripts/validate_docs.py`

**Quarterly Review:**
- [ ] Read through CLAUDE.md for obsolete sections
- [ ] Verify docs/*.md files still accurate
- [ ] Check file paths and service counts
- [ ] Update recent architecture changes section
- [ ] Run full validation

**On Major Architecture Change:**
- [ ] Update affected docs/*.md files first
- [ ] Update CLAUDE.md references if structure changed
- [ ] Create Serena memory file documenting change
- [ ] Run validation to ensure consistency

### Validation

**Automated Validation (planned):**
```bash
# Validate all referenced file paths exist
python scripts/validate_docs.py

# Check service count matches actual files
python scripts/validate_docs.py --check-services

# Verify integration points are valid
python scripts/validate_docs.py --check-integrations
```

**Manual Validation:**
- Verify all file paths in CLAUDE.md exist
- Check that docs/*.md links work
- Ensure service count (29) matches actual: `ls src/lorairo/services/*.py src/lorairo/gui/services/*.py | grep -v __init__ | wc -l`
- Test that AI agents can find referenced documentation

### Design Decisions

**Why 3-layer structure?**
- **Maintainability**: Separates stable principles from volatile details
- **Efficiency**: Updates take <10 minutes instead of 1+ hour
- **Accuracy**: Layer 2 docs updated on feature completion, not quarterly
- **Scalability**: Easy to add new docs/*.md files for new domains

**Why not auto-generation?**
- **Context**: Human-written explanations provide valuable context
- **Flexibility**: Can highlight important patterns vs listing everything
- **Stability**: Auto-gen would change frequently, causing churn

**Why reference docs/*.md instead of inline?**
- **Single source of truth**: No duplication = no drift
- **Focused content**: CLAUDE.md stays scannable for AI agents
- **Easy updates**: Change one place instead of many

### Maintenance History

**Major Updates:**
- 2026-01-01: Implemented 3-layer architecture (this update)
  - Fixed 30+ path errors and missing services
  - Created docs/services.md, docs/integrations.md, docs/testing.md
  - Added Qt-Free Core Pattern, Tag Management System documentation
  - Documented tasks/ directory obsolescence

**Next Review:** 2026-04-01 (quarterly)