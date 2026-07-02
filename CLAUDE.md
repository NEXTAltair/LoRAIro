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
# ✅ CORRECT: LoRAIro 本体テストはプロジェクトルートから
cd /workspaces/LoRAIro
uv run pytest                                # tests/ のみ collection (ADR 0024)

# ✅ CORRECT: local package テストは package root への cd 経由で独立 venv に隔離
#   (ADR 0024: package ごとに独立 .venv が作られるが、make チェーン順次実行 +
#    CI runner 隔離で Issue #222 の並列 drift は再発しない)
make test-iam-lib    # cd local_packages/image-annotator-lib && uv run pytest
make test-genai-tag  # cd local_packages/genai-tag-db-tools  && uv run pytest

# ❌ WRONG: 並列で複数 package の `uv sync` を同時実行 (Issue #222 の温床)
(cd local_packages/image-annotator-lib && uv sync) &
(cd local_packages/genai-tag-db-tools  && uv sync) &
wait
```

**並列実行**: 複数の `uv run` を同時に走らせる場合は [.claude/rules/parallel-execution.md](.claude/rules/parallel-execution.md) を参照。`uv run --active` は Hook で自動ブロックされる。

## Development Commands

### Environment Setup

```bash
make setup                 # Fetch submodules (local_packages/*) + uv sync --dev
# 個別に実行する場合:
#   git submodule update --init --recursive
#   uv sync --dev

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
# LoRAIro 本体テストのみ (testpaths = ["tests"], ADR 0024)
uv run pytest
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests (headless)
uv run pytest -m bdd               # BDD tests (pytest-bdd)
uv run pytest --cov=src --cov-report=xml

# local package のテストは package root で独立した pytest セッション
make test-iam-lib                  # image-annotator-lib (Python 3.12)
make test-genai-tag                # genai-tag-db-tools
make test-all                      # 3 セッションを順次実行
```

### Diagnostic Logs

`logs/lorairo.log` and `logs/image-annotator-lib.log` are intentionally gitignored, but they are first-class debugging context. When investigating runtime errors, failed GUI flows, annotation/model issues, worker failures, or test failures that may involve app behavior, inspect them proactively even if the user did not attach or mention them.

Use bounded reads:

```bash
tail -200 logs/lorairo.log
tail -200 logs/image-annotator-lib.log
```

If a log file is missing, note that and continue. Do not add these logs to git or paste large log dumps in responses; summarize only relevant lines.

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
- Main Window: `src/lorairo/gui/window/main_window.py`
- Configuration: `config/lorairo.toml`

**Data Layer:**
- Schema: `src/lorairo/database/schema.py`
- Repositories: `src/lorairo/database/repository/`
- Manager: `src/lorairo/database/db_manager.py`
- Core: `src/lorairo/database/db_core.py`

**Service Layer (2-Tier Architecture):**
- **Business Logic Services** (`src/lorairo/services/`) — Qt-free
- **GUI Services** (`src/lorairo/gui/services/`) — Qt-dependent, Signal-based
- See [docs/services.md](docs/services.md) for the service catalog

**AI Integration (Local Packages):**
- **image-annotator-lib**: `src/lorairo/annotation/annotator_adapter.py`, `annotation_runner.py`
- **genai-tag-db-tools**: `src/lorairo/database/repository/annotation_record.py`, Public APIs: `search_tags()`, `register_tag()`

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

**Dependency management:** `uv.lock` is tracked in git (ADR 0025, uv 公式推奨). Commit lockfile alongside `pyproject.toml` / submodule pin updates. **AI 推論 SDK (`pydantic-ai` / `anthropic` / `openai` / `google-genai` / `litellm` / `transformers` / `huggingface-hub` / `torch`) は常に最新の安定版を使う**: `pyproject.toml` は lower bound (`>=`) のみ、upper bound (`<X.Y`) は付けない。新モデル対応 / WebAPI バグ修正 / 月次 review で `uv lock --upgrade-package <name>` で bump する。詳細は [.claude/rules/dependency-management.md](.claude/rules/dependency-management.md)。

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

### Workflow (調査 → 計画 → 実装 → 検証 → 記録)

旧 `/planning` `/implement` `/test` `/build-fix` `/code-review` `/save-session` コマンドは廃止。
ネイティブ機能 + superpowers + LoRAIro skill に集約済み:

- **調査**: `check-existing` skill — 要件ヒアリング + 既存ライブラリ/local_packages 調査
- **計画**: ネイティブ Plan Mode (`/plan`) または superpowers `brainstorming` → `writing-plans`（`rules/planning-memory.md` が ADR/教訓の事前確認を強制）
- **実装**: superpowers `executing-plans` / `test-driven-development` + `lorairo-repository-pattern` / `lorairo-qt-widget` skill（ブランチ戦略は `rules/git-workflow.md`）
- **検証**: superpowers `test-driven-development` + `lorairo-test-generator` skill（test-sync 含む）+ `rules/testing.md`。クイックチェックは `make format` / `make mypy` / `uv run pytest`
- **デバッグ**: superpowers `systematic-debugging` + `build-error-resolver` agent
- **レビュー**: 組み込み `/code-review` + `code-reviewer` / `security-reviewer` agent + superpowers `requesting-code-review`
- **記録**: `lorairo-mem` skill（session 保存 workflow を内包）+ `docs/decisions/` ADR + `docs/lessons-learned.md`

### Agents

Agent Teams 有効（実験的）。チームメートとしても利用可能（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`）。
推奨チームサイズ: 3〜5人、1人あたり5〜6タスク。チームメートごとに担当ファイルを分離してファイル競合を防ぐ。

- **investigation**: コードベース調査・分析
- **solutions**: 多角的問題解決・アプローチ評価
- **code-formatter**: コード品質管理（Ruff統合）
- **test-runner**: テスト実行・結果解析
- **db-schema-reviewer**: スキーマ・マイグレーション品質検査

### Skills

`.agents/skills/`: `check-existing` (実装前の既存解調査), `lorairo-repository-pattern`, `interface-design`, `lorairo-qt-widget`, `lorairo-test-generator`, `lorairo-mem` (長期記憶 + session保存), `lorairo-cli-db-access` (画像DB調査は sqlite3 直叩きでなく lorairo-cli 経由), `lazy-import-refactor`, `agent-pr-maintainer` (PR保守ポリシー), `agent-pr-autoloop` (PR保守ループ自走)

`npx skills` (Vercel) で管理。`.claude/skills/<name>` は `.agents/skills/<name>` への symlink。

#### agent-pr-autoloop の Claude Code 実装

`agent-pr-autoloop` skill の poll 待機は Claude Code では **ScheduleWakeup 自走** で回す (repair / reply / escalation / merge の判断基準は `agent-pr-maintainer` skill と ADR 0039 に従う):

- 1ターン = 1 poll サイクル (`gh pr view` / `gh pr checks` で状態取得 → continue / repair / escalate / merge / timeout を分類)。
- 分類が **continue** なら `ScheduleWakeup(delaySeconds=180, prompt=skill再実行)` で次サイクルを予約する。3分間隔は ADR 0039、180s は prompt cache 温存域 (<270s)。
- 上限 20分 (≈6–7サイクル) で打ち切り、PR に日本語コメントして停止する。
- **`sleep && <next>` 直列・先頭 sleep は runtime にブロックされる** (`.claude/rules/testing.md`)。ScheduleWakeup が使えないセッションでのみ、bounded な bash `until` ループで代替する。

### Pre-PR check

`gh pr create` で submodule (`local_packages/*`) 変更を含む PR を起票する際は、事前に CI-equivalent filter で local test を実行する (`.claude/rules/testing.md` の "CI-equivalent filter" セクション参照)。Hook (`.claude/hooks/hook_pre_pr_submodule_check.py`) が gate として強制する。bypass は command 内に `CI-EQUIV-TESTED` marker を含める。

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
- [Services Catalog](docs/services.md) — 全サービス一覧
- [Testing Guide](docs/testing.md) — テスト戦略
- [Integrations](docs/integrations.md) — 外部パッケージ統合
- [Design Decisions](docs/decisions/README.md) — ADR インデックス
- [Lessons Learned](docs/lessons-learned.md) — バグパターン・教訓
- [Development Workflow](docs/development-workflow.md) — 開発プロセス詳細
- [Documentation Maintenance](docs/documentation-maintenance.md) — ドキュメント管理方針
