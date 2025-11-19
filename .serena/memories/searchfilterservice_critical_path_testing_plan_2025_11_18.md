# SearchFilterService致命経路テスト強化計画

**策定日**: 2025-11-18  
**目的**: SearchFilterServiceの初期化失敗時の致命的エラー処理の自動テスト強化  
**ステータス**: 計画完了、実装待ち  
**優先度**: 高（GUI起動の安定性に直結）

---

## 背景

### 発見契機
mainwindow_initialization_issue_2025_11_17 で特定された初期化問題の修正時に、致命的エラー処理（`_handle_critical_initialization_failure`）の自動テストが存在しないことが判明。

### 現状の問題
- **テストカバレッジ**: 致命経路 0%（5つの経路すべてが未テスト）
- **リスク**: 初期化失敗時の動作が未検証（アプリ終了、エラーダイアログ表示）
- **保守性**: 将来の変更でデグレードしても検出できない

---

## 致命経路の特定

**MainWindow初期化フロー（src/lorairo/gui/window/main_window.py）**:

| No | 行番号 | 致命経路 | トリガー条件 |
|----|--------|---------|------------|
| 1 | L242-246 | filterSearchPanel属性欠落 | setupUi()がfilterSearchPanelを作成しない |
| 2 | L256-261 | インターフェース検証失敗 | filterSearchPanelに必須メソッド欠落 |
| 3 | L680-683 | filterSearchPanel null | filterSearchPanel属性がNone |
| 4 | L686-689 | db_manager null | db_managerがNone |
| 5 | L692-704 | Service作成/注入失敗 | SearchFilterService作成時の例外 |

**_handle_critical_initialization_failureの動作**:
```python
def _handle_critical_initialization_failure(self, component_name: str, error: Exception) -> None:
    # 1. ログ記録（logger.critical）
    # 2. エラーダイアログ表示（QMessageBox.critical）
    # 3. アプリケーション終了（QApplication.quit）
```

---

## 実装方法

### 採用する方法: モック中心の統合テスト

**実装コード**:
```python
@pytest.mark.integration
@pytest.mark.fast_integration
class TestMainWindowCriticalInitializationFailures:
    
    @pytest.fixture
    def critical_failure_hooks(self, monkeypatch):
        """致命的失敗時のhookをモック"""
        calls = {"quit": [], "messagebox": [], "logger": MagicMock()}
        monkeypatch.setattr("PySide6.QtWidgets.QApplication.quit", lambda: calls["quit"].append(True))
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *a: calls["messagebox"].append(a))
        monkeypatch.setattr("lorairo.gui.window.main_window.logger", calls["logger"])
        return calls
    
    def test_missing_filter_search_panel_triggers_critical_failure(self, qtbot, critical_failure_hooks):
        # 実装
    
    def test_invalid_filter_panel_interface_triggers_critical_failure(self, qtbot, critical_failure_hooks):
        # 実装
    
    def test_missing_db_manager_triggers_critical_failure(self, qtbot, critical_failure_hooks):
        # 実装
    
    def test_service_creation_exception_triggers_critical_failure(self, qtbot, critical_failure_hooks):
        # 実装
    
    def test_service_injection_exception_triggers_critical_failure(self, qtbot, critical_failure_hooks):
        # 実装
```

**特徴**:
- 実行速度: 高速（全5テストで約5秒）
- CI/CD適合性: 高（ヘッドレス環境で実行可能）
- 既存パターンとの一貫性: test_mainwindow_signal_connection.pyと同じ

**採用理由**:
- test_strategy_policy_change_2025_11_06に記載された「統合テスト = モックのみ使用」に準拠
- 既存のtest_mainwindow_signal_connection.pyと同じパターン

---

## 実装計画

### Phase 1: 基盤整備（1-2時間）

**Task 1.1**: テストファイル作成
- ファイル: `tests/integration/gui/test_mainwindow_critical_initialization.py`
- 内容: テストクラスとフィクスチャの骨格

**Task 1.2**: 共通フィクスチャ実装
- `critical_failure_hooks`: quit/messagebox/loggerモック

### Phase 2: 最重要経路テスト（2-3時間）

| Task | テストメソッド | 推定時間 |
|------|---------------|---------|
| 2.1 | `test_missing_filter_search_panel_triggers_critical_failure` | 30分 |
| 2.2 | `test_missing_db_manager_triggers_critical_failure` | 20分 |
| 2.3 | `test_service_creation_exception_triggers_critical_failure` | 30分 |

### Phase 3: 追加経路テスト（1-2時間）

| Task | テストメソッド | 推定時間 |
|------|---------------|---------|
| 3.1 | `test_invalid_filter_panel_interface_triggers_critical_failure` | 20分 |
| 3.2 | `test_service_injection_exception_triggers_critical_failure` | 20分 |

### Phase 4: 検証（1時間）

**Task 4.1**: テスト実行
```bash
uv run pytest tests/integration/gui/test_mainwindow_critical_initialization.py -v
```

**Task 4.2**: CI/CD確認
```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/gui/test_mainwindow_critical_initialization.py
```

**Task 4.3**: カバレッジ確認
```bash
uv run pytest --cov=src/lorairo/gui/window/main_window --cov-report=term-missing
```

**総推定時間**: 5-8時間

---

## テスト戦略

### 検証項目（各テストケース共通）

1. `QApplication.quit()` が1回呼ばれる
2. `QMessageBox.critical()` が適切なメッセージで表示される
3. `logger.critical()` が適切なメッセージを記録する
4. エラーメッセージに期待されるキーワードが含まれる

### モック戦略

**外部依存のみモック**:
- `ConfigurationService`: 設定ファイル読み込み
- `ImageDatabaseManager`: DB接続
- `FileSystemManager`: ファイルシステム操作

**致命経路トリガー用モック**:
- `Ui_MainWindow.setupUi`: UI生成失敗のシミュレート
- `get_service_container`: ServiceContainer状態の制御

### 成功基準

**機能要件**:
- 5つの致命経路すべてがテストされている
- 各テストケースが独立して実行可能
- ヘッドレス環境で実行可能
- 実行時間が10秒以内（全テストケース合計）

**品質要件**:
- テストカバレッジ: `_handle_critical_initialization_failure`呼び出し経路 100%
- テストカバレッジ: `_setup_search_filter_integration` 80%以上
- False Positive率: 0%
- False Negative率: 0%

---

## リスクと対策

### リスク1: QApplication.quit()のテスト実行への影響（優先度: 高）

**リスク内容**: `QApplication.quit()`が呼ばれるとテスト実行全体が停止する可能性

**対策**:
```python
monkeypatch.setattr("PySide6.QtWidgets.QApplication.quit", lambda: quit_called.append(True))
```

### リスク2: QMessageBox.critical()のヘッドレス実行（優先度: 高）

**リスク内容**: ヘッドレス環境（QT_QPA_PLATFORM=offscreen）でQMessageBoxが正常に動作しない可能性

**対策**:
```python
monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *a: messagebox_calls.append(a))
```

### リスク3: MainWindow初期化の複雑さ（優先度: 中）

**リスク内容**: MainWindowの初期化が複雑で、致命経路のみをトリガーすることが困難

**対策**:
```python
# _setup_search_filter_integration()を直接呼び出す
window = MainWindow.__new__(MainWindow)
window.filterSearchPanel = None
window._setup_search_filter_integration()
```

### リスク4: テスト環境の依存関係（優先度: 低）

**リスク内容**: CI/CD環境でのPySide6やQtの依存関係が不足

**対策**: devcontainer環境 + `QT_QPA_PLATFORM=offscreen`（既存のGUIテストで実績あり）

---

## 配置計画

### 新規ファイル
```
tests/integration/gui/
└── test_mainwindow_critical_initialization.py  (新規、200-300行)
```

### 既存ファイルへの影響
- **変更なし**: `src/lorairo/gui/window/main_window.py`（テスト対象のみ）
- **影響なし**: 既存テスト（独立したテスト追加）

### CI/CDパイプライン
```yaml
- name: Run critical initialization tests
  run: |
    QT_QPA_PLATFORM=offscreen uv run pytest \
      tests/integration/gui/test_mainwindow_critical_initialization.py \
      -v --cov
```

---

## 実装後の期待される状態

### テストカバレッジ
- `_handle_critical_initialization_failure`: 0% → **100%**
- `_setup_search_filter_integration`（致命経路部分）: 0% → **100%**

### 品質向上
- MainWindow初期化失敗時の動作が自動検証される
- 将来のデグレードを早期検出できる
- CI/CDでの継続的な品質保証

---

## 設計判断の記録

### モック中心アプローチを採用した理由

1. **既存テスト方針との整合性**
   - `test_strategy_policy_change_2025_11_06`で定義された「統合テスト＝モックのみ」に準拠

2. **既存パターンとの一貫性**
   - `test_mainwindow_signal_connection.py`と同じモックパターン
   - 開発者にとって理解しやすい

3. **実行速度とCI/CD適合性**
   - 高速実行（5秒以内）
   - ヘッドレス環境で確実に動作

4. **可読性とデバッグ性**
   - 各経路を個別にテストメソッドで実装
   - テスト失敗時の原因特定が容易

---

**記録日**: 2025-11-18  
**適用開始**: /implement実行後  
**影響**: 今後のMainWindow初期化テスト、致命的エラー処理テスト全般