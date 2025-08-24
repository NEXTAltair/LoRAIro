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

### MCP Integration (serena+cipher統合)

**統合アーキテクチャ:**
- **serena**: 高速操作（検索、メモリ管理、基本編集）- 直接接続
- **cipher**: 複合分析（context7経由ライブラリ検索、長期記憶管理）- aggregator経由
- **自動選択**: タスクの複雑さに応じて最適なMCP経路を自動選択

**Operation Selection:**
- **Fast operations** (1-3s): Direct serena（symbol検索、メモリ操作、基本編集）
- **Complex analysis** (10-30s): Cipher aggregator（ライブラリ研究、複数ツール統合）
- **Library Research**: context7経由でのライブラリ情報検索・長期記憶
- **Fallback**: 直接操作 when cipher timeouts occur

### Serena Memory Management（統合知識管理）

**Memory-First開発原則:**
- **事前確認**: `mcp__serena__read_memory` で関連実装知識を確認
- **実装中記録**: 進捗と判断を `mcp__serena__write_memory` で記録
- **完了後蓄積**: 実装パターンと教訓を永続化

**Memory Categories:**
- **current-project-status**: プロジェクト全体状況と進捗
- **active-development-tasks**: 現在の開発タスクと計画
- **実装記録**: 具体的実装の詳細と根拠（例: `thumbnail_null_check_implementation_2025`）
- **アーカイブ**: 完了タスクの歴史的記録（例: `archived_active_context_*`）

**Memory Operations:**
```bash
# 関連知識検索
mcp__serena__list_memories  # 利用可能なメモリ一覧
mcp__serena__read_memory <memory_name>  # 特定メモリ読み込み

# 知識記録・更新
mcp__serena__write_memory <memory_name> <content>  # 新規記録・更新
```

**Development Integration:**
- 実装前: 過去の類似実装パターン確認
- 実装中: 進捗・課題・判断の継続記録
- 完了後: 実装知識・教訓・パターンの蓄積

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

### Context Migration完了後の統合ワークフロー

**新しい開発サイクル（2025-08-24以降）:**
1. **Memory-First Analysis**: 関連実装知識をSerena memoryから事前確認
2. **コマンド実行**: `/check-existing` → `/plan` → `/implement` → `/test`
3. **知識蓄積**: 実装完了後に新しい知識・パターンをSerena memoryに記録

**従来との比較:**
- **Before**: `tasks/active_context.md`, `tasks/tasks_plan.md` による静的管理
- **After**: Serena memory による動的・検索可能な知識管理

**利点:**
- **即座の知識参照**: 過去の実装パターンへの高速アクセス
- **重複回避**: 既存実装の再利用と改善
- **継続的蓄積**: 開発知識の永続化と共有
- **効率化**: Memory-First原則による開発速度向上

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

### Serena Memory Operations（統合知識管理）
- **`mcp__serena__list_memories`**: 利用可能なメモリ一覧取得
- **`mcp__serena__read_memory <name>`**: 特定メモリ読み込み
- **`mcp__serena__write_memory <name> <content>`**: メモリ作成・更新
- **Key Memories**: `current-project-status`, `active-development-tasks`

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

