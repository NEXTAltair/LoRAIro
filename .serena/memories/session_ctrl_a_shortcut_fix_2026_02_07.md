# Session: Ctrl+A ショートカット競合修正

**Date**: 2026-02-07
**Branch**: feature/annotator-library-integration
**Status**: completed
**Commits**: caeed1d, 1ecd0e6, cdf9b66

---

## 実装結果

### 問題の発見と解決プロセス

1. **初期実装**（caeed1d）: `keyPressEvent` + `selectAllRequested` Signal
   - 実装: `CustomGraphicsView.keyPressEvent` でCtrl+A検出 → Signal発火
   - 結果: テストは通過したが、実アプリでは動作せず

2. **第2試行**（1ecd0e6）: `QShortcut` 追加
   - 実装: `QShortcut("Ctrl+A", self)` を `ThumbnailSelectorWidget` に追加
   - 結果: テストは通過したが、実アプリでは依然動作せず

3. **根本原因の特定**: Qt Ambiguous Shortcut 問題
   - MainWindow.ui に既存の `actionSelectAll(Ctrl+A)` を発見
   - `actionSelectAll` (WindowShortcut) と `QShortcut` (WidgetShortcut) が競合
   - Qtは「曖昧なショートカット」として両方を無効化

4. **最終修正**（cdf9b66）: QAction接続に統一
   - ThumbnailSelectorWidgetの競合コードを全除去
   - MainWindowで `actionSelectAll.triggered` → `_select_all_items()` 接続
   - 結果: 実アプリで正常動作を確認

### 変更ファイル

- **src/lorairo/gui/widgets/thumbnail.py** (-55行, +2行)
  - ❌ `QShortcut("Ctrl+A", self)` 除去
  - ❌ `CustomGraphicsView.keyPressEvent` 除去
  - ❌ `ThumbnailSelectorWidget.keyPressEvent` 除去
  - ❌ `selectAllRequested` Signal 除去
  - ✅ `CustomGraphicsView.setFocusPolicy(StrongFocus)` は維持（将来のキー操作対応）

- **src/lorairo/gui/window/main_window.py** (+17行)
  - ✅ `actionSelectAll.triggered` → `thumbnail_selector._select_all_items` 接続
  - ✅ `actionDeselectAll.triggered` → `thumbnail_selector._deselect_all_items` 接続
  - ✅ エラーハンドリングとログ出力

- **tests/unit/gui/widgets/test_thumbnail_selector_widget.py** (-18行, +13行)
  - ✅ `keyPressEvent` 直接呼び出しから `_select_all_items()` 直接テストに変更
  - ✅ テスト名変更: `test_ctrl_a_*` → `test_select_all_*`

## テスト結果

```
✅ tests/unit/gui/widgets/test_thumbnail_selector_widget.py
   - 39 passed (全テストパス)
   - test_select_all_items
   - test_select_all_with_existing_selection

✅ tests/unit/gui/window/test_main_window.py
   - 4 passed (全テストパス)

✅ 実アプリケーション動作確認
   - Ctrl+A で全選択: ✅
   - メニュー「編集」→「すべて選択」: ✅
   - 右クリック「すべて選択」: ✅
```

## 設計意図

### なぜ QAction 接続に統一したか

**代替案と却下理由:**

1. **QShortcut の ShortcutContext 変更**
   - `Qt.ShortcutContext.WindowShortcut` や `ApplicationShortcut` に変更
   - 却下理由: 既存の `actionSelectAll` と依然競合。根本解決にならない

2. **actionSelectAll の削除**
   - MainWindow.ui から `actionSelectAll` を削除し、ThumbnailSelectorWidget の QShortcut のみ使用
   - 却下理由: MainWindow レベルの標準メニュー項目を削除するのは設計上不適切

3. **QAction 接続に統一（採用）**
   - MainWindow の既存 `actionSelectAll` を活用し、ThumbnailSelectorWidget に接続
   - 利点:
     - Qt の標準的なアクション管理に準拠
     - メニューバー、ショートカット、将来のツールバーボタンが統一的に動作
     - ショートカット競合の根本原因を解消
     - コード量が減少（-73行, +30行 = -43行）

### Qt Ambiguous Shortcut の仕組み

```
[ユーザー] Ctrl+A 押下
    ↓
[Qt ショートカット検索]
    ├→ MainWindow.actionSelectAll (WindowShortcut) 発見
    └→ ThumbnailSelectorWidget.QShortcut (WidgetShortcut) 発見
    ↓
[Qt 判定] 2つ検出 → Ambiguous Shortcut
    ↓
[Qt 動作] どちらも発火しない（警告ログなし）
```

**修正後:**
```
[ユーザー] Ctrl+A 押下
    ↓
[Qt ショートカット検索]
    └→ MainWindow.actionSelectAll (WindowShortcut) のみ発見
    ↓
[actionSelectAll.triggered] Signal 発火
    ↓
[接続先] thumbnail_selector._select_all_items() 実行 ✅
```

## 問題と解決

### 問題1: テストは通るが実アプリで動作しない

**原因**: 単体テストは `keyPressEvent` を直接呼び出すため、Qt のショートカット検索システムをバイパス

**解決**: 
- ユニットテストは `_select_all_items()` のロジックを検証
- QAction の Signal/Slot 接続は Qt フレームワークの責任範囲
- 実アプリ動作確認で統合テスト代替

### 問題2: 根本原因の特定に時間がかかった

**原因**: Qt は Ambiguous Shortcut を検出しても警告ログを出力しない

**教訓**: 
- キーボードショートカットが動作しない場合、まず `Grep actionSelectAll` で既存 QAction を検索
- `git grep "Ctrl+A"` で全ショートカット定義を確認
- MainWindow.ui などの Designer ファイルも必ず確認

### 問題3: フォーカス管理の誤解

**誤解**: `setFocusPolicy(StrongFocus)` を設定すれば `keyPressEvent` が必ず呼ばれる

**真実**: QAction の WindowShortcut は、フォーカス位置に関わらず MainWindow 全体で有効

**教訓**: 
- WindowShortcut: フォーカス不要、MainWindow 全体で動作
- WidgetShortcut: ウィジェットまたは子にフォーカスが必要
- ApplicationShortcut: アプリケーション全体で動作

## 未完了・次のステップ

✅ 完了済み

### 参考: 他の選択機能

- Ctrl+Click: トグル選択 ✅
- Shift+Click: 範囲選択 ✅
- Ctrl+Shift+Click: 範囲追加選択 ✅
- ドラッグ選択: ラバーバンド矩形選択 ✅
- 右クリックメニュー「すべて選択」「選択解除」 ✅

すべて正常動作確認済み。
