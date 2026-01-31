# Repository Guidelines

## Project Structure & Module Organization
- `src/lorairo/` holds the main Python package (entry point: `lorairo.main:main`).
- Key subpackages: `config/` (settings), `database/` (SQLAlchemy + Alembic), `gui/` (PySide6 UI), `image/` (image processing), `utils/` (shared helpers).
- `tests/` contains pytest suites and fixtures; `tests/resources/` stores test assets.
- `local_packages/` includes editable submodules used by the app (e.g., `genai-tag-db-tools/`, `image-annotator-lib/`).
- `docs/` contains Sphinx docs; `scripts/` contains dev utilities (e.g., GUI launcher, UI generation).

## Build, Test, and Development Commands
- `uv sync` (or `make install`) installs runtime dependencies.
- `make install-dev` installs dev dependencies and editable package setup.
- `uv run lorairo` or `make run-gui` starts the GUI.
- `make test` runs pytest with repo defaults.
- `make mypy` runs strict type checks against the `lorairo` package.
- `make format` applies Ruff formatting and fixes.
- `make docs` builds Sphinx documentation; `make docs-serve` serves it locally.

## Coding Style & Naming Conventions
- Python 3.12; 4-space indentation; line length 108.
- Ruff is the formatter and linter. Use double quotes and let Ruff handle imports.
- Generated Qt Designer code lives under `*/gui/designer/` and is excluded from linting; avoid manual edits unless necessary.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-qt`, and `pytest-bdd`.
- Naming: files `test_*.py`, classes `Test*`, functions `test_*`.
- Coverage: fails under 75% (`coverage` config in `pyproject.toml`).
- Example: `uv run pytest -m "fast"` to run quick unit tests.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits: `feat: ...`, `refactor: ...`, `docs: ...`, `test: ...`, `chore: ...`.
- PRs should include a clear description, test results, and screenshots for GUI changes.
- Link related issues and note any migration or config changes.

## Security & Configuration Tips
- Store API keys in a local `.env` (see `.env.example`). Never commit secrets.
- Keep local data and logs out of version control (`logs/`, `lorairo_data/`).
