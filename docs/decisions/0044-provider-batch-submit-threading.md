# ADR 0044: Provider Batch Submit Threading

- **日付**: 2026-05-31
- **ステータス**: Accepted
- **関連 Issue**: #576

## Context

Provider Batch タブの `ProviderBatchJobWidget.submit_job()` は、ユーザー操作の slot 内で
`ProviderBatchWorkflowService.submit_images()` を同期実行していた。

`submit_images()` は画像メタデータ取得、保存パス解決、provider request 構築、provider API submit、
provider_batch_jobs / provider_batch_items の DB 作成までを含む。ステージング画像が多い場合や
API / DB / filesystem I/O が遅い場合、Qt の GUI スレッドが占有され、アプリケーションウィンドウ全体が
一時的に応答しなくなる。

Issue #571 で二重送信を防ぐため submit 中の再入ガードと busy 表示が入ったが、`QApplication.processEvents()`
により再入可能性を局所的に扱う構造であり、GUI スレッドを占有する根本原因は残っていた。

## Decision

Provider Batch の submit 本体は `QThread` 上の専用 worker で実行する。

GUI スレッドで行う処理は以下に限定する。

- 選択モデル、task_type、prompt_profile、description、image_ids の snapshot 作成
- submit ボタンの busy 表示と二重送信ガード
- worker 完了後のステージング除外、job 一覧更新、メッセージ表示
- エラー時のダイアログ表示とステージング維持

worker は `workflow_service.submit_images(...)` だけを実行し、成功時は `job_id`、失敗時は例外オブジェクトを
signal で GUI スレッドへ返す。GUI widget / Qt UI オブジェクトは worker から触らない。

submit thread は widget の child にしない。完了まで module-level の active set で保持し、widget が submit 中に
破棄されても `QThread: Destroyed while thread is still running` を起こさないようにする。

`QApplication.processEvents()` による手動イベント処理は submit busy 表示から削除する。

## Rationale

Provider Batch submit は「送信ボタンを押した瞬間に完了する軽量処理」ではなく、DB / filesystem / network I/O を
含む user operation である。Qt の GUI スレッドでは UI state の snapshot と表示更新だけを担当し、I/O を伴う
処理は worker thread に分離する方が、既存の Worker / Operation lifecycle 方針 (ADR 0034) と整合する。

既存の `WorkerService` に統合する案もあるが、今回の submit は Provider Batch タブ内の単発 orchestration で、
progress dialog や cancellation contract をまだ持たない。既存 worker lifecycle 全体へ広げると #576 の
フリーズ修正より大きい設計変更になるため、widget-local の小さな `QThread` worker に留める。

## Consequences

- `submit_job()` は同期完了しなくなる。テストは `submit_completed` signal を待つ。
- submit 中も Qt イベントループは戻るため、ウィンドウ全体の応答停止を避けられる。
- submit 中に widget が破棄された場合、送信処理は完了まで走り、widget 向けの Qt signal は receiver
  破棄により配送されない。provider job が作成された場合は次回表示更新や job 一覧から確認する。
- 成功後のステージング除外は送信前 image_ids snapshot に対して行うため、送信中に追加された画像は残る。
- 失敗時は従来どおりステージングを保持し、ユーザーが再試行できる。
- 将来、Provider Batch submit に進捗表示やキャンセルが必要になった場合は、`WorkerService` の operation
  event へ昇格する余地を残す。
