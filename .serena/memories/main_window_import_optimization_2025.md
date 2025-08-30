# MainWindow 遅延インポート最適化実装記録

## 実装日時
2025-08-28

## 対象課題
ユーザーリクエスト: "あとメインウィンドウの無駄な遅延インポートも修正して"

## 実装概要

### Before (遅延インポート)
```python
# メソッド内での都度インポート
def _on_batch_registration_error(self, error_message: str) -> None:
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.critical(...)

def select_dataset_directory(self) -> None:
    from pathlib import Path
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    # 処理...
```

### After (モジュールレベルインポート)
```python
# モジュール冒頭での一括インポート
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from ...database.db_core import resolve_stored_path
from ..services.image_db_write_service import ImageDBWriteService
# その他必要なインポート...
```

## 最適化対象の遅延インポート

### 1. PySide6関連
- `QMessageBox` (複数箇所)
- `QFileDialog` (select_dataset_directory)
- `QSize` (_get_thumbnail_size)

### 2. 外部モジュール
- `resolve_stored_path` (get_processed_image_paths)
- `ImageDBWriteService` (handle_metadata_update)

### 3. 標準ライブラリ
- `Path` (select_dataset_directory) ※すでにモジュールレベル存在

## 最適化効果

### パフォーマンス向上
- インポート処理の重複実行回避
- モジュール初期化時の一回のみ実行
- メソッド実行時のオーバーヘッド削減

### コード品質向上
- import文の集約による可読性向上
- Python import ベストプラクティス準拠
- 静的解析ツール対応改善

## 副作用対策

### テスト修正
遅延インポートをモジュールレベルに移動したことでテストのmockパッチ対象が変更。以下を削除:
- `ImageRepository` パッチ (存在しないため)
- `PreviewDetailPanel` パッチ (存在しないため)

### Ruff警告
- 複雑度警告は既存のもので最適化とは無関係
- インポート最適化により新たな警告は発生せず

## 技術的考慮事項

### メモリ使用量
- 使用しない場合でもインポートされるモジュールのメモリ消費
- 実際のアプリケーションでは全て使用されるため実質的影響なし

### 初期化時間
- アプリケーション起動時のわずかな初期化時間増加
- ランタイムでのインポート時間節約で相殺

## 実装パターン

### 統合前インポート構成
```python
# 基本インポート
from pathlib import Path
from typing import Any

# Qt関連
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

# LoRAIro関連
from ...database.db_manager import ImageDatabaseManager
# その他...
```

### 統合後インポート構成
```python
# 基本インポート (変更なし)
from pathlib import Path
from typing import Any

# Qt関連 (拡張)
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

# LoRAIro関連 (拡張)
from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ..services.image_db_write_service import ImageDBWriteService
# その他...
```

## 成果

### 実装前課題
- 10箇所の遅延インポート散在
- メソッド実行時の不要なインポート処理
- コード可読性低下

### 実装後成果
- モジュールレベル一括インポートによる処理効率化
- 可読性向上とベストプラクティス準拠
- テストの正常実行確認

## 関連実装

### 対象ファイル
- `src/lorairo/gui/window/main_window.py`
- `tests/gui/test_main_window_qt.py` (テスト修正)

### 実装手法
- MultiEdit tool による一括最適化
- 段階的テスト実行による品質確保
- Memory-First記録による知識蓄積

## 教訓・パターン

### Python Import Best Practice
1. モジュールレベルインポートを優先
2. 遅延インポートは循環参照回避など特殊用途のみ
3. 静的解析対応のため明示的インポート推奨

### Qt GUI開発
1. Qt関連インポートのまとめ集約
2. Signal/Slot パターンでのインポート最適化
3. テストでのmock対象明確化

### 最適化プロセス
1. パターン検索による対象特定
2. 影響範囲確認（テスト含む）
3. 段階的適用と動作確認
4. 知識記録による再利用促進