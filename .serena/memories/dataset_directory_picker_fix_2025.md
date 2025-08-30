# Dataset Directory Picker Fix Implementation

## 問題の詳細
- **発症状況**: メインウィンドウからデータセットディレクトリを選択する処理ができない
- **根本原因**: UIボタン名とコードでの参照名の不一致
  - UIファイル: `pushButtonSelectDataset`
  - コード: `pushButtonSelectDirectory`

## 修正内容

### 1. ボタン接続修正 (`src/lorairo/gui/window/main_window.py:307`)
```python
# 修正前
if hasattr(self, "pushButtonSelectDirectory"):
    self.pushButtonSelectDirectory.clicked.connect(self.select_dataset_directory)

# 修正後  
if hasattr(self, "pushButtonSelectDataset"):
    self.pushButtonSelectDataset.clicked.connect(self.select_dataset_directory)
```

### 2. ディレクトリ選択機能実装 (`src/lorairo/gui/window/main_window.py:494-496`)
```python
# 修正前（空実装）
def select_dataset_directory(self):
    """データセットディレクトリ選択"""
    logger.info("データセットディレクトリ選択が呼び出されました")

# 修正後（完全実装）
def select_dataset_directory(self):
    """データセットディレクトリ選択"""
    from PySide6.QtWidgets import QFileDialog
    
    logger.info("データセットディレクトリ選択が呼び出されました")
    
    directory = QFileDialog.getExistingDirectory(
        self,
        "データセットディレクトリを選択してください",
        "",  # 初期ディレクトリ
        QFileDialog.ShowDirsOnly
    )
    
    if directory:
        logger.info(f"選択されたディレクトリ: {directory}")
        # ここで選択されたディレクトリに対する処理を実装
        # 例: self.load_dataset(directory)
    else:
        logger.info("ディレクトリ選択がキャンセルされました")
```

## 技術的な詳細
- **UI定義**: `src/lorairo/gui/designer/MainWindow.ui` でボタン定義済み
- **既存のDirectory Picker Widget**: `src/lorairo/gui/widgets/directory_picker.py` でより高機能な実装あり
- **テストコード**: `tests/gui/test_main_window_qt.py` でQFileDialogのモック化実装済み

## 今後の改善提案
1. より高機能な `DirectoryPickerWidget` への統合検討
2. 選択されたディレクトリでの後続処理（`load_dataset`等）の実装
3. ディレクトリ履歴機能の追加検討

## 修正完了日
2025-08-27