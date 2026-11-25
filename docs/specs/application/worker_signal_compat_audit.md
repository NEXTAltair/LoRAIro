# Worker Signal 互換監査

version: "0.1.0" (Updated: 2026-05-24)

Parent: GitHub Issue #434 / Subissue #440

## 1. 目的

本書は、`WorkerService` が公開している既存のワーカー互換シグナルを棚卸しし、#434 の操作ライフサイクル移行で同時に変更する範囲と、後続 Issue へ分離する範囲を明確にする。

### 結論

- 検索・サムネイルパイプラインは、#434 の操作イベント移行対象に含める。
- バッチ登録・バッチ取込み・拡張アノテーションは #434 ではアダプタを維持し、操作イベント化は後続 Issue へ分離する。
- `worker_progress_updated` と `worker_batch_progress` は終端イベントではなく進捗通知チャネルのため、#434 では廃止対象としない。

## 2. シグナル棚卸し一覧

| シグナル | 主な購読者 | 現在の役割 | 即時判断 | 廃止順序・後続対応 |
| --- | --- | --- | --- | --- |
| `worker_terminal(object)` | `MainWindow._on_worker_terminal` | `WorkerTerminalEvent` を UI 層へ渡す正規のワーカー事実イベント | 維持 | #434 では生ワーカーライフサイクルの事実通知として残す。現在操作かどうかの判定は `WorkerService` 側へ移す |
| `search_started(str)` | `MainWindow._on_pipeline_search_started` | パイプライン進捗・状態の開始通知 | 操作イベントへ移行 | #438 で `OperationPhase.STARTED` 相当へ置換する。互換シグナルはアダプタとして残す |
| `search_finished(object)` | `MainWindow._on_search_completed_start_thumbnail`, `FilterSearchPanel._on_search_finished` | 検索成功結果をパイプラインと検索パネルへ通知 | 操作イベントへ移行 | #438 でパイプライン後始末とサムネイル開始判定を操作イベント主導へ移す。`FilterSearchPanel.search_completed` は外部互換として残す |
| `search_error(str)` | `MainWindow._on_pipeline_search_error`, `FilterSearchPanel._on_search_error` | 検索失敗時のパイプライン後始末、エラー通知、検索パネル状態更新 | 操作イベントへ移行 | #438 で現行・置換済み判定後の操作失敗へ置換する。互換エラーはアダプタ化し、新規購読を禁止する |
| `search_canceled(str)` | `FilterSearchPanel._on_search_canceled` | 検索キャンセル時の検索パネル状態更新 | 操作イベントへ移行 | #438 で `CANCELED` と `SUPERSEDED` を区別する。置換キャンセルはユーザー可視キャンセルとして扱わない |
| `thumbnail_started(str)` | `MainWindow._on_pipeline_thumbnail_started` | サムネイル段階の進捗・状態開始通知 | 操作イベントへ移行 | #438 でサムネイル操作開始イベントへ置換する |
| `thumbnail_finished(object)` | `MainWindow._on_thumbnail_completed_update_display` | サムネイル成功後の表示更新 | 操作イベントへ移行 | #438 で現行サムネイル操作の成功時のみ表示更新する |
| `thumbnail_error(str)` | `MainWindow._on_pipeline_thumbnail_error` | サムネイル失敗時のパイプライン後始末とエラー通知 | 操作イベントへ移行 | #438 で現行・置換済み判定後の操作失敗へ置換する。プリフェッチや置換では表示を破棄しない |
| `thumbnail_canceled(str)` | 現在の直接購読なし | サムネイルキャンセルの互換通知 | アダプタ維持のみ | #438 後に未使用であれば非推奨としてドキュメントへ記載し、削除は後続で判断する |
| `batch_registration_started(str)` | `MainWindow._on_batch_registration_started` | データセット登録の進捗状態開始 | アダプタ維持 | 後続 Issue で登録操作イベント化を検討する |
| `batch_registration_finished(object)` | `MainWindow._on_batch_registration_finished` | 登録結果処理と完了シグナル発行 | アダプタ維持 | 後続 Issue。`ResultHandlerService` と完了シグナルの移行設計が必要 |
| `batch_registration_error(str)` | `MainWindow._on_batch_registration_error` | 進捗状態エラー、`QMessageBox`、エラー通知更新 | アダプタ維持 | 後続 Issue。UI ダイアログ表示責務の分離が必要 |
| `batch_registration_canceled(str)` | `MainWindow._on_batch_registration_canceled` | 進捗状態のキャンセル更新 | アダプタ維持 | 後続 Issue。キャンセル通知と進捗状態を操作結果へ寄せる |
| `batch_import_started(str)` | 現在の直接購読なし | 取込み進捗ダイアログ開始用に発行されるが `MainWindow` では未接続 | アダプタ維持・監査対象 | 後続 Issue。未接続が意図どおりか確認し、必要なら進捗状態の開始ハンドラを追加する |
| `batch_import_finished(object)` | `MainWindow._on_batch_import_finished` | 結果ダイアログとステータスバー更新 | アダプタ維持 | 後続 Issue。dry-run・本番結果表示を操作結果ハンドラへ分離する |
| `batch_import_error(str)` | `MainWindow._on_batch_import_error` | `QMessageBox` とエラー通知更新 | アダプタ維持 | 後続 Issue。エラー UI 責務の分離が必要 |
| `batch_import_canceled(str)` | `MainWindow._on_batch_import_canceled` | 進捗状態のキャンセル更新 | アダプタ維持 | 後続 Issue |
| `enhanced_annotation_started(str)` | 現在の直接購読なし | アノテーション進捗ダイアログ開始用に発行されるが `MainWindow` では未接続 | アダプタ維持・監査対象 | 後続 Issue。別経路の `_on_batch_annotation_started` と統合すべきか確認する |
| `enhanced_annotation_finished(object)` | `MainWindow._on_annotation_finished` | サマリーダイアログ、結果ハンドラ、データセットキャッシュ更新 | アダプタ維持 | 後続 Issue。完了後のキャッシュ更新を操作結果ハンドラとして設計する |
| `enhanced_annotation_error(str)` | `MainWindow._on_annotation_error` | 結果ハンドラエラー、ステータスバー、エラー通知更新 | アダプタ維持 | 後続 Issue |
| `enhanced_annotation_canceled(str)` | `MainWindow._on_annotation_canceled` | 進捗状態のキャンセル更新 | アダプタ維持 | 後続 Issue |
| `worker_progress_updated(str, object)` | `MainWindow._on_worker_progress_updated`, `WorkerService._on_progress_updated` | ワーカー単位の進捗を進捗マネージャ・状態へ伝達 | 維持 | 操作終端移行とは別扱い。`operation_id` の追加は後続の進捗契約で検討する |
| `worker_batch_progress(str, int, int, str)` | `MainWindow._on_worker_batch_progress`, `FilterSearchPanel._on_worker_batch_progress`, `WorkerService._on_batch_progress_updated` | バッチ進捗と検索パネル進捗の更新 | 維持 | #438 で検索パネル側の現行ワーカー判定のみ操作コンテキストへ寄せる可能性がある |
| `active_worker_count_changed(int)` | `WorkerService` 経由で外部公開 | アクティブワーカー数の更新 | 維持 | ワーカーライフサイクル管理シグナルのため操作イベント移行対象外 |
| `all_workers_finished()` | `WorkerService` 経由で外部公開 | 全ワーカー停止通知 | 維持 | ワーカーライフサイクル管理シグナルのため操作イベント移行対象外 |

## 3. 発行元と購読者の所見

- **`WorkerManager`**: `worker_started`、`worker_terminal`、`worker_finished`、`worker_error`、`worker_canceled`、`active_worker_count_changed`、`all_workers_finished` を持つ。この層の `worker_finished`、`worker_error`、`worker_canceled` は `WorkerTerminalEvent` から派生するマネージャ層の互換シグナルであり、操作単位や現行・置換済みの判定は入れない。
- **`WorkerService`**: `WorkerManager.worker_terminal` を受け取り、ワーカー ID のプレフィックスから検索・サムネイル・バッチ・アノテーションの各互換シグナルへ振り分けている。このプレフィックス振り分けは移行用アダプタとみなし、新規 UI は直接依存しない。
- **`MainWindow`**: 現在も検索・サムネイル・バッチ登録・バッチ取込み・拡張アノテーションの互換シグナルを購読している。検索・サムネイルは `PipelineControlService` へ委譲するだけの箇所が多く、操作イベントへ移行しやすい。一方、バッチ・アノテーション系は `QMessageBox`、ステータスバー、サマリーダイアログ、キャッシュ更新、完了シグナルに直結しているため、#434 のパイプライン移行とは同時に変更しない。
- **`FilterSearchPanel`**: `search_finished`、`search_error`、`search_canceled` と `worker_batch_progress` を直接購読している。#438 ではこれらを見落とさず、検索パネルの内部状態 `PipelineState` と外部互換 `search_completed` を操作イベントから更新する。
- **`DatasetController`・`AnnotationWorkflowController`**: ワーカーを開始するだけで、互換シグナルを直接購読していない。ただし、バッチ登録や拡張アノテーションの後続移行では、開始 API と `operation_id` の返却形式がこれらのコントローラへ影響する可能性がある。

## 4. #434 で残してよい互換シグナル

#434 の完了時点で、以下のシグナルは意図的に残してよい。

- **バッチ登録**: `batch_registration_started`、`finished`、`error`、`canceled`
- **バッチ取込み**: `batch_import_started`、`finished`、`error`、`canceled`
- **拡張アノテーション**: `enhanced_annotation_started`、`finished`、`error`、`canceled`
- **進捗通知**: `worker_progress_updated`、`worker_batch_progress`
- **マネージャライフサイクル**: `active_worker_count_changed`、`all_workers_finished`

検索・サムネイルの互換シグナルは #434 の途中でアダプタ扱いへ格下げする。削除は #434 の最終 PR では行わず、購読者を操作イベントへ移行したあとに別 Issue で検討する。

## 5. 後続 Issue 候補

1. **バッチ登録の操作イベント移行**
   - `batch_registration_*` を操作結果から派生するアダプタへ変更する。
   - `ProgressStateService`、`ResultHandlerService`、`database_registration_completed` の責務を分離する。
2. **バッチ取込みの操作イベント移行**
   - `batch_import_started` が未接続のままでよいか確認する。
   - 結果ダイアログ・ステータスバー・dry-run 表示を操作結果ハンドラへ分離する。
3. **拡張アノテーションの操作イベント移行**
   - `enhanced_annotation_started` が未接続のままでよいか確認する。
   - サマリーダイアログ・結果ハンドラ・データセットキャッシュ更新を操作結果ハンドラへ分離する。
4. **進捗チャネル契約の整理**
   - `worker_progress_updated` と `worker_batch_progress` に `operation_id` を持たせるか検討する。
   - 検索パネルの進捗判定をワーカー ID 依存から操作コンテキスト依存へ移行する。
5. **検索・サムネイル互換シグナルの廃止**
   - #438 で直接購読者を操作イベントへ移したあと、`search_*` と `thumbnail_*` の公開範囲をプライベートアダプタまたは非推奨 API として整理する。
