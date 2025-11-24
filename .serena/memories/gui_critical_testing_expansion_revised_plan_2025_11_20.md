# GUI致命的初期化テスト展開計画（修正版）

**作成日**: 2025-11-20  
**前回計画**: gui_critical_testing_expansion_plan_2025_11_20.md（問題点発覚により改訂）

## Executive Summary

当初計画で指摘された3つの重大問題を解決した実装可能な計画。`critical_failure_hooks`の汎用化、`CriticalInitializationError`による例外統一、段階的実装ステップを確立。

---

## 1. 当初計画の問題点

### 問題1: critical_failure_hooksの再利用不可能性 ❌

**発覚内容**: `tests/integration/gui/test_mainwindow_critical_initialization.py:24-73`の`critical_failure_hooks`フィクスチャは`lorairo.gui.window.main_window`にハードコードされており、他のウィジェットでは使用不可。

```python
# L68-71: モジュールパスがハードコード
monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox", mock_messagebox_class)
monkeypatch.setattr("lorairo.gui.window.main_window.logger", calls["logger"])
```

**影響**: DatasetExportWidget等のテストで再利用できず、各テストファイルで重複実装が必要。

---

### 問題2: sys.exit(1)統一の設計変更影響 ❌

**発覚内容**: 各ウィジェットは現在、エラー時に**継続する設計**。

| コンポーネント | 現在のエラー処理 | sys.exit(1)の適切性 |
|--------------|----------------|-------------------|
| MainWindow | `sys.exit(1)` | ✅ 適切（アプリ起動失敗は致命的） |
| DatasetExportWidget | `QMessageBox.critical` + 継続 | ❌ 不適切（エクスポート失敗でアプリ終了は過剰） |
| AnnotationControlWidget | `logger.error` + 継続 | ❌ 不適切（アノテーション失敗でアプリ終了は過剰） |
| ModelSelectionTableWidget | `logger.warning` + 空リスト表示 | ❌ 不適切（モデル読み込み失敗でアプリ終了は過剰） |

**DatasetExportWidget._handle_error** (L412-420):
```python
def _handle_error(self, message: str) -> None:
    logger.error(message)
    self.ui.statusLabel.setText("エラーが発生しました")
    QMessageBox.critical(self, "エラー", message)
    # sys.exit(1)は呼ばない
```

**影響**: すべてをsys.exit(1)に統一すると、部分的な機能障害でアプリ全体が終了（UX悪化、データ損失リスク）。

---

### 問題3: 初期化エラーの伝播なし ❌

**発覚内容**: 各ウィジェットはtry/exceptで例外を握りつぶす。

**AnnotationControlWidget._setup_model_table_widget** (L100-112):
```python
try:
    self.modelSelectionTable.model_selection_changed.connect(...)
except Exception as e:
    logger.error(f"Error setting up ModelSelectionTableWidget: {e}", exc_info=True)
    # 例外を握りつぶして継続
```

**ModelSelectionTableWidget.load_models** (L96-120):
```python
def load_models(self) -> None:
    if not self.search_filter_service:
        logger.warning("SearchFilterService not available for model loading")
        self.all_models = []
        return  # 警告のみで継続
```

**影響**: sys.exitまで到達しないため、`critical_failure_hooks`で検証できない。

---

## 2. 修正計画：Plan A（推奨）

### 2.1 コンセプト

**critical_failure_hooks汎用化 + CriticalInitializationError統一**

- `critical_failure_hooks`をモジュールパス指定可能に汎用化
- `CriticalInitializationError`例外で致命的エラーを統一
- 呼び出し側（MainWindow等）でsys.exit(1)判断
- ウィジェットは例外を再発生させるだけ（責任分離）

---

### 2.2 実装ステップ

#### Step 1: 共通インフラ整備（1-2日）

**1.1 汎用critical_failure_hooksフィクスチャ作成**

**ファイル**: `tests/conftest.py`（既存ファイルに追加）

```python
@pytest.fixture
def critical_failure_hooks(monkeypatch):
    """致命的失敗時のhookをモック（汎用版）
    
    Args:
        monkeypatch: pytestのmonkeypatchフィクスチャ
    
    Returns:
        callable: モジュールパスを受け取り、hooksを返す関数
    
    Usage:
        @pytest.fixture
        def widget_critical_hooks(critical_failure_hooks):
            return critical_failure_hooks("lorairo.gui.widgets.dataset_export_widget")
    """
    def _create_hooks(module_path: str):
        calls = {
            "sys_exit": [],
            "messagebox_instances": [],
            "logger": MagicMock(),
        }
        
        # sys.exitをモック
        def mock_sys_exit(code):
            calls["sys_exit"].append(code)
            raise SystemExit(code)
        
        import sys
        monkeypatch.setattr(sys, "exit", mock_sys_exit)
        
        # QMessageBoxをモック
        def _create_mock_messagebox(*_args, **_kwargs):
            instance = Mock()
            calls["messagebox_instances"].append(instance)
            return instance
        
        mock_messagebox_class = Mock(side_effect=_create_mock_messagebox)
        mock_icon = Mock()
        mock_icon.Critical = Mock()
        mock_messagebox_class.Icon = mock_icon
        
        # モジュールパスを引数で指定
        monkeypatch.setattr(f"{module_path}.QMessageBox", mock_messagebox_class)
        monkeypatch.setattr(f"{module_path}.logger", calls["logger"])
        
        return calls
    
    return _create_hooks
```

**1.2 例外クラス定義**

**ファイル**: `src/lorairo/gui/exceptions.py`（新規作成）

```python
"""GUI初期化例外定義"""

class WidgetInitializationError(Exception):
    """ウィジェット初期化エラー基底クラス"""
    pass


class CriticalInitializationError(WidgetInitializationError):
    """致命的な初期化エラー
    
    このエラーが発生した場合、呼び出し側は適切な処理を行う必要がある：
    - MainWindow: sys.exit(1)でアプリケーション終了
    - ダイアログ: QDialog.reject()で閉じる
    - 子ウィジェット: 親に再発生させる
    """
    
    def __init__(
        self, 
        component: str, 
        reason: str, 
        original_error: Exception | None = None
    ):
        self.component = component
        self.reason = reason
        self.original_error = original_error
        super().__init__(f"{component} initialization failed: {reason}")


class DegradedInitializationError(WidgetInitializationError):
    """機能制限エラー（警告表示 + 継続可能）
    
    このエラーが発生した場合、機能を制限して動作を継続できる。
    """
    
    def __init__(
        self, 
        component: str, 
        reason: str, 
        fallback_available: bool = True
    ):
        self.component = component
        self.reason = reason
        self.fallback_available = fallback_available
        super().__init__(f"{component} degraded: {reason}")
```

**1.3 MainWindowテストで動作検証**

既存の`tests/integration/gui/test_mainwindow_critical_initialization.py`を修正し、汎用版`critical_failure_hooks`で動作確認。

---

#### Step 2: DatasetExportWidget改修（2-3日）

**2.1 実装ファイル修正**

**ファイル**: `src/lorairo/gui/widgets/dataset_export_widget.py`

```python
from ...gui.exceptions import CriticalInitializationError

class DatasetExportWidget(QDialog):
    def __init__(
        self,
        service_container: ServiceContainer,
        initial_image_ids: list[int],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        
        try:
            # Phase 1: UI生成
            self.ui = Ui_DatasetExportWidget()
            self.ui.setupUi(self)
            
            # Phase 2: サービス初期化（致命的依存関係）
            self.service_container = service_container
            self.export_service = service_container.dataset_export_service()
            
            if not self.export_service:
                raise CriticalInitializationError(
                    component="DatasetExportWidget",
                    reason="DatasetExportService is required but not available",
                    original_error=None
                )
            
            # Phase 3: UI設定
            self._setup_ui()
            self._connect_signals()
            self._update_initial_state()
            
        except CriticalInitializationError:
            # 致命的エラーは再発生させる
            raise
        except Exception as e:
            # 予期しないエラーも致命的として扱う
            raise CriticalInitializationError(
                component="DatasetExportWidget",
                reason="Unexpected initialization error",
                original_error=e
            ) from e
```

**2.2 テストファイル作成**

**ファイル**: `tests/integration/gui/widgets/test_dataset_export_widget_critical_initialization.py`（新規作成）

```python
"""DatasetExportWidget致命的初期化テスト

テスト対象の致命的経路:
1. export_service欠落 (Phase 2)
2. setupUi例外 (Phase 1)
3. _setup_ui例外 (Phase 3)
"""
import pytest
from unittest.mock import Mock
from PySide6.QtWidgets import QWidget
from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget
from lorairo.gui.exceptions import CriticalInitializationError


@pytest.fixture
def dataset_export_critical_hooks(critical_failure_hooks):
    """DatasetExportWidget用critical hooks"""
    return critical_failure_hooks("lorairo.gui.widgets.dataset_export_widget")


class TestDatasetExportWidgetCriticalInitialization:
    """DatasetExportWidget致命的初期化テスト"""
    
    def test_export_service_missing_raises_critical_error(
        self, qtbot, dataset_export_critical_hooks
    ):
        """export_service欠落時にCriticalInitializationError発生"""
        # ServiceContainerをモックしてNoneを返す
        mock_container = Mock()
        mock_container.dataset_export_service.return_value = None
        
        # CriticalInitializationErrorが発生することを検証
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = DatasetExportWidget(
                service_container=mock_container,
                initial_image_ids=[1, 2, 3],
                parent=None
            )
            qtbot.addWidget(widget)
        
        # エラー内容の検証
        assert exc_info.value.component == "DatasetExportWidget"
        assert "DatasetExportService" in exc_info.value.reason
    
    def test_setupui_exception_raises_critical_error(
        self, qtbot, dataset_export_critical_hooks, monkeypatch
    ):
        """setupUi例外時にCriticalInitializationError発生"""
        mock_container = Mock()
        mock_container.dataset_export_service.return_value = Mock()
        
        # setupUiで例外を投げる
        def mock_setupui_with_error(ui_self, instance):
            raise RuntimeError("UI generation failed")
        
        monkeypatch.setattr(
            "lorairo.gui.widgets.dataset_export_widget.Ui_DatasetExportWidget.setupUi",
            mock_setupui_with_error
        )
        
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = DatasetExportWidget(
                service_container=mock_container,
                initial_image_ids=[],
                parent=None
            )
            qtbot.addWidget(widget)
        
        assert exc_info.value.component == "DatasetExportWidget"
        assert "Unexpected initialization error" in exc_info.value.reason
        assert isinstance(exc_info.value.original_error, RuntimeError)
    
    def test_setup_ui_exception_raises_critical_error(
        self, qtbot, dataset_export_critical_hooks, monkeypatch
    ):
        """_setup_ui例外時にCriticalInitializationError発生"""
        mock_container = Mock()
        mock_container.dataset_export_service.return_value = Mock()
        
        # _setup_uiで例外を投げる
        def mock_setup_ui_with_error(self):
            raise RuntimeError("UI setup failed")
        
        monkeypatch.setattr(
            "lorairo.gui.widgets.dataset_export_widget.DatasetExportWidget._setup_ui",
            mock_setup_ui_with_error
        )
        
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = DatasetExportWidget(
                service_container=mock_container,
                initial_image_ids=[],
                parent=None
            )
            qtbot.addWidget(widget)
        
        assert exc_info.value.component == "DatasetExportWidget"
```

---

#### Step 3: 他ウィジェット展開（3-5日）

**3.1 AnnotationControlWidget改修**

**ファイル**: `src/lorairo/gui/widgets/annotation_control_widget.py`

主な変更点:
- `_setup_model_table_widget`のtry/exceptを除去
- 例外を`CriticalInitializationError`でラップ
- テストファイル作成: `tests/integration/gui/widgets/test_annotation_control_widget_critical_initialization.py`

**3.2 ModelSelectionTableWidget改修**

**ファイル**: `src/lorairo/gui/widgets/model_selection_table_widget.py`

主な変更点:
- `load_models`の`if not self.search_filter_service`チェックを例外に変更
- try/exceptを除去
- テストファイル作成: `tests/integration/gui/widgets/test_model_selection_table_widget_critical_initialization.py`

---

#### Step 4: 統合検証（1-2日）

**4.1 MainWindowとの統合テスト**

`tests/integration/gui/test_mainwindow_widget_integration.py`（新規作成）で以下を検証:
- MainWindowがDatasetExportWidgetの`CriticalInitializationError`を捕捉
- 適切なエラーメッセージ表示
- sys.exit(1)呼び出し

**4.2 エンドツーエンドシナリオ検証**

手動テスト:
1. DB接続失敗時のMainWindow起動失敗
2. エクスポートサービス欠落時のダイアログ開けない
3. アノテーションモデル読み込み失敗時の警告表示

**4.3 ドキュメント更新**

- `docs/testing_strategy.md`に致命的初期化テストパターンを追加
- `docs/error_handling.md`に`CriticalInitializationError`使用ガイドを追加

---

## 3. 品質基準（修正版）

### 3.1 カバレッジ目標

**目標**: 致命的初期化経路 100%（例外ベース検証）

| コンポーネント | 致命的経路数 | テスト数 | 検証方法 |
|--------------|------------|---------|---------|
| MainWindow | 7 | 7 | sys.exit(1) + critical_failure_hooks ✅ |
| DatasetExportWidget | 3 | 3 | CriticalInitializationError + pytest.raises |
| AnnotationControlWidget | 3 | 3 | CriticalInitializationError + pytest.raises |
| ModelSelectionTableWidget | 3 | 3 | CriticalInitializationError + pytest.raises |
| **合計** | **16** | **16** | **100%** |

### 3.2 テスト実行時間への影響

**予測**:
- DatasetExportWidget 3テスト: 約5秒（例外ベースで高速化）
- AnnotationControlWidget 3テスト: 約5秒
- ModelSelectionTableWidget 3テスト: 約4秒
- **合計追加時間**: 約14秒（当初予測22秒から改善）

**理由**: sys.exitモックではなく、`pytest.raises`で例外を直接捕捉するため高速。

### 3.3 保守性を担保する設計方針

**1. 例外ベース設計**
- すべての致命的エラーは`CriticalInitializationError`
- テストは`pytest.raises`で統一
- sys.exitは呼び出し側（MainWindow）のみ

**2. 責任分離**
- ウィジェット: エラー検出 → `CriticalInitializationError`発生
- MainWindow: エラー処理 → QMessageBox表示 + sys.exit(1)
- テスト: 例外発生の検証

**3. ドキュメント化**
- `CriticalInitializationError`のdocstringに使用方法を記載
- 各ウィジェットの致命的経路をコメントで明記

---

## 4. 代替案：Plan B（段階的デグレード戦略）

### 4.1 コンセプト

致命的エラーとせず、機能制限モードで継続。

```python
class DatasetExportWidget(QDialog):
    def __init__(self, ...):
        self._initialization_state = "uninitialized"
        
        try:
            self.export_service = service_container.dataset_export_service()
            self._initialization_state = "full"
        except Exception as e:
            logger.error(f"Export service unavailable: {e}")
            self._initialization_state = "degraded"
            self._setup_degraded_mode()
    
    def _setup_degraded_mode(self):
        """機能制限モードでの初期化"""
        self.ui.exportButton.setEnabled(False)
        self.ui.statusLabel.setText("エクスポート機能は利用できません")
        QMessageBox.warning(
            self, 
            "機能制限",
            "エクスポートサービスが利用できません。"
        )
```

### 4.2 メリット・デメリット

| 観点 | Plan A（例外統一） | Plan B（デグレード） |
|------|------------------|-------------------|
| テスト容易性 | ✅ 高（pytest.raises） | ⚠️ 中（状態検証） |
| UX | ⚠️ エラーダイアログ表示 | ✅ 機能制限で継続 |
| 保守性 | ✅ 高（責任分離明確） | ❌ 低（状態管理複雑） |
| 実装工数 | ⚠️ 中（例外処理追加） | ❌ 高（デグレードモード実装） |

**推奨**: Plan A（例外統一）

---

## 5. リスクと対策

### 5.1 リスク1: MainWindowの既存テスト破壊

**影響**: 中

**対策**:
- Step 1で既存のMainWindowテストを汎用版`critical_failure_hooks`に移行
- 動作確認後、Step 2以降を開始

### 5.2 リスク2: 例外処理の波及範囲

**影響**: 中

**対策**:
- `CriticalInitializationError`を捕捉する箇所を最小化
- 基本的にはMainWindowのみで捕捉し、sys.exit(1)判断

### 5.3 リスク3: 実装工数の増加

**影響**: 低

**対策**:
- Step 2（DatasetExportWidget）を先行実装してパターン確立
- 他ウィジェットは同じパターンをコピー

---

## 6. 実装優先順位（修正版）

### Phase 1: 共通インフラ整備（必須、1-2日）
- `tests/conftest.py`に汎用`critical_failure_hooks`追加
- `src/lorairo/gui/exceptions.py`作成
- MainWindowテストで動作検証

### Phase 2: DatasetExportWidget（推奨、2-3日）
- `CriticalInitializationError`導入
- テストケース3つ作成
- パターン確立

### Phase 3: AnnotationControlWidget（オプション、2-3日）
- Phase 2のパターン適用
- SearchFilterService注入パターン検証

### Phase 4: ModelSelectionTableWidget（オプション、1-2日）
- Phase 2のパターン適用
- テーブルウィジェット初期化パターン確立

---

## 7. まとめ

### 当初計画からの変更点

| 項目 | 当初計画 | 修正計画 |
|-----|---------|---------|
| critical_failure_hooks | MainWindow専用 | 汎用化（モジュールパス指定） |
| エラー処理方針 | sys.exit(1)統一 | `CriticalInitializationError`統一 |
| テスト方法 | sys.exitモック | `pytest.raises`例外検証 |
| 責任分離 | 不明確 | ウィジェット=検出、MainWindow=処理 |

### 推奨実装アプローチ

**Plan A + Phase 1-2の優先実装**
- Phase 1（共通インフラ）で基盤確立
- Phase 2（DatasetExportWidget）でパターン検証
- Phase 3-4はROI次第で判断

### 期待される成果

1. **テスト可能性向上**: `pytest.raises`で明確な例外検証
2. **保守性向上**: 責任分離が明確（検出 vs 処理）
3. **UX維持**: 致命的エラーのみsys.exit(1)、他は継続
4. **段階的実装**: Phase 1-2で十分な効果、Phase 3-4はオプション

---

**作成日**: 2025-11-20  
**次のアクション**: Phase 1実装開始の承認待ち