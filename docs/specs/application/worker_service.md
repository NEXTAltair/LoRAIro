# GUI ワーカーサービス 仕様書

version: "2.1.0" (Updated: 2026/05/24)

## 1. 目的

本仕様書は、`lorairo` アプリケーションの GUI 層(`src/lorairo/gui`)における `QThread` と `QObject.moveToThread()` を基盤とした非同期処理システムの設計と実装仕様を定義する。

主な目的は以下のとおりである。

- UI スレッドをブロックせずに、時間のかかるタスク(DB 登録、AI 処理、検索、サムネイル読み込み)を実行する。
- Qt 標準の `QThread` を活用し、ワーカーのライフサイクルを明示的に管理する。
- 進捗報告、エラーハンドリング、キャンセル処理を統一的な仕組みで実現する。

## 2. アーキテクチャ設計

### 2.1 配置構造

```
src/lorairo/gui/
├── services/
│   └── worker_service.py      # GUI向け高レベルAPI
└── workers/
    ├── base.py               # 基底クラスとQt統合
    ├── manager.py            # QThread管理
    ├── terminal.py           # 終端 outcome / cancel reason / terminal event
    ├── registration_worker.py # DB登録ワーカー
    ├── search_worker.py       # DB検索ワーカー
    ├── thumbnail_worker.py    # サムネイル読み込みワーカー
    ├── annotation_worker.py  # AI処理ワーカー
    └── ...
```

### 2.2 基底クラス設計

- **基底クラス**: すべてのワーカーは `src.lorairo.gui.workers.base.LoRAIroWorkerBase` を継承する。
- **`LoRAIroWorkerBase` の役割**:
  - `QObject` と `Generic[T]` を継承し、型安全な結果返却を提供する。
  - 標準シグナル(`finished(result: T)`、`error_occurred(message: str)`、`canceled()`)を定義する。
  - 進捗報告とキャンセル機能を統合する。
  - 基本的なキャンセル処理の枠組み(`cancel()` メソッド、`_is_cancelled` フラグ)を提供する。
  - 個別の `QThread` 上で実行されるエントリーポイント(`run()` メソッド)を提供する。`run()` はキャンセル確認、抽象メソッド `execute()` の呼び出し、例外処理、および `finished`・`error_occurred`・`canceled` シグナルの発行を担う。
- **サブクラスの役割**:
  - `LoRAIroWorkerBase` を継承し、具体的な非同期タスクを `execute()` メソッド内に実装する。
  - 必要に応じて `progress` シグナルを発行する。
  - タスク固有のキャンセル処理(実行中プロセスの停止やループ中断など)が必要な場合は `cancel()` をオーバーライドする。その際、必ず `super().cancel()` を呼び出す。
- **サービスとの連携**:
  - `WorkerService` は、対応するワーカークラス(例:`AnnotationWorker`、`SearchWorker`)のインスタンスを生成する。
  - `WorkerService` は `WorkerManager` 経由でワーカーを個別の `QThread` へ移動して実行する。
  - `WorkerManager` はワーカーの `finished`・`error_occurred`・`canceled` を `WorkerTerminalEvent` へ変換し、`WorkerService` がそのイベントを UI 向けシグナルへ振り分ける。
  - `WorkerService` はワーカーの `cancel()` メソッドを呼び出し、タスクの中断を要求できる。

## 3. 責務

ワーカー系シグナルのライフサイクル境界は [ADR 0034](../../decisions/0034-worker-operation-pipeline-lifecycle.md) に従う。`WorkerManager` はワーカーの事実イベントのみを扱い、`WorkerService` が操作・リクエスト単位のライフサイクルへ変換する。パイプライン UI は操作イベントを正規の入力として扱う。

- **タスク実行**: 割り当てられた非同期タスク(AI アノテーション、画像読み込み、設定保存など)を実行する。
- **結果通知**: タスク完了時、`WorkerManager.worker_terminal` が `WorkerTerminalEvent` を一度だけ通知する。既存の `worker_finished`、`worker_error`、`worker_canceled` は互換用シグナルとして位置づける。
- **進捗通知(任意)**: タスク実行中に、`progress` シグナルで進捗状況(通常は 0〜100 のパーセンテージ)を通知する。
- **キャンセル処理**: サービスからのキャンセル要求を受け付け、可能な範囲でタスクを安全に中断する。通常のキャンセルは失敗ではなく、ErrorLogViewer 用のエラーレコードには記録しない。キャンセル要求は `CancelReason` を持ち、UI はユーザー要求・パイプラインキャンセル・ワーカー置換・プリフェッチ後始末・進捗ダイアログ・シャットダウンを区別できる。
- **強制終了**: キャンセル待機のタイムアウト後に `thread.terminate()` を使用した場合は、通常のキャンセルとして扱わない。停止を確認できた場合は `TERMINATED`、確認できない場合は `UNRESPONSIVE` として終端イベントに記録する。

### 3.1 終端契約(Terminal Contract)

- `WorkerTerminalEvent` は `worker_id`、`worker_type`、`outcome`、`result`、`error`、`cancel_reason` を保持する。
- `WorkerOutcome` は `SUCCEEDED`、`FAILED`、`CANCELED`、`CANCEL_TIMEOUT`、`TERMINATED`、`UNRESPONSIVE` を定義する。
- `CancelReason` は `USER_REQUESTED`、`PIPELINE_CANCEL`、`SEARCH_REPLACED`、`THUMBNAIL_REPLACED`、`PREFETCH_REPLACED`、`PROGRESS_DIALOG`、`SHUTDOWN`、`TIMEOUT_FALLBACK` を定義する。
- `WorkerManager` はワーカーごとに終端イベントを一度だけ確定する。キャンセル要求後にキュー済みの `finished` や `error_occurred` が届いた場合は、キャンセルフォールバックよりそちらの終端を優先する。
- サムネイル置換やプリフェッチのキャンセルでは検索結果を破棄しない。一方、明示的なパイプラインキャンセルでは検索結果とサムネイル表示を破棄する。

### 3.2 操作イベント移行契約(Operation Event Migration Contract)

- `WorkerTerminalEvent` は UI 後始末の所有者ではない。ワーカーの事実を `WorkerService` へ渡すためのイベントである。
- `WorkerService` は `operation_id`、`request_id`、`generation` を用いて、現在の操作と後続に置き換えられた操作(superseded)を区別する。
- `search_error(str)` や `thumbnail_error(str)` などのワーカー種別別シグナルは移行用アダプタである。新規 UI は操作イベントを購読する。
- 互換シグナル側で UI 後始末の処理を直接増やしてはならない。検索・サムネイルパイプラインの後始末は操作イベント経路へ集約する。
- 進捗ダイアログを閉じる処理は終端ハンドリング側で一度だけ実行する。互換シグナルの購読者は進捗ダイアログを閉じる責務を持たない。

### 3.3 互換シグナル監査

`WorkerService` が公開する `search_error(str)` や `thumbnail_error(str)` などの既存シグナルは、`WorkerTerminalEvent` から派生する移行用アダプタである。#434 の操作ライフサイクル移行では、検索・サムネイルパイプラインを操作イベント主導へ移し、バッチ登録・バッチ取込み・拡張アノテーションは後続 Issue までアダプタを維持する。

詳細な購読者・役割・移行判断は [`worker_signal_compat_audit.md`](worker_signal_compat_audit.md) を参照する。

## 4. 実装ガイドライン

- **`execute()` の実装**:
  - 具体的な処理ロジックを記述し、正常完了時は結果オブジェクトを返す。
  - 処理中にエラーが発生した場合は例外を送出する(`LoRAIroWorkerBase.run` で捕捉される)。特定のビジネスロジックエラーについては、`execute()` 内で捕捉してエラーを示すオブジェクトを返す設計も許容する。
- **エラーハンドリング**:
  - `BaseWorker.run()` が一般的な `Exception` を捕捉し、`error_occurred` シグナルで通知する。
  - キャンセルは `CancellationError` またはキャンセルフラグで検出し、`WorkerStatus.CANCELED` と `canceled` シグナルで通知する。
  - `FileNotFoundError` や `ValueError` など予期される例外は、`execute()` 内で捕捉して具体的なエラー情報を含む結果を返すことも検討する。
- **状態管理**: ワーカーは自身の状態(実行中、キャンセル済みなど)を管理するが、サービスや UI には直接依存しない。状態の通知にはシグナルを使う。
- **リソース管理**: ファイルハンドルやネットワーク接続などのリソースを使用する場合は、`execute()` 内または `finally` ブロックで確実に解放する。
- **UI 非依存**: ワーカークラスは UI コンポーネントへ直接アクセスしない。UI とのやり取りは、サービス層を経由してシグナルとスロットで行う。

## 5. 命名規則

- ワーカークラス名は、対応するサービス名に基づいて `[ServiceName]Worker` とする(例:`AnnotationWorker`、`ImageLoadingWorker`)。

## 6. 改訂履歴

- 2.1.0(2026-05-24): `QThread` 実装に合わせて更新し、`WorkerTerminalEvent`、`WorkerOutcome`、`CancelReason` による終端契約を追加
- 1.0.0(2025-04-18): 初版作成
