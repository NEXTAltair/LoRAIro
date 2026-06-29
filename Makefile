# LoRAIro Project Makefile
# Development task automation

.PHONY: help setup test test-iam-lib test-runtime-local test-runtime-webapi test-genai-tag test-all mypy format format-iam-lib format-genai-tag adr-drift adr-index adr-okf docs-okf install install-dev clean run-gui generate-ui skills-update venv-rebuild worktree-cleanup-merged worktree-cleanup-merged-dry-run _ensure-submodules _ensure-root-venv

WORKTREE_ROOT := /workspaces/LoRAIro/.agents/worktree
ifeq ($(filter $(WORKTREE_ROOT)/%,$(CURDIR)),)
LORAIRO_UV_PROJECT_ENVIRONMENT := $(CURDIR)/.venv
else
LORAIRO_UV_PROJECT_ENVIRONMENT := /workspaces/LoRAIro/.venv
export UV_PROJECT_ENVIRONMENT := $(LORAIRO_UV_PROJECT_ENVIRONMENT)
endif

# Default target
help:
	@echo "LoRAIro Project - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  setup        Fetch submodules + install dev dependencies (recommended entry point)"
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
	@echo "  skills-update Update community skills in .github/skills/"

# Development targets
# setup: 開発環境セットアップの唯一の人間向け入口。submodule 取得 + dev 依存インストール。
# devcontainer の postCreateCommand.sh もコンテナ固有処理の後にこの target を呼ぶ。
setup: _ensure-submodules
	@echo "Setting up LoRAIro development environment..."
	uv sync --dev

install: _ensure-submodules
	@echo "Installing project dependencies..."
	uv sync

install-dev: _ensure-submodules
	@echo "Installing development dependencies..."
	uv sync --dev

run-gui: _ensure-submodules
	@echo "Running LoRAIro GUI..."
	uv run lorairo

generate-ui: _ensure-submodules
	@echo "Generating Python files from Qt Designer UI files..."
	uv run python scripts/generate_ui.py

test: _ensure-submodules
	@echo "Running LoRAIro main tests (testpaths=[\"tests\"], ADR 0024)..."
	uv run pytest

# NOTE (ADR 0024 amended #291): `cd <pkg> && UV_PROJECT_ENVIRONMENT=$(LORAIRO_UV_PROJECT_ENVIRONMENT) uv run --no-sync pytest`
# で LoRAIro root `.venv` を共有 (bind mount I/O 制約回避、ADR 0024 amendment 参照)。
# worktree (`/workspaces/LoRAIro/.agents/worktree/<wt>`) では `/workspaces/LoRAIro/.venv` を強制し、worktree 内 `.venv` を作らない。
# `_ensure-root-venv` prerequisite で dev deps の install を保証 (fresh checkout / new dev deps pull 直後でも fail しない)。
# `--no-sync` は LoRAIro `.venv` が iam-lib pyproject に合わせて re-sync されるのを防ぐ。
# iam-lib dev deps (pytest-clarity / pytest-mock / pytest-xdist) は LoRAIro [dependency-groups] dev に統合済。
# pytest セッション境界 = package 境界 は維持 (cwd = package root、conftest は iam-lib 側、coverage は package 自身)。
_ensure-submodules:
	@if git submodule status --recursive | grep -q '^U'; then \
		echo "Submodule conflict detected. Resolve it before running this target."; \
		exit 1; \
	fi
	@if git submodule status --recursive | grep -q '^-'; then \
		echo "Initializing git submodules..."; \
		git submodule update --init --recursive; \
	fi

_ensure-root-venv: _ensure-submodules
	@uv sync --dev

test-iam-lib: _ensure-root-venv
	@echo "Running image-annotator-lib tests (sharing LoRAIro root .venv via UV_PROJECT_ENVIRONMENT)..."
	cd local_packages/image-annotator-lib && \
		UV_PROJECT_ENVIRONMENT=$(LORAIRO_UV_PROJECT_ENVIRONMENT) \
		uv run --no-sync pytest \
		-m "not downloads_and_runs_model and not calls_real_webapi"

test-runtime-local: _ensure-submodules
	@echo "Running local-only image-annotator-lib real model runtime smoke tests..."
	cd local_packages/image-annotator-lib && uv run pytest tests/runtime_validation/test_real_model_runtime.py -m downloads_and_runs_model

test-runtime-webapi: _ensure-root-venv
	@echo "Running local-only image-annotator-lib real WebAPI runtime validation..."
	uv run python scripts/run_runtime_webapi_tests.py

test-genai-tag: _ensure-submodules
	@echo "Running genai-tag-db-tools tests (creates local_packages/genai-tag-db-tools/.venv)..."
	cd local_packages/genai-tag-db-tools && \
		UV_PROJECT_ENVIRONMENT=$(CURDIR)/local_packages/genai-tag-db-tools/.venv \
		QT_QPA_PLATFORM=offscreen \
		uv run pytest

test-all: _ensure-submodules
	@echo "Running all package test sessions sequentially (ADR 0024)..."
	$(MAKE) test
	$(MAKE) test-iam-lib
	$(MAKE) test-genai-tag

mypy: _ensure-submodules
	@echo "Running mypy..."
	uv run mypy -p lorairo

format: _ensure-submodules
	@echo "Formatting code..."
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

format-iam-lib: _ensure-root-venv
	@echo "Formatting image-annotator-lib (sharing LoRAIro root .venv via UV_PROJECT_ENVIRONMENT)..."
	cd local_packages/image-annotator-lib && \
		UV_PROJECT_ENVIRONMENT=$(LORAIRO_UV_PROJECT_ENVIRONMENT) \
		uv run --no-sync ruff format src/ tests/ && \
		UV_PROJECT_ENVIRONMENT=$(LORAIRO_UV_PROJECT_ENVIRONMENT) \
		uv run --no-sync ruff check src/ tests/ --fix

format-genai-tag: _ensure-submodules
	@echo "Formatting genai-tag-db-tools (uses local_packages/genai-tag-db-tools/.venv)..."
	cd local_packages/genai-tag-db-tools && \
		UV_PROJECT_ENVIRONMENT=$(CURDIR)/local_packages/genai-tag-db-tools/.venv \
		uv run ruff format . && \
		UV_PROJECT_ENVIRONMENT=$(CURDIR)/local_packages/genai-tag-db-tools/.venv \
		uv run ruff check . --fix

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
	@for d in local_packages/image-annotator-lib/docs local_packages/genai-tag-db-tools/docs; do \
		if [ -d "$$d" ]; then \
			python3 .agents/skills/okf-bundle/scripts/okf_validate.py --bundle-root "$$d" \
				--skip-missing --exclude $(DOCS_OKF_EXCLUDE); \
		else \
			echo "skip (submodule not checked out): $$d"; \
		fi; \
	done

skills-update:
	@echo "Restoring skills from skills-lock.json..."
	npx skills experimental_install --yes
	@echo "Updating community skills to latest versions..."
	npx skills update --yes
	@for skill in $$(ls .agents/skills/ 2>/dev/null); do \
		cp -r .agents/skills/$$skill/. .github/skills/$$skill/; \
		echo "Updated: $$skill"; \
	done
	@echo "Skills updated. Review changes and commit."

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
