# GUI致命的初期化テスト - 最終実装計画（行番号レベル詳細版）

**作成日**: 2025-11-20  
**前回計画の問題**: 再利用不可能性、設計変更影響、エラー伝播の具体化不足  
**本計画**: ユーザー指摘3点を完全解決、行番号レベルの詳細実装

---

## 1. 問題点の確認と解決方針

### 1.1 critical_failure_hooksの再利用不可能性 ✅ 解決

**問題**:
- 現在: `tests/integration/gui/test_mainwindow_critical_initialization.py:24-73`内のクラスフィクスチャ
- パッチ先が`"lorairo.gui.window.main_window"`固定
- 他のテストファイルからインポート不可

**解決策**:
- `tests/conftest.py:524以降`に汎用版フィクスチャを追加
- `request.param`でパッチ先モジュールを引数化
- 関数スコープフィクスチャに変更（`self`削除）

### 1.2 sys.exit(1)統一の設計変更影響 ✅ 解決

**問題**:
- DatasetExportWidget等は`_handle_error`でQMessageBox表示→継続
- sys.exit(1)統一はUX悪化（部分的機能障害でアプリ終了）

**解決策: ハイブリッド方式**
- **致命的初期化エラー（__init__内）**: `CriticalInitializationError`例外発生
- **ランタイムエラー（実行時）**: 既存の`_handle_error`パターン継続
- **MainWindowのみ**: `_handle_critical_initialization_failure`でsys.exit(1)

### 1.3 エラー伝播の具体化不足 ✅ 解決

**問題**:
- try/exceptで例外を握りつぶし（logger.error/warningのみ）
- `_handle_critical_initialization_failure`呼び出しステップが不明

**解決策**:
- try/exceptを除去または再構成
- `CriticalInitializationError`として例外を再発生
- 具体的な変更箇所を行番号レベルで明記

---

## 2. critical_failure_hooks移動計画

### 2.1 移動元・移動先

**移動元**: `tests/integration/gui/test_mainwindow_critical_initialization.py:24-73`

**移動先**: `tests/conftest.py:524以降`（既存フィクスチャの後）

### 2.2 実装コード

**追加コード** (`tests/conftest.py:524以降`):

```python
# --- GUI Critical Initialization Test Fixtures ---

@pytest.fixture(scope="function")
def critical_failure_hooks(monkeypatch, request):
    """致命的失敗時のhookをモック（再利用可能版）
    
    Args:
        monkeypatch: pytestのmonkeypatchフィクスチャ
        request: pytestのrequestフィクスチャ（パラメータ取得用）
    
    Returns:
        dict: モック呼び出しを記録する辞書
            - "sys_exit": sys.exit()の呼び出し記録
            - "messagebox_instances": QMessageBox関連の呼び出し記録
            - "logger": モック化されたlogger
    
    Usage:
        # デフォルト（main_window用）
        def test_mainwindow_failure(critical_failure_hooks):
            # ...
        
        # パラメータ指定（他のウィジェット用）
        @pytest.mark.parametrize("critical_failure_hooks", [
            {"patch_target": "lorairo.gui.widgets.dataset_export_widget"}
        ], indirect=True)
        def test_widget_failure(critical_failure_hooks):
            # ...
    """
    # パッチ対象モジュールを取得（デフォルト: main_window）
    patch_params = getattr(request, "param", {})
    patch_target = patch_params.get("patch_target", "lorairo.gui.window.main_window")
    
    calls = {
        "sys_exit": [],
        "messagebox_instances": [],
        "logger": MagicMock(),
    }
    
    # sys.exitをモック（SystemExit例外を発生させる）
    def mock_sys_exit(code):
        calls["sys_exit"].append(code)
        raise SystemExit(code)
    
    import sys
    monkeypatch.setattr(sys, "exit", mock_sys_exit)
    
    # QMessageBoxをモック（ヘッドレス環境対応）
    def _create_mock_messagebox(*_args, **_kwargs):
        instance = Mock()
        calls["messagebox_instances"].append(instance)
        return instance
    
    mock_messagebox_class = Mock(side_effect=_create_mock_messagebox)
    mock_icon = Mock()
    mock_icon.Critical = Mock()
    mock_messagebox_class.Icon = mock_icon
    
    # パッチ先を引数化
    monkeypatch.setattr(f"{patch_target}.QMessageBox", mock_messagebox_class)
    monkeypatch.setattr(f"{patch_target}.logger", calls["logger"])
    
    return calls
```

### 2.3 既存テストの修正

**ファイル**: `tests/integration/gui/test_mainwindow_critical_initialization.py`

**変更1**: 行24-73の`critical_failure_hooks`フィクスチャを削除（conftest.pyに移動）

**変更2**: クラスメソッドから関数ベーステストに変更

**変更前**:
```python
class TestMainWindowCriticalInitialization:
    @pytest.fixture
    def critical_failure_hooks(self, monkeypatch):
        # ... (削除)
    
    def test_configuration_service_initialization_failure(self, qtbot, critical_failure_hooks, monkeypatch):
        # ...
```

**変更後**:
```python
@pytest.mark.integration
@pytest.mark.gui
class TestMainWindowCriticalInitialization:
    # critical_failure_hooksフィクスチャを削除（conftest.pyから取得）
    
    def test_configuration_service_initialization_failure(qtbot, critical_failure_hooks, monkeypatch):
        # ← selfを削除
        # ...
```

**影響範囲**: 全7テストメソッドで`self`を削除

---

## 3. ウィジェット実装変更（行番号レベル）

### 3.1 AnnotationControlWidget

**ファイル**: `src/lorairo/gui/widgets/annotation_control_widget.py`

#### 変更1: カスタム例外定義追加（行1-22の後）

**追加位置**: 行22の後（インポート直後）

**追加コード**:
```python
# カスタム例外定義
class CriticalInitializationError(Exception):
    """致命的初期化エラー（ウィジェット初期化失敗）"""
    
    def __init__(self, component_name: str, original_error: Exception):
        self.component_name = component_name
        self.original_error = original_error
        super().__init__(f"{component_name} initialization failed: {original_error}")
```

#### 変更2: _setup_model_table_widget修正（行100-112）

**変更前**:
```python
def _setup_model_table_widget(self) -> None:
    """ModelSelectionTableWidgetの設定と接続"""
    try:
        # ModelSelectionTableWidgetのシグナル接続
        self.modelSelectionTable.model_selection_changed.connect(self._on_model_selection_changed)
        self.modelSelectionTable.selection_count_changed.connect(self._on_selection_count_changed)
        self.modelSelectionTable.models_loaded.connect(self._on_models_loaded)
        
        logger.debug("ModelSelectionTableWidget setup completed")
    
    except Exception as e:
        logger.error(f"Error setting up ModelSelectionTableWidget: {e}", exc_info=True)
```

**変更後**:
```python
def _setup_model_table_widget(self) -> None:
    """ModelSelectionTableWidgetの設定と接続
    
    Raises:
        CriticalInitializationError: ModelSelectionTableWidget設定失敗時
    """
    try:
        # ModelSelectionTableWidgetのシグナル接続
        self.modelSelectionTable.model_selection_changed.connect(self._on_model_selection_changed)
        self.modelSelectionTable.selection_count_changed.connect(self._on_selection_count_changed)
        self.modelSelectionTable.models_loaded.connect(self._on_models_loaded)
        
        logger.debug("ModelSelectionTableWidget setup completed")
    
    except Exception as e:
        logger.critical(f"Critical error during ModelSelectionTableWidget setup: {e}", exc_info=True)
        raise CriticalInitializationError("ModelSelectionTableWidget", e) from e
```

#### 変更3: __init__の例外ハンドリング（行50-72）

**変更前**:
```python
def __init__(
    self,
    parent: QWidget | None = None,
):
    super().__init__(parent)
    self.setupUi(self)  # type: ignore
    
    # 依存関係（Phase 1パターン継承）
    self.search_filter_service: SearchFilterService | None = None
    
    # 現在の設定
    self.current_settings: AnnotationSettings = AnnotationSettings(
        selected_function_types=["caption", "tags", "scores"],
        selected_providers=["web_api", "local"],
        selected_models=[],
    )
    
    # UI初期化
    self._setup_connections()
    self._setup_widget_properties()
    self._setup_model_table_widget()
    
    logger.debug("AnnotationControlWidget initialized (ModelSelectionTableWidget integrated)")
```

**変更後**:
```python
def __init__(
    self,
    parent: QWidget | None = None,
):
    """AnnotationControlWidgetの初期化
    
    Args:
        parent: 親ウィジェット
    
    Raises:
        CriticalInitializationError: 致命的初期化エラー発生時
    """
    super().__init__(parent)
    self.setupUi(self)  # type: ignore
    
    # 依存関係（Phase 1パターン継承）
    self.search_filter_service: SearchFilterService | None = None
    
    # 現在の設定
    self.current_settings: AnnotationSettings = AnnotationSettings(
        selected_function_types=["caption", "tags", "scores"],
        selected_providers=["web_api", "local"],
        selected_models=[],
    )
    
    # UI初期化（例外伝播を許可）
    try:
        self._setup_connections()
        self._setup_widget_properties()
        self._setup_model_table_widget()  # CriticalInitializationErrorが発生する可能性
        
        logger.debug("AnnotationControlWidget initialized (ModelSelectionTableWidget integrated)")
    
    except CriticalInitializationError:
        # カスタム例外はそのまま再発生
        raise
    except Exception as e:
        # 予期しない例外はCriticalInitializationErrorに変換
        logger.critical(f"Unexpected error during AnnotationControlWidget initialization: {e}", exc_info=True)
        raise CriticalInitializationError("AnnotationControlWidget", e) from e
```

### 3.2 ModelSelectionTableWidget

**ファイル**: `src/lorairo/gui/widgets/model_selection_table_widget.py`

#### 変更: load_models修正（行96-120）

**変更前**:
```python
def load_models(self) -> None:
    """モデル情報をSearchFilterService経由で取得"""
    if not self.search_filter_service:
        logger.warning("SearchFilterService not available for model loading")
        self.all_models = []
        self._update_table_display()
        return
    
    try:
        self.all_models = self.search_filter_service.get_annotation_models_list()
        logger.info(f"Loaded {len(self.all_models)} models via SearchFilterService")
        
        self.filtered_models = self.all_models.copy()
        self._update_table_display()
        
        self.models_loaded.emit(len(self.all_models))
    
    except Exception as e:
        logger.error(f"Failed to load models via SearchFilterService: {e}", exc_info=True)
        self.all_models = []
        self.filtered_models = []
        self._update_table_display()
```

**変更後**:
```python
def load_models(self) -> None:
    """モデル情報をSearchFilterService経由で取得
    
    Raises:
        RuntimeError: SearchFilterServiceが設定されていない場合
        Exception: モデル取得失敗時
    
    Note:
        このメソッドは初期化時に呼ばれるため、例外は呼び出し側（AnnotationControlWidget）で
        CriticalInitializationErrorに変換される。
    """
    if not self.search_filter_service:
        error_msg = "SearchFilterService not available for model loading"
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    try:
        self.all_models = self.search_filter_service.get_annotation_models_list()
        logger.info(f"Loaded {len(self.all_models)} models via SearchFilterService")
        
        self.filtered_models = self.all_models.copy()
        self._update_table_display()
        
        self.models_loaded.emit(len(self.all_models))
    
    except Exception as e:
        logger.critical(f"Failed to load models via SearchFilterService: {e}", exc_info=True)
        raise
```

### 3.3 DatasetExportWidget

**ファイル**: `src/lorairo/gui/widgets/dataset_export_widget.py`

**変更**: **変更不要**

**理由**:
- 初期化時に致命的エラーが発生しない設計
- `_handle_error`はランタイムエラー用（検証失敗等）
- ユーザーが修正して再実行可能→sys.exit(1)不要

---

## 4. テスト実装計画

### 4.1 新規テストファイル1: AnnotationControlWidget

**ファイルパス**: `tests/integration/gui/widgets/test_annotation_control_widget_critical_initialization.py`（新規作成）

**実装コード**:
```python
"""AnnotationControlWidget致命的初期化エラーテスト

テスト対象:
- ModelSelectionTableWidget設定失敗時のCriticalInitializationError発生
- SearchFilterService未設定時のエラー
- シグナル接続失敗時のエラー
"""

import pytest
from unittest.mock import Mock, MagicMock

from lorairo.gui.widgets.annotation_control_widget import (
    AnnotationControlWidget,
    CriticalInitializationError,
)


@pytest.mark.integration
@pytest.mark.gui
class TestAnnotationControlWidgetCriticalInitialization:
    """AnnotationControlWidget致命的初期化エラーテスト"""

    def test_model_selection_table_signal_connection_failure(self, qtbot, monkeypatch):
        """ModelSelectionTableWidgetシグナル接続失敗時のCriticalInitializationError発生テスト"""
        # setupUi()をモック（modelSelectionTableを不完全な状態で作成）
        def mock_setupui(ui_self, widget_instance):
            mock_table = Mock(spec=[])  # 空のspecでシグナル不存在
            widget_instance.modelSelectionTable = mock_table
            
            # 他の必須属性
            widget_instance.checkBoxCaption = Mock()
            widget_instance.checkBoxTagger = Mock()
            widget_instance.checkBoxScorer = Mock()
            widget_instance.checkBoxWebAPI = Mock()
            widget_instance.checkBoxLocal = Mock()
            widget_instance.checkBoxLowResolution = Mock()
            widget_instance.checkBoxBatchMode = Mock()
            widget_instance.pushButtonStart = Mock()
        
        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui,
        )
        
        # AnnotationControlWidget初期化を試みる（CriticalInitializationError発生）
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = AnnotationControlWidget()
            qtbot.addWidget(widget)
        
        # 検証
        assert exc_info.value.component_name == "ModelSelectionTableWidget"
        assert exc_info.value.original_error is not None

    def test_search_filter_service_not_set_on_load_models(self, qtbot, monkeypatch):
        """SearchFilterService未設定時のload_models()失敗テスト"""
        def mock_setupui(ui_self, widget_instance):
            mock_table = MagicMock()
            mock_table.load_models.side_effect = RuntimeError("SearchFilterService not available for model loading")
            widget_instance.modelSelectionTable = mock_table
            
            # 他の必須属性
            widget_instance.checkBoxCaption = Mock()
            widget_instance.checkBoxTagger = Mock()
            widget_instance.checkBoxScorer = Mock()
            widget_instance.checkBoxWebAPI = Mock()
            widget_instance.checkBoxLocal = Mock()
            widget_instance.checkBoxLowResolution = Mock()
            widget_instance.checkBoxBatchMode = Mock()
            widget_instance.pushButtonStart = Mock()
        
        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui,
        )
        
        widget = AnnotationControlWidget()
        qtbot.addWidget(widget)
        
        mock_service = Mock()
        
        with pytest.raises(RuntimeError) as exc_info:
            widget.set_search_filter_service(mock_service)
        
        assert "SearchFilterService not available" in str(exc_info.value)

    def test_unexpected_error_during_initialization(self, qtbot, monkeypatch):
        """予期しないエラー発生時のCriticalInitializationError変換テスト"""
        def mock_setupui_with_unexpected_error(ui_self, widget_instance):
            raise ValueError("Unexpected error during setupUi")
        
        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui_with_unexpected_error,
        )
        
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = AnnotationControlWidget()
            qtbot.addWidget(widget)
        
        assert exc_info.value.component_name == "AnnotationControlWidget"
        assert isinstance(exc_info.value.original_error, ValueError)
```

### 4.2 新規テストファイル2: ModelSelectionTableWidget

**ファイルパス**: `tests/integration/gui/widgets/test_model_selection_table_widget_critical_initialization.py`（新規作成）

**実装コード**:
```python
"""ModelSelectionTableWidget致命的初期化エラーテスト

テスト対象:
- SearchFilterService未設定時のload_models()失敗
- モデル取得失敗時の例外伝播
"""

import pytest
from unittest.mock import Mock

from lorairo.gui.widgets.model_selection_table_widget import ModelSelectionTableWidget


@pytest.mark.integration
@pytest.mark.gui
class TestModelSelectionTableWidgetCriticalInitialization:
    """ModelSelectionTableWidget致命的初期化エラーテスト"""

    def test_load_models_without_search_filter_service(self, qtbot):
        """SearchFilterService未設定時のload_models()失敗テスト"""
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)
        
        with pytest.raises(RuntimeError) as exc_info:
            widget.load_models()
        
        assert "SearchFilterService not available" in str(exc_info.value)

    def test_load_models_service_exception_propagation(self, qtbot):
        """SearchFilterService.get_annotation_models_list()失敗時の例外伝播テスト"""
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)
        
        mock_service = Mock()
        mock_service.get_annotation_models_list.side_effect = ConnectionError("API connection failed")
        
        widget.set_search_filter_service(mock_service)
        
        with pytest.raises(ConnectionError) as exc_info:
            widget.load_models()
        
        assert isinstance(exc_info.value, ConnectionError)
        assert "API connection failed" in str(exc_info.value)

    def test_load_models_empty_list_handling(self, qtbot):
        """モデルリストが空の場合の正常動作テスト"""
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)
        
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = []
        
        widget.set_search_filter_service(mock_service)
        
        models_loaded_count = []
        widget.models_loaded.connect(lambda count: models_loaded_count.append(count))
        
        widget.load_models()
        
        assert len(models_loaded_count) == 1
        assert models_loaded_count[0] == 0
        assert widget.all_models == []
```

---

## 5. 実装工数見積もり

| ステップ | 作業内容 | 見積時間 |
|---------|---------|---------|
| 1. conftest.py修正 | critical_failure_hooksフィクスチャ追加 | 30分 |
| 2. AnnotationControlWidget修正 | CriticalInitializationError追加、__init__修正 | 1時間 |
| 3. ModelSelectionTableWidget修正 | load_models()例外伝播修正 | 30分 |
| 4. 既存テスト修正 | test_mainwindow_critical_initialization.py | 30分 |
| 5. 新規テスト作成1 | test_annotation_control_widget_critical_initialization.py | 1.5時間 |
| 6. 新規テスト作成2 | test_model_selection_table_widget_critical_initialization.py | 1時間 |
| 7. テスト実行・デバッグ | 全テスト実行、修正 | 1.5時間 |
| **合計** | | **6.5時間** |

---

## 6. 変更対象ファイル一覧

### 実装変更（3ファイル）

1. **tests/conftest.py**
   - 行524以降に`critical_failure_hooks`フィクスチャ追加

2. **src/lorairo/gui/widgets/annotation_control_widget.py**
   - 行22以降: `CriticalInitializationError`定義追加
   - 行50-72: `__init__`の例外ハンドリング追加
   - 行100-112: `_setup_model_table_widget`の例外伝播修正

3. **src/lorairo/gui/widgets/model_selection_table_widget.py**
   - 行96-120: `load_models`の例外伝播修正

### テスト追加（2ファイル）

4. **tests/integration/gui/widgets/test_annotation_control_widget_critical_initialization.py**（新規）
   - 3テストケース

5. **tests/integration/gui/widgets/test_model_selection_table_widget_critical_initialization.py**（新規）
   - 3テストケース

### テスト修正（1ファイル）

6. **tests/integration/gui/test_mainwindow_critical_initialization.py**
   - 行24-73: `critical_failure_hooks`フィクスチャ削除
   - 全7テストメソッド: `self`引数削除

---

## 7. テスト実行コマンド

```bash
# 新規テストのみ実行
uv run pytest tests/integration/gui/widgets/ -v

# 既存テスト含め全実行
uv run pytest tests/integration/gui/ -v -m integration

# カバレッジ確認
uv run pytest tests/integration/gui/ --cov=src/lorairo/gui/widgets --cov-report=term-missing
```

---

## 8. 期待される成果

### カバレッジ目標

| コンポーネント | 現在 | 目標 | 新規テスト数 |
|--------------|------|------|------------|
| MainWindow | 90%+ | 90%+ 維持 | 0（既存7テスト維持） |
| AnnotationControlWidget | - | 85%+ | 3テスト |
| ModelSelectionTableWidget | - | 80%+ | 3テスト |

### 品質向上

- 致命的初期化エラーの検出可能性向上
- テスト容易性向上（`pytest.raises`で明確な検証）
- 責任分離明確化（ウィジェット=検出、呼び出し側=処理）

---

**作成日**: 2025-11-20  
**次のアクション**: 実装開始の承認待ち