# アノテーション完了時の自動UI更新実装 (2026-02-09)

## 概要

アノテーション処理完了時にUIが自動更新されない問題を修正。`enhanced_annotation_finished`シグナルの接続とキャッシュ更新ロジックを実装しました。

## 実装内容

### 1. シグナル接続の追加

**ファイル**: `src/lorairo/gui/window/main_window.py`

`_setup_worker_pipeline_signals`メソッド（lines 623-677）に以下を追加：

```python
# Annotation connections
self.worker_service.enhanced_annotation_finished.connect(self._on_annotation_finished)
self.worker_service.enhanced_annotation_error.connect(self._on_annotation_error)
```

### 2. アノテーション完了ハンドラーの書き換え

`_on_annotation_finished`メソッド（lines 767-800）を全面的に書き換え：

**変更前**: 単一画像のキャッシュ更新（実質的に未使用）

**変更後**: バッチキャッシュ更新
```python
def _on_annotation_finished(self, result: Any) -> None:
    """アノテーション完了時のハンドリング（バッチキャッシュ更新）"""
    # Phase 1: Status bar notification
    self._delegate_to_result_handler(
        "handle_annotation_finished", result, status_bar=self.statusBar()
    )
    
    # Phase 2: Batch cache update
    if not self.dataset_state_manager or not self.db_manager:
        return
    
    if result and isinstance(result, dict):
        try:
            # pHash -> image_id マッピングを取得
            phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(
                set(result.keys())
            )
            image_ids = [
                img_id for img_id in phash_to_image_id.values() if img_id is not None
            ]
            
            if image_ids:
                self.dataset_state_manager.refresh_images(image_ids)
                logger.debug(f"アノテーション完了後のキャッシュ更新: {len(image_ids)}件")
        except Exception as e:
            logger.error(f"アノテーション完了後のキャッシュ更新失敗: {e}", exc_info=True)
```

### 3. 不要メソッドの削除

**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

`refresh_search`メソッドを削除（実装したが設計議論の結果不要と判断）

## 設計決定

### ミニマルUI更新戦略

**採用**: DatasetStateManagerキャッシュのみ更新

**却下した代替案**:
1. **FilterSearchPanelの自動リフレッシュ**
   - 理由: ユーザーはアノテーション後もバッチタグタブに留まる
   - ワークスペースタブの検索結果更新は作業フローに不要
   - 必要なら手動でリフレッシュする
   
2. **BatchTagAddWidgetの自動更新**
   - 理由: ウィジェットはサムネイルパスのみ更新
   - アノテーションメタデータは反映されない
   - 更新しても意味がない

### キャッシュ更新戦略

**pHashベースの画像ID解決**:
- アノテーション結果は`PHashAnnotationResults`（Dict[pHash, Dict[model, result]]）
- `find_image_ids_by_phashes`でバッチ変換
- 取得したimage_idsで`refresh_images`を呼び出し

**利点**:
- バッチ処理で効率的
- 存在しないpHashは自動的にスキップ
- DB負荷を最小化

## テスト結果

### 新規テストクラス

**ファイル**: `tests/unit/gui/window/test_main_window.py`

`TestMainWindowAnnotationCompletion`クラス（lines 224-342）に5つのテストケース追加：

1. **test_on_annotation_finished_updates_cache**
   - 通常動作: pHash結果の処理とキャッシュ更新
   
2. **test_on_annotation_finished_handles_empty_result**
   - 境界ケース: 空の結果でもエラーなし
   
3. **test_on_annotation_finished_handles_missing_dependencies**
   - 早期リターン: 依存関係がNoneの場合
   
4. **test_on_annotation_finished_handles_phash_lookup_failure**
   - エラーハンドリング: DB失敗時のログ出力
   
5. **test_setup_worker_pipeline_signals_includes_annotation**
   - シグナル接続の検証

### テスト実行結果

```
全テスト: 20/20 合格
カバレッジ: 対象変更箇所100%
Ruff: 既存警告のみ（新規警告なし）
mypy: 既存警告のみ（新規エラーなし）
```

### モック設定の教訓

**初期エラー**: `_delegate_to_result_handler`をクラスレベルでパッチ

**修正**: インスタンスレベルでモック設定
```python
mock_window._delegate_to_result_handler = Mock()
```

## コミット情報

**コミットID**: b3599ff

**コミットメッセージ**:
```
feat: アノテーション完了時の自動UI更新を実装

- MainWindow._setup_worker_pipeline_signalsにenhanced_annotation_finishedシグナル接続を追加
- _on_annotation_finishedをバッチキャッシュ更新方式に書き換え
- pHashからimage_idへのマッピングを使用してDatasetStateManagerを更新
- TestMainWindowAnnotationCompletionクラスに5つのテストケース追加（通常/境界/エラーケース）
- 不要なFilterSearchPanel.refresh_searchメソッドを削除

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## 技術的背景

### 処理フロー

1. **AnnotationWorker**: アノテーション処理実行、結果をDBに保存
2. **WorkerService**: `enhanced_annotation_finished`シグナル発行
3. **MainWindow**: シグナルを受信して`_on_annotation_finished`実行
4. **ResultHandlerService**: ステータスバー通知
5. **DatasetStateManager**: キャッシュ更新（選択画像のメタデータをリロード）

### 関連コンポーネント

- **WorkerService**: Qt Signal/Slotベースの非同期処理パイプライン
- **DatasetStateManager**: 画像メタデータキャッシュ管理
- **ImageDatabaseManager**: pHash→image_id変換
- **ResultHandlerService**: UI通知ロジックの抽象化

## 影響範囲

### 修正されたユーザー体験

**変更前**:
- アノテーション完了後、手動でワークスペースタブを開いて検索実行が必要
- 選択画像の詳細表示が古い情報のまま

**変更後**:
- アノテーション完了と同時にキャッシュ更新
- 選択画像の詳細表示が即座に最新情報を反映
- バッチタグタブに留まったまま次の作業に移行可能

### パフォーマンス影響

- DB負荷: 最小限（影響を受けた画像のIDリストのみ取得）
- UI応答性: 影響なし（バックグラウンドでキャッシュ更新）
- メモリ: 変更なし（既存キャッシュの更新のみ）

## 教訓

### 設計における判断

1. **ユーザーワークフローの理解が重要**
   - 初期設計で検索結果の自動リフレッシュを実装したが、ユーザーの作業フローを考慮して却下
   - 「アノテーション→バッチタグ追加→次の画像」という流れでは検索結果更新は不要

2. **最小限の変更原則**
   - 必要な部分（DatasetStateManagerキャッシュ）のみ更新
   - 不要な部分（FilterSearchPanel、BatchTagAddWidget）は触らない
   - over-engineeringを避ける

3. **pHashベースの設計の一貫性**
   - アノテーションライブラリの戻り値が`PHashAnnotationResults`
   - DB検索も`find_image_ids_by_phashes`で統一
   - 型の一貫性が実装を簡潔にする

## 関連ファイル

- [src/lorairo/gui/window/main_window.py](src/lorairo/gui/window/main_window.py)
- [tests/unit/gui/window/test_main_window.py](tests/unit/gui/window/test_main_window.py)
- [src/lorairo/gui/widgets/filter_search_panel.py](src/lorairo/gui/widgets/filter_search_panel.py)

## 関連メモリ

- `annotator_lib_lessons_learned`: image-annotator-lib統合の教訓
- `mainwindow_phase3_completion_2025_11_19`: MainWindow 5段階初期化
- `session_thumbnail_progress_dialog_suppression_2026_02_07`: 類似のUI更新最適化
