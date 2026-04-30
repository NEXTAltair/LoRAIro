# LoRAIro Project Makefile
# Development task automation

.PHONY: help test mypy format install install-dev clean run-gui generate-ui skills-update venv-rebuild

# Default target
help:
	@echo "LoRAIro Project - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  install      Install project dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  run-gui      Run LoRAIro GUI application"
	@echo "  generate-ui  Generate Python files from Qt Designer .ui files"
	@echo "  test         Run tests"
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
	@echo "Running tests..."
	uv run pytest

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
