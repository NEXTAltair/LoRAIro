# バッチタグタブAIアノテーションバグ修正設計 (2026-02-09)

## 核心バグ

**バッチタグタブ**のアノテーション実行ボタン（`btnAnnotationExecute`）が、
ステージング画像ではなく**ワークスペース選択画像**をアノテーション対象にする。

### 呼び出し経路（現在の問題）
```
btnAnnotationExecute → MainWindow.start_annotation()
  → AnnotationWorkflowController.start_annotation_workflow()
    → SelectionStateService.get_selected_image_paths()
      → DatasetStateManager.selected_image_ids  ← ワークスペースの選択状態
```

## UI構造

```
tabWidgetMainMode (メインタブ)
├── tabWorkspace (ワークスペース)
└── tabBatchTag (バッチタグ)
    └── tabWidgetBatchTagWorkflow (サブタブ)
        ├── tabBatchTagTagAdd (タグ追加)
        │   └── batchTagAddWidget (ステージング画像管理)
        │       ├── _staged_images: OrderedDict[int, tuple[str, str]]
        │       ├── tag_add_requested(image_ids, tag) Signal
        │       └── btnAddTag (tag_add_requestedを発行)
        │
        └── tabBatchTagAnnotation (アノテーション設定)
            └── groupBoxAnnotation
                └── btnAnnotationExecute
                    └── MainWindow.start_annotation()
```

## タブ判定メカニズム

バッチタグタブがアクティブかは以下で判定可能:
```python
self.tabWidgetMainMode.currentIndex() == 1  # tabBatchTagのインデックス
```

または
```python
self.tabWidgetBatchTagWorkflow.currentIndex()  # サブタブ (0=タグ追加, 1=アノテーション)
```

## 設計案比較

### 案A: AnnotationWorkflowControllerに画像パス引数を追加

**実装変更箇所:**
1. `AnnotationWorkflowController.start_annotation_workflow()`に`image_paths`引数を追加
2. `MainWindow.start_annotation()`で引数判定:
   - バッチタグタブ → `batchTagAddWidget._staged_imagesのパスを渡す`
   - ワークスペース → `image_paths=None`（現在の動作）

**具体的なコード変更:**

```python
# annotation_workflow_controller.py
def start_annotation_workflow(
    self,
    selected_models: list[str] | None = None,
    model_selection_callback: Callable[..., str | None] | None = None,
    image_paths: list[str] | None = None,  # ← NEW
) -> None:
    """
    ...
    Args:
        image_paths: 明示的な画像パスリスト（指定時は優先、ワークスペース選択を上書き）
    """
    ...
    # image_paths指定時はそれを使用、未指定時はSelectionStateService経由で取得
    if image_paths is None:
        image_paths = self._get_selected_image_paths()
    else:
        logger.debug(f"画像パス明示指定: {len(image_paths)}件")
    ...

# main_window.py
def start_annotation(self) -> None:
    """アノテーション処理を開始"""
    if not self.annotation_workflow_controller:
        ...
        return

    selected_models: list[str] = []
    if hasattr(self, "batchModelSelection") and self.batchModelSelection:
        selected_models = self.batchModelSelection.get_selected_models()

    # NEW: バッチタグタブ判定
    override_image_paths: list[str] | None = None
    if self.tabWidgetMainMode.currentIndex() == 1:  # tabBatchTagタブ
        batch_widget = getattr(self, "batchTagAddWidget", None)
        if batch_widget and batch_widget._staged_images:
            # ステージング画像のパスを取得
            from lorairo.database.db_core import resolve_stored_path
            override_image_paths = []
            for image_id, (_, stored_path) in batch_widget._staged_images.items():
                if stored_path:
                    override_image_paths.append(str(resolve_stored_path(stored_path)))

    self.annotation_workflow_controller.start_annotation_workflow(
        selected_models=selected_models if selected_models else None,
        model_selection_callback=self._show_model_selection_dialog if not selected_models else None,
        image_paths=override_image_paths,  # ← NEW
    )
```

**メリット:**
- 実装が簡潔で、AnnotationWorkflowControllerの責任を明確に保つ
- バッチタグタブ固有のロジックをMainWindowに閉じ込められる
- SelectionStateServiceの変更が不要

**デメリット:**
- MainWindow.start_annotation()がバッチタグ固有ロジックを含む（職責混在）
- タブ判定値（1）がハードコード化される
- batchTagAddWidget._staged_imagesのprivate属性に直接アクセス（カプセル化違反）

**影響範囲:**
- `AnnotationWorkflowController.start_annotation_workflow()`のシグネチャ変更
- 他の呼び出し箇所への波及（引数不要時はimage_paths=Noneで対応）

---

### 案B: SelectionStateServiceに上書きメソッドを追加

**実装変更箇所:**
1. `SelectionStateService.set_override_image_ids()`メソッドを追加
2. `SelectionStateService.get_selected_images_for_annotation()`を修正して上書き値を優先
3. `MainWindow.start_annotation()`でバッチタグタブ判定時に上書き設定

**具体的なコード変更:**

```python
# selection_state_service.py
class SelectionStateService:
    def __init__(self, ...):
        ...
        self._override_image_ids: list[int] | None = None  # ← NEW

    def set_override_image_ids(self, image_ids: list[int] | None) -> None:
        """アノテーション対象画像IDを一時上書き（バッチタグ用）

        Args:
            image_ids: 上書き画像IDリスト（Noneで解除）
        """
        self._override_image_ids = image_ids
        if image_ids:
            logger.debug(f"画像ID上書き設定: {len(image_ids)}件")
        else:
            logger.debug("画像ID上書き設定を解除")

    def get_selected_images_for_annotation(self) -> list[dict]:
        """アノテーション対象画像取得

        上書き値がある場合は優先的に使用
        """
        if not self.dataset_state_manager:
            raise ValueError("DatasetStateManagerが設定されていません。")

        # NEW: 上書き値優先
        if self._override_image_ids:
            logger.debug(
                f"上書き画像IDから選択画像を取得: {len(self._override_image_ids)}件"
            )
            return self._get_images_by_ids(self._override_image_ids)

        # 既存のフォールバック戦略
        selected_image_ids = self.dataset_state_manager.selected_image_ids
        ...

# main_window.py
def start_annotation(self) -> None:
    """アノテーション処理を開始"""
    if not self.annotation_workflow_controller:
        ...
        return

    selected_models: list[str] = []
    if hasattr(self, "batchModelSelection") and self.batchModelSelection:
        selected_models = self.batchModelSelection.get_selected_models()

    # NEW: バッチタグタブ判定
    if self.tabWidgetMainMode.currentIndex() == 1:  # tabBatchTagタブ
        batch_widget = getattr(self, "batchTagAddWidget", None)
        if batch_widget and batch_widget._staged_images:
            # ステージング画像IDで上書き
            image_ids = list(batch_widget._staged_images.keys())
            if self.selection_state_service:
                self.selection_state_service.set_override_image_ids(image_ids)

    self.annotation_workflow_controller.start_annotation_workflow(
        selected_models=selected_models if selected_models else None,
        model_selection_callback=self._show_model_selection_dialog if not selected_models else None,
    )

    # 上書きを解除（重要：次の呼び出し時に影響しないように）
    if self.selection_state_service:
        self.selection_state_service.set_override_image_ids(None)
```

**メリット:**
- SelectionStateServiceが上書きメカニズムを一元管理
- AnnotationWorkflowControllerの変更不要（互換性を保つ）
- 将来的に他のバッチ処理にも使える設計

**デメリット:**
- SelectionStateServiceが副作用（上書き）を持つ（関数型設計に反する）
- 上書き・解除の管理がMainWindowの責任になる
- タイミングの問題：解除が必要な点でバグが起きやすい

**影響範囲:**
- `SelectionStateService.get_selected_images_for_annotation()`のロジック変更
- 上書き設定・解除のライフサイクル管理が必要

---

### 案C: BatchTagAddWidgetにannotation_requestedシグナルを新設

**実装変更箇所:**
1. `BatchTagAddWidget`に`annotation_requested(image_ids, models)`シグナルを追加
2. `BatchTagAddWidget`に`annotation_requested`シグナル発行メソッドを追加
3. `MainWindow`で`annotation_requested`を`_handle_batch_annotation`に接続
4. AnnotationExecuteボタンをバッチタグ側で制御（AnnotationWorkflowController不要）

**具体的なコード変更:**

```python
# batch_tag_add_widget.py
class BatchTagAddWidget(QWidget):
    # シグナル
    staged_images_changed = Signal(list)
    tag_add_requested = Signal(list, str)
    staging_cleared = Signal()
    annotation_requested = Signal(list, list)  # (image_ids, model_names) ← NEW

    def set_annotation_execution_handler(
        self,
        btn_annotation_execute: QPushButton,
        model_selector: "ModelSelectionWidget",
    ) -> None:
        """アノテーション実行ボタンとモデル選択ウィジェットを接続

        Args:
            btn_annotation_execute: btnAnnotationExecuteボタン
            model_selector: モデル選択ウィジェット（チェックボックス）
        """
        self._btn_annotation_execute = btn_annotation_execute
        self._model_selector = model_selector
        btn_annotation_execute.clicked.connect(self._on_annotation_execute_clicked)
        logger.debug("Annotation execution button connected")

    @Slot()
    def _on_annotation_execute_clicked(self) -> None:
        """アノテーション実行ボタンクリックハンドラ"""
        if not self._staged_images:
            QMessageBox.warning(self, "エラー", "ステージングリストに画像がありません。")
            return

        # モデル選択を取得
        if not hasattr(self, "_model_selector") or not self._model_selector:
            QMessageBox.warning(self, "エラー", "モデル選択が初期化されていません。")
            return

        selected_models = self._model_selector.get_selected_models()
        if not selected_models:
            QMessageBox.warning(self, "エラー", "アノテーションに使用するモデルを選択してください。")
            return

        # annotation_requested シグナル発行
        image_ids = list(self._staged_images.keys())
        logger.info(f"Annotation requested: {len(image_ids)} images, {len(selected_models)} models")
        self.annotation_requested.emit(image_ids, selected_models)

# main_window.py
def _connect_worker_and_services(self) -> None:
    """Phase 3: ワーカーとサービス連携"""
    ...
    # BatchTagAddWidget.annotation_requested 接続（NEW）
    if hasattr(self, "batchTagAddWidget"):
        try:
            batch_widget = self.batchTagAddWidget
            model_selector = getattr(self, "batchModelSelection", None)
            if model_selector:
                batch_widget.set_annotation_execution_handler(
                    self.ui.btnAnnotationExecute,
                    model_selector,
                )
            batch_widget.annotation_requested.connect(self._handle_batch_annotation_requested)
            logger.info("    ✅ BatchTagAddWidget.annotation_requested 接続完了")
        except Exception as e:
            logger.error(f"    ❌ BatchTagAddWidget.annotation_requested 接続失敗: {e}")

def _handle_batch_annotation_requested(
    self,
    image_ids: list[int],
    model_names: list[str],
) -> None:
    """BatchTagAddWidget からのアノテーション要求ハンドラ

    Args:
        image_ids: ステージング画像IDリスト
        model_names: 選択モデル名リスト
    """
    from lorairo.database.db_core import resolve_stored_path

    if not self.annotation_workflow_controller:
        QMessageBox.warning(
            self,
            "エラー",
            "AnnotationWorkflowControllerが初期化されていません。",
        )
        return

    # 画像IDをパスに変換
    image_paths = []
    for image_id in image_ids:
        image_metadata = self.dataset_state_manager.get_image_by_id(image_id)
        if image_metadata:
            stored_path = image_metadata.get("stored_image_path")
            if stored_path:
                image_paths.append(str(resolve_stored_path(stored_path)))

    if not image_paths:
        QMessageBox.warning(self, "エラー", "処理対象の画像パスが取得できませんでした。")
        return

    # AnnotationWorkflowController呼び出し（画像パス明示）
    # ← 案Aと組み合わせる場合はimage_paths引数を使用
    # ← 案Aなしの場合は set_override_image_ids を使用
    self.annotation_workflow_controller.start_annotation_workflow(
        selected_models=model_names,
        model_selection_callback=None,  # モデル選択済みなのでコールバック不要
    )
```

**メリット:**
- BatchTagAddWidgetが自身のアノテーション実行を管理（単一責任）
- MainWindow.start_annotation()との関係を分離（相互干渉なし）
- tag_add_requestedと同じパターンで一貫性がある
- 将来的に別のアノテーション実行パスにも対応可能

**デメリット:**
- 実装コード量が多い（ウィジェット+ハンドラ）
- btnAnnotationExecuteの制御がWidgetとMainWindowで分散
- ボタンハンドラの管理がやや複雑（2つのシグナル経路）

**影響範囲:**
- BatchTagAddWidgetに新メソッド・シグナル追加
- MainWindowに新接続・新ハンドラを追加
- AnnotationWorkflowControllerは変更なし（後方互換）

---

## 推奨案

**案A + 案B のハイブリッド: 軽量版案A（案Bの副作用なし）**

理由:
1. **最小変更**: AnnotationWorkflowControllerに`image_paths`引数を追加するだけ
2. **副作用なし**: SelectionStateServiceの状態変更がない（案Bの問題回避）
3. **主要な職責を保つ**: MainWindowはバッチタグ判定＆パス取得のみ（案Cのバッチ化は不要）
4. **保守性**: ワークスペース・バッチタブの両方が同一の流れで処理される

### 最終推奨実装フロー

```python
# AnnotationWorkflowController のシグネチャ拡張（後方互換）
def start_annotation_workflow(
    self,
    selected_models: list[str] | None = None,
    model_selection_callback: Callable[..., str | None] | None = None,
    image_paths: list[str] | None = None,  # ← NEW: デフォルトNone
) -> None:
    ...
    # image_paths が指定されている場合は優先利用
    if image_paths is None:
        image_paths = self._get_selected_image_paths()
    ...

# MainWindow.start_annotation() の拡張
def start_annotation(self) -> None:
    ...
    override_image_paths: list[str] | None = None

    # バッチタグタブ判定
    if self.tabWidgetMainMode.currentIndex() == 1:
        batch_widget = getattr(self, "batchTagAddWidget", None)
        if batch_widget and batch_widget._staged_images:
            override_image_paths = self._get_staged_image_paths()

    self.annotation_workflow_controller.start_annotation_workflow(
        selected_models=...,
        model_selection_callback=...,
        image_paths=override_image_paths,  # ← NEW
    )

def _get_staged_image_paths(self) -> list[str]:
    """ステージング画像のパスリスト取得"""
    from lorairo.database.db_core import resolve_stored_path

    batch_widget = getattr(self, "batchTagAddWidget", None)
    if not batch_widget or not batch_widget._staged_images:
        return []

    paths = []
    for image_id, (_, stored_path) in batch_widget._staged_images.items():
        if stored_path:
            paths.append(str(resolve_stored_path(stored_path)))
    return paths
```

**最終採用理由:**
- コード変更が最小限（ControllerとMainWindowだけ）
- 既存のワークスペースタブ機能との干渉なし
- テスト対象が明確（image_paths引数のロジック）
- 将来的な拡張に対応可能（他のバッチ処理で同じパターン使用可）
