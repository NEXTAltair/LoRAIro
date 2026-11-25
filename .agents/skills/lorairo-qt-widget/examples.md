# ウィジェット実装例

LoRAIro で頻出するウィジェット実装シナリオの具体例をまとめる。

## 例 1: シンプルな表示専用ウィジェット

**シナリオ:** 画像メタデータを読み取り専用で表示するウィジェットを作成する。

### 実装

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

        # グループボックスを作成
        group = QGroupBox("Image Metadata")
        group_layout = QVBoxLayout()

        # ラベルを作成
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

### `MainWindow` での接続

```python
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # サムネイル選択 -> メタデータ表示
        self.thumbnail_widget.image_selected.connect(
            self.metadata_widget.display_metadata
        )

        # クリアボタン -> 表示クリア
        self.clear_button.clicked.connect(
            self.metadata_widget.clear_display
        )
```

## 例 2: 対話的な入力ウィジェット

**シナリオ:** ユーザー入力を受け取り、シグナルを発火する検索フィルターウィジェットを作成する。

### 実装

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

        # 検索クエリ入力
        layout.addWidget(QLabel("Search Query:"))
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Enter search terms...")
        layout.addWidget(self._query_input)

        # 最小スコアフィルター
        layout.addWidget(QLabel("Minimum Score:"))
        self._score_input = QSpinBox()
        self._score_input.setRange(0, 100)
        self._score_input.setValue(50)
        layout.addWidget(self._score_input)

        # タグ未付与画像を含めるチェックボックス
        self._include_untagged = QCheckBox("Include untagged images")
        self._include_untagged.setChecked(True)
        layout.addWidget(self._include_untagged)

        # 検索ボタン
        self._search_button = QPushButton("Search")
        layout.addWidget(self._search_button)

        layout.addStretch()
        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        # 入力変更のたびに filter_changed を発火
        self._query_input.textChanged.connect(self._on_filter_changed)
        self._score_input.valueChanged.connect(self._on_filter_changed)
        self._include_untagged.stateChanged.connect(self._on_filter_changed)

        # ボタン押下で search_triggered を発火
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

### `MainWindow` での接続

```python
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # リアルタイムのフィルター変更 -> 該当件数を更新
        self.search_filter.filter_changed.connect(
            self._update_result_count
        )

        # 検索実行トリガー -> 検索を実行
        self.search_filter.search_triggered.connect(
            self._execute_search
        )

    @Slot(dict)
    def _update_result_count(self, criteria: dict) -> None:
        """Update result count based on filter."""
        # 本検索を実行せず件数だけプレビュー表示する
        count = self._search_service.count_results(criteria)
        self.status_label.setText(f"{count} images match")

    @Slot(dict)
    def _execute_search(self, criteria: dict) -> None:
        """Execute full search."""
        results = self._search_service.search(criteria)
        self.result_widget.display_results(results)
```

## 例 3: Qt Designer との連携

**シナリオ:** Qt Designer でウィジェット UI を設計し、Python クラスから機能を追加する。

### 手順 1: Qt Designer で UI を設計する

`CustomFilterWidget.ui` として保存する。

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

### 手順 2: Python UI コードを生成する

```bash
cd /workspaces/LoRAIro
uv run python scripts/generate_ui.py
```

これにより `CustomFilterWidget_ui.py` が生成される。

### 手順 3: ウィジェットクラスを実装する

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

        # Qt Designer で生成した UI を読み込む
        self._ui = Ui_CustomFilterWidget()
        self._ui.setupUi(self)

        # シグナルを接続する
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

## 例 4: 非同期ワーカーとの連携

**シナリオ:** 非同期処理を開始し、進捗をプログレスバーで表示するウィジェットを作成する。

### 実装

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

        # ワーカーを生成する
        worker = AnnotationWorker(
            image_id=self._current_image_id,
            model="gpt-4o"
        )

        # ワーカーのシグナルを接続する
        worker.signals.started.connect(self._on_worker_started)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.error.connect(self._on_worker_error)

        # ワーカーマネージャーへ投入する
        self._worker_manager.submit(worker)

        # 開始シグナルを発火する
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

        # 完了シグナルを発火する
        self.annotation_completed.emit(self._current_image_id, results)

    @Slot(str)
    def _on_worker_error(self, error_msg: str) -> None:
        """Handle worker error."""
        logger.error(f"Annotation error: {error_msg}")

        self._status_label.setText(f"Error: {error_msg}")
        self._progress_bar.setVisible(False)
        self._annotate_button.setEnabled(True)
```

### `MainWindow` での接続

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
        # サムネイル選択 -> アノテーションウィジェット
        self.thumbnail_widget.image_selected.connect(
            lambda metadata: self.annotation_widget.set_image(metadata["id"])
        )

        # アノテーション完了 -> データベース更新
        self.annotation_widget.annotation_completed.connect(
            self._save_annotation_results
        )

    @Slot(int, dict)
    def _save_annotation_results(self, image_id: int, results: dict) -> None:
        """Save annotation results to database."""
        self._image_repository.update_annotation(image_id, results)
        logger.info(f"Saved annotation results for image {image_id}")
```

## 例 5: 複数ウィジェットの協調動作

**シナリオ:** 複雑なワークフローを実現するため、複数のウィジェットを協調させる。

### 実装

```python
# ウィジェット 1: 画像セレクター
class ImageSelectorWidget(QWidget):
    image_selected = Signal(int)  # image_id

# ウィジェット 2: アノテーション制御
class AnnotationControlWidget(QWidget):
    annotation_started = Signal(int)   # image_id
    annotation_stopped = Signal(int)   # image_id

    @Slot(int)
    def set_image(self, image_id: int) -> None:
        self._current_image_id = image_id
        self._update_ui()

# ウィジェット 3: 結果表示
class AnnotationResultsWidget(QWidget):
    @Slot(int, dict)
    def display_results(self, image_id: int, results: dict) -> None:
        self._show_results(results)

# ウィジェット 4: 進捗モニター
class ProgressMonitorWidget(QWidget):
    @Slot(int)
    def start_monitoring(self, image_id: int) -> None:
        self._start_timer(image_id)

    @Slot(int)
    def stop_monitoring(self, image_id: int) -> None:
        self._stop_timer()

# MainWindow が全ウィジェットの接続を調整する
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # 画像選択 -> 関連ウィジェットを更新
        self.selector.image_selected.connect(
            self.annotation_control.set_image
        )

        # アノテーション開始 -> 進捗監視を開始
        self.annotation_control.annotation_started.connect(
            self.progress_monitor.start_monitoring
        )

        # アノテーション完了 -> 結果表示と進捗監視の停止
        self._annotation_service.annotation_completed.connect(
            self.results_display.display_results
        )
        self._annotation_service.annotation_completed.connect(
            lambda img_id, _: self.progress_monitor.stop_monitoring(img_id)
        )

        # 手動停止 -> 進捗監視を停止
        self.annotation_control.annotation_stopped.connect(
            self.progress_monitor.stop_monitoring
        )
```

## テスト実装例

### テスト例 1: シグナル発火の検証

```python
import pytest
from PySide6.QtCore import Qt

def test_search_filter_signal_emission(qtbot):
    """Test that filter_changed signal is emitted."""
    widget = SearchFilterWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.filter_changed, timeout=1000) as blocker:
        widget._query_input.setText("test query")

    # シグナルのペイロードを検証する
    assert blocker.args[0]["query"] == "test query"
    assert "min_score" in blocker.args[0]
```

### テスト例 2: ウィジェット操作フローの検証

```python
def test_annotation_widget_flow(qtbot):
    """Test complete annotation workflow."""
    widget = AnnotationWidget()
    qtbot.addWidget(widget)

    # ワーカーマネージャーをモック化する
    mock_manager = MagicMock()
    widget.set_worker_manager(mock_manager)

    # 対象画像を設定する
    widget.set_image(123)

    # アノテーション開始ボタンをクリックする
    with qtbot.waitSignal(widget.annotation_started) as blocker:
        qtbot.mouseClick(widget._annotate_button, Qt.LeftButton)

    # シグナル引数を検証する
    assert blocker.args[0] == 123

    # ワーカー投入を検証する
    mock_manager.submit.assert_called_once()
```

### テスト例 3: Qt Designer ウィジェットの検証

```python
def test_custom_filter_ui_elements(qtbot):
    """Test Qt Designer widget UI elements exist."""
    widget = CustomFilterWidget()
    qtbot.addWidget(widget)

    # UI 要素の読み込みを検証する
    assert widget._ui.queryInput is not None
    assert widget._ui.searchButton is not None

    # ボタンの有効状態を検証する
    assert widget._ui.searchButton.isEnabled()
```
