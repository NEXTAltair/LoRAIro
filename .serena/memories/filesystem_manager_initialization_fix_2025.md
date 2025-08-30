# FileSystemManager初期化問題の解決実装記録

## 実装日時
2025-08-28

## 問題概要
データセット選択→データベース登録処理で以下のエラーが発生：
```
original_images_dir is not set. Call initialize() first.
```

## 根本原因分析

### 問題の核心
`DatabaseRegistrationWorker`が`FileSystemManager.save_original_image()`を呼び出す際、`FileSystemManager.initialize()`が呼び出されていないため、`original_images_dir`が未設定の状態。

### アーキテクチャ上の問題
```
MainWindow.select_dataset_directory()
  ↓
WorkerService.start_batch_registration()  # MainWindowのFSMインスタンスとは別
  ↓
DatabaseRegistrationWorker(directory, db_manager, self.fsm)  # 未初期化のFSM
  ↓
fsm.save_original_image() → エラー：original_images_dir未設定
```

## 解決アプローチ

### 1. MainWindow側の修正
**対象**: `src/lorairo/gui/window/main_window.py:select_dataset_directory()`

**Before**: 
```python
# バッチ登録開始
self.worker_service.start_batch_registration(Path(directory))
```

**After**:
```python
# FileSystemManagerの初期化（必須）
if not self.file_system_manager:
    # 致命的エラー - アプリケーション終了
    error_msg = "FileSystemManagerが初期化されていません。バッチ登録処理を実行できません。"
    logger.critical(f"Critical error during batch registration: {error_msg}")
    self._handle_critical_initialization_failure("FileSystemManager", RuntimeError(error_msg))
    return
    
# 選択されたディレクトリの親ディレクトリに出力する
output_dir = Path(directory).parent / "lorairo_output"
self.file_system_manager.initialize(output_dir)

# バッチ登録開始（初期化済みFileSystemManagerを渡す）
worker_id = self.worker_service.start_batch_registration_with_fsm(
    Path(directory), self.file_system_manager
)
```

### 2. WorkerService側の拡張
**対象**: `src/lorairo/gui/services/worker_service.py`

**新規メソッド追加**:
```python
def start_batch_registration_with_fsm(self, directory: Path, fsm: FileSystemManager) -> str:
    """
    バッチ登録開始（FileSystemManager指定版）

    Args:
        directory: 登録対象ディレクトリ
        fsm: 初期化済みFileSystemManager

    Returns:
        str: ワーカーID
    """
    worker = DatabaseRegistrationWorker(directory, self.db_manager, fsm)
    worker_id = f"batch_reg_{uuid.uuid4().hex[:8]}"

    # 進捗シグナル接続
    worker.progress_updated.connect(
        lambda progress: self.worker_progress_updated.emit(worker_id, progress)
    )
    worker.batch_progress.connect(
        lambda current, total, filename: self.worker_batch_progress.emit(
            worker_id, current, total, filename
        )
    )

    if self.worker_manager.start_worker(worker_id, worker):
        logger.info(f"バッチ登録開始: {directory} (ID: {worker_id})")
        return worker_id
    else:
        raise RuntimeError(f"ワーカー開始失敗: {worker_id}")
```

## 技術的詳細

### FileSystemManager初期化仕様
```python
def initialize(self, output_dir: Path) -> None:
    """
    FileSystemManagerを初期化　基本的なディレクトリ構造のみ作成
    
    Args:
        output_dir (Path): 出力ディレクトリのパス
    """
    # 画像出力ディレクトリをセットアップ
    self.image_dataset_dir = output_dir / "image_dataset"
    original_dir = self.image_dataset_dir / "original_images"
    
    # 日付ベースのサブディレクトリ
    current_date = datetime.now().strftime("%Y/%m/%d")
    self.original_images_dir = original_dir / current_date
```

### 出力ディレクトリ構造
```
選択されたディレクトリの親/
└── lorairo_output/
    ├── image_database.db
    ├── image_dataset/
    │   └── original_images/
    │       └── 2025/08/28/
    │           ├── 1_20250626/
    │           │   ├── sample_xxx.jpg
    │           │   └── gamingadultlb.gif
    │           └── 1_20250816/
    │               └── 画像ファイル群...
    └── batch_request_jsonl/
```

### エラーハンドリング方針
- `file_system_manager`が利用不可の場合：致命的エラーとして`_handle_critical_initialization_failure()`でアプリケーション終了
- 初期化済みインスタンスを明示的に渡すことで、依存性を明確化

## 実装効果

### Before（エラー状態）
```
ERROR | original_images_dir is not set. Call initialize() first.
ERROR | 画像登録失敗: sample_xxx.jpg
INFO  | データベース登録完了: 登録=0, スキップ=0, エラー=2
```

### After（期待結果）
```
INFO  | バッチ登録開始: J:\...\1_20250626 (ID: batch_reg_xxx)
INFO  | 元画像を保存: .../lorairo_output/image_dataset/original_images/2025/08/28/1_20250626/sample_xxx.jpg
INFO  | オリジナル画像を登録しました: ID=1, Path=...
INFO  | データベース登録完了: 登録=2, スキップ=0, エラー=0
```

## 関連実装

### 依存コンポーネント
- `FileSystemManager.initialize()`: 出力ディレクトリ構造の作成
- `DatabaseRegistrationWorker`: FSMインスタンスを引数で受け取り
- `MainWindow._handle_critical_initialization_failure()`: 致命的エラー処理

### 代替アプローチとの比較
1. **WorkerService内でFSM初期化**: ディレクトリ情報がWorkerServiceに伝わらない
2. **DatabaseRegistrationWorkerで自動初期化**: 責任分離の原則に反する
3. **GlobalなFSMインスタンス**: テスタビリティ低下
4. **選択アプローチ（依存注入）**: 責任明確・テスト容易・アーキテクチャ一貫性

## 教訓・パターン

### 依存注入パターン
- 初期化済みサービスを明示的に渡すことで依存関係を明確化
- テスト時のモック化が容易
- デバッグ時の問題特定が迅速

### エラーハンドリング戦略
- 致命的エラー（システム初期化失敗）：アプリケーション終了
- 一時的エラー（ネットワーク等）：リトライ・フォールバック
- 予期可能エラー（ユーザー入力）：ユーザー通知

### ファイルシステム設計
- 日付ベースディレクトリ構造による整理性
- 親ディレクトリへの出力でユーザーファイル保護
- 設定可能な出力先による柔軟性