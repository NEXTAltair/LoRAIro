# LoRAIro Project Makefile
# Development task automation

.PHONY: help setup test test-iam-lib test-runtime-local test-runtime-webapi test-genai-tag test-all mypy format format-iam-lib format-genai-tag adr-drift adr-index adr-okf docs-okf install install-dev clean run-gui generate-ui venv-rebuild worktree-cleanup-merged worktree-cleanup-merged-dry-run _ensure-submodules

ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

# Preserve the existing Linux guard for legacy targets not migrated below.
# Portable tasks validate the environment again via Git in dev_tasks.py.
WORKTREE_ROOT := /workspaces/LoRAIro/.agents/worktree
ifneq ($(filter $(WORKTREE_ROOT)/%,$(CURDIR)),)
export UV_PROJECT_ENVIRONMENT := /workspaces/LoRAIro/.venv
endif

# Default target
.PHONY: lint

help:
	@echo "LoRAIro Project - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  setup        Fetch submodules + install dev dependencies + restore external skills (recommended entry point)"
	@echo "  skills-install Restore external agent skills from skills-lock.json (requires Node.js/npx)"
	@echo "  install      Install project dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  run-gui      Run LoRAIro GUI application"
	@echo "  generate-ui  Generate Python files from Qt Designer .ui files"
	@echo "  test         Run LoRAIro main tests only (uv run pytest, ADR 0024)"
	@echo "  test-iam-lib Run image-annotator-lib tests in its package root"
	@echo "  test-runtime-local Run local-only iam-lib real model runtime smoke tests"
	@echo "  test-runtime-webapi Run local-only iam-lib real WebAPI runtime validation"
	@echo "  test-genai-tag Run genai-tag-db-tools tests in its package root"
	@echo "  test-all     Run all 3 package test sessions sequentially"
	@echo "  mypy         Run code check (mypy)"
	@echo "  lint         Read-only Ruff lint and formatting checks"
	@echo "  format       Format LoRAIro main code (ruff format + check --fix on src/ tests/)"
	@echo "  format-iam-lib Format image-annotator-lib in its package root"
	@echo "  format-genai-tag Format genai-tag-db-tools in its package root"
	@echo "  adr-drift    List ADR review candidates (drift detection)"
	@echo "  adr-index    Regenerate ADR index.md + README from frontmatter (ADR 0069)"
	@echo "  adr-okf      Validate ADR frontmatter and check index is up to date"
	@echo "  docs-okf     Validate documentation OKF frontmatter (lazy, ADR 0082)"
	@echo "  clean        Clean build artifacts"
	@echo "  venv-rebuild Rebuild .venv from scratch (recovery from corruption)"
	@echo "  worktree-cleanup-merged Remove clean merged /workspaces/LoRAIro/.agents/worktree entries"
	@echo "  worktree-cleanup-merged-dry-run Show clean merged /workspaces/LoRAIro/.agents/worktree entries"

# Setup is explicit and may update dependencies; normal tasks never sync.
setup:
	git submodule update --init --recursive
	$(PYTHON) scripts/dev_tasks.py install-dev
	$(MAKE) skills-install

skills-install:
	$(PYTHON) scripts/install_agent_skills.py

# Portable Python entrypoint is also usable without Make on Windows.
install install-dev run-gui test test-iam-lib test-runtime-local test-runtime-webapi test-genai-tag test-all mypy lint format format-iam-lib format-genai-tag:
	$(PYTHON) scripts/dev_tasks.py $@

# UI generation and legacy cleanup/docs targets are migrated separately.
generate-ui: _ensure-submodules
	uv run python scripts/generate_ui.py

_ensure-submodules:
	@if git submodule status --recursive | grep -q '^U'; then \
		echo "Submodule conflict detected. Resolve it before running this target."; \
		exit 1; \
	fi
	@if git submodule status --recursive | grep -q '^-'; then \
		echo "Initializing git submodules..."; \
		git submodule update --init --recursive; \
	fi


adr-drift:
	@echo "Checking ADR drift (見直し候補)..."
	uv run python scripts/check_adr_drift.py

# ADR (OKF バンドル) の index.md + README テーブルを frontmatter から再生成する (ADR 0069)。
adr-index:
	@echo "Regenerating ADR index from frontmatter..."
	python3 .agents/skills/okf-bundle/scripts/okf_index.py --bundle-root docs/decisions \
		--table --columns id,title,timestamp,status --headers "ADR,タイトル,日付,ステータス" \
		--link-column id --exclude README.md --table-output docs/decisions/README.md
	python3 .agents/skills/okf-bundle/scripts/okf_index.py --bundle-root docs/decisions \
		--index --index-output docs/decisions/index.md \
		--index-title "Architecture Decision Records" --exclude README.md

# ADR の frontmatter を OKF 規約に照らして検証する (ADR 0069)。
adr-okf:
	@echo "Validating ADR frontmatter (OKF)..."
	python3 .agents/skills/okf-bundle/scripts/okf_validate.py --bundle-root docs/decisions \
		--require type,title,status,timestamp --exclude README.md
	python3 .agents/skills/okf-bundle/scripts/okf_index.py --bundle-root docs/decisions \
		--table --columns id,title,timestamp,status --headers "ADR,タイトル,日付,ステータス" \
		--link-column id --exclude README.md --table-output docs/decisions/README.md --check
	python3 .agents/skills/okf-bundle/scripts/okf_index.py --bundle-root docs/decisions \
		--index --index-output docs/decisions/index.md \
		--index-title "Architecture Decision Records" --exclude README.md --check

# 通常ドキュメント (docs / local_packages docs) の OKF frontmatter を検証する (ADR 0082)。
# lazy migration: --skip-missing で frontmatter 未付与ファイルは pass、付与済みのみ type/timestamp を検証。
# docs/decisions は全件必須なので別 target (adr-okf)。
# DOCS_OKF_EXCLUDE: frontmatter 規約の対象外 (README/メタ系 + 外部ツールが固有形式を要求する SKILL.md)。
DOCS_OKF_EXCLUDE := README.md,CHANGELOG.md,CLAUDE.md,AGENTS.md,GEMINI.md,SKILL.md

docs-okf:
	@echo "Validating documentation OKF frontmatter (lazy migration, ADR 0082)..."
	python3 .agents/skills/okf-bundle/scripts/okf_validate.py --bundle-root docs \
		--skip-missing --exclude $(DOCS_OKF_EXCLUDE)
	@rc=0; for d in local_packages/image-annotator-lib/docs local_packages/genai-tag-db-tools/docs; do \
		if [ -d "$$d" ]; then \
			python3 .agents/skills/okf-bundle/scripts/okf_validate.py --bundle-root "$$d" \
				--skip-missing --exclude $(DOCS_OKF_EXCLUDE) || rc=1; \
		else \
			echo "skip (submodule not checked out): $$d"; \
		fi; \
	done; exit $$rc

venv-rebuild: _ensure-submodules
	@echo "Rebuilding .venv from scratch (Issue #222 recovery)..."
	rm -rf .venv
	uv sync --dev
	@echo ".venv rebuilt successfully."

worktree-cleanup-merged:
	@echo "Removing clean merged worktrees under /workspaces/LoRAIro/.agents/worktree..."
	uv run python scripts/cleanup_merged_worktrees.py

worktree-cleanup-merged-dry-run:
	@echo "Checking clean merged worktrees under /workspaces/LoRAIro/.agents/worktree..."
	uv run python scripts/cleanup_merged_worktrees.py --dry-run

clean:
	@echo "Cleaning build artifacts and caches..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".eggs" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build/ dist/ .coverage coverage.xml
	@echo "Build artifacts and caches cleaned."
