---
type: Report
title: 廃止機能一覧 (DEPRECATIONS)
status: Accepted (Historical)
timestamp: 2026-07-02
tags: [gui, migration]
---
# 廃止機能一覧(DEPRECATIONS)

> **注記**: 本ドキュメントは 2025 年頃に行った「専用ページから 3 パネル MainWindow への移行」の記録である。
> その後 Epic #867 で 3 パネル MainWindow 自体もタブ構成(`src/lorairo/gui/tab/`)へ再分解された。現行の GUI 構成は `docs/architecture.md` の「GUI アーキテクチャ」節、サービス一覧は `docs/services.md` を参照する。

## GUI アーキテクチャ移行による廃止機能

PySide6 統合ワークフロー(`MainWindow`)への移行に伴い、以下の機能を廃止した。

### 6.1. AI タグ付けページ(廃止)

**旧実装**: 専用ページでの AI アノテーション処理

**主要メソッド**:
- `on_pushButtonSelectDirectory_clicked()` — ディレクトリ選択
- `on_pushButtonStartAnnotation_clicked()` — アノテーション開始
- `display_annotation_results()` — 結果表示
- `save_annotations_to_files()` — ファイル保存

**進捗管理**:
- `update_progress_bar()` — プログレスバー更新
- `update_status_label()` — ステータス表示
- `show_completion_message()` — 完了メッセージ表示

**移行先(当時)**:
- `MainWindow` の `AnnotationWorker` へ統合
- `PreviewDetailPanel` での直接編集に対応
- `WorkerService` による統一的な進捗管理

### 6.2. データセット概要ページ(廃止)

**旧実装**: 専用ページでのデータセット管理と概要表示

**主要メソッド**:
- `load_dataset_overview()` — データセット概要の読み込み
- `display_image_statistics()` — 統計情報の表示
- `show_recent_annotations()` — 最新アノテーションの表示
- `export_dataset_summary()` — サマリーのエクスポート

**統計表示**:
- `calculate_tag_distribution()` — タグ分布の計算
- `calculate_resolution_stats()` — 解像度統計の計算
- `show_annotation_coverage()` — アノテーション率の表示

**移行先(当時)**:
- `FilterSearchPanel` による統合検索・フィルタリング
- `ThumbnailSelectorWidget` による直感的なデータセット表示
- `DatasetStateManager` による統一的な状態管理

## 旧ワーカーシステム(`progress.py`)

**廃止クラス**:
- `Worker(QObject)` — コールバック基盤の旧実装
- `ProgressWidget` — 専用の進捗表示ウィジェット
- `Controller` — 旧ワーカー制御システム

**新実装**:
- `LoRAIroWorkerBase`(`workers/base.py`)による統一基底クラス
- PySide6 の `QProgressDialog` による標準進捗表示
- `WorkerService` による高レベル API の提供

## 旧メインウィンドウ(`main_window.py`)

**廃止クラス**:
- `MainWindow(QMainWindow, Ui_MainWindow)` — レガシーメインウィンドウ

**新実装(当時)**:
- `MainWindow`(`src/lorairo/gui/window/main_window.py`)によるデータベース中心の統合ワークフロー
- 3 パネル構成による直感的な操作体系
- ワーカーシステムの完全統合

**さらなる移行(Epic #867)**: 上記の 3 パネル構成も後にタブ構成へ再分解された。現在の `MainWindow` は各タブウィジェット(`src/lorairo/gui/tab/`)を配置する接着剤役に徹しており、`FilterSearchPanel`・`ThumbnailSelectorWidget`・`PreviewDetailPanel` の具体クラスは存在しない。詳細は `docs/architecture.md` の「GUI アーキテクチャ」節を参照する。

## 移行ガイド

### 開発者向け

**旧 API から新 API への置き換え**:

```python
# 旧実装
from .progress import Worker, ProgressWidget
worker = Worker(function, args)

# 新実装
from ...workers.registration_worker import DatabaseRegistrationWorker
worker = DatabaseRegistrationWorker(directory, db_manager, fsm)
```

**統合ワークフローへの変更点**:
- 専用ページから `MainWindow` の統合パネルへ移行した
- 個別処理から `WorkerService` の統一 API へ移行した
- 独自の進捗ウィジェットから PySide6 標準ダイアログへ移行した

### ユーザー向け

**ワークフローの変更点**:
1. **AI タグ付け**: メニューバー起点の操作から統合ワークフローへ移行した
2. **データセット管理**: 専用ページから 3 パネル統合表示へ移行した
3. **進捗表示**: カスタムウィジェットから標準ダイアログへ移行した

**統合による利点**:
- シングルウィンドウでの一貫した操作
- リアルタイムな状態同期
- 直感的なワークフロー
