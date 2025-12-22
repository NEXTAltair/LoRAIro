# Scenario: Basic Widget Creation with PySide6

## Input
**User request:** "Create a new FilterPanelWidget for the image browser. It should have filter controls (dropdowns, checkboxes) and follow LoRAIro's widget patterns."

**Context:**
- LoRAIro uses PySide6 (Qt for Python)
- Widget patterns to follow:
  - Clear class structure with type hints
  - Signal definitions using @Slot decorator
  - Direct Widget Communication (not service layer for widget-to-widget)
  - Proper initialization pattern
- Existing examples: SearchFilterWidget, MetadataDisplayWidget
- Location: `src/lorairo/gui/widgets/`

## Expected Behavior
1. Skill `lorairo-qt-widget` should be invoked automatically
2. Should guide widget creation workflow:

   **Phase 1: Explore Existing Widgets**
   - Use `mcp__serena__find_symbol` to examine existing widget (e.g., SearchFilterWidget)
   - Analyze structure: __init__, signals, slots, layout
   - Check memory for widget patterns

   **Phase 2: Widget Implementation**
   - Create FilterPanelWidget class inheriting QWidget
   - Define signals for filter changes
   - Implement __init__ with type hints
   - Create UI layout (dropdowns, checkboxes)
   - Add @Slot decorated methods
   - Follow Direct Widget Communication pattern

   **Phase 3: Integration Guidance**
   - Show how parent widget connects to signals
   - Demonstrate type-safe signal/slot connections
   - Mention Qt Designer integration (if applicable)

3. Should produce:
   - Complete widget implementation
   - Type-safe signals and slots
   - Follows LoRAIro widget patterns
   - Clear docstrings (Google style)
   - Direct communication pattern

4. Should NOT:
   - Use service layer for widget-to-widget communication
   - Skip type hints
   - Forget @Slot decorators
   - Use generic `QObject.connect()` without type safety

## Success Criteria
- [x] Correct skill invoked (lorairo-qt-widget)
- [x] Explores existing widgets before implementing
- [x] Widget structure follows LoRAIro patterns
- [x] Signals defined with proper types
- [x] @Slot decorators present
- [x] Type hints throughout
- [x] Direct Widget Communication pattern used
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic widget structure; may need guidance on signal/slot typing
- **Sonnet:** Should create complete widget following all patterns; good type safety and structure
- **Opus:** May suggest UI/UX improvements; may optimize layout; excellent pattern adherence and documentation

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-qt-widget` in metadata
2. Check exploration phase:
   - Used `find_symbol` to examine existing widget
   - Analyzed structure before implementing
3. Verify widget structure:
   ```python
   from PySide6.QtWidgets import QWidget
   from PySide6.QtCore import Signal, Slot

   class FilterPanelWidget(QWidget):
       # Type-safe signals
       filter_changed = Signal(dict)  # or more specific type

       def __init__(self, parent: QWidget | None = None):
           super().__init__(parent)
           self._setup_ui()

       def _setup_ui(self) -> None:
           # Layout creation
           ...

       @Slot()
       def _on_filter_change(self) -> None:
           # Slot implementation
           ...
   ```
4. Check pattern adherence:
   - Inherits from QWidget
   - Signals defined at class level
   - @Slot decorators on slot methods
   - Type hints on all methods
   - Private methods prefixed with `_`
5. Verify Direct Communication:
   - No service layer for widget-to-widget
   - Parent connects to signals directly
   - Type-safe connections mentioned
6. Check documentation:
   - Google-style docstrings
   - Signal documentation (what data they emit)
   - Method parameter descriptions
