# LoRAIro Project Patterns for Serena Operations

This file provides LoRAIro-specific guidance for using Serena MCP tools effectively.

## Project Structure

### Source Code
- **Main implementation**: `src/lorairo/` - Core application code
- **Tests**: `tests/` - Unit, integration, and GUI tests
- **Configuration**: `config/lorairo.toml` - Application settings
- **Local packages**:
  - `local_packages/genai-tag-db-tools` - Tag database utilities
  - `local_packages/image-annotator-lib` - AI annotation functionality

### Key Directories
```
src/lorairo/
├── database/          # Data access layer
│   ├── repositories/  # Repository pattern implementations
│   └── schema.py      # SQLAlchemy models
├── services/          # Business logic layer
├── gui/               # PySide6 GUI components
│   ├── widgets/       # Custom widgets
│   ├── workers/       # Async workers (QThreadPool)
│   └── window/        # Main window
└── annotations/       # AI annotation integration
```

## Architecture Patterns

### Repository Pattern
Database operations use repository pattern:
```
src/lorairo/database/repositories/
├── image_repository.py
├── tag_repository.py
└── ... (other repositories)
```

**Key characteristics**:
- Session management via `db_core.get_session()`
- Type-safe transactions
- ORM-based queries (SQLAlchemy)

### Service Layer
Business logic separated from data and GUI:
```
src/lorairo/services/
├── ImageProcessingService
├── ConfigurationService
├── AnnotatorLibraryAdapter
└── ... (other services)
```

### Direct Widget Communication
GUI components use Qt Signal/Slot pattern:
- Widgets emit signals
- Parent widget (MainWindow) connects signals
- No service layer for widget-to-widget communication

**Example**:
```python
# In parent widget
self.image_list_widget.image_selected.connect(
    self.metadata_widget.update_metadata
)
```

## Memory Naming Conventions

### Standard Memory Files
- **current-project-status**: Overall project state
- **active-development-tasks**: Current tasks
- **{feature}_implementation_{date}**: Implementation records
  - Example: `annotation_worker_implementation_2025_12_20`
- **archived_***: Completed task archives

### Memory Content Structure
```markdown
# {Feature} Implementation

## Status
[Current status: in-progress/completed/blocked]

## Progress
- [x] Completed step 1
- [ ] Pending step 2

## Decisions
- Decision 1: Rationale
- Decision 2: Trade-offs

## Issues
- Issue 1: Description and resolution
```

## Code Organization Patterns

### Imports
```python
# Standard library
from pathlib import Path
from typing import Any

# Third-party
from PySide6.QtWidgets import QWidget
from sqlalchemy.orm import Session

# Local application
from lorairo.database.repositories import ImageRepository
from lorairo.services import ImageProcessingService
```

### Type Hints
- Use modern Python types: `list[str]` not `List[str]`
- Use `| None` not `Optional[...]`
- Always type function parameters and returns
- Avoid `Any` type

### Docstrings
Google-style docstrings:
```python
def process_image(image_path: Path, quality: int) -> ProcessedImage:
    """
    Processes an image with specified quality settings.

    Args:
        image_path: Path to source image file
        quality: Quality level (1-100)

    Returns:
        ProcessedImage instance with results

    Raises:
        FileNotFoundError: If image_path doesn't exist
        ValueError: If quality out of range
    """
```

## Common Symbol Search Patterns

### Finding Repositories
```
name_path: "{Repository}" (e.g., "ImageRepository")
relative_path: "src/lorairo/database/repositories/"
include_body: True
depth: 1  # Include methods
```

### Finding Services
```
name_path: "{Service}" (e.g., "ImageProcessingService")
relative_path: "src/lorairo/services/"
```

### Finding Widgets
```
name_path: "{Widget}" (e.g., "ThumbnailWidget")
relative_path: "src/lorairo/gui/widgets/"
```

### Finding Workers
```
name_path: "{Worker}" (e.g., "AnnotationWorker")
relative_path: "src/lorairo/gui/workers/"
```

## Testing Patterns

### Test Organization
```
tests/
├── unit/              # Unit tests (@pytest.mark.unit)
│   ├── database/      # Repository tests
│   ├── services/      # Service tests
│   └── ...
├── integration/       # Integration tests (@pytest.mark.integration)
│   └── gui/           # GUI tests (@pytest.mark.gui)
└── conftest.py        # Shared fixtures
```

### pytest Markers
- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Multi-component integration tests
- `@pytest.mark.gui` - PySide6 GUI tests (pytest-qt)

### Coverage Requirement
- Minimum 75% code coverage
- Run: `uv run pytest --cov=src/lorairo --cov-report=xml`

## Virtual Environment Rules

**CRITICAL**: Always use project root venv:
- Virtual environment: `/workspaces/LoRAIro/.venv`
- **Never** run `uv run` from `local_packages/*/`
- **Always** run `uv run` from `/workspaces/LoRAIro/`

### Correct Usage
```bash
# ✅ CORRECT: From project root
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/tests/
```

### Incorrect Usage
```bash
# ❌ WRONG: From local package (creates separate .venv)
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
uv run pytest tests/
```

## Editing Guidelines

### When to Use Symbol Editing
- Modifying entire function/method/class
- Adding new methods to existing classes
- Inserting imports at file beginning

### When to Use Pattern Search + Replace
- Renaming variables across multiple locations
- Updating similar code patterns
- Refactoring parameter names

### Symbol Editing Example
```python
# Use replace_symbol_body for:
# - Complete method rewrite
# - Significant logic changes
# - Type signature changes

# Use insert_after_symbol for:
# - Adding new methods to class
# - Adding new functions to module

# Use insert_before_symbol for:
# - Adding imports
# - Adding module-level constants
```

## Reference Tracking Usage

### Before Refactoring
1. `find_symbol` - Locate symbol definition
2. `find_referencing_symbols` - Find all usages
3. Analyze impact across codebase
4. Edit symbol and all references

### Before Deletion
1. `find_referencing_symbols` - Check for dependencies
2. If no references, safe to delete
3. If references exist, refactor or update

## Performance Tips

### Efficient Symbol Discovery
```
1. get_symbols_overview (fast overview)
   ↓
2. find_symbol (specific symbol)
   ↓
3. find_referencing_symbols (if editing)
   ↓
4. Edit operations
```

### Memory Operations
- **list_memories** first to see available memories
- **read_memory** for specific memory content
- **write_memory** or **edit_memory** for updates
- Avoid full memory rewrites; use **edit_memory** for changes

### Progressive Disclosure
- Start with overview tools (get_symbols_overview, list_dir)
- Drill down with specific tools (find_symbol, read_memory)
- Retrieve full content only when necessary
