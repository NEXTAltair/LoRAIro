# genai-tag-db-tools GUI Service Migration - 2025-12-29

## Overview

Successfully migrated GUI services from `services/app_services.py` to `gui/services/` directory, separating Qt-dependent code from Qt-free core services. This enables CLI tools to remain Qt-free while GUI components have access to Qt Signal functionality.

## Completed Tasks

### 1. Service Architecture Redesign

**Qt-free Core Services:**
- Created `services/tag_register.py` with `TagRegisterService` (Qt-free, for CLI/library/GUI use)
- Created `services/core_services.py` with `TagCoreService` (basic tag operations)
- Existing `TagRegister` class remains for bulk operations

**Qt-dependent GUI Services:**
- Created `gui/services/gui_service_base.py` - Base class with Qt Signals (progress_updated, process_finished, error_occurred)
- Created `gui/services/tag_register_service.py` - `GuiTagRegisterService` wraps Qt-free `TagRegisterService`
- Created `gui/services/tag_search_service.py` - `TagSearchService` with Qt Signals
- Created `gui/services/tag_cleaner_service.py` - `TagCleanerService` with Qt Signals
- Created `gui/services/tag_statistics_service.py` - `TagStatisticsService` with Qt Signals
- Retained `gui/services/db_initialization.py` - DB initialization service with Qt worker

### 2. Design Pattern: Composition over Duplication

**GuiTagRegisterService implementation:**
```python
class GuiTagRegisterService(GuiServiceBase):
    """GUI向けのタグ登録サービス (TagRegisterService wrapper with Qt signals)"""

    def __init__(self, parent: QObject | None = None, repository: TagRepository | None = None, reader: "MergedTagReader | None" = None):
        super().__init__(parent)
        self._core = TagRegisterService(repository=repository, reader=reader)  # Composition
        self._repo = self._core._repo  # For legacy methods
        self._reader = self._core._reader  # For legacy methods

    def register_tag(self, request: "TagRegisterRequest") -> "TagRegisterResult":
        try:
            result = self._core.register_tag(request)  # Delegate to core
            return result
        except Exception as e:
            self.logger.error("タグ登録中にエラー発生: %s", e)
            self.error_occurred.emit(str(e))  # Add Qt Signal
            raise
```

**Benefits:**
- No code duplication between CLI and GUI
- Single source of truth for business logic
- GUI wrapper only adds Qt Signal emission
- Easy to maintain and test

### 3. Import Updates

**CLI (Qt-free):**
```python
# cli.py
from genai_tag_db_tools.services.tag_register import TagRegisterService  # Qt-free
```

**GUI Components:**
```python
# gui/widgets/tag_register.py
from genai_tag_db_tools.gui.services import (
    GuiTagRegisterService,
    TagSearchService,
)
```

**Updated Files:**
- `src/genai_tag_db_tools/cli.py`
- `src/genai_tag_db_tools/gui/widgets/tag_cleaner.py`
- `src/genai_tag_db_tools/gui/widgets/tag_register.py`
- `src/genai_tag_db_tools/gui/widgets/tag_statistics.py`
- `src/genai_tag_db_tools/gui/windows/main_window.py`
- `src/genai_tag_db_tools/gui/services/__init__.py`

### 4. Test Updates

**Mock Class Pattern (avoid DB initialization in tests):**
```python
class MockTagRegisterService(GuiTagRegisterService):
    """GuiTagRegisterService のモック"""

    def __init__(self) -> None:
        # Don't call super().__init__() to avoid DB initialization in tests
        self.mock_register_or_update_tag = MagicMock(return_value=123)
        self.mock_get_tag_details = MagicMock(...)

    def register_or_update_tag(self, tag_info: dict[str, object]) -> int:
        return self.mock_register_or_update_tag(tag_info)
```

**Updated Test Files:**
- `tests/gui/unit/test_tag_register_widget.py`
- `tests/gui/unit/test_tag_cleaner_widget.py`
- `tests/gui/unit/test_tag_statistics_widget.py`

**Test Results:**
- All 101 GUI unit tests passing
- No DB initialization errors
- Mock classes properly avoid Qt initialization

## File Structure

```
src/genai_tag_db_tools/
├── services/
│   ├── core_services.py          # NEW: TagCoreService (Qt-free)
│   └── tag_register.py           # NEW: TagRegisterService (Qt-free) + existing TagRegister
└── gui/
    └── services/
        ├── __init__.py            # UPDATED: Exports GUI services
        ├── gui_service_base.py    # NEW: Base class with Qt Signals
        ├── tag_register_service.py # NEW: GuiTagRegisterService (Qt wrapper)
        ├── tag_search_service.py  # NEW: TagSearchService (moved from app_services)
        ├── tag_cleaner_service.py # NEW: TagCleanerService (moved from app_services)
        ├── tag_statistics_service.py # NEW: TagStatisticsService (moved from app_services)
        └── db_initialization.py  # EXISTING: Kept as-is
```

## Key Design Decisions

### 1. Naming Convention
- **Rejected**: `CoreTagRegisterService` (confusing, implies hierarchy)
- **Accepted**: `TagRegisterService` (Qt-free, standard) and `GuiTagRegisterService` (GUI wrapper)
- **Rationale**: Clear distinction between standard service and GUI-specific wrapper

### 2. CLI Independence
- **Requirement**: CLI must remain Qt-free
- **Solution**: CLI imports from `services.tag_register`, not `gui.services`
- **Validation**: CLI has no PySide6 imports

### 3. Code Reuse
- **Problem**: Initial approach duplicated business logic between GUI and core
- **Solution**: GUI wrapper uses composition to delegate to core service
- **Result**: Single source of truth, no duplication

### 4. Test Strategy
- **Problem**: Mock classes inheriting from GUI services triggered DB initialization
- **Solution**: Don't call `super().__init__()` in test mocks
- **Result**: Tests run without DB dependency

## Lessons Learned

1. **Qt Dependency Management**: Always verify Qt dependencies don't leak into non-GUI code
2. **Composition Pattern**: More flexible than inheritance for wrapping services
3. **Test Isolation**: Mock classes should avoid calling parent constructors that have side effects
4. **Naming Clarity**: "Core" prefix is ambiguous, use "Gui" prefix for GUI-specific wrappers
5. **Import Verification**: Check all import paths in both source and test files

## Next Steps (Potential)

1. **Deprecate old imports**: Add deprecation warnings to `services/app_services.py`
2. **Remove legacy code**: Delete `services/app_services.py` after confirming no external dependencies
3. **Documentation**: Update API docs to reflect new service architecture
4. **Integration tests**: Verify CLI and GUI work correctly with new service structure

## Test Coverage

- **GUI Unit Tests**: 101/101 passed (100%)
- **Widget Tests**: All widget initialization, signal handling, and error cases covered
- **Service Tests**: DbInitializationService, WorkerService fully tested
- **Converter Tests**: All data conversion utilities tested

## Success Criteria

✅ CLI remains Qt-free  
✅ GUI services have Qt Signal support  
✅ No code duplication between CLI and GUI  
✅ All tests passing (101/101)  
✅ Clear separation of concerns  
✅ Maintainable architecture
