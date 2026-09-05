# LoRAIro Project Makefile
# Development task automation

.PHONY: help setup test test-iam-lib test-runtime-local test-runtime-webapi test-genai-tag test-all mypy format format-iam-lib format-genai-tag adr-drift adr-index adr-okf docs-okf install install-dev clean run-gui generate-ui venv-rebuild worktree-cleanup-merged worktree-cleanup-merged-dry-run clean-dry-run venv-rebuild-dry-run

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
	@echo "  test         Run LoRAIro main tests only (shared Python, ADR 0024)"
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
	@echo "  clean        Remove app-owned build artifacts (clean-dry-run previews)"
	@echo "  venv-rebuild Back up shared .venv and reinstall from main (venv-rebuild-dry-run previews)"
	@echo "  worktree-cleanup-merged Remove clean merged /workspaces/LoRAIro/.agents/worktree entries"
	@echo "  worktree-cleanup-merged-dry-run Show clean merged /workspaces/LoRAIro/.agents/worktree entries"

# Setup is explicit and may update dependencies; normal tasks never sync.
setup:
	git submodule update --init --recursive
	$(PYTHON) scripts/dev_tasks.py install-dev
	$(MAKE) skills-install
	$(MAKE) harness-install

.PHONY: harness-install skills-install
harness-install:
	$(PYTHON) -X utf8 scripts/install_agent_harness.py

skills-install:
	$(PYTHON) scripts/install_agent_skills.py

# Portable Python entrypoint is also usable without Make on Windows.
install install-dev run-gui test test-iam-lib test-runtime-local test-runtime-webapi test-genai-tag test-all mypy lint format format-iam-lib format-genai-tag generate-ui adr-drift adr-index adr-okf docs-okf:
	$(PYTHON) scripts/dev_tasks.py $@

# Destructive maintenance has a read-only preview and explicit app-owned scope.
clean venv-rebuild:
	$(PYTHON) scripts/safe_cleanup.py $@

clean-dry-run:
	$(PYTHON) scripts/safe_cleanup.py clean --dry-run

venv-rebuild-dry-run:
	$(PYTHON) scripts/safe_cleanup.py venv-rebuild --dry-run

# Shared-kit worktree lifecycle commands are intentionally unchanged here.
worktree-cleanup-merged:
	uv run python scripts/cleanup_merged_worktrees.py

worktree-cleanup-merged-dry-run:
	uv run python scripts/cleanup_merged_worktrees.py --dry-run
