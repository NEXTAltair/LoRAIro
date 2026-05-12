# Widget Implementation Examples

Detailed examples for common LoRAIro widget implementation scenarios.

## Example 1: Simple Display Widget

**Scenario:** Create a widget to display image metadata (read-only).

### Implementation

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox
from PySide6.QtCore import Slot
from typing import Optional

class ImageMetadataWidget(QWidget):
    """Display image metadata in read-only format.

    This widget receives metadata via slot and displays it.
    No signals needed (display-only widget).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        self._metadata: Optional[dict] = None

    def _setup_ui(self) -> None:
        """Setup UI layout."""
        layout = QVBoxLayout()

        # Create group box
        group = QGroupBox("Image Metadata")
        group_layout = QVBoxLayout()

        # Create labels
        self._path_label = QLabel("Path: -")
        self._size_label = QLabel("Size: -")
        self._format_label = QLabel("Format: -")
        self._tags_label = QLabel("Tags: -")

        group_layout.addWidget(self._path_label)
        group_layout.addWidget(self._size_label)
        group_layout.addWidget(self._format_label)
        group_layout.addWidget(self._tags_label)

        group.setLayout(group_layout)
        layout.addWidget(group)
        self.setLayout(layout)

    @Slot(dict)
    def display_metadata(self, metadata: dict) -> None:
        """Update display with new metadata.

        Args:
            metadata: Dictionary containing image metadata
                Expected keys: path, size, format, tags
        """
        self._metadata = metadata

        self._path_label.setText(f"Path: {metadata.get('path', '-')}")
        self._size_label.setText(f"Size: {metadata.get('size', '-')}")
        self._format_label.setText(f"Format: {metadata.get('format', '-')}")

        tags = metadata.get('tags', [])
        tags_str = ", ".join(tags) if tags else "-"
        self._tags_label.setText(f"Tags: {tags_str}")

    @Slot()
    def clear_display(self) -> None:
        """Clear all displayed metadata."""
        self._metadata = None
        self._path_label.setText("Path: -")
        self._size_label.setText("Size: -")
        self._format_label.setText("Format: -")
        self._tags_label.setText("Tags: -")
```

### Connection in MainWindow

```python
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # Thumbnail → Metadata display
        self.thumbnail_widget.image_selected.connect(
            self.metadata_widget.display_metadata
        )

        # Clear button → Clear display
        self.clear_button.clicked.connect(
            self.metadata_widget.clear_display
        )
```

## Example 2: Interactive Input Widget

**Scenario:** Create a search filter widget with user input and signal emission.

### Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QSpinBox, QLabel
)
from PySide6.QtCore import Signal, Slot
from loguru import logger

class SearchFilterWidget(QWidget):
    """Search filter input widget with multiple criteria.

    Signals:
        filter_changed: Emitted when filter criteria change (dict)
        search_triggered: Emitted when search button clicked (dict)
    """

    filter_changed = Signal(dict)
    search_triggered = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QVBoxLayout()

        # Search query input
        layout.addWidget(QLabel("Search Query:"))
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Enter search terms...")
        layout.addWidget(self._query_input)

        # Minimum score filter
        layout.addWidget(QLabel("Minimum Score:"))
        self._score_input = QSpinBox()
        self._score_input.setRange(0, 100)
        self._score_input.setValue(50)
        layout.addWidget(self._score_input)

        # Include untagged checkbox
        self._include_untagged = QCheckBox("Include untagged images")
        self._include_untagged.setChecked(True)
        layout.addWidget(self._include_untagged)

        # Search button
        self._search_button = QPushButton("Search")
        layout.addWidget(self._search_button)

        layout.addStretch()
        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        # Emit filter_changed on any input change
        self._query_input.textChanged.connect(self._on_filter_changed)
        self._score_input.valueChanged.connect(self._on_filter_changed)
        self._include_untagged.stateChanged.connect(self._on_filter_changed)

        # Emit search_triggered on button click
        self._search_button.clicked.connect(self._on_search_triggered)

    def _get_filter_data(self) -> dict:
        """Get current filter criteria as dictionary."""
        return {
            "query": self._query_input.text(),
            "min_score": self._score_input.value(),
            "include_untagged": self._include_untagged.isChecked()
        }

    @Slot()
    def _on_filter_changed(self) -> None:
        """Handle filter criteria change."""
        filter_data = self._get_filter_data()
        logger.debug(f"Filter changed: {filter_data}")
        self.filter_changed.emit(filter_data)

    @Slot()
    def _on_search_triggered(self) -> None:
        """Handle search button click."""
        filter_data = self._get_filter_data()
        logger.info(f"Search triggered with: {filter_data}")
        self.search_triggered.emit(filter_data)

    @Slot(dict)
    def set_filter_criteria(self, criteria: dict) -> None:
        """Set filter criteria programmatically.

        Args:
            criteria: Dictionary with keys: query, min_score, include_untagged
        """
        if "query" in criteria:
            self._query_input.setText(criteria["query"])
        if "min_score" in criteria:
            self._score_input.setValue(criteria["min_score"])
        if "include_untagged" in criteria:
            self._include_untagged.setChecked(criteria["include_untagged"])
```

### Connection in MainWindow

```python
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # Real-time filter updates → Update result count
        self.search_filter.filter_changed.connect(
            self._update_result_count
        )

        # Search triggered → Execute search
        self.search_filter.search_triggered.connect(
            self._execute_search
        )

    @Slot(dict)
    def _update_result_count(self, criteria: dict) -> None:
        """Update result count based on filter."""
        # Preview result count without executing search
        count = self._search_service.count_results(criteria)
        self.status_label.setText(f"{count} images match")

    @Slot(dict)
    def _execute_search(self, criteria: dict) -> None:
        """Execute full search."""
        results = self._search_service.search(criteria)
        self.result_widget.display_results(results)
```

## Example 3: Qt Designer Integration

**Scenario:** Use Qt Designer to create widget UI, then add functionality.

### Step 1: Design UI in Qt Designer

Save as `CustomFilterWidget.ui`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>CustomFilterWidget</class>
 <widget class="QWidget" name="CustomFilterWidget">
  <layout class="QVBoxLayout">
   <item>
    <widget class="QLineEdit" name="queryInput"/>
   </item>
   <item>
    <widget class="QPushButton" name="searchButton">
     <property name="text">
      <string>Search</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
```

### Step 2: Generate Python UI

```bash
cd /workspaces/LoRAIro
uv run python scripts/generate_ui.py
```

This creates `CustomFilterWidget_ui.py`.

### Step 3: Implement Widget Class

```python
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot
from .CustomFilterWidget_ui import Ui_CustomFilterWidget
from loguru import logger

class CustomFilterWidget(QWidget):
    """Custom filter widget using Qt Designer UI.

    Signals:
        search_requested: Emitted when search button clicked (str)
    """

    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Load Qt Designer UI
        self._ui = Ui_CustomFilterWidget()
        self._ui.setupUi(self)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect UI element signals to handlers."""
        self._ui.searchButton.clicked.connect(self._on_search_clicked)
        self._ui.queryInput.returnPressed.connect(self._on_search_clicked)

    @Slot()
    def _on_search_clicked(self) -> None:
        """Handle search button click or Enter key."""
        query = self._ui.queryInput.text()
        if query.strip():
            logger.debug(f"Search requested: {query}")
            self.search_requested.emit(query)
        else:
            logger.warning("Empty search query")

    @Slot(str)
    def set_query(self, query: str) -> None:
        """Set search query programmatically."""
        self._ui.queryInput.setText(query)

    @Slot()
    def clear_query(self) -> None:
        """Clear search query."""
        self._ui.queryInput.clear()
```

## Example 4: Async Worker Integration

**Scenario:** Widget that starts async operation and displays progress.

### Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QProgressBar, QLabel
)
from PySide6.QtCore import Signal, Slot
from src.lorairo.gui.workers.annotation_worker import AnnotationWorker
from loguru import logger

class AnnotationWidget(QWidget):
    """Widget for image annotation with async processing.

    Signals:
        annotation_started: Emitted when annotation starts (int image_id)
        annotation_completed: Emitted when done (int image_id, dict results)
    """

    annotation_started = Signal(int)
    annotation_completed = Signal(int, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._worker_manager = None
        self._current_image_id: Optional[int] = None

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._annotate_button = QPushButton("Start Annotation")
        layout.addWidget(self._annotate_button)

        self._annotate_button.clicked.connect(self._on_annotate_clicked)

        self.setLayout(layout)

    def set_worker_manager(self, worker_manager) -> None:
        """Set worker manager for async operations."""
        self._worker_manager = worker_manager

    @Slot(int)
    def set_image(self, image_id: int) -> None:
        """Set image to annotate."""
        self._current_image_id = image_id
        self._status_label.setText(f"Image {image_id} selected")
        self._annotate_button.setEnabled(True)

    @Slot()
    def _on_annotate_clicked(self) -> None:
        """Start annotation process."""
        if not self._current_image_id:
            logger.warning("No image selected")
            return

        if not self._worker_manager:
            logger.error("Worker manager not set")
            return

        # Create worker
        worker = AnnotationWorker(
            image_id=self._current_image_id,
            model="gpt-4o"
        )

        # Connect worker signals
        worker.signals.started.connect(self._on_worker_started)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.error.connect(self._on_worker_error)

        # Submit to worker manager
        self._worker_manager.submit(worker)

        # Emit signal
        self.annotation_started.emit(self._current_image_id)

    @Slot()
    def _on_worker_started(self) -> None:
        """Handle worker start."""
        self._status_label.setText("Annotation in progress...")
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._annotate_button.setEnabled(False)

    @Slot(int, int)
    def _on_worker_progress(self, current: int, total: int) -> None:
        """Handle worker progress update."""
        progress = int(current / total * 100)
        self._progress_bar.setValue(progress)
        self._status_label.setText(f"Annotating... {progress}%")

    @Slot(object)
    def _on_worker_finished(self, results: dict) -> None:
        """Handle worker completion."""
        logger.info(f"Annotation completed for image {self._current_image_id}")

        self._status_label.setText("Annotation completed")
        self._progress_bar.setVisible(False)
        self._annotate_button.setEnabled(True)

        # Emit completion signal
        self.annotation_completed.emit(self._current_image_id, results)

    @Slot(str)
    def _on_worker_error(self, error_msg: str) -> None:
        """Handle worker error."""
        logger.error(f"Annotation error: {error_msg}")

        self._status_label.setText(f"Error: {error_msg}")
        self._progress_bar.setVisible(False)
        self._annotate_button.setEnabled(True)
```

### Connection in MainWindow

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker_manager = WorkerManager()
        self._setup_widgets()
        self._connect_widgets()

    def _setup_widgets(self) -> None:
        self.annotation_widget = AnnotationWidget()
        self.annotation_widget.set_worker_manager(self._worker_manager)

    def _connect_widgets(self) -> None:
        # Thumbnail → Annotation widget
        self.thumbnail_widget.image_selected.connect(
            lambda metadata: self.annotation_widget.set_image(metadata["id"])
        )

        # Annotation completed → Update database
        self.annotation_widget.annotation_completed.connect(
            self._save_annotation_results
        )

    @Slot(int, dict)
    def _save_annotation_results(self, image_id: int, results: dict) -> None:
        """Save annotation results to database."""
        self._image_repository.update_annotation(image_id, results)
        logger.info(f"Saved annotation results for image {image_id}")
```

## Example 5: Multi-Widget Coordination

**Scenario:** Multiple widgets need to coordinate for complex workflow.

### Implementation

```python
# Widget 1: Image selector
class ImageSelectorWidget(QWidget):
    image_selected = Signal(int)  # image_id

# Widget 2: Annotation control
class AnnotationControlWidget(QWidget):
    annotation_started = Signal(int)   # image_id
    annotation_stopped = Signal(int)   # image_id

    @Slot(int)
    def set_image(self, image_id: int) -> None:
        self._current_image_id = image_id
        self._update_ui()

# Widget 3: Results display
class AnnotationResultsWidget(QWidget):
    @Slot(int, dict)
    def display_results(self, image_id: int, results: dict) -> None:
        self._show_results(results)

# Widget 4: Progress monitor
class ProgressMonitorWidget(QWidget):
    @Slot(int)
    def start_monitoring(self, image_id: int) -> None:
        self._start_timer(image_id)

    @Slot(int)
    def stop_monitoring(self, image_id: int) -> None:
        self._stop_timer()

# MainWindow coordinates all widgets
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # Image selection → Update all widgets
        self.selector.image_selected.connect(
            self.annotation_control.set_image
        )

        # Annotation started → Update progress monitor
        self.annotation_control.annotation_started.connect(
            self.progress_monitor.start_monitoring
        )

        # Annotation completed → Update results and stop progress
        self._annotation_service.annotation_completed.connect(
            self.results_display.display_results
        )
        self._annotation_service.annotation_completed.connect(
            lambda img_id, _: self.progress_monitor.stop_monitoring(img_id)
        )

        # Annotation stopped manually → Stop progress
        self.annotation_control.annotation_stopped.connect(
            self.progress_monitor.stop_monitoring
        )
```

## Testing Examples

### Test Example 1: Signal Emission

```python
import pytest
from PySide6.QtCore import Qt

def test_search_filter_signal_emission(qtbot):
    """Test that filter_changed signal is emitted."""
    widget = SearchFilterWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
        widget._query_input.setText("test query")

    # Verify signal payload
    assert blocker.args[0]["query"] == "test query"
    assert "min_score" in blocker.args[0]
```

### Test Example 2: Widget Interaction

```python
def test_annotation_widget_flow(qtbot):
    """Test complete annotation workflow."""
    widget = AnnotationWidget()
    qtbot.addWidget(widget)

    # Mock worker manager
    mock_manager = MagicMock()
    widget.set_worker_manager(mock_manager)

    # Set image
    widget.set_image(123)

    # Click annotate button
    with qtbot.waitSignal(widget.annotation_started) as blocker:
        qtbot.mouseClick(widget._annotate_button, Qt.LeftButton)

    # Verify signal
    assert blocker.args[0] == 123

    # Verify worker submitted
    mock_manager.submit.assert_called_once()
```

### Test Example 3: Qt Designer Widget

```python
def test_custom_filter_ui_elements(qtbot):
    """Test Qt Designer widget UI elements exist."""
    widget = CustomFilterWidget()
    qtbot.addWidget(widget)

    # Verify UI elements loaded
    assert widget._ui.queryInput is not None
    assert widget._ui.searchButton is not None

    # Verify button enabled
    assert widget._ui.searchButton.isEnabled()
```
