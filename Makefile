# LoRAIro Project Makefile
# Documentation and development task automation

.PHONY: help docs docs-clean docs-publish docs-serve test mypy format install install-dev clean run-gui generate-ui

# Default target
help:
	@echo "LoRAIro Project - Available Commands:"
	@echo ""
	@echo "Documentation:"
	@echo "  docs         Build documentation with Sphinx"
	@echo "  docs-clean   Clean documentation build artifacts"
	@echo "  docs-serve   Serve documentation locally"
	@echo "  docs-publish Publish documentation to gh-pages"
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
	@echo "  clean-log     Clean LoRAIro log files"

# Documentation targets
docs:
	@echo "Building documentation with Sphinx..."
	sphinx-build -b html docs/source docs/build
	@echo "Documentation build completed successfully."

docs-clean:
	@echo "Cleaning documentation build artifacts..."
	@rm -rf docs/build/
	@echo "Documentation artifacts cleaned."

docs-serve: docs
	@echo "Starting local documentation server..."
	@cd docs/build && python -m http.server 8000

docs-publish: docs
	@echo "Publishing documentation to gh-pages..."
	@current_branch=$$(git rev-parse --abbrev-ref HEAD); \
	echo "Current branch: $$current_branch"; \
	temp_dir="gh-pages-temp"; \
	remote_url=$$(git config --get remote.origin.url); \
	echo "Remote URL: $$remote_url"; \
	if [ -d "$$temp_dir" ]; then \
		echo "Removing existing temporary directory..."; \
		rm -rf "$$temp_dir"; \
	fi; \
	echo "Cloning gh-pages branch into $$temp_dir..."; \
	git clone -b gh-pages "$$remote_url" "$$temp_dir" || exit 1; \
	echo "Clone succeeded."; \
	cd "$$temp_dir"; \
	echo "Removing existing files from gh-pages branch..."; \
	find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +; \
	echo "Copying new build results..."; \
	cp -r ../docs/build/* . || exit 1; \
	echo "Copy succeeded."; \
	echo "Committing and pushing changes..."; \
	git add -A; \
	git commit -m "Update documentation - $$(date '+%Y-%m-%d %H:%M:%S')"; \
	git push origin gh-pages || exit 1; \
	echo "Push succeeded."; \
	cd ..; \
	echo "Removing temporary directory..."; \
	rm -rf "$$temp_dir"; \
	echo "Checking out original branch: $$current_branch..."; \
	git checkout "$$current_branch" || exit 1; \
	echo "Documentation published to gh-pages branch successfully."

# Development targets
install:
	@echo "Installing project dependencies..."
	uv sync

install-dev:
	@echo ">>> Installing development dependencies and setting up editable install..."
	# 依存関係をインストール
	uv sync --dev
	# 編集可能モードでプロジェクトをインストール
	uv pip install -e . --no-deps
	@echo ">>> Setup complete!"

run-gui:
	@echo "Running LoRAIro GUI..."
	./scripts/run_gui.sh

gene-ui:
	@echo "Generating Python files from Qt Designer UI files..."
	uv run python scripts/generate_ui.py

test:
	@echo "src/ and tests..."
	uv run pytest

clean:
	@echo "Cleaning build artifacts and caches..."
	# Remove Python bytecode and cache dirs
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	# Remove packaging/build artifacts
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".eggs" -exec rm -rf {} + 2>/dev/null || true
	# Remove test/tool caches
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	# Remove other common caches and tooling dirs
	@find . -type d -name ".cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".tox" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null || true
	# Remove build outputs, coverage and logs
	@rm -rf build/ dist/ docs/build/ .coverage coverage.xml
	@rm -rf logs/* .claude/logs
	@echo "Build artifacts and caches cleaned."


# Windows compatibility (optional .bat targets)
docs-publish-win:
	@echo "Use 'make docs-publish' or run publish_docs.bat for W
		rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.mypy_cache' --exclude='.ruff_cache' --exclude='resources/img' tests/ /tmp/lorairo_test_src/tests/; \
		if [ -d tests/resources/img/1_img ]; then \
			mkdir -p /tmp/lorairo_test_src/tests/resources/img/; \
			rsync -a tests/resources/img/1_img/ /tmp/lorairo_test_src/tests/resources/img/1_img/; \
		fi; \
	fi
	@echo "Running tests in /tmp/lorairo_test_src/tests ..."
	uv run pytest /tmp/lorairo_test_src/tests

mypy:
	@echo "Running mypy..."
	uv run mypy -p lorairo

format:
	@echo "Formatting code..."
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix
