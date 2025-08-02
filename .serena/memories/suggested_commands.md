# LoRAIro Essential Commands

## Development Setup

### Environment Management
```bash
# Automatic cross-platform setup (recommended)
./scripts/setup.sh

# Manual Linux environment
uv sync --dev

# Manual Windows environment
$env:UV_PROJECT_ENVIRONMENT=".venv_windows"; uv sync --dev

# Add dependencies
uv add package-name
uv add --dev package-name
```

## Application Execution

### Running the GUI
```bash
# Recommended method
make run-gui

# Direct execution
uv run lorairo

# Alternative
uv run python -m lorairo.main

# Using script (Linux/container)
./scripts/run_gui.sh
```

## Testing Commands

### Test Execution
```bash
# All tests
pytest
# or
make test

# Specific test categories
pytest -m unit         # Unit tests only
pytest -m integration  # Integration tests only
pytest -m gui          # GUI tests only
pytest -m slow         # Long-running tests

# Single test file
pytest tests/path/to/test_file.py

# With coverage
pytest --cov=src --cov-report=html
```

## Code Quality

### Linting and Formatting
```bash
# Format code
ruff format src/ tests/
# or
make format

# Check linting
ruff check src/ tests/ --fix
# or
make lint

# Type checking
mypy src/
# or
make mypy
```

## Database Operations

### Migration Management
```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Check migration status
alembic current
```

## Development Utilities

### Cleanup
```bash
# Clean build artifacts
make clean

# Clean log files
make clean-log
```

### Documentation
```bash
# Build documentation
make docs

# Serve documentation locally
make docs-serve

# Publish documentation
make docs-publish
```

## System Utilities (Linux Container)

### File Operations
```bash
ls          # List directory contents
find        # Search files (use Grep tool instead)
grep        # Search content (use rg/ripgrep instead)
rg          # ripgrep (preferred search tool)
tree        # Directory tree view
cd          # Change directory
```

### Git Operations
```bash
git status              # Check repository status
git add .               # Stage changes
git commit -m "message" # Commit changes
git push                # Push to remote
git pull                # Pull from remote
```

## Task Completion Workflow

### After Code Changes
1. `ruff format src/ tests/`  # Format code
2. `ruff check src/ tests/ --fix`  # Fix linting issues
3. `mypy src/`  # Type checking
4. `pytest`  # Run tests
5. Check test coverage meets 75% minimum

### Before Commit
1. Run all code quality checks
2. Ensure tests pass
3. Update documentation if needed
4. Check no sensitive data in commits