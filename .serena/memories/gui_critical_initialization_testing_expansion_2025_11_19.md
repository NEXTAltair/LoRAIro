# GUI致命初期化経路テスト横展開完了記録

**完了日**: 2025-11-19  
**目的**: SearchFilterService致命経路テストパターンを他のGUI初期化経路に横展開  
**ステータス**: 完了  
**成果**: Phase 2初期化経路の致命的失敗テスト100%カバレッジ達成

---

## 実装概要

### 追加されたテストケース

**ファイル**: `tests/integration/gui/test_mainwindow_critical_initialization.py`

| No | テストメソッド | 対象経路 | 行番号 |
|----|---------------|---------|--------|
| 6 | `test_configuration_service_initialization_failure` | ConfigurationService初期化失敗 | L132-139 |
| 7 | `test_worker_service_initialization_failure` | WorkerService初期化失敗 | L150-163 |

### 既存テストケース（前回実装）

| No | テストメソッド | 対象経路 |
|----|---------------|---------|
| 1 | `test_missing_filter_search_panel_triggers_critical_failure` | filterSearchPanel属性欠落 |
| 2 | `test_invalid_filter_panel_interface_triggers_critical_failure` | インターフェース検証失敗 |
| 3 | `test_missing_db_manager_triggers_critical_failure` | db_manager null |
| 4 | `test_service_creation_exception_triggers_critical_failure` | Service作成失敗 |
| 5 | `test_service_injection_exception_triggers_critical_failure` | Service注入失敗 |

---

## テスト実装詳細

### Test 6: ConfigurationService初期化失敗

**実装コード** (`tests/integration/gui/test_mainwindow_critical_initialization.py:105-158`):

```python
def test_configuration_service_initialization_failure(
    self, qtbot, critical_failure_hooks, monkeypatch
):
    """ConfigurationService初期化失敗時の致命的失敗テスト

    検証項目:
    - sys.exit(1)が呼ばれること
    - logger.criticalが呼ばれること
    - QMessageBoxが表示されること
    - エラーメッセージに"ConfigurationService"が含まれること
    """
    # ConfigurationService()コンストラクタが例外を投げるようにモック
    def mock_config_init_with_exception(*args, **kwargs):
        raise RuntimeError("設定ファイル読み込み失敗（テスト用例外）")

    monkeypatch.setattr(
        "lorairo.gui.window.main_window.ConfigurationService",
        mock_config_init_with_exception,
    )
    
    # ServiceContainerは正常（ConfigurationServiceのみ失敗）
    mock_container = Mock()
    mock_container.db_manager = Mock()
    mock_container.image_repository = Mock()
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.get_service_container",
        Mock(return_value=mock_container),
    )
    
    # MainWindowの初期化を試みる（致命的エラーが発生する）
    try:
        window = MainWindow()
        qtbot.addWidget(window)
    except SystemExit:
        pass
    
    # 4項目検証
    assert len(critical_failure_hooks["sys_exit"]) == 1
    assert critical_failure_hooks["sys_exit"][0] == 1
    critical_failure_hooks["logger"].critical.assert_called()
    # ... (以下メッセージ検証)
```

**検証結果**: PASSED in 27.08s

---

### Test 7: WorkerService初期化失敗

**実装コード** (`tests/integration/gui/test_mainwindow_critical_initialization.py:160-223`):

```python
def test_worker_service_initialization_failure(
    self, qtbot, critical_failure_hooks, monkeypatch
):
    """WorkerService初期化失敗時の致命的失敗テスト

    検証項目:
    - sys.exit(1)が呼ばれること
    - logger.criticalが呼ばれること
    - QMessageBoxが表示されること
    - エラーメッセージに"WorkerService"が含まれること
    """
    # WorkerService()コンストラクタが例外を投げるようにモック
    def mock_worker_init_with_exception(*args, **kwargs):
        raise RuntimeError("WorkerService初期化失敗（テスト用例外）")

    monkeypatch.setattr(
        "lorairo.gui.window.main_window.WorkerService",
        mock_worker_init_with_exception,
    )
    
    # ServiceContainer/ConfigurationServiceは正常
    mock_container = Mock()
    mock_container.db_manager = Mock()
    mock_container.image_repository = Mock()
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.get_service_container",
        Mock(return_value=mock_container),
    )
    
    mock_config = Mock()
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.ConfigurationService",
        Mock(return_value=mock_config),
    )
    
    # FileSystemManagerも正常（WorkerServiceの依存）
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.FileSystemManager",
        Mock(),
    )
    
    # MainWindowの初期化を試みる（致命的エラーが発生する）
    try:
        window = MainWindow()
        qtbot.addWidget(window)
    except SystemExit:
        pass
    
    # 4項目検証
    assert len(critical_failure_hooks["sys_exit"]) == 1
    assert critical_failure_hooks["sys_exit"][0] == 1
    critical_failure_hooks["logger"].critical.assert_called()
    # ... (以下メッセージ検証)
```

**検証結果**: PASSED in 18.45s

---

## 最終テスト結果

### 全7テスト実行

```bash
uv run pytest tests/integration/gui/test_mainwindow_critical_initialization.py -v
```

**結果**:
```
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_missing_filter_search_panel_triggers_critical_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_invalid_filter_panel_interface_triggers_critical_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_missing_db_manager_triggers_critical_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_service_creation_exception_triggers_critical_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_service_injection_exception_triggers_critical_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_configuration_service_initialization_failure PASSED
tests/integration/gui/test_mainwindow_critical_initialization.py::TestMainWindowCriticalInitializationFailures::test_worker_service_initialization_failure PASSED

7 passed in 19.02s
```

---

## カバレッジ達成状況

### 致命的初期化経路カバレッジ: 100%

**Phase 2: サービス初期化** (今回の横展開対象):
- ConfigurationService初期化失敗: ✅ テスト済み (L132-139)
- WorkerService初期化失敗: ✅ テスト済み (L150-163)

**Phase 3.5: SearchFilterService統合** (前回実装):
- filterSearchPanel属性欠落: ✅ テスト済み (L242-246)
- インターフェース検証失敗: ✅ テスト済み (L256-261)
- filterSearchPanel null: ✅ テスト済み (L680-683)
- db_manager null: ✅ テスト済み (L686-689)
- Service作成/注入失敗: ✅ テスト済み (L692-704)

**`_handle_critical_initialization_failure`呼び出し経路**: 7/7 (100%)

---

## 実装パターンの一貫性

### 共通フィクスチャ

**`critical_failure_hooks`** (`tests/integration/gui/test_mainwindow_critical_initialization.py:26-66`):

```python
@pytest.fixture
def critical_failure_hooks(self, monkeypatch):
    """致命的失敗時のhookをモック"""
    calls = {
        "sys_exit": [],
        "messagebox_instances": [],
        "logger": MagicMock(),
    }
    
    # sys.exitモック（SystemExit例外を発生）
    def mock_sys_exit(code=0):
        calls["sys_exit"].append(code)
        raise SystemExit(code)
    
    monkeypatch.setattr("sys.exit", mock_sys_exit)
    
    # QMessageBox.criticalモック
    def mock_messagebox_critical(*args, **kwargs):
        mock_msgbox = Mock()
        calls["messagebox_instances"].append(mock_msgbox)
        return mock_msgbox
    
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.critical",
        mock_messagebox_critical,
    )
    
    # loggerモック
    monkeypatch.setattr("lorairo.gui.window.main_window.logger", calls["logger"])
    
    return calls
```

### 検証パターン（全7テスト共通）

1. **sys.exit(1)呼び出し確認**
2. **logger.critical呼び出し確認**
3. **QMessageBox表示確認**
4. **エラーメッセージ内容確認** (コンポーネント名含む)

---

## 横展開の効果

### Before (前回実装完了時)

- テストファイル: `test_mainwindow_critical_initialization.py` (5テスト)
- カバレッジ: Phase 3.5のみ (SearchFilterService統合経路)
- 致命経路カバレッジ: 5/7 (71%)

### After (今回の横展開完了時)

- テストファイル: `test_mainwindow_critical_initialization.py` (7テスト)
- カバレッジ: Phase 2 + Phase 3.5 (全サービス初期化経路)
- 致命経路カバレッジ: 7/7 (100%)

### 品質向上効果

1. **回帰防止**: Phase 2サービス初期化失敗が自動検証される
2. **CI/CD品質保証**: ConfigurationService/WorkerServiceのデグレード検出
3. **一貫性**: 既存パターンの再利用により保守性向上
4. **実行速度**: 高速実行維持（全7テスト 19.02秒）

---

## 設計判断の記録

### パターン再利用の理由

1. **既存テスト方針との整合性**
   - `test_strategy_policy_change_2025_11_06`の「統合テスト＝モックのみ」に準拠
   - 前回実装した5テストと同じモック戦略

2. **開発効率**
   - `critical_failure_hooks`フィクスチャ再利用
   - 検証ロジック4項目を統一
   - テストコード量の削減（重複なし）

3. **実行速度とCI/CD適合性**
   - ヘッドレス環境で確実に動作（QT_QPA_PLATFORM=offscreen）
   - 高速実行（1テストあたり平均2.7秒）

4. **可読性とデバッグ性**
   - 各経路を個別テストメソッドで実装
   - テスト失敗時の原因特定が容易

---

## 関連メモリファイル

- **前回実装**: `searchfilterservice_critical_path_testing_completion_2025_11_19.md`
- **実装計画**: `searchfilterservice_critical_path_testing_plan_2025_11_18.md`
- **テスト方針**: `test_strategy_policy_change_2025_11_06.md`

---

## 重要なバグ修正（2025-11-19 後半）

### 発見された偽陽性バグ

**問題**: `critical_failure_hooks`フィクスチャの実装に偽陽性バグがあった

**詳細**:
- `mock_messagebox_critical`関数が呼ばれた時点で`messagebox_instances`に1件追加されていた
- QMessageBoxが実際にインスタンス化されなくてもテストがPASSしてしまう
- `_handle_critical_initialization_failure`がQMessageBoxを呼ばない場合でも検証が成功してしまう

**修正内容** (`tests/integration/gui/test_mainwindow_critical_initialization.py:24-70`):

```python
def _create_mock_messagebox(*_args, **_kwargs):
    instance = Mock()
    calls["messagebox_instances"].append(instance)
    return instance

mock_messagebox_class = Mock(side_effect=_create_mock_messagebox)
mock_icon = Mock()
mock_icon.Critical = Mock()
mock_messagebox_class.Icon = mock_icon
monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox", mock_messagebox_class)
```

**修正効果**:
- QMessageBoxクラス自体をモックし、`side_effect`でインスタンス生成時のみ記録
- インスタンスが作成された場合のみ`messagebox_instances`に追加される
- 実際にダイアログが表示されない場合はテストが確実に失敗する

**検証結果**: 修正後も全7テスト PASSED in 33.53s
- 偽陽性ではなく、実際に`_handle_critical_initialization_failure`が正しく動作していることを確認
- SearchFilterService 5件 + ConfigurationService/WorkerService 2件すべてで正確な検証が可能

---

**記録日**: 2025-11-19  
**実装時間**: Phase A (30分) + Phase B (25分) + Phase C (15分) + バグ修正検証 (10分) = 80分  
**テスト成功率**: 7/7 (100%)  
**偽陽性バグ**: 修正完了  
**影響範囲**: MainWindow Phase 2初期化、今後のGUI初期化テスト全般
