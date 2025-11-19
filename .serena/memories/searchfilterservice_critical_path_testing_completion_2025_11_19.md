# SearchFilterService致命経路テスト実装完了記録

**実装日**: 2025-11-19  
**ステータス**: ✅ 完了  
**テスト結果**: 5/5 PASSED (100%)  
**実装時間**: 約2時間

---

## 実装概要

MainWindowの初期化時に発生する5つの致命的エラー経路の自動テストを実装・完了。
すべてのテストが`QT_QPA_PLATFORM=offscreen`環境で正常動作を確認。

---

## テスト実装完了

### ファイル
- **新規作成**: `tests/integration/gui/test_mainwindow_critical_initialization.py` (350行)

### テストケース (5つ)

| # | テストメソッド | 対象経路 | 結果 |
|---|--------------|---------|------|
| 1 | test_missing_filter_search_panel_triggers_critical_failure | setupUi()がfilterSearchPanel未作成 | ✅ PASSED |
| 2 | test_missing_db_manager_triggers_critical_failure | ServiceContainer.db_manager が None | ✅ PASSED |
| 3 | test_invalid_filter_panel_interface_triggers_critical_failure | filterSearchPanelに必須メソッド欠落 | ✅ PASSED |
| 4 | test_service_creation_exception_triggers_critical_failure | SearchFilterService作成時例外 | ✅ PASSED |
| 5 | test_service_injection_exception_triggers_critical_failure | set_search_filter_service()例外 | ✅ PASSED |

---

## 技術的課題と解決策

### 課題1: sys.exit()モックが機能しない

**問題**: monkeypatch.setattr("sys.exit", mock)でパッチしたが、呼び出しが記録されない

**原因**: main_window.py の `_handle_critical_initialization_failure` 内で `import sys` がローカルインポートされている (line 232)

**解決策**:
```python
import sys
monkeypatch.setattr(sys, "exit", mock_sys_exit)
```
sysモジュール自体をインポートしてからexitをパッチ。さらに、`SystemExit(code)`を発生させてsys.exit()の本来の動作を模倣。

### 課題2: setupUi()モックの適用失敗

**問題**: Ui_MainWindow.setupUi()をモックしたが、実際のUIが生成されてしまう

**原因1**: setupUi()のシグネチャが不正 (2パラメータ必要なのに1パラメータしか定義していない)

**解決策1**:
```python
def mock_setupui(ui_self, main_window_instance):
    # 正しいシグネチャ
    main_window_instance.filterSearchPanel = ...
```

**原因2**: モジュールパスでパッチしていない

**解決策2**:
```python
monkeypatch.setattr(
    "lorairo.gui.designer.MainWindow_ui.Ui_MainWindow.setupUi",
    mock_setupui
)
```

### 課題3: ServiceContainerモックの適用失敗

**問題**: get_service_container()をモックしたが、実際のServiceContainerが初期化される

**原因1**: 間違ったプロパティ名 (`image_db_manager` ではなく `db_manager`)

**解決策1**:
```python
mock_container.db_manager = None  # 正しいプロパティ名
```

**原因2**: インポート先でパッチしていない

**解決策2**:
```python
# main_window.py でインポートされている場所でパッチ
monkeypatch.setattr(
    "lorairo.gui.window.main_window.get_service_container",
    Mock(return_value=mock_container)
)
```

---

## 実装パターン (再利用可能)

### 1. sys.exit()のモック

```python
def mock_sys_exit(code):
    calls["sys_exit"].append(code)
    raise SystemExit(code)  # 本来の動作を模倣

import sys
monkeypatch.setattr(sys, "exit", mock_sys_exit)
```

### 2. Ui_MainWindow.setupUi()のモック

```python
def mock_setupui(ui_self, main_window_instance):
    # 2パラメータ必須
    main_window_instance.centralwidget = Mock()
    # filterSearchPanel を作成しない (テスト目的)

monkeypatch.setattr(
    "lorairo.gui.designer.MainWindow_ui.Ui_MainWindow.setupUi",
    mock_setupui
)
```

### 3. QMessageBoxのモック

```python
mock_messagebox_class = Mock()
mock_messagebox_instance = Mock()
mock_messagebox_class.return_value = mock_messagebox_instance

# Icon列挙型もモック
mock_icon = Mock()
mock_icon.Critical = Mock()
mock_messagebox_class.Icon = mock_icon

monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox", mock_messagebox_class)
```

---

## 検証項目 (全テスト共通)

1. ✅ `sys.exit(1)` が1回呼ばれること
2. ✅ `logger.critical()` が適切なメッセージで呼ばれること
3. ✅ `QMessageBox` が作成・表示されること
4. ✅ エラーメッセージに期待されるキーワードが含まれること

---

## CI/CD実行確認

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/integration/gui/test_mainwindow_critical_initialization.py \
  -v --no-cov

# 結果: 5/5 PASSED in 18.16s
```

ヘッドレス環境での実行が正常に機能することを確認。

---

## カバレッジ改善結果

- **Before**: `_handle_critical_initialization_failure` 呼び出し経路 0%
- **After**: 5つの致命経路すべてテスト済み (100%)

---

## 学んだ教訓

1. **pytestのmonkeypatchは「使用箇所」でパッチする**: インポート元ではなく、実際に呼び出される場所でパッチを適用
2. **メソッドシグネチャの正確性**: setupUi(self, MainWindow) は2パラメータが必須
3. **sys.exit()は SystemExitを発生させる**: モックも同じ動作を模倣しないとテストが正しく動作しない
4. **Qtのヘッドレステスト**: QT_QPA_PLATFORM=offscreen で GUI要素も正常にテスト可能

---

## 関連ファイル

- **テストファイル**: `tests/integration/gui/test_mainwindow_critical_initialization.py`
- **対象コード**: `src/lorairo/gui/window/main_window.py`
  - `_handle_critical_initialization_failure` (line 198-234)
  - `setup_custom_widgets` (line 236-263)
  - `_setup_search_filter_integration` (line 668-710)
- **計画書**: `.serena/memories/searchfilterservice_critical_path_testing_plan_2025_11_18.md`

---

**次のステップ**: 他のGUI初期化経路への同様のテスト適用を検討可能
