# SearchFilterService致命エラー自動テスト方針の他GUI展開計画

**作成日**: 2025-11-20  
**基準**: MainWindow Phase 2+3.5テストパターン（gui_critical_initialization_testing_expansion_2025_11_19.md）

## Executive Summary

MainWindow Phase 2+3.5で確立された致命的初期化テストパターン(7テスト、100%カバレッジ)を他のGUIコンポーネントに横展開する計画。優先度の高い展開対象は3コンポーネント、合計9テスト追加で致命的初期化経路の完全カバレッジを維持。

---

## 1. 現在の成功パターン要約

### 1.1 Phase 2+3.5テストパターン構造

**テストファイル**: `tests/integration/gui/test_mainwindow_critical_initialization.py`

**カバレッジ**: 致命的初期化経路 7/7 (100%)

| Phase | 対象経路 | テスト数 | 検証項目 |
|-------|---------|---------|---------|
| Phase 2 | サービス初期化 | 2 | ConfigurationService, WorkerService |
| Phase 3.5 | SearchFilterService統合 | 5 | filterSearchPanel, db_manager, Service作成/注入 |

### 1.2 critical_failure_hooks フィクスチャ

**場所**: `tests/integration/gui/test_mainwindow_critical_initialization.py:24-73`

**機能**:
```python
@pytest.fixture
def critical_failure_hooks(self, monkeypatch):
    calls = {
        "sys_exit": [],
        "messagebox_instances": [],
        "logger": MagicMock(),
    }
    
    # 1. sys.exitモック (SystemExit発生)
    def mock_sys_exit(code):
        calls["sys_exit"].append(code)
        raise SystemExit(code)
    
    # 2. QMessageBox.criticalモック (インスタンス記録)
    def _create_mock_messagebox(*_args, **_kwargs):
        instance = Mock()
        calls["messagebox_instances"].append(instance)
        return instance
    
    # 3. loggerモック
    # ...
    
    return calls
```

### 1.3 4項目検証パターン（全7テスト共通）

```python
# 1. sys.exit(1)呼び出し確認
assert len(critical_failure_hooks["sys_exit"]) == 1
assert critical_failure_hooks["sys_exit"][0] == 1

# 2. logger.critical呼び出し確認
critical_failure_hooks["logger"].critical.assert_called()
assert "ComponentName" in str(logger_args)

# 3. QMessageBox表示確認
assert len(critical_failure_hooks["messagebox_instances"]) > 0
messagebox.exec.assert_called()

# 4. エラーメッセージ内容確認
assert "ComponentName" in str(text_args)
```

### 1.4 再利用可能な設計要素

**1. モックフィクスチャの汎用性**
- `critical_failure_hooks` は他のGUIコンポーネントでもそのまま使用可能

**2. 初期化失敗の注入パターン**
```python
# パターンA: コンストラクタ例外
monkeypatch.setattr("path.to.Service", mock_service_init_with_exception)

# パターンB: setupUi()での属性欠落
monkeypatch.setattr("path.to.Ui_Widget.setupUi", mock_setupui)

# パターンC: メソッド呼び出し例外
mock_widget.method.side_effect = RuntimeError("処理失敗")
```

**3. テスト実行速度**
- 全7テスト: 19.02秒 (平均2.7秒/テスト)
- ヘッドレス環境対応 (QT_QPA_PLATFORM=offscreen)

---

## 2. 展開対象リスト（優先順位順）

### 2.1 優先度A: DatasetExportWidget

**ファイル**: `src/lorairo/gui/widgets/dataset_export_widget.py`  
**クラス**: `DatasetExportWidget(QDialog)` (L96-483)

**初期化フロー**:
```python
def __init__(self, service_container, initial_image_ids, parent):
    super().__init__(parent)
    self.ui = Ui_DatasetExportWidget()
    self.ui.setupUi(self)  # Phase 1: UI生成
    
    # Phase 2: サービス初期化
    self.service_container = service_container
    self.export_service = service_container.dataset_export_service()  # 致命的
    
    # Phase 3: UI設定
    self._setup_ui()
    self._connect_signals()
    self._update_initial_state()
```

**致命的初期化経路** (3経路):
1. `service_container.dataset_export_service()` が None
2. `_setup_ui()` で UI要素アクセス失敗
3. `_connect_signals()` でシグナル接続失敗

**複雑度評価**: 中 (3-4時間)

**優先度理由**:
- QDialogパターンの代表例（他のダイアログへの横展開可能）
- ServiceContainer依存の典型例
- エクスポート機能は必須機能

### 2.2 優先度B: AnnotationControlWidget

**ファイル**: `src/lorairo/gui/widgets/annotation_control_widget.py`  
**クラス**: `AnnotationControlWidget(QWidget, Ui_AnnotationControlWidget)` (L39-232)

**初期化フロー**:
```python
def __init__(self, parent):
    super().__init__(parent)
    self.setupUi(self)  # Phase 1: UI生成（多重継承パターン）
    
    # Phase 2: 依存関係初期化
    self.search_filter_service: SearchFilterService | None = None  # 後で注入
    
    # Phase 3: UI初期化
    self._setup_connections()
    self._setup_widget_properties()
    self._setup_model_table_widget()
```

**致命的初期化経路** (3経路):
1. `setupUi(self)` で Qt Designer UI要素欠落
2. `_setup_model_table_widget()` でテーブルウィジェット初期化失敗
3. `SearchFilterService` 注入後の `load_models()` 失敗

**複雑度評価**: 中 (3-4時間)

**優先度理由**:
- SearchFilterService依存（MainWindowと同じパターン）
- 多重継承パターンの代表例
- アノテーション機能の中核ウィジェット

### 2.3 優先度C: ModelSelectionTableWidget

**ファイル**: `src/lorairo/gui/widgets/model_selection_table_widget.py`  
**クラス**: `ModelSelectionTableWidget(QWidget, Ui_ModelSelectionTableWidget)` (L38-265)

**初期化フロー**:
```python
def __init__(self, parent):
    super().__init__(parent)
    self.setupUi(self)  # Phase 1: UI生成
    
    # Phase 2: 依存関係初期化
    self.search_filter_service: SearchFilterService | None = None  # 後で注入
    
    # Phase 3: UI初期化
    self._setup_table_properties()
    self._setup_connections()
```

**致命的初期化経路** (3経路):
1. `setupUi(self)` で tableWidgetModels 欠落
2. `_setup_table_properties()` でテーブルヘッダー設定失敗
3. `SearchFilterService` 注入後の `load_models()` 失敗

**複雑度評価**: 低 (2-3時間)

**優先度理由**:
- AnnotationControlWidget内で使用される
- テーブルウィジェット初期化パターン確立
- 既存単体テスト有り (`test_model_selection_table_widget.py`)

---

## 3. 実装計画（段階的展開）

### Phase 1: DatasetExportWidget (3-4時間)

**目標**: QDialog型の致命的初期化テスト確立

**実装内容**:

1. **実装ファイル修正**:
   - ファイル: `src/lorairo/gui/widgets/dataset_export_widget.py`
   - 追加: `_handle_critical_initialization_failure()` メソッド
   - 修正: 3つの致命的経路にエラーハンドリング追加

2. **テスト作成**:
   - ファイル: `tests/integration/gui/test_dataset_export_widget_critical_initialization.py`
   - フィクスチャ: `critical_failure_hooks` 再利用
   - テストケース:
     - `test_missing_export_service_triggers_critical_failure`
     - `test_setup_ui_exception_triggers_critical_failure`
     - `test_signal_connection_exception_triggers_critical_failure`

3. **検証**:
   - pytest実行で 3/3 テスト合格
   - 致命的経路 100% カバレッジ

**成果物**:
- QDialogパターンのテストテンプレート
- ServiceContainer依存の検証パターン

### Phase 2: AnnotationControlWidget (3-4時間)

**目標**: 多重継承パターン + SearchFilterService注入の検証

**実装内容**:

1. **実装ファイル修正**:
   - ファイル: `src/lorairo/gui/widgets/annotation_control_widget.py`
   - エラーハンドリング追加（setupUi, テーブル初期化, サービス注入）

2. **テスト作成**:
   - ファイル: `tests/integration/gui/test_annotation_control_widget_critical_initialization.py`
   - テストケース:
     - `test_missing_ui_elements_triggers_critical_failure`
     - `test_model_table_widget_initialization_failure`
     - `test_search_filter_service_injection_failure`

**成果物**:
- 多重継承パターンのテストテンプレート
- SearchFilterService注入パターンの検証

### Phase 3: ModelSelectionTableWidget (2-3時間)

**目標**: テーブルウィジェット初期化パターン確立

**実装内容**:

1. **実装ファイル修正**:
   - ファイル: `src/lorairo/gui/widgets/model_selection_table_widget.py`

2. **テスト作成**:
   - ファイル: `tests/integration/gui/test_model_selection_table_widget_critical_initialization.py`
   - テストケース:
     - `test_missing_table_widget_triggers_critical_failure`
     - `test_table_properties_setup_failure`
     - `test_load_models_exception_handling`

**成果物**:
- テーブルウィジェット初期化パターン
- 軽量ウィジェットのテスト基準

---

## 4. critical_failure_hooks再利用戦略

### 4.1 完全再利用可能なケース

**対象**: 全3コンポーネント

**条件**:
- `_handle_critical_initialization_failure()` メソッド実装
- sys.exit(1), logger.critical, QMessageBox.critical を使用

**実装テンプレート**:
```python
def _handle_critical_initialization_failure(self, component_name: str, error: Exception):
    """致命的な初期化エラーを処理"""
    error_message = f"致命的な初期化エラー: {component_name}\n{error}"
    logger.critical(f"Critical initialization failure - {component_name}: {error}")
    
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("エラー")
    msg_box.setText(error_message)
    msg_box.exec()
    
    import sys
    sys.exit(1)
```

### 4.2 新規フックが必要な箇所

**ケース1**: QDialogの閉じる動作
- DatasetExportWidgetはQDialogなので、sys.exit()ではなくダイアログを閉じる可能性
- 対応: 致命的エラーは sys.exit(1) で統一（アプリ全体の方針）

**ケース2**: 非致命的エラー処理
- 一部のウィジェットは初期化失敗を許容する可能性
- 対応: 致命的 vs 非致命的の判断基準を明確化

---

## 5. 品質基準

### 5.1 カバレッジ目標

**目標**: 致命的初期化経路 100%

| コンポーネント | 致命的経路数 | テスト数 | カバレッジ |
|--------------|------------|---------|-----------|
| MainWindow | 7 | 7 | 100% ✅ |
| DatasetExportWidget | 3 | 3 | 100% (目標) |
| AnnotationControlWidget | 3 | 3 | 100% (目標) |
| ModelSelectionTableWidget | 3 | 3 | 100% (目標) |
| **合計** | **16** | **16** | **100%** |

### 5.2 テスト実行時間への影響

**現状**: MainWindow 7テスト = 19.02秒

**予測**:
- DatasetExportWidget 3テスト: 約8秒
- AnnotationControlWidget 3テスト: 約8秒
- ModelSelectionTableWidget 3テスト: 約6秒
- **合計追加時間**: 約22秒

**影響評価**: 低（CI/CD許容範囲内）

### 5.3 保守性を担保する設計方針

**1. 一貫性の維持**
- 全テストで `critical_failure_hooks` フィクスチャを使用
- 4項目検証パターンを統一
- テストメソッド命名規則: `test_<failure_condition>_triggers_critical_failure`

**2. ドキュメント化**
- 各テストファイルにdocstringで致命的経路を記載
- 初期化フェーズ（Phase 1, 2, 3）をコメントで明記

**3. 再利用可能なヘルパー関数**（検討）
```python
# tests/integration/gui/helpers/critical_failure_helpers.py
def verify_critical_failure(hooks, component_name):
    """致命的失敗の4項目検証を実行"""
    assert len(hooks["sys_exit"]) == 1
    assert hooks["sys_exit"][0] == 1
    hooks["logger"].critical.assert_called()
    assert component_name in str(hooks["logger"].critical.call_args)
    assert len(hooks["messagebox_instances"]) > 0
```

---

## 6. リスクと対策

### 6.1 リスク1: ウィジェットに `_handle_critical_initialization_failure` 未実装

**影響**: 高（テストが無意味になる）

**対策**:
- 実装フェーズで先に `_handle_critical_initialization_failure` を追加
- または、既存のエラーハンドリングを利用

### 6.2 リスク2: QDialog固有の動作

**影響**: 中（sys.exit()が適切でない可能性）

**対策**:
- QDialogは致命的エラー時に `reject()` + 親ウィンドウへの通知
- または、sys.exit(1)で統一（アプリケーション全体の方針）

### 6.3 リスク3: テスト実行時間の増加

**影響**: 低（22秒追加）

**対策**:
- 並列実行（`pytest -n auto`）
- 必要に応じて `@pytest.mark.slow` でフィルタリング可能に

---

## 7. 推奨アプローチ

### 即座に開始: Phase 1（DatasetExportWidget）

**理由**:
- QDialogパターンの代表例
- 他のダイアログへの横展開が容易
- エクスポート機能は必須機能

**ROI**: 高（4時間の投資で、今後のQDialog実装の品質基準確立）

---

## 8. 展開対象外コンポーネント

以下のウィジェットは初期化フローが単純で、致命的失敗経路が少ないため**優先度低**:

| ウィジェット | 理由 |
|------------|------|
| `ImagePreviewWidget` | UI要素のみ、サービス依存なし |
| `ThumbnailSelectorWidget` | 既存テスト有り、DatasetStateManager注入のみ |
| `SelectedImageDetailsWidget` | 既存テスト有り、シグナル接続のみ |
| `ModelCheckboxWidget` | 単純な表示ウィジェット |
| `DirectoryPicker`, `FilePicker` | 単純な入力ウィジェット |

---

**作成日**: 2025-11-20  
**次のアクション**: Phase 1（DatasetExportWidget）実装開始