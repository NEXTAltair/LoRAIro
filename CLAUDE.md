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
uv run pytest
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests (headless)
uv run pytest -m bdd               # BDD tests (pytest-bdd)
uv run pytest --cov=src --cov-report=xml
```

### Code Quality

```bash
make format                # Format with Ruff
make mypy                  # Type checking
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
```

### Database Migrations

```bash
alembic upgrade head       # Apply migrations
alembic revision --autogenerate -m "description"
```

### Cleanup

```bash
make clean                 # Remove build artifacts and caches
```

## Project Architecture

### Core Components

**Main Application Flow:**
- Entry point: `src/lorairo/main.py`
- Main Window: `src/lorairo/gui/window/main_window.py` (5段階初期化、688行)
- Configuration: `config/lorairo.toml`

**Data Layer:**
- Schema: `src/lorairo/database/schema.py`
- Repository: `src/lorairo/database/db_repository.py`
- Manager: `src/lorairo/database/db_manager.py`
- Core: `src/lorairo/database/db_core.py`

**Service Layer (2-Tier Architecture):**
- **Business Logic Services** (`src/lorairo/services/`, 22 services) — Qt-free
- **GUI Services** (`src/lorairo/gui/services/`, 7 services) — Qt-dependent, Signal-based
- See [docs/services.md](docs/services.md) for all 29 services

**AI Integration (Local Packages):**
- **image-annotator-lib**: `src/lorairo/annotations/annotator_adapter.py`, `annotation_logic.py`
- **genai-tag-db-tools**: `src/lorairo/database/db_repository.py`, Public APIs: `search_tags()`, `register_tag()`

**Workers:** `src/lorairo/gui/workers/` (DatabaseRegistration, Annotation, Search, Thumbnail)

**Storage:** `lorairo_data/project_name_YYYYMMDD_NNN/` — SQLite + `image_dataset/`

### Key Design Patterns

- **Repository Pattern**: Data access abstracted through repository layer
- **Service Layer**: Business logic separated from GUI and data access
- **Worker Pattern**: Asynchronous operations using Qt QRunnable/QThreadPool
- **Qt-Free Core Pattern**: Core services have no Qt dependencies; GUI wrappers use composition
- **Dependency Injection**: Services injected into GUI components

### Local Dependencies

- `local_packages/genai-tag-db-tools` — Tag DB management. User DB: format_id 1000+, auto-init at startup
- `local_packages/image-annotator-lib` — AI annotation. Providers: OpenAI, Anthropic, Google, Local ML

### Development Notes

**Code Style:** Ruff (line length: 108), type hints required, modern Python types (`list`/`dict`, `X | None`), pathlib not os, NO `# type: ignore` or `# noqa`, avoid `Any`, specific class names

**Error Handling:** Catch specific exceptions only (FileNotFoundError, ValueError), avoid broad `Exception`

**Documentation:** Google-style docstrings, Japanese implementation comments, FIXME/PENDING tags with Issue numbers

**Testing:** 75%+ coverage, pytest-qt — use `qtbot.waitSignal()` / `qtbot.waitUntil()`, always mock `QMessageBox`

**Database:** Alembic migrations in `src/lorairo/database/migrations/`

**Logging:** Loguru. INFO: batch summaries only. DEBUG: per-item details. See `.claude/rules/logging.md`

## Problem-Solving Approach

**Design Principles:** YAGNI, Readability First, Single Responsibility

**Solution Analysis:**
1. Enumerate approaches (minimum 3 options)
2. Evaluate trade-offs (complexity, maintainability, performance)
3. Select optimal solution
4. Document decisions (→ `docs/decisions/` as ADR)

**When to Ask User:** If violating principles is unavoidable, stuck after 3+ attempts, ambiguous requirements, or design changes affect established architecture.

## Troubleshooting

**Test Discovery:** No conflicting `.venv` in local packages, verify `uv sync --dev`

**UI Generation Issues:** If "SearchFilterService が設定されていません" or missing `filterSearchPanel`:
```bash
uv run python scripts/generate_ui.py
```
Always run after modifying `.ui` files.

## Quick Reference

### Commands

- **`/check-existing`**: 既存機能の詳細分析
- **`/planning`**: 戦略的設計・計画立案
- **`/implement`**: コード開発実装
- **`/test`**: 品質保証・テスト実行
- **`/save-session`**: 設計意図を OpenClaw LTM に保存

### Agents

Agent Teams 有効（実験的）。チームメートとしても利用可能（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`）。
推奨チームサイズ: 3〜5人、1人あたり5〜6タスク。チームメートごとに担当ファイルを分離してファイル競合を防ぐ。

- **investigation**: コードベース調査・分析
- **solutions**: 多角的問題解決・アプローチ評価
- **code-formatter**: コード品質管理（Ruff統合）
- **test-runner**: テスト実行・結果解析
- **db-schema-reviewer**: スキーマ・マイグレーション品質検査

### Skills

`.github/skills/`: `lorairo-repository-pattern`, `interface-design`, `lorairo-qt-widget`, `lorairo-test-generator`

### Configuration

```toml
# config/lorairo.toml
[api]
openai_key = ""
claude_key = ""
google_key = ""

[directories]
database_base_dir = "lorairo_data"

[log]
level = "INFO"
```

## Further Reading

- [Architecture](docs/architecture.md) — システム設計原則
- [Services Catalog](docs/services.md) — 全29サービス一覧
- [Testing Guide](docs/testing.md) — テスト戦略
- [Integrations](docs/integrations.md) — 外部パッケージ統合
- [Design Decisions](docs/decisions/README.md) — ADR インデックス
- [Lessons Learned](docs/lessons-learned.md) — バグパターン・教訓
- [Development Workflow](docs/development-workflow.md) — 開発プロセス詳細
- [Documentation Maintenance](docs/documentation-maintenance.md) — ドキュメント管理方針
