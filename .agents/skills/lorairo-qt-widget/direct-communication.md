# ウィジェット間の直接通信パターン

LoRAIro のウィジェット間直接通信(Direct Widget Communication)パターンは、中間の状態管理層を省き、見通しが良く保守しやすい GUI アーキテクチャを実現する。

## 基本原則

### 1. 中間の状態管理層を置かない

**非推奨:**

```python
# 非推奨: 状態マネージャーを仲介役にする
class ThumbnailWidget(QWidget):
    def _on_clicked(self, index: int) -> None:
        # 状態マネージャー経由の間接通信
        self._state_manager.set_selected_image(index)

class DetailsWidget(QWidget):
    def __init__(self, state_manager):
        self._state_manager = state_manager
        self._state_manager.image_changed.connect(self._update)
```

**推奨:**

```python
# 推奨: ウィジェット同士をシグナルで直接接続する
class ThumbnailWidget(QWidget):
    image_selected = Signal(dict)  # 直接シグナル

    def _on_clicked(self, index: int) -> None:
        metadata = self._images[index]
        self.image_selected.emit(metadata)

class DetailsWidget(QWidget):
    @Slot(dict)
    def display_metadata(self, metadata: dict) -> None:
        self._update_ui(metadata)

# MainWindow で接続する
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        self.thumbnail.image_selected.connect(self.details.display_metadata)
```

### 2. 接続管理を `MainWindow` に集約する

すべてのウィジェット間接続は `MainWindow` の 1 箇所にまとめる。

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._setup_widgets()
        self._connect_widgets()  # 接続を集約する単一の入口

    def _connect_widgets(self) -> None:
        """Centralize all widget connections here."""
        # Thumbnail -> Details
        self.thumbnail_widget.image_selected.connect(
            self.details_widget.display_metadata
        )

        # Thumbnail -> Metadata
        self.thumbnail_widget.image_selected.connect(
            self.metadata_widget.update_metadata
        )

        # Search -> Thumbnail
        self.search_widget.search_completed.connect(
            self.thumbnail_widget.display_results
        )

        # Details -> Annotation Worker
        self.details_widget.annotation_requested.connect(
            self._handle_annotation_request
        )
```

### 3. `connect_to_*` パターン

各ウィジェットに接続専用メソッドを用意する。

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

**`MainWindow` での利用例:**

```python
def _connect_widgets(self) -> None:
    # connect_to_* メソッドで接続する
    self.details_widget.connect_to_thumbnail_widget(self.thumbnail_widget)
    self.details_widget.connect_to_annotation_service(self.annotation_service)
```

## シグナルの型とペイロード

### 基本データ型

```python
class FilterWidget(QWidget):
    # プリミティブ型
    filter_changed = Signal(str)      # フィルター文字列
    count_updated = Signal(int)       # 検索結果件数
    score_threshold = Signal(float)   # スコア閾値
    enabled_changed = Signal(bool)    # 有効/無効の切り替え状態
```

### 複合データ型

```python
class SearchWidget(QWidget):
    # 複合データには辞書を使う
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

### 複数パラメーター

```python
class ThumbnailWidget(QWidget):
    # 型を明示した複数パラメーター
    item_selected = Signal(int, str, dict)  # (index, image_path, metadata)

    def _on_click(self, index: int) -> None:
        path = self._paths[index]
        metadata = self._metadata[index]
        self.item_selected.emit(index, path, metadata)
```

## 実践パターン

### パターン 1: マスター・ディテール

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

### パターン 2: フィルターチェーン

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

### パターン 3: 双方向通信

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
        # Editor -> Status (単方向)
        editor.content_changed.connect(self._update_status)
        editor.save_requested.connect(self._show_saving)

    @Slot(str)
    def _update_status(self, content: str) -> None:
        char_count = len(content)
        self._label.setText(f"{char_count} characters")

# MainWindow
class MainWindow(QMainWindow):
    def _connect_widgets(self) -> None:
        # 双方向: Editor <-> Status
        self.status_widget.connect_to_editor(self.editor_widget)

        # Editor は外部イベントにも応答する
        self.load_button.clicked.connect(
            lambda: self.editor_widget.load_content(self._load_data())
        )
```

## 利点

### 1. データフローの明確化

**変更前(状態マネージャー経由):**

```
ThumbnailWidget -> StateManager -> DetailsWidget
                -> StateManager -> MetadataWidget
                -> StateManager -> StatusWidget
```

シグナルの流れを追いにくく、隠れた依存関係が生まれる。

**変更後(直接通信):**

```
ThumbnailWidget -> DetailsWidget
                -> MetadataWidget
                -> StatusWidget
```

`MainWindow._connect_widgets()` を見れば、すべての接続関係を一目で把握できる。

### 2. 結合度の低減

ウィジェットが `StateManager` の実装に依存しなくなる。

```python
# ウィジェットが自己完結する
class ThumbnailWidget(QWidget):
    image_selected = Signal(dict)  # 自身のシグナルだけを知っていればよい

    # StateManager への依存がない
```

### 3. テストの容易さ

```python
def test_thumbnail_selection(qtbot):
    """Test thumbnail widget independently."""
    thumbnail = ThumbnailWidget()

    with qtbot.waitSignal(thumbnail.image_selected) as blocker:
        qtbot.mouseClick(thumbnail._items[0], Qt.LeftButton)

    # シグナルのペイロードを検証する
    assert blocker.args[0]["id"] == 1
    assert "path" in blocker.args[0]
```

### 4. 配線の柔軟な変更

ウィジェット本体を修正せずに接続先を追加・変更できる。

```python
# 変更前: Details ウィジェットのみ接続
def _connect_widgets(self) -> None:
    self.thumbnail.image_selected.connect(self.details.display_metadata)

# 変更後: Preview ウィジェットを追加しても各ウィジェットの修正は不要
def _connect_widgets(self) -> None:
    self.thumbnail.image_selected.connect(self.preview.show_image)
    self.thumbnail.image_selected.connect(self.details.display_metadata)
```

## 状態管理を使うべき場面

基本は直接通信を優先するが、次の用途では状態管理クラスを使う。

### 1. アプリケーション全体の共有状態

```python
class AppStateManager:
    """Global application state only."""
    current_project = Signal(str)      # プロジェクトパス
    database_connected = Signal(bool)  # DB 接続状態
    config_changed = Signal(dict)      # 設定変更
```

### 2. 永続化が必要なデータ

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

### 3. 多数ウィジェット間の複雑な調整

```python
# 多数のウィジェットが同一データを参照する場合は状態マネージャーを使う
class SearchSessionManager:
    """Coordinate complex search session."""
    search_results = Signal(list)

    def execute_search(self, query: str) -> None:
        # 複数のデータソースを統合する
        results = self._search_database(query)
        results += self._search_tags(query)
        results += self._search_metadata(query)
        self.search_results.emit(results)
```

## アンチパターン

### 循環依存

```python
# 非推奨: 循環するシグナル接続
class WidgetA(QWidget):
    data_changed = Signal(str)

    def connect_to_b(self, b: 'WidgetB') -> None:
        b.data_changed.connect(self._update)  # A -> B

class WidgetB(QWidget):
    data_changed = Signal(str)

    def connect_to_a(self, a: WidgetA) -> None:
        a.data_changed.connect(self._update)  # B -> A

# シグナルの無限ループを引き起こす
```

**対処法:** 単方向データフローにするか、Mediator パターンを導入する。

### 深すぎるシグナル連鎖

```python
# 非推奨: 長いシグナルチェーン
WidgetA -> WidgetB -> WidgetC -> WidgetD -> WidgetE

# デバッグが難しく、変更に弱い
```

**対処法:** 直接接続に切り替えるか、調整役のコーディネーターを導入する。

### シグナルペイロードの破壊的変更

```python
# 非推奨: 受け取ったペイロードを直接書き換える
class SenderWidget(QWidget):
    data_sent = Signal(dict)

    def send_data(self) -> None:
        data = {"value": 10}
        self.data_sent.emit(data)

class ReceiverWidget(QWidget):
    @Slot(dict)
    def receive_data(self, data: dict) -> None:
        data["value"] = 20  # 元の辞書を書き換えてしまう
```

**対処法:** イミュータブルなデータを渡すか、コピーを作成して扱う。

## まとめ

**ウィジェット間直接通信の利点:**

- データフローが明示的で追いやすい
- ウィジェット間の結合度を下げられる
- テストと保守が容易になる
- 接続の組み替えに柔軟に対応できる

**実装の要点:**

1. ウィジェットに型を明示したシグナルを定義する
2. 接続処理は `MainWindow` に集約する
3. `connect_to_*` メソッドを提供する
4. 不要な中間状態層を避ける
5. 状態管理はグローバル状態や永続データに限定する
