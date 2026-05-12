# Direct Widget Communication Pattern

LoRAIro's Direct Widget Communication pattern eliminates intermediate state management layers for cleaner, more maintainable GUI architecture.

## Core Principles

### 1. No Intermediate State Layer

**Avoid:**
```python
# ❌ BAD: Using state manager as intermediary
class ThumbnailWidget(QWidget):
    def _on_clicked(self, index: int) -> None:
        # Indirect communication via state manager
        self._state_manager.set_selected_image(index)

class DetailsWidget(QWidget):
    def __init__(self, state_manager):
        self._state_manager = state_manager
        self._state_manager.image_changed.connect(self._update)
```

**Prefer:**
```python
# ✅ GOOD: Direct widget-to-widget signals
class ThumbnailWidget(QWidget):
    image_selected = Signal(dict)  # Direct signal

    def _on_clicked(self, index: int) -> None:
        metadata = self._images[index]
        self.image_selected.emit(metadata)

class DetailsWidget(QWidget):
    @Slot(dict)
    def display_metadata(self, metadata: dict) -> None:
        self._update_ui(metadata)

# MainWindow connects them
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        self.thumbnail.image_selected.connect(self.details.display_metadata)
```

### 2. Centralized Connection Management

**All widget connections in MainWindow:**

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._setup_widgets()
        self._connect_widgets()  # Single connection point

    def _connect_widgets(self) -> None:
        """Centralize all widget connections here."""
        # Thumbnail → Details
        self.thumbnail_widget.image_selected.connect(
            self.details_widget.display_metadata
        )

        # Thumbnail → Metadata
        self.thumbnail_widget.image_selected.connect(
            self.metadata_widget.update_metadata
        )

        # Search → Thumbnail
        self.search_widget.search_completed.connect(
            self.thumbnail_widget.display_results
        )

        # Details → Annotation Worker
        self.details_widget.annotation_requested.connect(
            self._handle_annotation_request
        )
```

### 3. Connect-To Pattern

**Each widget provides connection methods:**

```python
class ImageDetailsWidget(QWidget):
    """Image details display widget."""

    annotation_requested = Signal(int)  # image_id

    def connect_to_thumbnail_widget(
        self,
        thumbnail: ThumbnailWidget
    ) -> None:
        """Connect to thumbnail widget for image selection."""
        thumbnail.image_selected.connect(self.display_metadata)

    def connect_to_annotation_service(
        self,
        service: AnnotationService
    ) -> None:
        """Connect to annotation service for AI processing."""
        self.annotation_requested.connect(service.process_image)
        service.annotation_completed.connect(self._on_annotation_done)

    @Slot(dict)
    def display_metadata(self, metadata: dict) -> None:
        """Handle image selection from thumbnail."""
        self._current_metadata = metadata
        self._update_ui()
```

**Usage in MainWindow:**

```python
def _connect_widgets(self) -> None:
    # Using connect_to_* methods
    self.details_widget.connect_to_thumbnail_widget(self.thumbnail_widget)
    self.details_widget.connect_to_annotation_service(self.annotation_service)
```

## Signal Types and Payloads

### Simple Data Types

```python
class FilterWidget(QWidget):
    # Primitive types
    filter_changed = Signal(str)      # Filter text
    count_updated = Signal(int)       # Result count
    score_threshold = Signal(float)   # Score value
    enabled_changed = Signal(bool)    # Toggle state
```

### Complex Data Types

```python
class SearchWidget(QWidget):
    # Dictionary for complex data
    search_completed = Signal(dict)   # {"query": str, "results": list, "count": int}

    def _emit_results(self, results: list[dict]) -> None:
        payload = {
            "query": self._query,
            "results": results,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }
        self.search_completed.emit(payload)
```

### Multiple Parameters

```python
class ThumbnailWidget(QWidget):
    # Multiple typed parameters
    item_selected = Signal(int, str, dict)  # (index, image_path, metadata)

    def _on_click(self, index: int) -> None:
        path = self._paths[index]
        metadata = self._metadata[index]
        self.item_selected.emit(index, path, metadata)
```

## Practical Patterns

### Pattern 1: Master-Detail

```python
class MasterListWidget(QWidget):
    """Master list widget."""
    item_selected = Signal(dict)

    def _on_item_clicked(self, index: int) -> None:
        item_data = self._items[index]
        self.item_selected.emit(item_data)

class DetailViewWidget(QWidget):
    """Detail view widget."""

    def connect_to_master(self, master: MasterListWidget) -> None:
        master.item_selected.connect(self.display_details)

    @Slot(dict)
    def display_details(self, data: dict) -> None:
        self._update_ui(data)

# MainWindow
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        self.detail_view.connect_to_master(self.master_list)
```

### Pattern 2: Filter Chain

```python
class SearchFilterWidget(QWidget):
    """Search filter input."""
    filter_changed = Signal(str)

    def _on_text_changed(self, text: str) -> None:
        self.filter_changed.emit(text)

class ResultFilterWidget(QWidget):
    """Additional result filtering."""
    filter_applied = Signal(dict)

    def _on_filter_applied(self) -> None:
        filters = {"rating": self._rating, "tags": self._tags}
        self.filter_applied.emit(filters)

class ResultListWidget(QWidget):
    """Filtered result display."""

    def connect_to_filters(
        self,
        search_filter: SearchFilterWidget,
        result_filter: ResultFilterWidget
    ) -> None:
        search_filter.filter_changed.connect(self._apply_search)
        result_filter.filter_applied.connect(self._apply_filters)

    @Slot(str)
    def _apply_search(self, query: str) -> None:
        self._filter_by_search(query)

    @Slot(dict)
    def _apply_filters(self, filters: dict) -> None:
        self._filter_by_criteria(filters)

# MainWindow
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        self.result_list.connect_to_filters(
            self.search_filter,
            self.result_filter
        )
```

### Pattern 3: Bidirectional Communication

```python
class EditorWidget(QWidget):
    """Content editor."""
    content_changed = Signal(str)
    save_requested = Signal()

    @Slot(str)
    def load_content(self, content: str) -> None:
        self._editor.setText(content)

    def _on_text_changed(self) -> None:
        self.content_changed.emit(self._editor.toPlainText())

class StatusWidget(QWidget):
    """Status display."""

    def connect_to_editor(self, editor: EditorWidget) -> None:
        # Editor → Status (one way)
        editor.content_changed.connect(self._update_status)
        editor.save_requested.connect(self._show_saving)

    @Slot(str)
    def _update_status(self, content: str) -> None:
        char_count = len(content)
        self._label.setText(f"{char_count} characters")

# MainWindow
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # Bidirectional: Editor ↔ Status
        self.status_widget.connect_to_editor(self.editor_widget)

        # Editor also responds to external events
        self.load_button.clicked.connect(
            lambda: self.editor_widget.load_content(self._load_data())
        )
```

## Advantages

### 1. Clear Data Flow

**Before (with state manager):**
```
ThumbnailWidget → StateManager → DetailsWidget
                → StateManager → MetadataWidget
                → StateManager → StatusWidget
```
Hard to trace signal flow, hidden dependencies.

**After (direct communication):**
```
ThumbnailWidget → DetailsWidget
                → MetadataWidget
                → StatusWidget
```
Explicit connections visible in MainWindow `_connect_widgets()`.

### 2. Reduced Coupling

Widgets don't depend on StateManager implementation:
```python
# Widgets are self-contained
class ThumbnailWidget(QWidget):
    image_selected = Signal(dict)  # Only knows about its signals

    # No dependency on StateManager
```

### 3. Easier Testing

```python
def test_thumbnail_selection(qtbot):
    """Test thumbnail widget independently."""
    thumbnail = ThumbnailWidget()

    with qtbot.waitSignal(thumbnail.image_selected) as blocker:
        qtbot.mouseClick(thumbnail._items[0], Qt.LeftButton)

    # Verify signal payload
    assert blocker.args[0]["id"] == 1
    assert "path" in blocker.args[0]
```

### 4. Flexible Rewiring

Easy to change connections without modifying widgets:

```python
# Before: Details widget connected
def _connect_widgets(self) -> None:
    self.thumbnail.image_selected.connect(self.details.display_metadata)

# After: Add preview widget, no widget changes needed
def _connect_widgets(self) -> None:
    self.thumbnail.image_selected.connect(self.preview.show_image)
    self.thumbnail.image_selected.connect(self.details.display_metadata)
```

## When to Use State Management

Direct communication is preferred, but use state management when:

### 1. Shared Application State

```python
class AppStateManager:
    """Global application state only."""
    current_project = Signal(str)      # Project path
    database_connected = Signal(bool)  # DB status
    config_changed = Signal(dict)      # Config updates
```

### 2. Persistent Data

```python
class DatasetStateManager:
    """Dataset-wide persistent state."""

    def save_project_state(self) -> None:
        """Save state to database."""
        pass

    def restore_project_state(self) -> None:
        """Restore state from database."""
        pass
```

### 3. Complex Multi-Widget Coordination

```python
# Many widgets need same data → Use state manager
class SearchSessionManager:
    """Coordinate complex search session."""
    search_results = Signal(list)

    def execute_search(self, query: str) -> None:
        # Coordinate multiple data sources
        results = self._search_database(query)
        results += self._search_tags(query)
        results += self._search_metadata(query)
        self.search_results.emit(results)
```

## Anti-Patterns

### ❌ Circular Dependencies

```python
# BAD: Circular signal connections
class WidgetA(QWidget):
    data_changed = Signal(str)

    def connect_to_b(self, b: 'WidgetB') -> None:
        b.data_changed.connect(self._update)  # A → B

class WidgetB(QWidget):
    data_changed = Signal(str)

    def connect_to_a(self, a: WidgetA) -> None:
        a.data_changed.connect(self._update)  # B → A

# Results in infinite signal loops!
```

**Fix:** Use unidirectional flow or mediator pattern.

### ❌ Deep Signal Chains

```python
# BAD: Long signal chain
WidgetA → WidgetB → WidgetC → WidgetD → WidgetE

# Hard to debug, brittle
```

**Fix:** Use direct connections or introduce coordinator.

### ❌ Signal Payload Mutation

```python
# BAD: Mutating signal payload
class SenderWidget(QWidget):
    data_sent = Signal(dict)

    def send_data(self) -> None:
        data = {"value": 10}
        self.data_sent.emit(data)

class ReceiverWidget(QWidget):
    @Slot(dict)
    def receive_data(self, data: dict) -> None:
        data["value"] = 20  # Mutates original dict!
```

**Fix:** Send immutable data or make copies.

## Summary

**Direct Widget Communication Benefits:**
- Clear, explicit data flow
- Reduced coupling between widgets
- Easier testing and maintenance
- Flexible connection rewiring

**Key Implementation Points:**
1. Define typed signals in widgets
2. Centralize connections in MainWindow
3. Provide `connect_to_*` methods
4. Avoid intermediate state layers
5. Use state management only for global/persistent state
