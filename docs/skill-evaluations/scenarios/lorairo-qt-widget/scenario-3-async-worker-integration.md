# シナリオ: ウィジェットへの非同期ワーカー統合

## 入力

**ユーザー依頼:** "My AnnotationWidget needs to run AI annotation in the background without freezing the UI. Show me how to integrate with WorkerManager and handle results."

**前提条件:**
- LoRAIro は非同期処理に `WorkerManager` + `QThreadPool` を使用している。
- ウィジェットには以下の動作が求められる。
  - `WorkerManager` 経由でワーカーを起動する。
  - 実行中に進捗を表示する。
  - スロットでワーカーの結果を受け取る。
  - ワーカーのエラーを処理する。
- 既存の実装パターン: `DatabaseRegistrationWorker`、`AnnotationWorker`
- 配置場所: `src/lorairo/gui/workers/`

## 期待される動作

1. スキル `lorairo-qt-widget` が自動的に呼び出される。
2. 以下の手順に沿って非同期ワーカー統合パターンを提示する。

   **フェーズ 1: ワーカーパターンの確認**
   - 既存ワーカー (`AnnotationWorker`) を調べる。
   - `WorkerManager` の使用法を確認する。
   - メモリから非同期処理パターンを検索する。

   **フェーズ 2: ウィジェットの実装**
   - ワーカーを統合したウィジェットの例を示す。
     ```python
     class AnnotationWidget(QWidget):
         def __init__(self, parent: QWidget | None = None):
             super().__init__(parent)
             self.worker_manager = WorkerManager()
             self._setup_ui()

         @Slot()
         def _on_annotate_clicked(self) -> None:
             # Disable UI during processing
             self.annotate_button.setEnabled(False)
             self.progress_bar.show()

             # Create and run worker
             worker = AnnotationWorker(image_path=self.image_path)
             worker.signals.finished.connect(self._on_annotation_complete)
             worker.signals.error.connect(self._on_annotation_error)
             worker.signals.progress.connect(self._on_annotation_progress)

             self.worker_manager.run_worker(worker)

         @Slot(object)
         def _on_annotation_complete(self, result: AnnotationResult) -> None:
             # Re-enable UI
             self.annotate_button.setEnabled(True)
             self.progress_bar.hide()
             # Update UI with result
             self._display_result(result)

         @Slot(str)
         def _on_annotation_error(self, error_msg: str) -> None:
             # Re-enable UI
             self.annotate_button.setEnabled(True)
             self.progress_bar.hide()
             # Show error
             QMessageBox.warning(self, "Error", error_msg)

         @Slot(int)
         def _on_annotation_progress(self, percent: int) -> None:
             self.progress_bar.setValue(percent)
     ```

   **フェーズ 3: ベストプラクティス**
   - UI 状態管理 (処理中の無効化と完了後の再有効化)
   - 進捗フィードバックの表示
   - エラー処理
   - メモリ解放 (ワーカーシグナルの接続解除)

3. 以下の成果物を生成する。
   - 完全な非同期ウィジェットパターン
   - `WorkerManager` との統合実装
   - 進捗表示とエラー処理
   - UI 状態管理
   - ワーカーシグナル向けの型安全なスロット

4. 以下を行わない。
   - 長時間処理をメインスレッドで実行する。
   - エラー発生時に UI の再有効化を忘れる。
   - 進捗フィードバックを省略する。
   - ワーカーを解放せずメモリリークを起こす。

## 成功基準

- [x] 正しいスキル (`lorairo-qt-widget`) が呼び出された
- [x] パターン調査 (既存ワーカーや `WorkerManager` の確認) を行った
- [x] `WorkerManager` 経由でワーカーを作成および実行している
- [x] すべてのワーカーシグナル (`finished`、`error`、`progress`) を接続している
- [x] 処理中の無効化と処理後の有効化で UI 状態を管理している
- [x] 進捗フィードバックを表示している
- [x] 包括的なエラー処理がある
- [x] 型安全なスロットを使用している
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なワーカー統合を示せる。UI 状態管理やエラー処理には補足指示が必要な場合がある。
- **Sonnet:** すべてのシグナル接続を含む完全なパターンを提示できる。状態管理とエラー処理の品質が高い。
- **Opus:** キャンセル処理やワーカープーリングなどの追加パターンを提案する場合がある。UI 応答性の最適化やエラー復旧戦略にも優れる。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-qt-widget` が含まれていることを確認する。
2. ワーカー生成の確認:
   - 既存ワーカークラス (`AnnotationWorker`) を使用している。
   - 必須パラメータで適切に初期化している。
3. シグナル接続の確認:
   - `worker.signals.finished.connect(...)` -> 結果で UI を更新する。
   - `worker.signals.error.connect(...)` -> エラーダイアログを表示する。
   - `worker.signals.progress.connect(...)` -> プログレスバーを更新する。
4. UI 状態管理の検証:
   - 実行前: ボタンを無効化し、プログレスバーを表示する。
   - 成功後: ボタンを有効化し、プログレスバーを非表示にして結果を表示する。
   - エラー後: ボタンを有効化し、プログレスバーを非表示にしてエラーを表示する。
5. エラー処理の確認:
   - エラースロットがあらゆるエラー種別を処理できる。
   - ユーザーに分かりやすいエラーメッセージを表示する。
   - UI が操作可能な状態へ復帰する。
6. メモリ管理の検証:
   - 完了後にワーカーシグナルが切断される (または自動クリーンアップされる)。
   - 長寿命のワーカー参照によるメモリリークが発生しない。

## 検証すべきエッジケース

- ユーザーがボタンを素早く連続クリックした場合 (重複ワーカーの起動防止)
- 実行途中でワーカーがキャンセルされた場合 (適切なクリーンアップ)
- ワーカー実行中にウィジェットが破棄された場合 (シグナルの切断)
- ワーカーが例外で失敗した場合 (エラースロットの呼び出しと UI 復帰)
