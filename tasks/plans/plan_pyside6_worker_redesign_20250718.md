# 🎯 PySide6ワーカー再設計 - 実装計画

**策定日**: 2025-07-18  
**プロジェクト**: LoRAIro  
**対象**: GUI統合型ワーカーシステム再設計

## 📋 Executive Summary

PySide6の標準機能を活用した、シンプルで保守性の高いワーカーシステムへの再設計計画。現在の複雑な独自実装（800行）をPySide6標準機能で75%削減（200行）し、GUI統合型ディレクトリ構成を採用する。

## 🎯 プロジェクト目標

### 主要目標
- **コード削減**: 800行 → 200行（75%削減）
- **保守性向上**: 新人の理解時間50%短縮
- **PySide6標準機能採用**: QRunnable + QThreadPool + QProgressDialog
- **ディレクトリ構造最適化**: GUI統合型（Option 1）採用

### 成功基準
- **定量的**: コード行数75%削減、処理速度95%以上維持、テストカバレッジ85%以上
- **定性的**: 保守性向上、新人理解時間短縮、PySide6標準機能活用

## 🔍 現状分析

### 問題点
1. **複雑な独自ワーカーシステム**: WorkerManager 263行、LoRAIroWorkerBase 164行
2. **PySide6機能の未活用**: 標準機能で実現可能な機能を独自実装
3. **直感に反するディレクトリ構造**: workers/がgui/外にあるが完全にPySide6依存
4. **保守性の低下**: 複雑な抽象化により理解が困難

### 現在の使用状況
- **DatabaseRegistrationWorker**: バッチ登録処理
- **SearchWorker**: データベース検索処理
- **ThumbnailWorker**: サムネイル読み込み処理
- **AnnotationWorker**: AI アノテーション処理

## 🏗️ 新アーキテクチャ設計

### 設計原則
1. **PySide6標準機能最大活用**: QRunnable + QThreadPool + QProgressDialog
2. **GUI統合型ディレクトリ**: workers/をgui/内に配置
3. **段階的移行**: 機能停止を避けるため並行運用期間を設ける
4. **既存APIの維持**: WorkerServiceのAPIを保持

### 新ディレクトリ構成
```
src/lorairo/
├── gui/
│   ├── workers/              # 新設：GUI統合型ワーカー
│   │   ├── __init__.py
│   │   ├── base.py          # 簡素化された基底クラス（30行）
│   │   ├── database.py      # データベース関連ワーカー
│   │   ├── thumbnail.py     # サムネイル読み込み
│   │   └── annotation.py    # アノテーション
│   ├── widgets/
│   └── window/
├── services/
│   └── worker_service.py    # 既存APIを維持
└── workers/                 # 段階的削除対象
```

### 核心設計：SimpleWorkerBase（30行）

```python
from PySide6.QtCore import QRunnable, QObject, Signal
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar('T')

@dataclass
class WorkerProgress:
    percentage: int
    message: str
    current_item: str = ""

class WorkerSignals(QObject):
    progress = Signal(WorkerProgress)
    finished = Signal(object)
    error = Signal(str)

class SimpleWorkerBase(QRunnable, Generic[T]):
    """PySide6標準機能ベースの簡素化ワーカー"""
    
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._is_canceled = False
    
    def run(self):
        try:
            result = self.execute()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
    
    def execute(self) -> T:
        raise NotImplementedError
    
    def cancel(self):
        self._is_canceled = True
    
    def is_canceled(self) -> bool:
        return self._is_canceled
    
    def report_progress(self, percentage: int, message: str, current_item: str = ""):
        progress = WorkerProgress(percentage, message, current_item)
        self.signals.progress.emit(progress)
```

### 進捗管理の簡素化：ProgressManager

```python
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import Qt, QThreadPool

class ProgressManager:
    def __init__(self, parent=None):
        self.parent = parent
        self.progress_dialog = None
        self.current_worker = None
    
    def start_worker_with_progress(self, worker, title: str, max_value: int = 100):
        # プログレスダイアログ作成
        self.progress_dialog = QProgressDialog(
            title, "キャンセル", 0, max_value, self.parent
        )
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        
        # ワーカーとの接続
        worker.signals.progress.connect(self.update_progress)
        worker.signals.finished.connect(self.on_finished)
        worker.signals.error.connect(self.on_error)
        
        # キャンセル処理
        self.progress_dialog.canceled.connect(worker.cancel)
        
        # 実行開始
        self.current_worker = worker
        self.progress_dialog.show()
        QThreadPool.globalInstance().start(worker)
    
    def update_progress(self, progress):
        if self.progress_dialog:
            self.progress_dialog.setValue(progress.percentage)
            self.progress_dialog.setLabelText(progress.message)
    
    def on_finished(self, result):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
```

### 新ワーカー実装例

```python
# src/lorairo/gui/workers/database.py
from PySide6.QtCore import QThreadPool
from .base import SimpleWorkerBase
from pathlib import Path

class DatabaseRegistrationWorker(SimpleWorkerBase):
    def __init__(self, directory: Path, db_manager, fsm):
        super().__init__()
        self.directory = directory
        self.db_manager = db_manager
        self.fsm = fsm
    
    def execute(self):
        image_files = list(self.fsm.get_image_files(self.directory))
        
        registered = 0
        for i, image_path in enumerate(image_files):
            if self.is_canceled():
                break
                
            if not self.db_manager.detect_duplicate_image(image_path):
                self.db_manager.register_image(image_path)
                registered += 1
            
            # 進捗報告
            percentage = int((i + 1) / len(image_files) * 100)
            self.report_progress(percentage, f"登録中: {image_path.name}")
        
        return {"registered": registered, "total": len(image_files)}

# 使用方法（QThreadPool使用）
worker = DatabaseRegistrationWorker(directory, db_manager, fsm)
worker.signals.progress.connect(update_progress)
worker.signals.finished.connect(on_finished)
QThreadPool.globalInstance().start(worker)
```

## 📋 実装計画

### Phase 1: 基盤実装 (3-4日)

**タスク:**
1. **GUI統合型ディレクトリ作成** (0.5日)
   - `src/lorairo/gui/workers/` ディレクトリ作成
   - `__init__.py`, `base.py` の基本実装

2. **SimpleWorkerBase実装** (1日)
   - QRunnable + QObject のハイブリッド実装
   - WorkerSignals, WorkerProgress の実装
   - 基本的なキャンセル機能

3. **ProgressManager実装** (1日)
   - QProgressDialog ベースの進捗管理
   - ワーカーとの統合インターフェース

4. **概念実証ワーカー** (1-1.5日)
   - SearchWorker の簡素化版実装
   - 動作確認とパフォーマンステスト

### Phase 2: 主要ワーカー移行 (4-5日)

**タスク:**
1. **DatabaseRegistrationWorker移行** (1.5日)
   - 新基底クラスベースで再実装
   - 既存機能の完全保持
   - 統合テスト

2. **ThumbnailWorker移行** (1.5日)
   - QPixmap処理の最適化
   - 大量画像対応の確認

3. **AnnotationWorker移行** (1.5日)
   - 非同期処理の改善
   - QtAsyncio活用の検討

4. **WorkerService統合** (0.5日)
   - 既存APIの維持
   - 内部実装の切り替え

### Phase 3: 完全移行とクリーンアップ (2-3日)

**タスク:**
1. **既存ワーカーシステム削除** (1日)
   - `src/lorairo/workers/` の段階的削除
   - インポートの更新

2. **テスト更新** (1日)
   - 新システム対応のテスト修正
   - 統合テストの実行

3. **ドキュメント更新** (0.5日)
   - アーキテクチャドキュメント更新
   - 使用方法の説明

## 🧪 テスト戦略

### 単体テスト
```python
# tests/unit/gui/workers/test_base.py
def test_simple_worker_base():
    worker = TestWorker()
    assert worker.is_canceled() == False
    worker.cancel()
    assert worker.is_canceled() == True
```

### 統合テスト
```python
# tests/integration/gui/workers/test_database_worker.py
def test_database_registration_worker():
    worker = DatabaseRegistrationWorker(test_dir, db_manager, fsm)
    result = worker.execute()
    assert result["registered"] > 0
```

### GUIテスト
```python
# tests/gui/test_worker_progress.py
def test_progress_dialog_integration(qtbot):
    progress_manager = ProgressManager()
    worker = TestWorker()
    progress_manager.start_worker_with_progress(worker, "Test", 100)
    qtbot.waitUntil(lambda: worker.is_finished())
```

## ⚠️ リスク分析と対策

| リスク | 影響度 | 対策 |
|--------|---------|------|
| 既存機能の破綻 | 高 | 段階的移行、並行テスト |
| パフォーマンス劣化 | 中 | ベンチマーク、最適化 |
| QtAsyncio互換性問題 | 中 | PySide6 6.6+要件確認 |
| テスト不足 | 中 | 包括的統合テスト |

## 🔄 移行戦略

### 段階的移行アプローチ
1. **並行運用期間**: 新旧システムが同時に存在
2. **機能単位切り替え**: Search → Thumbnail → Registration → Annotation
3. **即座のロールバック**: 問題発生時の迅速な対応

### 移行順序
- 非重要機能から開始
- 各段階での動作確認
- ユーザー影響の最小化

## 📊 期待される効果

### 定量的効果
- **コード削減**: 800行 → 200行（75%削減）
- **保守性向上**: 新人の理解時間50%短縮
- **パフォーマンス**: 現在の95%以上を維持
- **テストカバレッジ**: 85%以上

### 定性的効果
- PySide6標準機能の活用
- 直感的なディレクトリ構造
- 簡素で理解しやすいコード
- 将来的な拡張性向上

## 🎯 次のステップ

### 実装開始準備
1. PySide6バージョン確認
2. 既存テストのベースライン取得
3. 段階的移行ブランチの作成

### 承認事項
- [ ] 実装スケジュールの承認
- [ ] リスク対策の妥当性確認
- [ ] テスト戦略の合意

---

**実装開始予定**: 承認後即座  
**完了予定**: 承認から9-12日後  
**次フェーズ**: `@implement` コマンドで実装開始