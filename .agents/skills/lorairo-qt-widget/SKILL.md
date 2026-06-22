---
name: lorairo-qt-widget
version: "1.2.0"
description: PySide6 widget technical implementation for LoRAIro GUI. Covers Signal/Slot patterns, Direct Widget Communication, Qt Designer integration, and async workers. For design intent and aesthetics, use interface-design skill first.
metadata:
  short-description: PySide6技術実装（Signal/Slot、Qt Designer）。デザイン意図はinterface-design参照。
allowed-tools:
  # Code exploration
  - Grep
  - Grep
  # Memory (widget patterns)
  - Grep
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

## Layout & Sizing Pitfalls

レイアウト/サイズの不具合 (余白・隙間・はみ出し) は対症療法で潰すと別の症状に化けて堂々巡りになる。**まず実測して根本原因を特定する。**

### 余白/隙間の原因は実測で特定する

「スコアカード下に異常な余白が出る」のような症状を見たら、推測で `addStretch` 追加やサイズポリシー変更を繰り返さない。次を測る:

```python
# どの widget が想定より高い/低いかを実測
print(inner.height(), inner.sizeHint().height(), inner.minimumSizeHint().height())
# scroll なら viewport vs inner、各子の minimumSizeHint を dump して伝播源を探す
```

トップ詰め (末尾 stretch) ⇄ ボトム固定 ⇄ 縦ハグ は「下の余白 ↔ セクション間の隙間 ↔ 中身のクリップ」を**交換するだけ**。原因 widget を特定せず切り替えると無限ループになる (LoRAIro #823→#827→#831→#833→#835 の実例)。

### `heightForWidth` レイアウト (FlowLayout 等) を `widgetResizable=True` の QScrollArea に入れない (素のままでは)

FlowLayout のような折り返しレイアウトは **`minimumSizeHint` を「最小幅で全アイテム縦積み」した過大値**で報告する。これがネストした親 → `widgetResizable=True` のスクロール領域へ伝播すると、Qt が container を minimumSize まで引き伸ばし、コンテンツ末尾に**ビューポートを超える余白 + 不要スクロール**が出る。

対処:
- **可変高さの折り返し領域は高さ上限付きの内側 `QScrollArea` に隔離**し、親の高さがアイテム数に依存しないよう有界化する (`setFixedHeight(min(layout.heightForWidth(実幅), 上限))`、`resizeEvent` で追従)。
- 手動 `setFixedHeight(sizeHint().height())` での縦ハグは FlowLayout の `sizeHint` 過小報告で**アイテムをクリップ**し、レイアウト確定前 width での timing 依存になるため避ける。

### 込み入ったレイアウト部品は専用ウィジェットへ切り出してカプセル化する

`sizeHint`/`minimumSizeHint`/`heightForWidth` を内部で閉じた専用ウィジェット (例: `TagChipBox(QWidget)`) に切り出せば、過大な最小サイズが親へ漏れる伝播事故を構造的に断てる。**Qt ではウィジェット分割 + composition は基本設計であり「大幅リファクタ」ではない** — コストを過大評価せず第一級の選択肢として検討する。

詳細は `docs/lessons-learned.md` の「PySide6 / Qt」セクション参照。

## Best Practices

**DO:**
- Use `@Slot()` decorator on all slot methods
- Add type hints to all methods
- Separate public/private with `_` prefix
- Provide `connect_to_*` methods for connections
- Log important events with loguru
- Apply styling from interface-design decisions
- **Diagnose layout issues by measurement** (`height()` / `sizeHint()` / `minimumSizeHint()`) before changing layout
- **Isolate variable-height wrap layouts (FlowLayout) in a height-capped inner QScrollArea**; extract complex layout parts into a dedicated widget to encapsulate sizing

**DON'T:**
- Access `widget._ui.button` from outside
- Store shared state in widgets
- Mix business logic into widgets
- Run long operations on UI thread (use workers)
- Rely on auto-connection (explicit `connect()` only)
- Make design decisions here (use interface-design)
- **Trade layout symptoms by trial-and-error** (top-pack ⇄ bottom-anchor ⇄ hug) without finding the root cause
- **Put a `heightForWidth` layout (FlowLayout) directly in a `widgetResizable=True` QScrollArea** — its inflated `minimumSizeHint` propagates and bloats the scroll container

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
1. Grep("current-project-status")
2. Check for existing widget patterns
3. Review interface-design system.md if exists
```

**After implementation:**
```
1. Grep - Record widget structure
```

## Examples

See [examples.md](./examples.md) for detailed widget implementation scenarios.

## Reference

See [reference.md](./reference.md) for complete PySide6 API reference and Qt Designer workflow.
