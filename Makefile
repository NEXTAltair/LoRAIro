# LoRAIro Project Makefile
# Development task automation

.PHONY: help test test-iam-lib test-runtime-local test-genai-tag test-all mypy format install install-dev clean run-gui generate-ui skills-update venv-rebuild

# Default target
help:
	@echo "LoRAIro Project - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  install      Install project dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  run-gui      Run LoRAIro GUI application"
	@echo "  generate-ui  Generate Python files from Qt Designer .ui files"
	@echo "  test         Run LoRAIro main tests only (uv run pytest, ADR 0024)"
	@echo "  test-iam-lib Run image-annotator-lib tests in its package root"
	@echo "  test-runtime-local Run local-only iam-lib real model runtime smoke tests"
	@echo "  test-genai-tag Run genai-tag-db-tools tests in its package root"
	@echo "  test-all     Run all 3 package test sessions sequentially"
	@echo "  mypy         Run code check (mypy)"
	@echo "  format       Format code (ruff format)"
	@echo "  clean        Clean build artifacts"
	@echo "  venv-rebuild Rebuild .venv from scratch (recovery from corruption)"
	@echo "  skills-update Update community skills in .github/skills/"

# Development targets
install:
	@echo "Installing project dependencies..."
	uv sync

install-dev:
	@echo "Installing development dependencies..."
	uv sync --dev

run-gui:
	@echo "Running LoRAIro GUI..."
	uv run lorairo

generate-ui:
	@echo "Generating Python files from Qt Designer UI files..."
	uv run python scripts/generate_ui.py

test:
	@echo "Running LoRAIro main tests (testpaths=[\"tests\"], ADR 0024)..."
	uv run pytest

# NOTE (ADR 0024 amended #291): `cd <pkg> && UV_PROJECT_ENVIRONMENT=... uv run --no-sync pytest`
# で LoRAIro root `.venv` を共有 (bind mount I/O 制約回避、ADR 0024 amendment 参照)。
# `--no-sync` は LoRAIro `.venv` が iam-lib pyproject に合わせて re-sync されるのを防ぐ。
# iam-lib dev deps (pytest-clarity / pytest-mock / pytest-xdist) は LoRAIro [dependency-groups] dev に統合済。
# pytest セッション境界 = package 境界 は維持 (cwd = package root、conftest は iam-lib 側、coverage は package 自身)。
test-iam-lib:
	@echo "Running image-annotator-lib tests (sharing LoRAIro root .venv via UV_PROJECT_ENVIRONMENT)..."
	cd local_packages/image-annotator-lib && \
		UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv \
		uv run --no-sync pytest

test-runtime-local:
	@echo "Running local-only image-annotator-lib real model runtime smoke tests..."
	cd local_packages/image-annotator-lib && uv run pytest tests/runtime_validation/test_real_model_runtime.py -m downloads_and_runs_model

test-genai-tag:
	@echo "Running genai-tag-db-tools tests (creates local_packages/genai-tag-db-tools/.venv)..."
	cd local_packages/genai-tag-db-tools && uv run pytest

test-all:
	@echo "Running all package test sessions sequentially (ADR 0024)..."
	$(MAKE) test
	$(MAKE) test-iam-lib
	$(MAKE) test-genai-tag

mypy:
	@echo "Running mypy..."
	uv run mypy -p lorairo

format:
	@echo "Formatting code..."
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

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

venv-rebuild:
	@echo "Rebuilding .venv from scratch (Issue #222 recovery)..."
	rm -rf .venv
	uv sync --dev
	@echo ".venv rebuilt successfully."

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
