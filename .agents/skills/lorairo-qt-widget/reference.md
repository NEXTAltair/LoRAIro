# PySide6 ウィジェットリファレンス

LoRAIro における PySide6 ウィジェット開発の完全リファレンスである。

## Signal/Slot API

### シグナル宣言

**基本構文:**

```python
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    # パラメーターなし
    action_triggered = Signal()

    # 単一パラメーター
    value_changed = Signal(int)
    text_changed = Signal(str)
    data_updated = Signal(dict)

    # 複数パラメーター
    selection_changed = Signal(int, str)
    range_selected = Signal(int, int)

    # 複数のオーバーロード
    progress_updated = Signal([int], [int, str])
```

**型指定:**

```python
# Python 標準型
signal_str = Signal(str)
signal_int = Signal(int)
signal_float = Signal(float)
signal_bool = Signal(bool)
signal_list = Signal(list)
signal_dict = Signal(dict)

# Qt 型
from PySide6.QtCore import QPointF, QSize
signal_point = Signal(QPointF)
signal_size = Signal(QSize)

# カスタム型
from typing import Optional
signal_optional = Signal(object)  # Optional[CustomClass] 用
```

### スロット宣言

**デコレーター構文:**

```python
from PySide6.QtCore import Slot

class MyWidget(QWidget):
    # パラメーターなし
    @Slot()
    def handle_action(self) -> None:
        pass

    # 単一パラメーター
    @Slot(int)
    def handle_value(self, value: int) -> None:
        pass

    @Slot(str)
    def handle_text(self, text: str) -> None:
        pass

    # 複数パラメーター
    @Slot(int, str)
    def handle_selection(self, index: int, name: str) -> None:
        pass

    # 複数のオーバーロード
    @Slot(int)
    @Slot(int, str)
    def handle_progress(self, value: int, message: str = "") -> None:
        pass
```

### シグナル接続

**接続構文:**

```python
# 直接接続
sender.signal_name.connect(receiver.slot_name)

# ラムダによる接続
sender.signal_name.connect(lambda x: self._process(x))

# partial による接続
from functools import partial
sender.signal_name.connect(partial(self._process, extra_arg="value"))

# オーバーロード型を明示した接続
sender.value_changed[int].connect(receiver.handle_value)
```

**接続タイプ:**

```python
from PySide6.QtCore import Qt

# 自動接続(既定)
sender.signal.connect(receiver.slot)

# 直接接続(同一スレッド・同期)
sender.signal.connect(receiver.slot, Qt.DirectConnection)

# キュー接続(スレッド間・非同期)
sender.signal.connect(receiver.slot, Qt.QueuedConnection)

# ブロッキングキュー接続(スレッド間・同期)
sender.signal.connect(receiver.slot, Qt.BlockingQueuedConnection)
```

**切断:**

```python
# 特定スロットの切断
sender.signal.disconnect(receiver.slot)

# 全スロットの切断
sender.signal.disconnect()

# 接続状態の確認
is_connected = sender.signal.isSignalConnected(receiver.slot)
```

## Qt Designer ワークフロー

### UI ファイル構造

**`.ui` ファイルの例:**

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

### UI コード生成

**Python UI ファイルの一括生成:**

```bash
cd /workspaces/LoRAIro
uv run python scripts/generate_ui.py
```

**単一ファイルの手動生成:**

```bash
pyside6-uic src/lorairo/gui/designer/ImageDetailsWidget.ui \
    -o src/lorairo/gui/designer/ImageDetailsWidget_ui.py
```

**生成される UI ファイルの構造:**

```python
# ImageDetailsWidget_ui.py (自動生成)
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

### 生成済み UI の利用

**パターン 1: 標準的な利用法(推奨)**

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
        # 開くアクションを処理する

    @Slot(str)
    def _on_path_changed(self, text: str) -> None:
        # パス変更を処理する
        pass
```

**パターン 2: 多重継承(非推奨)**

```python
# LoRAIro では非推奨
class ImageDetailsWidget(QWidget, Ui_ImageDetailsWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)  # self._ui ではなく self に展開される
```

### UI 要素へのアクセス

**`_ui` 属性経由でのアクセス(推奨):**

```python
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._ui = Ui_MyWidget()
        self._ui.setupUi(self)

    def update_display(self, data: dict) -> None:
        # self._ui 経由でアクセスする
        self._ui.titleLabel.setText(data["title"])
        self._ui.pathInput.setText(data["path"])
        self._ui.openButton.setEnabled(data["exists"])
```

**子ウィジェットの検索:**

```python
# オブジェクト名で検索
button = self.findChild(QPushButton, "openButton")

# 指定型の子ウィジェットをすべて取得
labels = self.findChildren(QLabel)

# 特定の命名パターンで絞り込む
search_inputs = [
    widget for widget in self.findChildren(QLineEdit)
    if "search" in widget.objectName().lower()
]
```

## 基本的なウィジェットパターン

### `QWidget` ベース

```python
from PySide6.QtWidgets import QWidget

class CustomWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    # サイズ計算
    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(400, 300)

    def minimumSizeHint(self) -> QSize:
        """Return minimum size."""
        return QSize(200, 150)

    # イベント処理
    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle paint events."""
        super().paintEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events."""
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close events."""
        # 後片付け
        event.accept()
```

### `QMainWindow`

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

        # セントラルウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

    def _setup_menubar(self) -> None:
        menubar = self.menuBar()

        # ファイルメニュー
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

### `QDialog`

```python
from PySide6.QtWidgets import QDialog, QDialogButtonBox

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # 設定コンテンツ
        # ...

        # ボタンボックス
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

## レイアウト管理

### `QVBoxLayout` / `QHBoxLayout`

```python
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout

# 垂直レイアウト
layout = QVBoxLayout()
layout.addWidget(widget1)
layout.addWidget(widget2)
layout.addStretch()  # 余白を追加
layout.addWidget(widget3)

# 水平レイアウト
hlayout = QHBoxLayout()
hlayout.addWidget(left_widget)
hlayout.addWidget(center_widget)
hlayout.addWidget(right_widget)
hlayout.setStretch(1, 1)  # 中央ウィジェットを伸縮させる

# ネストしたレイアウト
main_layout = QVBoxLayout()
main_layout.addLayout(hlayout)
main_layout.addWidget(bottom_widget)
```

### `QGridLayout`

```python
from PySide6.QtWidgets import QGridLayout

layout = QGridLayout()

# addWidget(widget, row, col, rowSpan, colSpan)
layout.addWidget(QLabel("Name:"), 0, 0)
layout.addWidget(QLineEdit(), 0, 1)
layout.addWidget(QLabel("Email:"), 1, 0)
layout.addWidget(QLineEdit(), 1, 1)
layout.addWidget(QPushButton("Submit"), 2, 0, 1, 2)  # 2 列にまたがる配置

# 間隔と余白
layout.setSpacing(10)
layout.setContentsMargins(10, 10, 10, 10)
```

### `QFormLayout`

```python
from PySide6.QtWidgets import QFormLayout

layout = QFormLayout()

# ラベル付き行を追加
layout.addRow("Name:", QLineEdit())
layout.addRow("Email:", QLineEdit())
layout.addRow("Age:", QSpinBox())

# 空行による区切り
layout.addRow(QLabel())

# ボタンを追加
layout.addRow(QPushButton("Submit"))
```

## ワーカー連携

### ワーカー基底クラス

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

### ウィジェットでのワーカー利用

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

## `pytest-qt` によるテスト

### 基本テスト

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
    # 実行結果を検証する
```

### シグナルテスト

```python
def test_signal_emission(qtbot, widget):
    """Test signal is emitted."""
    with qtbot.waitSignal(widget.value_changed, timeout=1000) as blocker:
        widget.set_value(42)

    # シグナルが発火されたことを検証する
    assert blocker.signal_triggered

    # シグナル引数を検証する
    assert blocker.args[0] == 42

def test_multiple_signals(qtbot, widget):
    """Test multiple signals."""
    with qtbot.waitSignals(
        [widget.signal1, widget.signal2],
        timeout=1000
    ):
        widget.trigger_both()
```

### 非同期テスト

```python
def test_async_operation(qtbot, widget):
    """Test async worker completion."""
    widget.start_async_operation()

    # 完了シグナルを待機する
    with qtbot.waitSignal(widget.operation_completed, timeout=5000):
        pass  # シグナル待機

    # 結果を検証する
    assert widget.get_results() is not None
```

## ファイル配置

### LoRAIro のディレクトリ構成

```
src/lorairo/gui/
├── widgets/                 # カスタムウィジェット実装
│   ├── thumbnail_widget.py
│   ├── details_widget.py
│   └── ...
├── designer/                # Qt Designer ファイル
│   ├── MainWindow.ui
│   ├── MainWindow_ui.py     # 自動生成ファイル
│   └── ...
├── window/                  # メインウィンドウ
│   └── main_window.py
├── workers/                 # 非同期ワーカー
│   ├── base.py
│   ├── annotation_worker.py
│   └── ...
└── services/                # GUI サービス
    └── worker_service.py
```

### インポートパターン

```python
# ウィジェットのインポート
from src.lorairo.gui.widgets.thumbnail_widget import ThumbnailWidget

# Designer 生成 UI のインポート
from src.lorairo.gui.designer.MainWindow_ui import Ui_MainWindow

# ワーカーのインポート
from src.lorairo.gui.workers.annotation_worker import AnnotationWorker

# サービスのインポート
from src.lorairo.gui.services.worker_service import WorkerService
```

## 参考資料

- **Qt 公式ドキュメント**: https://doc.qt.io/qtforpython/
- **PySide6 API**: https://doc.qt.io/qtforpython/PySide6/QtWidgets/
- **Qt Designer マニュアル**: https://doc.qt.io/qt-6/qtdesigner-manual.html
- **Signal/Slot 解説**: https://doc.qt.io/qtforpython/overviews/signalsandslots.html
