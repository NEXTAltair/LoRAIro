---
type: Report
title: 廃止機能一覧 (DEPRECATIONS)
status: Accepted (Historical)
timestamp: 2026-07-02
tags: [gui, migration]
---
# 廃止機能一覧 (DEPRECATIONS)

> **注記**: 本ドキュメントは2025年頃の「専用ページ → 3パネル MainWindow」移行の記録。
> その後 Epic #867 で 3パネル MainWindow 自体もタブ構成 (`src/lorairo/gui/tab/`) へ
> 再分解されている。現行の GUI 構成は `docs/architecture.md` の GUI Architecture 節、
> サービス一覧は `docs/services.md` を参照。

## GUI アーキテクチャ移行による廃止機能

新しいPySide6統合ワークフロー（MainWindow）への移行により、以下の機能が廃止されました。

### 6.1. AIタグ付けページ (廃止)

**旧実装:** 専用ページでのAI アノテーション処理

**主要メソッド:**
- `on_pushButtonSelectDirectory_clicked()` - ディレクトリ選択
- `on_pushButtonStartAnnotation_clicked()` - アノテーション開始  
- `display_annotation_results()` - 結果表示
- `save_annotations_to_files()` - ファイル保存

**進捗管理:**
- `update_progress_bar()` - プログレスバー更新
- `update_status_label()` - ステータス表示
- `show_completion_message()` - 完了メッセージ

**新実装での対応:** 
- MainWindow の AnnotationWorker により統合
- PreviewDetailPanel での直接編集対応
- WorkerService による統一進捗管理

### 6.2. データセット概要ページ (廃止)

**旧実装:** 専用ページでのデータセット管理・概要表示

**主要メソッド:**
- `load_dataset_overview()` - データセット概要読み込み
- `display_image_statistics()` - 統計情報表示
- `show_recent_annotations()` - 最新アノテーション表示
- `export_dataset_summary()` - サマリーエクスポート

**統計表示:**
- `calculate_tag_distribution()` - タグ分布計算
- `calculate_resolution_stats()` - 解像度統計
- `show_annotation_coverage()` - アノテーション率表示

**新実装での対応:**
- FilterSearchPanel による統合検索・フィルタリング
- ThumbnailSelectorWidget による直感的データセット表示
- DatasetStateManager による統一状態管理

## 旧ワーカーシステム (progress.py)

**廃止クラス:**
- `Worker(QObject)` - コールバック基盤の旧実装
- `ProgressWidget` - 専用進捗表示ウィジェット
- `Controller` - 旧ワーカー制御システム

**新実装:** 
- `LoRAIroWorkerBase` (workers/base.py) による統一基底クラス
- PySide6 QProgressDialog による標準進捗表示
- WorkerService による高レベルAPI提供

## 旧メインウィンドウ (main_window.py)

**廃止クラス:**
- `MainWindow(QMainWindow, Ui_MainWindow)` - レガシーメインウィンドウ

**新実装 (当時):**
- `MainWindow` (`src/lorairo/gui/window/main_window.py`) - データベース中心の統合ワークフロー
- 3パネル構成による直感的操作
- ワーカーシステム完全統合

**さらなる移行 (Epic #867)**: 上記の3パネル構成も後にタブ構成へ再分解された。
`MainWindow` は各タブウィジェット (`src/lorairo/gui/tab/`) を配置する接着剤役に変わり、
`FilterSearchPanel` / `ThumbnailSelectorWidget` / `PreviewDetailPanel` という具体クラスは
存在しない。詳細は `docs/architecture.md` の GUI Architecture 節を参照。

## 移行ガイド

### 開発者向け

**旧API → 新API:**
```python
# 旧実装
from .progress import Worker, ProgressWidget
worker = Worker(function, args)

# 新実装
from ...workers.registration_worker import DatabaseRegistrationWorker
worker = DatabaseRegistrationWorker(directory, db_manager, fsm)
```

**統合ワークフロー:**
- 専用ページ → MainWindow統合パネル
- 個別処理 → WorkerService統一API
- 独自進捗 → PySide6標準ダイアログ

### ユーザー向け

**ワークフロー変更:**
1. **AIタグ付け:** メニューバー → 統合ワークフロー
2. **データセット管理:** 専用ページ → 3パネル統合表示  
3. **進捗表示:** カスタムウィジェット → 標準ダイアログ

**機能統合による利点:**
- シングルウィンドウ操作
- リアルタイム状態同期
- 直感的なワークフロー
