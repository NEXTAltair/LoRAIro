# Search-Thumbnail Integration Phase 2 Implementation Plan

## 計画作成日: 2025-08-21

## Phase 2: Sequential Worker Pipeline Implementation

### 目標
SearchWorker完了 → ThumbnailWorker自動起動の連鎖パイプライン実装

### 確定要件（ユーザーヒアリング結果）

#### 1. パイプライン実行方式
- **オプションA採用**: 常に自動連鎖（検索完了 → 即座にサムネイル読み込み開始）

#### 2. 進捗表示詳細度  
- **簡易版採用**: 「検索中...」→「サムネイル読み込み中...」の2段階

#### 3. サムネイル表示領域動作
- **検索開始時**: サムネイルは即座にクリア
- **検索結果0件**: 何も表示しない（非表示状態）
- **読み込み中**: サムネイル領域に何も表示しない

#### 4. エラー・キャンセル処理
- **表示エラー時**: 検索結果も破棄
- **キャンセル時**: 検索結果も破棄  
- **自動リトライ**: 行わない

#### 5. パフォーマンス要件
- **読み込み枚数**: 上限設けない
- **並列処理**: 行わない（必要時に追加検討）
- **メモリ使用量**: 考慮しない

#### 6. UI/UX優先度
- **対象外**: このタスクではUI/UX改善は行わない（機能実装のみ）

### 実装計画

#### 1. WorkerService パイプライン機能追加
**ファイル**: `src/lorairo/gui/services/worker_service.py`
- **新規メソッド**: `start_search_to_thumbnail_pipeline(conditions)`
  - SearchWorker完了時の自動ThumbnailWorker起動ロジック
  - パイプライン全体の状態管理
- **新規シグナル**: `pipeline_stage_changed(stage_name: str)`
  - 段階通知: 「検索中」「サムネイル読み込み中」
- **エラー処理**: 任意段階でのエラー → 全体破棄・リセット

#### 2. FilterSearchPanel パイプライン対応
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`
- **検索メソッド変更**: `_on_search_requested()` 
  - `worker_service.start_search()` → `worker_service.start_search_to_thumbnail_pipeline()`
- **段階表示処理**: `pipeline_stage_changed` シグナル受信
  - プレビューテキスト更新（「検索中...」「サムネイル読み込み中...」）
- **破棄処理強化**: エラー・キャンセル時の即座リセット
  - 検索結果保持なし
- **新規シグナル**: `thumbnail_pipeline_completed(results)` 追加

#### 3. MainWindow 統合処理強化
**ファイル**: `src/lorairo/gui/window/main_window.py`
- **シグナル接続追加**: 
  - `FilterSearchPanel.thumbnail_pipeline_completed` → ThumbnailSelectorWidget表示処理
- **サムネイル領域制御**: 
  - 検索開始時の即座クリア実装
- **0件処理**: 
  - 結果0件時のサムネイル領域非表示処理

#### 4. ThumbnailSelectorWidget 連携確認・調整
**ファイル**: `src/lorairo/gui/widgets/thumbnail.py`
- **インターフェース確認**: 
  - `load_thumbnails_from_result()` メソッド引数仕様調査
- **結果0件対応**: 
  - 空結果での非表示処理実装確認

### 技術仕様詳細

#### パイプライン実行フロー
1. ユーザー検索実行 → `FilterSearchPanel._on_search_requested()`
2. `WorkerService.start_search_to_thumbnail_pipeline(conditions)` 呼び出し
3. SearchWorker開始 → `pipeline_stage_changed("検索中")`
4. SearchWorker完了 → 即座にThumbnailWorker開始
5. ThumbnailWorker開始 → `pipeline_stage_changed("サムネイル読み込み中")`
6. ThumbnailWorker完了 → `thumbnail_pipeline_completed(results)`
7. MainWindow → ThumbnailSelectorWidget自動表示

#### エラー処理フロー
- 任意段階でエラー発生 → パイプライン即座停止
- FilterSearchPanel → UI完全リセット
- MainWindow → サムネイル領域クリア
- 検索結果データ完全破棄

#### キャンセル処理フロー  
- ユーザーキャンセル → 現在段階のWorker停止
- 後続段階も含めパイプライン全体停止
- UI・データ完全リセット（エラー処理と同様）

### 完了判定基準
- ✅ 検索実行 → サムネイル自動読み込み → 表示の自動連鎖動作
- ✅ 2段階進捗表示（検索中/サムネイル読み込み中）  
- ✅ エラー・キャンセル時の完全破棄・リセット
- ✅ 検索結果0件時の適切な非表示処理
- ✅ 検索開始時のサムネイル領域即座クリア

### Phase 1からの継続項目
- Phase 1で実装済みの非同期検索機能は保持
- 進捗UI（プログレスバー/キャンセルボタン）は継続使用
- WorkerService依存注入は既存のまま活用

### 最終目標
**完全解決**: 「検索はできるが検索結果がサムネイルとして表示されない」問題

ユーザーが検索を実行すると、自動的に：
1. 検索実行（非同期・進捗表示付き）
2. 検索完了 → 即座にサムネイル読み込み開始
3. サムネイル読み込み完了 → 自動表示

この一連の流れが中断されることなく実行される。