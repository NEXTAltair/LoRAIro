# Plan: 右パネルレイアウト統合

**Created**: 2026-01-11
**Source**: plan_mode
**Original File**: calm-exploring-owl.md
**Status**: approved

---

## 概要

モックアップ（`scripts/mock_right_panel.py`）に基づき、MainWindowの右パネルレイアウトをシンプル化します。

## 目標

- **タブ数削減**: 3タブ → 2タブ（Rating/Score編集タブを画像詳細タブに統合）
- **UIシンプル化**: 関連情報を1箇所に集約し、タブ切り替えを削減
- **レイアウト最適化**: Stretch比率を3:1:2 → 3:1に変更

## 現状分析

### 現在の構造（MainWindow.ui）

```
framePreviewDetailContent
└── verticalLayout_previewDetailContent (stretch="3,1,2")
    ├── splitterPreviewDetails (QSplitter)
    │   ├── imagePreviewWidget
    │   └── tabWidgetRightPanel (QTabWidget)
    │       ├── [Tab 0] 画像詳細 (selectedImageDetailsWidget)
    │       ├── [Tab 1] Rating/Score編集 (ratingScoreEditWidget) ← 削除対象
    │       └── [Tab 2] バッチタグ追加 (batchTagAddWidget)
    └── groupBoxAnnotationControl (ModelSelectionWidget)
```

### モックアップの構造（mock_right_panel.py）

```
panel
└── layout (stretch: splitter=3, annotation=1)
    ├── splitter (QSplitter)
    │   ├── imagePreviewWidget
    │   └── tabWidget (QTabWidget) - 2タブのみ
    │       ├── [Tab 0] 画像詳細
    │       │   ├── 基本情報表示
    │       │   ├── AnnotationDataDisplay
    │       │   └── RatingScoreEditWidget ← ここに統合
    │       └── [Tab 1] バッチタグ追加
    └── groupBoxAnnotationControl
```

## 変更内容

### Phase 1: Qt Designer UIファイル変更

**ファイル**: `src/lorairo/gui/designer/MainWindow.ui`

1. **tabRatingScoreEdit削除**:
   - `tabWidgetRightPanel`からタブインデックス1を削除
   - `ratingScoreEditWidget`の配置を削除

2. **Stretch比率変更**:
   - `verticalLayout_previewDetailContent`のstretch属性: `"3,1,2"` → `"3,1"`

3. **タブインデックス更新**:
   - 現在: [0]画像詳細、[1]Rating/Score、[2]バッチタグ
   - 変更後: [0]画像詳細、[1]バッチタグ

### Phase 2: SelectedImageDetailsWidget変更

**ファイル**: `src/lorairo/gui/widgets/selected_image_details_widget.py`

1. **groupBoxRatingScore削除**:
   - UIファイルから該当GroupBoxを削除
   - 関連コードを削除

2. **RatingScoreEditWidget統合**:
   - `__init__`でRatingScoreEditWidgetインスタンスを作成
   - `verticalLayoutOverview`内のAnnotationDataDisplayの直後に配置
   - AnnotationDataDisplayにstretch=1を設定

3. **シグナル接続**:
   - RatingScoreEditWidgetの`rating_changed`、`score_changed`シグナルを外部に転送
   - 新規シグナル定義: `rating_changed = Signal(int, str)`、`score_changed = Signal(int, int)`

4. **データ更新メソッド拡張**:
   - `_update_details_display()`内でRatingScoreEditWidgetも更新
   - `populate_from_image_data()`メソッドをRatingScoreEditWidgetに委譲

### Phase 3: MainWindow統合

**ファイル**: `src/lorairo/gui/window/main_window.py`

1. **タブ初期化変更**（`_setup_tab_widget()`）:
   - タブインデックス参照を更新: バッチタグ = 2 → 1
   - Rating/Scoreタブ関連の初期化コードを削除

2. **イベント接続変更**（`_connect_events()`）:
   - `ratingScoreEditWidget`への直接接続を削除
   - `selectedImageDetailsWidget`から転送されるシグナルに接続
   ```python
   # 変更前
   self.ui.ratingScoreEditWidget.rating_changed.connect(self._handle_rating_changed)

   # 変更後
   self.ui.selectedImageDetailsWidget.rating_changed.connect(self._handle_rating_changed)
   ```

3. **タブ切り替え削除**（`_switch_to_edit_tab()`）:
   - このメソッドを削除（Rating/Scoreタブがなくなるため）
   - `actionEditImage`の接続を削除またはダミー化

4. **画像選択時の動作変更**（`_handle_image_selected()`）:
   - タブ切り替えロジックを削除
   - selectedImageDetailsWidget経由でRating/Score更新

### Phase 4: UIファイル再生成

**実行コマンド**:
```bash
uv run python scripts/generate_ui.py
```

## 影響範囲分析

### 変更対象ファイル

1. ✏️ `src/lorairo/gui/designer/MainWindow.ui` - タブ削除、Stretch変更
2. ✏️ `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui` - GroupBox削除
3. ✏️ `src/lorairo/gui/widgets/selected_image_details_widget.py` - Widget統合
4. ✏️ `src/lorairo/gui/window/main_window.py` - イベント接続変更

### 影響を受けるコンポーネント

- ✅ `RatingScoreEditWidget`: 配置場所のみ変更、機能は維持
- ✅ `BatchTagAddWidget`: タブインデックスのみ変更
- ✅ `ImagePreviewWidget`: 影響なし
- ✅ `ModelSelectionWidget`: 影響なし

### 削除される機能

- ❌ Ctrl+Eによる「Rating/Score編集」タブへの切り替え
  - 代替: 画像詳細タブ内で直接編集可能（タブ切り替え不要）

## 実装手順

### Step 1: Qt Designer UIファイル編集

1. MainWindow.ui を Qt Designer で開く
2. tabWidgetRightPanel からタブ1（tabRatingScoreEdit）を削除
3. verticalLayout_previewDetailContent のstretchプロパティを "3,1" に変更
4. 保存

### Step 2: SelectedImageDetailsWidget.ui編集

1. SelectedImageDetailsWidget.ui を Qt Designer で開く
2. groupBoxRatingScore を削除
3. 保存

### Step 3: UIファイル生成

```bash
cd /workspaces/LoRAIro
uv run python scripts/generate_ui.py
```

### Step 4: SelectedImageDetailsWidget実装

```python
# src/lorairo/gui/widgets/selected_image_details_widget.py

from PySide6.QtCore import Signal

class SelectedImageDetailsWidget(QWidget):
    # 新規シグナル定義
    rating_changed = Signal(int, str)  # (image_id, rating)
    score_changed = Signal(int, int)   # (image_id, score)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_SelectedImageDetailsWidget()
        self.ui.setupUi(self)

        # RatingScoreEditWidget統合
        self._rating_score_widget = RatingScoreEditWidget()
        self._integrate_rating_score_widget()

        # シグナル転送
        self._rating_score_widget.rating_changed.connect(self.rating_changed.emit)
        self._rating_score_widget.score_changed.connect(self.score_changed.emit)

    def _integrate_rating_score_widget(self):
        """RatingScoreEditWidgetをAnnotationDataDisplayの直後に配置"""
        target_layout = self.ui.verticalLayoutOverview

        # AnnotationDataDisplayの位置を取得
        annotation_index = target_layout.indexOf(self.ui.annotationDataDisplay)

        # その直後にRatingScoreEditWidgetを挿入
        if annotation_index != -1:
            target_layout.insertWidget(annotation_index + 1, self._rating_score_widget)
        else:
            target_layout.addWidget(self._rating_score_widget)

        # AnnotationDataDisplayにstretch=1を設定（モックアップと同様）
        for index in range(target_layout.count()):
            target_layout.setStretch(index, 0)
        if annotation_index != -1:
            target_layout.setStretch(annotation_index, 1)

    def _update_details_display(self, details: ImageDetails):
        """詳細表示を更新（既存メソッドを拡張）"""
        # 既存の更新処理...

        # RatingScoreEditWidgetも更新
        self._rating_score_widget.populate_from_image_data({
            "id": details.image_id,
            "rating": details.rating_value or "PG-13",
            "score": details.score_value,
        })
```

### Step 5: MainWindow実装変更

```python
# src/lorairo/gui/window/main_window.py

def _setup_tab_widget(self):
    """タブウィジェット初期化"""
    self.ui.tabWidgetRightPanel.setCurrentIndex(0)
    # Rating/Scoreタブ関連の初期化を削除

def _connect_events(self):
    """イベント接続"""
    # 変更前: ratingScoreEditWidgetへの直接接続
    # self.ui.ratingScoreEditWidget.rating_changed.connect(...)

    # 変更後: selectedImageDetailsWidgetから転送されるシグナルに接続
    self.ui.selectedImageDetailsWidget.rating_changed.connect(self._handle_rating_changed)
    self.ui.selectedImageDetailsWidget.score_changed.connect(self._handle_score_changed)

    # actionEditImageの接続を削除
    # self.ui.actionEditImage.triggered.connect(self._switch_to_edit_tab)

def _switch_to_edit_tab(self):
    """このメソッドを削除またはダミー化"""
    pass  # タブ切り替え不要
```

### Step 6: テスト

```bash
# GUIテスト実行
uv run pytest tests/gui/ -v -k "selected_image_details or rating_score or main_window"

# 手動テスト
uv run lorairo
```

## テスト戦略

### 単体テスト

**ファイル**: `tests/gui/widgets/test_selected_image_details_widget.py`

```python
def test_rating_score_widget_integrated(qtbot):
    """RatingScoreEditWidgetが統合されていることを確認"""
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)

    # RatingScoreEditWidgetが存在することを確認
    assert widget._rating_score_widget is not None
    assert widget._rating_score_widget.isVisible()

def test_rating_changed_signal_forwarded(qtbot):
    """rating_changedシグナルが転送されることを確認"""
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.rating_changed, timeout=1000) as blocker:
        widget._rating_score_widget.rating_changed.emit(1, "R-18")

    assert blocker.args == [1, "R-18"]
```

### 統合テスト

**ファイル**: `tests/gui/window/test_main_window.py`

```python
def test_tab_count_reduced(qtbot, main_window):
    """タブ数が2に削減されていることを確認"""
    tab_widget = main_window.ui.tabWidgetRightPanel
    assert tab_widget.count() == 2
    assert tab_widget.tabText(0) == "画像詳細"
    assert tab_widget.tabText(1) == "バッチタグ追加"

def test_rating_editing_in_details_tab(qtbot, main_window):
    """画像詳細タブ内でRating編集が可能であることを確認"""
    # 画像を選択
    main_window._handle_image_selected(1)

    # 画像詳細タブでRating/Score編集ウィジェットが表示されている
    details_widget = main_window.ui.selectedImageDetailsWidget
    assert details_widget._rating_score_widget.isVisible()

    # Rating変更シグナルがMainWindowに届く
    with qtbot.waitSignal(main_window._handle_rating_changed, timeout=1000):
        details_widget._rating_score_widget.rating_changed.emit(1, "R-18")
```

## リスク分析

### 高リスク

1. **既存のキーボードショートカット無効化**
   - 問題: Ctrl+Eが機能しなくなる
   - 対策: actionEditImageを削除せず、画像詳細タブに切り替えるように変更

2. **ユーザーワークフローの変更**
   - 問題: タブ切り替えに慣れたユーザーが混乱する可能性
   - 対策: リリースノートで明確に説明

### 中リスク

1. **シグナル接続の複雑化**
   - 問題: SelectedImageDetailsWidget経由のシグナル転送で遅延の可能性
   - 対策: シグナル転送は直接接続なので遅延は最小限

2. **レイアウトの視覚的バランス**
   - 問題: 3:1比率が画面サイズによっては不適切
   - 対策: Splitterのドラッグで調整可能

### 低リスク

1. **テストコードの更新**
   - 問題: タブインデックス変更で既存テストが失敗
   - 対策: テストコード更新（Step 6で対応）

## 検証方法

### 機能検証

1. ✅ 画像選択時に詳細タブでRating/Score編集が表示される
2. ✅ Rating/Score変更がデータベースに保存される
3. ✅ タブ数が2つになっている
4. ✅ Stretch比率が3:1になっている
5. ✅ Splitterでプレビュー/タブの比率を調整できる

### UI/UX検証

1. ✅ 画像詳細タブ内のレイアウトが適切
2. ✅ AnnotationDataDisplayが伸縮可能（stretch=1）
3. ✅ RatingScoreEditWidgetが適切な位置に配置
4. ✅ スクロールなしで全情報が見える（一般的な解像度）

### パフォーマンス検証

1. ✅ 画像選択時のUI更新が高速（100ms以内）
2. ✅ タブ切り替えがスムーズ
3. ✅ メモリ使用量が増加していない

## ロールバック計画

変更をロールバックする場合：

1. Git履歴から以下のファイルを復元:
   - `src/lorairo/gui/designer/MainWindow.ui`
   - `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui`
   - `src/lorairo/gui/widgets/selected_image_details_widget.py`
   - `src/lorairo/gui/window/main_window.py`

2. UIファイル再生成:
   ```bash
   uv run python scripts/generate_ui.py
   ```

3. テスト実行で確認:
   ```bash
   uv run pytest tests/gui/ -v
   ```

## 参考資料

- モックアップ: [scripts/mock_right_panel.py](scripts/mock_right_panel.py)
- 現在の実装: [src/lorairo/gui/window/main_window.py](src/lorairo/gui/window/main_window.py:688)
- ウィジェット: [src/lorairo/gui/widgets/selected_image_details_widget.py](src/lorairo/gui/widgets/selected_image_details_widget.py)
- UI仕様: [docs/specs/interfaces/gui_interface.md](docs/specs/interfaces/gui_interface.md)