---
type: ADR
title: Provider Batch Submit Threading
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0044: Provider Batch Submit Threading

- **関連 Issue**: #576

## Context

Provider Batch タブの `ProviderBatchJobWidget.submit_job()` は、ユーザー操作のスロット内で `ProviderBatchWorkflowService.submit_images()` を同期実行していた。

`submit_images()` は、画像メタデータの取得、保存パスの解決、プロバイダリクエストの構築、プロバイダ API への送信、`provider_batch_jobs` および `provider_batch_items` の DB 登録までを一貫して行う。ステージング画像が多い場合や、API・DB・ファイルシステム I/O が遅い場合、Qt の GUI スレッドが占有され、アプリケーションウィンドウ全体が一時的に応答しなくなっていた。

Issue #571 では二重送信を防ぐために送信中の再入ガードとビジー表示を導入した。しかし、その実装は `QApplication.processEvents()` で再入可能性を局所的に扱う構造にとどまっており、GUI スレッドを占有する根本原因は残っていた。

## Decision

Provider Batch の送信本体は、`QThread` 上で動作する専用ワーカーで実行する。

GUI スレッドが担当する処理は、以下の 4 点に限定する。

- 選択モデル、`task_type`、`prompt_profile`、`description`、`image_ids` のスナップショット作成
- 送信ボタンのビジー表示と二重送信ガード
- ワーカー完了後のステージング除外、ジョブ一覧の更新、メッセージ表示
- エラー発生時のダイアログ表示とステージング状態の維持

ワーカーは `workflow_service.submit_images(...)` のみを実行する。成功時は `job_id` を、失敗時は例外オブジェクトをシグナルで GUI スレッドへ返す。ワーカー側から GUI ウィジェットや Qt の UI オブジェクトには一切触れない。

また、送信スレッドはウィジェットの子オブジェクトにしない。完了までモジュールレベルのアクティブ集合(active set)で参照を保持し、送信中にウィジェットが破棄されても `QThread: Destroyed while thread is still running` が発生しないようにする。

これに伴い、送信時のビジー表示から `QApplication.processEvents()` による手動イベント処理を削除する。

## Rationale

Provider Batch の送信は、ボタンを押した瞬間に完了する軽量処理ではなく、DB、ファイルシステム、ネットワーク I/O を伴うユーザー操作である。Qt の GUI スレッドは UI 状態のスナップショット取得と表示更新だけに専念させ、I/O を伴う処理はワーカースレッドへ分離する方が、既存の Worker / Operation ライフサイクル方針(ADR 0034)と整合する。

既存の `WorkerService` へ統合する案も考えられる。しかし今回の送信処理は Provider Batch タブ内の単発オーケストレーションであり、プログレスダイアログやキャンセル契約をまだ持たない。既存のワーカーライフサイクル全体へ変更を広げると、#576 のフリーズ修正としては過大な設計変更になるため、ウィジェットローカルの小さな `QThread` ワーカーにとどめる。

## Consequences

- `submit_job()` は同期完了しなくなるため、テストでは `submit_completed` シグナルの完了を待機する必要がある。
- 送信中も Qt のイベントループが返るため、ウィンドウ全体の応答停止を防げる。
- 送信中にウィジェットが破棄された場合でも送信処理は完了まで継続し、ウィジェット向けの Qt シグナルは受信側の破棄により配送されない。プロバイダジョブが作成された場合は、次回の表示更新やジョブ一覧から確認する。
- 成功後のステージング除外は送信前の `image_ids` スナップショットに対して行うため、送信中に新しく追加された画像はそのまま残る。
- 失敗時は従来どおりステージングを保持するため、ユーザーはそのまま再試行できる。
- 将来、Provider Batch の送信に進捗表示やキャンセル機能が必要になった場合は、`WorkerService` の操作イベントへ昇格できる余地を残している。
