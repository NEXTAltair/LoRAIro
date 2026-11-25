---
name: lorairo-qt-widget
version: "1.3.0"
description: PySide6 widget technical implementation for LoRAIro GUI. Covers Signal/Slot patterns, Direct Widget Communication, Qt Designer integration, and async workers. For design intent and aesthetics, use interface-design skill first.
metadata:
  short-description: PySide6技術実装(Signal/Slot、Qt Designer)。デザイン意図はinterface-design参照。
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

# LoRAIro 向け PySide6 ウィジェット実装ガイド

Signal/Slot、ウィジェット間の直接通信(Direct Widget Communication)、Qt Designer 連携、非同期ワーカーを含む、PySide6 ウィジェットの技術実装パターンである。

## スキル間の役割分担

本スキルは**技術実装**に特化している。デザインの意図や方針を決めるときは、先に `interface-design` スキルを使う。

| 問い | 本スキル(`lorairo-qt-widget`) | `interface-design` |
|---|---|---|
| シグナルをどう発火するか | 対象 | 対象外 |
| どの色を使うべきか | 対象外 | 対象 |
| ウィジェットクラスをどう構成するか | 対象 | 対象外 |
| どのような質感・手触りにすべきか | 対象外 | 対象 |
| ウィジェット同士をどう接続するか | 対象 | 対象外 |
| この製品ならではの要素は何か | 対象外 | 対象 |

推奨ワークフローは次の順序である。

1. **`interface-design`**: 設計意図・ドメイン・特徴的要素・美観を定義する。
2. **`lorairo-qt-widget`**: 定義した設計を技術構造として実装する。

## 適用場面

- **ウィジェットの新規作成**: 新しい GUI コンポーネントを実装するとき
- **ウィジェットのリファクタリング**: 既存ウィジェットのアーキテクチャを改善するとき
- **Signal/Slot の配線**: ウィジェット間の通信を接続するとき
- **Qt Designer 連携**: `.ui` ファイルを扱うとき
- **ワーカー連携**: ウィジェットから非同期処理を呼び出すとき

## コアパターン

### 1. 基本的なウィジェット構造

標準的なウィジェットのテンプレートは次のとおりである。

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

### 2. ウィジェット間の直接通信(Direct Widget Communication)

LoRAIro では、ウィジェット同士を直接接続するパターンを採用している。

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

パターンの詳細は [direct-communication.md](./direct-communication.md) を参照する。

### 3. 型安全なシグナル

シグナルには必ず具体的な型を指定する。

**推奨: 型を明示したシグナル**

```python
class DataWidget(QWidget):
    data_changed = Signal(str)
    score_updated = Signal(float)
    item_selected = Signal(str, int)  # Multiple params
    metadata_loaded = Signal(dict)    # Complex data
```

**非推奨: 型が曖昧なシグナル**

```python
class BadWidget(QWidget):
    data_changed = Signal()      # Unclear payload
    value_updated = Signal(object)  # Ambiguous type
```

### 4. Qt Designer 連携

`.ui` ファイルを変更したら、次のコマンドで Python コードを再生成する。

```bash
uv run python scripts/generate_ui.py
```

生成された UI クラスの利用例は次のとおりである。

```python
from .ExampleWidget_ui import Ui_ExampleWidget

class ExampleWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._ui = Ui_ExampleWidget()
        self._ui.setupUi(self)
        self._ui.okButton.clicked.connect(self._on_ok_clicked)
```

### 5. 非同期ワーカー連携(`LoRAIroWorkerBase` + `QThread` + `moveToThread`)

ワーカーの実行とライフサイクルは `WorkerManager` や `WorkerService` で調整する。

```python
from lorairo.gui.workers.base import LoRAIroWorkerBase, WorkerProgress
from lorairo.gui.workers.manager import WorkerManager

class MyAsyncWorker(LoRAIroWorkerBase[dict]):
    def __init__(self, data: str) -> None:
        super().__init__()
        self._data = data

    def execute(self) -> dict:
        self._check_cancellation()
        self._report_progress_throttled(50, "処理中...", processed_count=1, total_count=2)
        return {"status": "ok", "data": self._data}

class AsyncWidget(QWidget):
    def __init__(self, worker_manager: WorkerManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker_manager = worker_manager

    def start_async_operation(self) -> None:
        worker = MyAsyncWorker(data="sample")
        worker.progress_updated.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error_occurred.connect(self._on_error)
        self._worker_manager.start_worker("my-async-op", worker)

    @Slot(object)
    def _on_progress(self, progress: WorkerProgress) -> None:
        self._ui.progressBar.setValue(progress.percentage)
```

## LoRAIro の規約

### ファイル構成

- **タブウィジェット(1 タブ = 1 ウィジェット)**: `src/lorairo/gui/tab/`(`search_tab.py`、`annotate_tab.py`、`jobs_tab.py`、`results_tab.py`、`export_tab.py`、`map_tab.py`、`errors_tab.py`、`cli_tab.py`)
- **再利用ウィジェット**: `src/lorairo/gui/widgets/`(`thumbnail_selector_widget.py`、`selected_image_details_widget.py`、`image_preview.py`、`filter_search_panel.py` など)
- **Qt Designer 定義**: `src/lorairo/gui/designer/*.ui`
- **自動生成 UI**: `src/lorairo/gui/designer/*_ui.py`
- **メインウィンドウ(接着剤・オーケストレーター)**: `src/lorairo/gui/window/main_window.py`
- **ワーカーとマネージャー**: `src/lorairo/gui/workers/`(`base.py`、`manager.py`、`annotation_worker.py`、`registration_worker.py`、`search_worker.py`、`thumbnail_worker.py`)
- **GUI サービスとテーマ**: `src/lorairo/gui/services/`(`worker_service.py`)、`src/lorairo/gui/theme.py`

### 命名規則

- **クラス名**: `{Name}Widget`(例: `ThumbnailWidget`)
- **シグナル名**: `{action}_{tense}`(例: `data_changed`、`item_selected`)
- **公開メソッド**: `set_*`、`get_*`、`update_*`
- **非公開メソッド**: `_on_*`(ハンドラー)、`_update_*`(内部更新)
- **スロット**: 必ず `@Slot()` デコレーターを付与する

### 直接通信の原則

1. **仲介層を避ける**: `DatasetStateManager` を経由せず、ウィジェット同士を直接接続する。
2. **`MainWindow` に集約する**: すべてのウィジェット間接続は `_connect_widgets()` にまとめる。
3. **`connect_to_*` パターン**: 接続用メソッドとして `connect_to_{widget}()` を提供する。
4. **型安全性**: すべてのシグナルとスロットで型を明示する。

### ウィジェット合成と `MainWindow` の責務(必須)

画面やタブの構成は**合成(コンポジション)**を基本とし、`MainWindow` は薄く保つ。

- **1 タブ・1 画面につき 1 つの専用ウィジェット**: レイアウト、子ウィジェット、シグナル配線、タブ固有の振る舞い(ピッカー起動、プリセット配線、実行バー構築、パイプライン構成など)は、すべてそのタブウィジェット自身が所有する。
- **`MainWindow` は接着剤(glue / orchestrator)に徹する**: 責務は「タブウィジェットの配置」「サービスの注入」「トップレベルのシグナル接続」の 3 点にとどめる。**タブや画面固有のロジックを `MainWindow` に直接書かない。** 書きたくなったら、対象タブウィジェットへ移す合図である。
- **再利用ウィジェットの切り出し基準**: 実際に複数画面で共有されるものだけを `widgets/` へ切り出す(YAGNI)。`ds/` のような部品ライブラリ用サブパッケージは事前に作らない。デザインとコードの整合性は `theme.py` のトークン整合(#782)と `docs/design/lorairo-design-system/`(Claude Design ミラー)が担い、Qt ウィジェットの配置構成とは独立している。
- **配置の判断基準**: 「タブ間を接着する処理」か「特定タブ固有の処理」かで見極める。固有なら `MainWindow` ではなくタブウィジェットへ、複数画面で再利用するなら `widgets/` へ置く。
- **分割コストの考え方**: ウィジェット分割と合成は Qt の基本設計であり低コストである。「大規模なリファクタリング」と過大評価しない([[feedback_qt_widget_extraction_cheap]])。根拠と全体方針は `docs/architecture.md` の GUI Architecture「Widget composition principle」および `docs/lessons-learned.md`(MainWindow 肥大)を参照する。

## QSS によるスタイリング

`interface-design` スキルで決定したデザイン方針を、Qt Style Sheets(QSS)で適用する。

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

**トークン命名例(`interface-design` 由来):**

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

## レイアウトとサイズの落とし穴

余白・隙間・はみ出しといったレイアウト不具合を対症療法で直すと、別の症状に姿を変えて堂々巡りになる。**まず実測して根本原因を特定する。**

### 実測で余白や隙間の原因を特定する

「スコアカードの下に異常な余白が出る」といった症状を見ても、推測で `addStretch` の追加やサイズポリシーの変更を繰り返してはならない。まず次の値を実測する。

```python
# どのウィジェットが想定より高い・低いかを実測
print(inner.height(), inner.sizeHint().height(), inner.minimumSizeHint().height())
# スクロール領域なら viewport と inner、各子要素の minimumSizeHint を出力して伝播源を探す
```

上詰め(末尾 stretch)・下固定・縦フィットの切り替えは、「下の余白」「セクション間の隙間」「中身のクリップ」の症状を**入れ替えるだけ**にすぎない。原因ウィジェットを特定せずに切り替えると無限ループに陥る(LoRAIro #823→#827→#831→#833→#835 の実例)。

### `heightForWidth` レイアウト(`FlowLayout` 等)をそのまま `widgetResizable=True` の `QScrollArea` に入れない

`FlowLayout` のような折り返しレイアウトは、「最小幅で全アイテムを縦積みした高さ」という過大な `minimumSizeHint` を返す。これが親レイアウトを経由して `widgetResizable=True` のスクロール領域へ伝播すると、Qt がコンテナを `minimumSize` まで引き伸ばす。その結果、コンテンツ末尾に**ビューポートを超える余白と不要なスクロール**が発生する。

対処法は次のとおりである。

- **高さ上限付きの内側 `QScrollArea` に隔離する**: 可変高さの折り返し領域を内側スクロール領域に閉じ込め、親の高さがアイテム数に依存しないよう有界化する。具体的には `setFixedHeight(min(layout.heightForWidth(実幅), 上限))` を設定し、`resizeEvent` で追従させる。
- **手動の縦フィットを避ける**: `setFixedHeight(sizeHint().height())` は、`FlowLayout` の `sizeHint` 過小報告によって**アイテムがクリップ**されるうえ、レイアウト確定前の幅に依存するため使用しない。

### 複雑なレイアウト部品は専用ウィジェットへ切り出す

`sizeHint`・`minimumSizeHint`・`heightForWidth` を内部に閉じた専用ウィジェット(例: `TagChipBox(QWidget)`)へ切り出せば、過大な最小サイズが親へ漏れる事故を構造的に断てる。**Qt においてウィジェット分割と合成は基本設計であり、「大規模なリファクタリング」ではない。** コストを過大評価せず、第一級の選択肢として検討する。

詳細は `docs/lessons-learned.md` の「PySide6 / Qt」セクションを参照する。

## ベストプラクティス

### 推奨事項

- すべてのスロットメソッドに `@Slot()` デコレーターを付ける。
- すべてのメソッドに型ヒントを記述する。
- 公開・非公開メソッドを `_` 接頭辞で明確に区別する。
- ウィジェット間接続には `connect_to_*` メソッドを用意する。
- 重要なイベントは `loguru` でログ出力する。
- `interface-design` で決めたデザイン方針をスタイルに反映する。
- レイアウト変更の前に `height()`・`sizeHint()`・`minimumSizeHint()` を**実測して原因を診断**する。
- 可変高さの折り返しレイアウト(`FlowLayout`)は**高さ上限付きの内側 `QScrollArea` に隔離**し、複雑なレイアウト部品は専用ウィジェットへ切り出してサイズ計算をカプセル化する。

### 禁止事項

- 外部から `widget._ui.button` のような内部 UI 要素へ直接アクセスしない。
- ウィジェット内部に共有状態を保持しない。
- ビジネスロジックをウィジェットに混在させない。
- 長時間かかる処理を UI スレッドで実行しない(ワーカーを使う)。
- 自動接続(auto-connection)に頼らず、明示的な `connect()` を使う。
- 本スキル内でデザイン判断を行わない(`interface-design` を使う)。
- 根本原因を特定せずに、試行錯誤でレイアウト症状を入れ替えない(上詰め・下固定・縦フィットの切り替え)。
- `heightForWidth` レイアウト(`FlowLayout`)を `widgetResizable=True` の `QScrollArea` へ直接配置しない。過大な `minimumSizeHint` が伝播してスクロールコンテナが肥大化する。

## テスト

`pytest-qt` を使ったテストの基本パターンは次のとおりである。

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

## メモリ連携

**実装前:**

```
1. Grep("current-project-status")
2. 既存のウィジェットパターンを確認する
3. interface-design の system.md があれば確認する
```

**実装後:**

```
1. Grep - ウィジェット構造を記録する
```

## 実装例

詳細なウィジェット実装シナリオは [examples.md](./examples.md) を参照する。

## リファレンス

PySide6 API の完全なリファレンスと Qt Designer ワークフローは [reference.md](./reference.md) を参照する。
