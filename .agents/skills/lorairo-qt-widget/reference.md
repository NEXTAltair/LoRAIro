# PySide6 Widget Reference

Complete reference for PySide6 widget development in LoRAIro.

## Signal/Slot API

### Signal Declaration

**Basic syntax:**
```python
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    # No parameters
    action_triggered = Signal()

    # Single parameter
    value_changed = Signal(int)
    text_changed = Signal(str)
    data_updated = Signal(dict)

    # Multiple parameters
    selection_changed = Signal(int, str)
    range_selected = Signal(int, int)

    # Multiple overloads
    progress_updated = Signal([int], [int, str])
```

**Type specifications:**
```python
# Python types
signal_str = Signal(str)
signal_int = Signal(int)
signal_float = Signal(float)
signal_bool = Signal(bool)
signal_list = Signal(list)
signal_dict = Signal(dict)

# Qt types
from PySide6.QtCore import QPointF, QSize
signal_point = Signal(QPointF)
signal_size = Signal(QSize)

# Custom types
from typing import Optional
signal_optional = Signal(object)  # For Optional[CustomClass]
```

### Slot Declaration

**Decorator syntax:**
```python
from PySide6.QtCore import Slot

class MyWidget(QWidget):
    # No parameters
    @Slot()
    def handle_action(self) -> None:
        pass

    # Single parameter
    @Slot(int)
    def handle_value(self, value: int) -> None:
        pass

    @Slot(str)
    def handle_text(self, text: str) -> None:
        pass

    # Multiple parameters
    @Slot(int, str)
    def handle_selection(self, index: int, name: str) -> None:
        pass

    # Multiple overloads
    @Slot(int)
    @Slot(int, str)
    def handle_progress(self, value: int, message: str = "") -> None:
        pass
```

### Signal Connection

**Connection syntax:**
```python
# Direct connection
sender.signal_name.connect(receiver.slot_name)

# Lambda connection
sender.signal_name.connect(lambda x: self._process(x))

# Partial connection
from functools import partial
sender.signal_name.connect(partial(self._process, extra_arg="value"))

# Connection with type checking
sender.value_changed[int].connect(receiver.handle_value)
```

**Connection types:**
```python
from PySide6.QtCore import Qt

# Auto connection (default)
sender.signal.connect(receiver.slot)

# Direct connection (same thread, synchronous)
sender.signal.connect(receiver.slot, Qt.DirectConnection)

# Queued connection (cross-thread, asynchronous)
sender.signal.connect(receiver.slot, Qt.QueuedConnection)

# Blocking queued connection (cross-thread, synchronous)
sender.signal.connect(receiver.slot, Qt.BlockingQueuedConnection)
```

**Disconnection:**
```python
# Disconnect specific slot
sender.signal.disconnect(receiver.slot)

# Disconnect all slots
sender.signal.disconnect()

# Check if connected
is_connected = sender.signal.isSignalConnected(receiver.slot)
```

## Qt Designer Workflow

### UI File Structure

**Example .ui file:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>ImageDetailsWidget</class>
 <widget class="QWidget" name="ImageDetailsWidget">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>400</width>
    <height>300</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string>Image Details</string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text">
      <string>Image Information</string>
     </property>
     <property name="font">
      <font>
       <pointsize>12</pointsize>
       <weight>75</weight>
       <bold>true</bold>
      </font>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="pathInput">
     <property name="readOnly">
      <bool>true</bool>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="openButton">
     <property name="text">
      <string>Open</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
```

### UI Generation

**Generate UI Python file:**
```bash
cd /workspaces/LoRAIro
uv run python scripts/generate_ui.py
```

**Manual generation (single file):**
```bash
pyside6-uic src/lorairo/gui/designer/ImageDetailsWidget.ui \
    -o src/lorairo/gui/designer/ImageDetailsWidget_ui.py
```

**Generated UI file structure:**
```python
# ImageDetailsWidget_ui.py (auto-generated)
from PySide6.QtCore import QCoreApplication, QMetaObject, QRect, QSize
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

class Ui_ImageDetailsWidget:
    def setupUi(self, ImageDetailsWidget):
        ImageDetailsWidget.setObjectName("ImageDetailsWidget")
        ImageDetailsWidget.resize(400, 300)

        self.verticalLayout = QVBoxLayout(ImageDetailsWidget)
        self.verticalLayout.setObjectName("verticalLayout")

        self.titleLabel = QLabel(ImageDetailsWidget)
        self.titleLabel.setObjectName("titleLabel")
        self.verticalLayout.addWidget(self.titleLabel)

        self.pathInput = QLineEdit(ImageDetailsWidget)
        self.pathInput.setObjectName("pathInput")
        self.pathInput.setReadOnly(True)
        self.verticalLayout.addWidget(self.pathInput)

        self.openButton = QPushButton(ImageDetailsWidget)
        self.openButton.setObjectName("openButton")
        self.verticalLayout.addWidget(self.openButton)

        self.retranslateUi(ImageDetailsWidget)
        QMetaObject.connectSlotsByName(ImageDetailsWidget)

    def retranslateUi(self, ImageDetailsWidget):
        ImageDetailsWidget.setWindowTitle(
            QCoreApplication.translate("ImageDetailsWidget", "Image Details")
        )
        self.titleLabel.setText(
            QCoreApplication.translate("ImageDetailsWidget", "Image Information")
        )
        self.openButton.setText(
            QCoreApplication.translate("ImageDetailsWidget", "Open")
        )
```

### Using Generated UI

**Pattern 1: Standard usage**
```python
from .ImageDetailsWidget_ui import Ui_ImageDetailsWidget

class ImageDetailsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = Ui_ImageDetailsWidget()
        self._ui.setupUi(self)
        self._connect_signals()

    def _connect_signals(self) -> None:
        self._ui.openButton.clicked.connect(self._on_open_clicked)
        self._ui.pathInput.textChanged.connect(self._on_path_changed)

    @Slot()
    def _on_open_clicked(self) -> None:
        path = self._ui.pathInput.text()
        # Handle open action

    @Slot(str)
    def _on_path_changed(self, text: str) -> None:
        # Handle path change
        pass
```

**Pattern 2: Multiple inheritance (not recommended)**
```python
# Not recommended in LoRAIro
class ImageDetailsWidget(QWidget, Ui_ImageDetailsWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)  # Note: self, not self._ui
```

### Accessing UI Elements

**Via _ui attribute (recommended):**
```python
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._ui = Ui_MyWidget()
        self._ui.setupUi(self)

    def update_display(self, data: dict) -> None:
        # Access via self._ui
        self._ui.titleLabel.setText(data["title"])
        self._ui.pathInput.setText(data["path"])
        self._ui.openButton.setEnabled(data["exists"])
```

**Finding child widgets:**
```python
# Find by object name
button = self.findChild(QPushButton, "openButton")

# Find all children of type
labels = self.findChildren(QLabel)

# Find with specific name pattern
search_inputs = [
    widget for widget in self.findChildren(QLineEdit)
    if "search" in widget.objectName().lower()
]
```

## Common Widget Patterns

### QWidget Base

```python
from PySide6.QtWidgets import QWidget

class CustomWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    # Geometry
    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(400, 300)

    def minimumSizeHint(self) -> QSize:
        """Return minimum size."""
        return QSize(200, 150)

    # Events
    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle paint events."""
        super().paintEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events."""
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close events."""
        # Cleanup
        event.accept()
```

### QMainWindow

```python
from PySide6.QtWidgets import QMainWindow, QMenuBar, QToolBar, QStatusBar

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()

    def _setup_ui(self) -> None:
        self.setWindowTitle("LoRAIro")
        self.resize(1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

    def _setup_menubar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("&Open", self._on_open, "Ctrl+O")
        file_menu.addAction("&Save", self._on_save, "Ctrl+S")
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close, "Ctrl+Q")

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        toolbar.addAction("Open", self._on_open)
        toolbar.addAction("Save", self._on_save)

    def _setup_statusbar(self) -> None:
        statusbar = self.statusBar()
        statusbar.showMessage("Ready")
```

### QDialog

```python
from PySide6.QtWidgets import QDialog, QDialogButtonBox

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # Settings content
        # ...

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    @classmethod
    def get_settings(cls, parent=None) -> Optional[dict]:
        """Show dialog and return settings if accepted."""
        dialog = cls(parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog._get_current_settings()
        return None
```

## Layout Management

### QVBoxLayout / QHBoxLayout

```python
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout

# Vertical layout
layout = QVBoxLayout()
layout.addWidget(widget1)
layout.addWidget(widget2)
layout.addStretch()  # Add spacing
layout.addWidget(widget3)

# Horizontal layout
hlayout = QHBoxLayout()
hlayout.addWidget(left_widget)
hlayout.addWidget(center_widget)
hlayout.addWidget(right_widget)
hlayout.setStretch(1, 1)  # Center widget stretches

# Nested layouts
main_layout = QVBoxLayout()
main_layout.addLayout(hlayout)
main_layout.addWidget(bottom_widget)
```

### QGridLayout

```python
from PySide6.QtWidgets import QGridLayout

layout = QGridLayout()

# addWidget(widget, row, col, rowSpan, colSpan)
layout.addWidget(QLabel("Name:"), 0, 0)
layout.addWidget(QLineEdit(), 0, 1)
layout.addWidget(QLabel("Email:"), 1, 0)
layout.addWidget(QLineEdit(), 1, 1)
layout.addWidget(QPushButton("Submit"), 2, 0, 1, 2)  # Span 2 columns

# Spacing
layout.setSpacing(10)
layout.setContentsMargins(10, 10, 10, 10)
```

### QFormLayout

```python
from PySide6.QtWidgets import QFormLayout

layout = QFormLayout()

# Add rows with labels
layout.addRow("Name:", QLineEdit())
layout.addRow("Email:", QLineEdit())
layout.addRow("Age:", QSpinBox())

# Add separator
layout.addRow(QLabel())

# Add button
layout.addRow(QPushButton("Submit"))
```

## Worker Integration

### Worker Base Class

```python
from PySide6.QtCore import QRunnable, QObject, Signal, Slot

class WorkerSignals(QObject):
    """Worker signal definitions."""
    started = Signal()
    progress = Signal(int, int)  # current, total
    finished = Signal(object)    # result
    error = Signal(str)          # error message

class BaseWorker(QRunnable):
    """Base worker for QThreadPool."""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._is_cancelled = False

    @Slot()
    def run(self) -> None:
        """Execute worker task."""
        try:
            self.signals.started.emit()
            result = self._execute()
            if not self._is_cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            logger.exception("Worker error")
            self.signals.error.emit(str(e))

    def _execute(self):
        """Implement in subclass."""
        raise NotImplementedError

    def cancel(self) -> None:
        """Cancel worker execution."""
        self._is_cancelled = True
```

### Worker Usage in Widget

```python
from PySide6.QtCore import QThreadPool

class ProcessingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._thread_pool = QThreadPool.globalInstance()

    def start_processing(self, data: dict) -> None:
        """Start async processing."""
        worker = ProcessingWorker(data)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)

        self._thread_pool.start(worker)

    @Slot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        progress = int(current / total * 100)
        self._progress_bar.setValue(progress)

    @Slot(object)
    def _on_finished(self, result) -> None:
        logger.info("Processing completed")
        self._display_results(result)

    @Slot(str)
    def _on_error(self, error_msg: str) -> None:
        QMessageBox.warning(self, "Error", error_msg)
```

## Testing with pytest-qt

### Basic Testing

```python
import pytest
from pytestqt.qtbot import QtBot

@pytest.fixture
def widget(qtbot: QtBot):
    """Create widget fixture."""
    w = MyWidget()
    qtbot.addWidget(w)
    return w

def test_widget_initialization(widget):
    """Test widget initializes correctly."""
    assert widget.isVisible()
    assert widget._ui.titleLabel.text() == "Expected Title"

def test_button_click(qtbot, widget):
    """Test button click."""
    qtbot.mouseClick(widget._ui.openButton, Qt.LeftButton)
    # Verify effect
```

### Signal Testing

```python
def test_signal_emission(qtbot, widget):
    """Test signal is emitted."""
    with qtbot.waitSignal(widget.value_changed, timeout=1000) as blocker:
        widget.set_value(42)

    # Verify signal was emitted
    assert blocker.signal_triggered

    # Verify signal arguments
    assert blocker.args[0] == 42

def test_multiple_signals(qtbot, widget):
    """Test multiple signals."""
    with qtbot.waitSignals(
        [widget.signal1, widget.signal2],
        timeout=1000
    ):
        widget.trigger_both()
```

### Async Testing

```python
def test_async_operation(qtbot, widget):
    """Test async worker completion."""
    widget.start_async_operation()

    # Wait for completion signal
    with qtbot.waitSignal(widget.operation_completed, timeout=5000):
        pass  # Wait for signal

    # Verify results
    assert widget.get_results() is not None
```

## File Locations

### LoRAIro Structure

```
src/lorairo/gui/
├── widgets/                 # Custom widget implementations
│   ├── thumbnail_widget.py
│   ├── details_widget.py
│   └── ...
├── designer/                # Qt Designer files
│   ├── MainWindow.ui
│   ├── MainWindow_ui.py    # Generated
│   └── ...
├── window/                  # Main window
│   └── main_window.py
├── workers/                 # Async workers
│   ├── base.py
│   ├── annotation_worker.py
│   └── ...
└── services/                # GUI services
    └── worker_service.py
```

### Import Patterns

```python
# Widget imports
from src.lorairo.gui.widgets.thumbnail_widget import ThumbnailWidget

# Designer UI imports
from src.lorairo.gui.designer.MainWindow_ui import Ui_MainWindow

# Worker imports
from src.lorairo.gui.workers.annotation_worker import AnnotationWorker

# Service imports
from src.lorairo.gui.services.worker_service import WorkerService
```

## Additional Resources

- **Qt Documentation**: https://doc.qt.io/qtforpython/
- **PySide6 API**: https://doc.qt.io/qtforpython/PySide6/QtWidgets/
- **Qt Designer**: https://doc.qt.io/qt-6/qtdesigner-manual.html
- **Signal/Slot**: https://doc.qt.io/qtforpython/overviews/signalsandslots.html
