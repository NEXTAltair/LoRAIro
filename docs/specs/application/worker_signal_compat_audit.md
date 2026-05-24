# Worker Signal 互換監査

version: "0.1.0" (Updated: 2026-05-24)

Parent: GitHub Issue #434 / Subissue #440

## 1. 目的

本書は `WorkerService` が公開している既存の worker compat signal を棚卸しし、#434 の
operation lifecycle 移行で同時に変更する範囲と、後続 issue に分離する範囲を明確にする。

結論:

- search / thumbnail pipeline は #434 の operation event 移行対象に含める。
- batch registration / batch import / enhanced annotation は #434 では adapter 維持とし、
  operation event 化は後続 issue に分離する。
- `worker_progress_updated` / `worker_batch_progress` は terminal event ではなく progress channel
  なので、#434 では廃止対象にしない。

## 2. Signal Inventory

| Signal | 主な購読者 | 現在の役割 | 即時判断 | 廃止順序 / 後続 |
| --- | --- | --- | --- | --- |
| `worker_terminal(object)` | `MainWindow._on_worker_terminal` | `WorkerTerminalEvent` を UI 層へ渡す canonical worker fact event | 維持 | #434 では raw worker lifecycle の事実通知として残す。operation/current 判定は `WorkerService` 側へ移す |
| `search_started(str)` | `MainWindow._on_pipeline_search_started` | pipeline progress/state 開始通知 | operation event へ移行 | #438 で `OperationPhase.STARTED` 相当に置換。compat は adapter として残す |
| `search_finished(object)` | `MainWindow._on_search_completed_start_thumbnail`, `FilterSearchPanel._on_search_finished` | 検索成功結果を pipeline と検索パネルへ通知 | operation event へ移行 | #438 で pipeline cleanup と thumbnail 開始判定を operation event 主導へ移す。`FilterSearchPanel.search_completed` は外部互換として残す |
| `search_error(str)` | `MainWindow._on_pipeline_search_error`, `FilterSearchPanel._on_search_error` | 検索失敗時の pipeline cleanup、エラー通知、検索パネル状態更新 | operation event へ移行 | #438 で current/superseded 判定後の operation failure に置換。compat error は adapter 化し、新規購読禁止 |
| `search_canceled(str)` | `FilterSearchPanel._on_search_canceled` | 検索キャンセル時の検索パネル状態更新 | operation event へ移行 | #438 で `CANCELED` / `SUPERSEDED` を区別する。replacement cancel は user-visible cancel として扱わない |
| `thumbnail_started(str)` | `MainWindow._on_pipeline_thumbnail_started` | thumbnail phase の progress/state 開始通知 | operation event へ移行 | #438 で thumbnail operation started へ置換 |
| `thumbnail_finished(object)` | `MainWindow._on_thumbnail_completed_update_display` | thumbnail 成功後の表示更新 | operation event へ移行 | #438 で current thumbnail operation の成功のみ表示更新する |
| `thumbnail_error(str)` | `MainWindow._on_pipeline_thumbnail_error` | thumbnail 失敗時の pipeline cleanup とエラー通知 | operation event へ移行 | #438 で current/superseded 判定後の operation failure に置換。prefetch/replacement は表示破棄しない |
| `thumbnail_canceled(str)` | 現在の直接購読なし | thumbnail cancel の互換通知 | adapter 維持のみ | #438 後に未使用なら deprecated として docs に残し、削除は後続で判断 |
| `batch_registration_started(str)` | `MainWindow._on_batch_registration_started` | dataset registration progress state 開始 | adapter 維持 | 後続 issue で registration operation event 化を検討 |
| `batch_registration_finished(object)` | `MainWindow._on_batch_registration_finished` | registration result handling と completion signal | adapter 維持 | 後続 issue。`ResultHandlerService` と completion signal の移行設計が必要 |
| `batch_registration_error(str)` | `MainWindow._on_batch_registration_error` | progress state error、QMessageBox、error notification 更新 | adapter 維持 | 後続 issue。UI dialog 表示責務の分離が必要 |
| `batch_registration_canceled(str)` | `MainWindow._on_batch_registration_canceled` | progress state cancel | adapter 維持 | 後続 issue。キャンセル通知と progress state を operation outcome に寄せる |
| `batch_import_started(str)` | 現在の直接購読なし | import progress dialog 開始用に emit されるが MainWindow では未接続 | adapter 維持 / 監査対象 | 後続 issue。未接続が意図通りか確認し、必要なら progress state started handler を追加する |
| `batch_import_finished(object)` | `MainWindow._on_batch_import_finished` | result dialog と status bar 更新 | adapter 維持 | 後続 issue。dry-run/live result 表示を operation result handler に分離する |
| `batch_import_error(str)` | `MainWindow._on_batch_import_error` | QMessageBox と error notification 更新 | adapter 維持 | 後続 issue。error UI 責務の分離が必要 |
| `batch_import_canceled(str)` | `MainWindow._on_batch_import_canceled` | progress state cancel | adapter 維持 | 後続 issue |
| `enhanced_annotation_started(str)` | 現在の直接購読なし | annotation progress dialog 開始用に emit されるが MainWindow では未接続 | adapter 維持 / 監査対象 | 後続 issue。別経路の `_on_batch_annotation_started` と統合要否を確認する |
| `enhanced_annotation_finished(object)` | `MainWindow._on_annotation_finished` | summary dialog、result handler、dataset cache refresh | adapter 維持 | 後続 issue。完了後 cache refresh を operation result handler として設計する |
| `enhanced_annotation_error(str)` | `MainWindow._on_annotation_error` | result handler error、status bar、error notification 更新 | adapter 維持 | 後続 issue |
| `enhanced_annotation_canceled(str)` | `MainWindow._on_annotation_canceled` | progress state cancel | adapter 維持 | 後続 issue |
| `worker_progress_updated(str, object)` | `MainWindow._on_worker_progress_updated`, `WorkerService._on_progress_updated` | per-worker progress を progress manager/state へ流す | 維持 | operation terminal 移行とは別。operation id 追加は後続の progress contract で検討 |
| `worker_batch_progress(str, int, int, str)` | `MainWindow._on_worker_batch_progress`, `FilterSearchPanel._on_worker_batch_progress`, `WorkerService._on_batch_progress_updated` | batch progress と検索パネル progress 更新 | 維持 | #438 で検索パネル側の current worker 判定だけ operation context に寄せる可能性あり |
| `active_worker_count_changed(int)` | WorkerService 経由で外部公開 | active worker count 更新 | 維持 | worker lifecycle の管理 signal。operation event 移行対象外 |
| `all_workers_finished()` | WorkerService 経由で外部公開 | 全 worker 停止通知 | 維持 | worker lifecycle の管理 signal。operation event 移行対象外 |

## 3. 発行元と購読者の所見

`WorkerManager` は `worker_started`, `worker_terminal`, `worker_finished`, `worker_error`,
`worker_canceled`, `active_worker_count_changed`, `all_workers_finished` を持つ。
この層の `worker_finished` / `worker_error` / `worker_canceled` は `WorkerTerminalEvent` から派生する
manager-level compat signal であり、operation/current/superseded 判定を入れない。

`WorkerService` は `WorkerManager.worker_terminal` を受け、worker id prefix から
search / thumbnail / batch / annotation の compat signal に dispatch している。
この prefix dispatch は移行用 adapter と見なし、新規 UI はここへ直接依存しない。

`MainWindow` は現在も search / thumbnail / batch registration / batch import / enhanced annotation の
compat signal を購読している。search / thumbnail は `PipelineControlService` に委譲するだけの箇所が多く、
operation event へ移しやすい。一方で batch / annotation は QMessageBox、status bar、summary dialog、
cache refresh、completion signal に直結しているため、#434 の pipeline 移行と同時に変更しない。

`FilterSearchPanel` は `search_finished` / `search_error` / `search_canceled` と
`worker_batch_progress` を直接購読している。#438 ではここを見落とさず、検索パネル内部状態
`PipelineState` と外部互換 `search_completed` を operation event から更新する。

`DatasetController` と `AnnotationWorkflowController` は worker を開始するだけで、compat signal を直接購読しない。
ただし batch registration / enhanced annotation の後続移行では、開始 API と operation id の返却形を
これらの controller に影響させる可能性がある。

## 4. #434 で残してよい compat signal

#434 完了時点では、以下を意図的に残してよい。

- batch registration: `batch_registration_started` / `finished` / `error` / `canceled`
- batch import: `batch_import_started` / `finished` / `error` / `canceled`
- enhanced annotation: `enhanced_annotation_started` / `finished` / `error` / `canceled`
- progress: `worker_progress_updated` / `worker_batch_progress`
- manager lifecycle: `active_worker_count_changed` / `all_workers_finished`

search / thumbnail の compat signal は #434 中に adapter 扱いへ格下げする。
削除は #434 の最終 PR では行わず、購読者を operation event へ移した後に別 issue で検討する。

## 5. Follow-up Issue Candidates

必要な後続 issue:

1. Batch registration operation event 移行
   - `batch_registration_*` を operation outcome から派生する adapter にする。
   - `ProgressStateService`, `ResultHandlerService`, `database_registration_completed` の責務を分離する。

2. Batch import operation event 移行
   - `batch_import_started` が未接続でよいか確認する。
   - result dialog / status bar / dry-run 表示を operation result handler に分離する。

3. Enhanced annotation operation event 移行
   - `enhanced_annotation_started` が未接続でよいか確認する。
   - summary dialog、result handler、dataset cache refresh を operation result handler に分離する。

4. Progress channel contract 整理
   - `worker_progress_updated` / `worker_batch_progress` に operation id を持たせるか検討する。
   - search panel の progress 判定を worker id 依存から operation context 依存へ移す。

5. Search / thumbnail compat signal 廃止
   - #438 で direct subscribers を operation event へ移した後、`search_*` / `thumbnail_*` の公開範囲を
     private adapter または deprecated API として整理する。
