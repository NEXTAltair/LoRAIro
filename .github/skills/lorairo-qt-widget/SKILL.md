---
name: lorairo-qt-widget
version: "1.1.0"
description: PySide6 widget technical implementation for LoRAIro GUI. Covers Signal/Slot patterns, Direct Widget Communication, Qt Designer integration, and async workers. For design intent and aesthetics, use interface-design skill first.
metadata:
  short-description: PySide6技術実装（Signal/Slot、Qt Designer）。デザイン意図はinterface-design参照。
allowed-tools:
  # Code exploration
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  # Memory (widget patterns)
  - mcp__serena__read_memory
  # Fallback
  - Read
  - Write
  - Edit
  - Bash
dependencies:
  - interface-design
---

# PySide6 Widget Implementation for LoRAIro

Technical implementation patterns for PySide6 widgets with Signal/Slot, Direct Widget Communication, and Qt Designer integration.

## Skill Coordination

This skill focuses on **technical implementation**. For design decisions, use `interface-design` first.

| Question | Use This Skill | Use interface-design |
|----------|----------------|---------------------|
| How to emit a signal? | Yes | No |
| What color should this be? | No | Yes |
| How to structure widget class? | Yes | No |
| What should this feel like? | No | Yes |
| How to connect widgets? | Yes | No |
| What's the signature element? | No | Yes |

**Recommended workflow:**
1. **interface-design**: Define intent, domain, signature, aesthetics
2. **lorairo-qt-widget**: Implement the technical structure

## When to Use

Use this skill when:
- **Creating widgets**: Implementing new GUI components
- **Refactoring widgets**: Improving existing widget architecture
- **Signal/Slot setup**: Connecting widget communication
- **Qt Designer integration**: Working with .ui files
- **Worker integration**: Async operations in widgets

## Core Patterns

### 1. Basic Widget Structure

**Standard widget template:**
```python
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot
from typing import Optional
from loguru import logger

class ExampleWidget(QWidget):
    """Example widget with type-safe signals.

    Signals:
        data_changed: Emitted when data changes (str)
        action_requested: Emitted on user action
    """

    # Type-safe signal definitions
    data_changed = Signal(str)
    action_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()
        self._data: Optional[str] = None

    def _setup_ui(self) -> None:
        """Initialize UI components."""
        # With Qt Designer:
        # from .ExampleWidget_ui import Ui_ExampleWidget
        # self._ui = Ui_ExampleWidget()
        # self._ui.setupUi(self)
        pass

    def _connect_signals(self) -> None:
        """Connect internal signals/slots."""
        pass

    @Slot(str)
    def set_data(self, data: str) -> None:
        """Set data (public interface)."""
        if self._data != data:
            self._data = data
            self._update_display()
            self.data_changed.emit(data)

    def _update_display(self) -> None:
        """Update display (private)."""
        pass
```

### 2. Direct Widget Communication

**LoRAIro pattern** - Direct widget-to-widget connections:

```python
class ThumbnailWidget(QWidget):
    image_metadata_selected = Signal(dict)

    def _on_thumbnail_clicked(self, index: int) -> None:
        metadata = self._image_metadata[index]
        self.image_metadata_selected.emit(metadata)

class ImageDetailsWidget(QWidget):
    def connect_to_thumbnail_widget(self, thumbnail: ThumbnailWidget) -> None:
        """Connect to thumbnail widget directly."""
        thumbnail.image_metadata_selected.connect(self._on_metadata_received)

    @Slot(dict)
    def _on_metadata_received(self, metadata: dict) -> None:
        self._display_metadata(metadata)

# MainWindow coordinates connections
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        """Centralize widget connections."""
        self.image_details.connect_to_thumbnail_widget(self.thumbnail)
```

See [direct-communication.md](./direct-communication.md) for complete pattern details.

### 3. Type-Safe Signals

**Good: Type-specified signals**
```python
class DataWidget(QWidget):
    data_changed = Signal(str)
    score_updated = Signal(float)
    item_selected = Signal(str, int)  # Multiple params
    metadata_loaded = Signal(dict)    # Complex data
```

**Bad: Untyped signals**
```python
class BadWidget(QWidget):
    data_changed = Signal()      # Unclear payload
    value_updated = Signal(object)  # Ambiguous type
```

### 4. Qt Designer Integration

**UI generation:**
```bash
uv run python scripts/generate_ui.py
```

**Usage pattern:**
```python
from .ExampleWidget_ui import Ui_ExampleWidget

class ExampleWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._ui = Ui_ExampleWidget()
        self._ui.setupUi(self)
        self._ui.okButton.clicked.connect(self._on_ok_clicked)
```

### 5. Async Worker Integration

**Worker coordination:**
```python
class AsyncWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._worker_manager = None

    def start_async_operation(self) -> None:
        worker = MyAsyncWorker(data=self._data)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        self._worker_manager.submit(worker)

    @Slot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        progress = int(current / total * 100)
        self._ui.progressBar.setValue(progress)
```

## LoRAIro Conventions

### File Structure
- **Widgets**: `src/lorairo/gui/widgets/`
- **Designer**: `src/lorairo/gui/designer/*.ui`
- **Generated UI**: `src/lorairo/gui/designer/*_ui.py`
- **Main Window**: `src/lorairo/gui/window/main_window.py`

### Naming Rules
- **Classes**: `{Name}Widget` (e.g., `ThumbnailWidget`)
- **Signals**: `{action}_{tense}` (e.g., `data_changed`, `item_selected`)
- **Public methods**: `set_*`, `get_*`, `update_*`
- **Private methods**: `_on_*` (handlers), `_update_*` (internal)
- **Slots**: Always use `@Slot()` decorator

### Direct Communication Principles
1. **Avoid intermediaries**: Skip DatasetStateManager, connect directly
2. **Centralize in MainWindow**: All connections in `_connect_widgets()`
3. **connect_to_* pattern**: Provide `connect_to_{widget}()` methods
4. **Type safety**: All signals/slots must specify types

## Styling with QSS

Apply design decisions from `interface-design` skill using Qt Style Sheets:

```python
class StyledWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply QSS styling based on interface-design decisions."""
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: #e0e0e0;
            }
            QLabel#titleLabel {
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)
```

**Token naming (from interface-design):**
```css
/* Domain-specific naming reflects product world */
QWidget {
    /* Archive/curation domain tokens */
    --surface-archive: #1a1a1a;
    --surface-lightbox: #242424;
    --border-specimen: rgba(255,255,255,0.08);
    --text-catalog: #e0e0e0;
}
```

## Best Practices

**DO:**
- Use `@Slot()` decorator on all slot methods
- Add type hints to all methods
- Separate public/private with `_` prefix
- Provide `connect_to_*` methods for connections
- Log important events with loguru
- Apply styling from interface-design decisions

**DON'T:**
- Access `widget._ui.button` from outside
- Store shared state in widgets
- Mix business logic into widgets
- Run long operations on UI thread (use workers)
- Rely on auto-connection (explicit `connect()` only)
- Make design decisions here (use interface-design)

## Testing

**pytest-qt pattern:**
```python
@pytest.fixture
def widget(qtbot):
    w = ExampleWidget()
    qtbot.addWidget(w)
    return w

def test_signal_emission(qtbot, widget):
    with qtbot.waitSignal(widget.data_changed, timeout=1000) as blocker:
        widget.set_data("test data")
    assert blocker.args[0] == "test data"
```

## Memory Integration

**Before implementation:**
```
1. mcp__serena__read_memory("current-project-status")
2. Check for existing widget patterns
3. Review interface-design system.md if exists
```

**After implementation:**
```
1. mcp__serena__write_memory - Record widget structure
```

## Examples

See [examples.md](./examples.md) for detailed widget implementation scenarios.

## Reference

See [reference.md](./reference.md) for complete PySide6 API reference and Qt Designer workflow.
