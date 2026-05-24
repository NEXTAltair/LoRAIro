# GUI ワーカーサービス 仕様書

version: "2.1.0" (Updated: 2026/05/24)

## 1. 目的

本仕様書は、`lorairo` アプリケーションのGUI層 (`src/lorairo/gui`) における `QThread` + `QObject.moveToThread()` ベースの非同期処理システムの設計と実装に関する仕様を定義します。

主な目的は以下の通りです。

- UIスレッドをブロックすることなく、時間のかかるタスク（DB登録、AI処理、検索、サムネイル読み込み）を実行する。
- Qt標準の `QThread` を活用した明示的なワーカーライフサイクル管理を提供する。
- 統一的な進捗報告、エラーハンドリング、キャンセレーション機能を実現する。

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
- **基底クラス:** 全てのワーカーは、`src.lorairo.gui.workers.base.LoRAIroWorkerBase` クラスを継承します。
- **`LoRAIroWorkerBase` の役割:**
    - `QObject` + `Generic[T]` を継承し、型安全な結果を提供します。
    - 標準シグナル (`finished(result: T)`, `error_occurred(message: str)`, `canceled()`) を定義します。
    - 進捗報告とキャンセレーション機能を統合します。
    - 基本的なキャンセル処理 (`cancel()` メソッド、`_is_cancelled` フラグ) の枠組みを提供します。
    - 個別の `QThread` 上で実行されるエントリーポイント (`run()` メソッド) を提供します。`run()` はキャンセルチェック、抽象メソッド `execute()` の呼び出し、例外処理、`finished` / `error_occurred` / `canceled` シグナルの発行を行います。
- **サブクラスの役割:**
    - `LoRAIroWorkerBase` を継承し、具体的な非同期タスクを `execute()` メソッド内に実装します。
    - 必要に応じて `progress` シグナルを発行します。
    - 必要に応じて `cancel()` メソッドをオーバーライドし、タスク固有のキャンセルロジックを追加します（例: 実行中プロセスの停止、ループの中断）。オーバーライドする場合は `super().cancel()` を呼び出す必要があります。
- **サービスとの連携:**
    - `WorkerService` は、対応するワーカークラス（例: `AnnotationWorker`, `SearchWorker`）のインスタンスを生成します。
    - `WorkerService` は `WorkerManager` 経由でワーカーを個別の `QThread` に移動して実行します。
    - `WorkerManager` はワーカーの `finished` / `error_occurred` / `canceled` を `WorkerTerminalEvent` に変換し、`WorkerService` はその event を UI 向け signal へ dispatch します。
    - `WorkerService` はワーカーの `cancel()` メソッドを呼び出して、タスクの中断を要求できます。

## 3. 責務

Worker 系 signal の lifecycle 境界は [ADR 0034](../../decisions/0034-worker-operation-pipeline-lifecycle.md)
に従います。`WorkerManager` は worker の事実イベントだけを扱い、`WorkerService` が
operation/request lifecycle へ変換し、pipeline UI は operation event を authoritative input として
扱います。

- **タスク実行:** 割り当てられた特定の非同期タスク（AI アノテーション、画像読み込み、設定の保存など）を実行します。
- **結果通知:** タスク完了時、`WorkerManager.worker_terminal` が `WorkerTerminalEvent` を一度だけ通知します。既存の `worker_finished` / `worker_error` / `worker_canceled` は互換用 signal です。
- **進捗通知:** (任意) タスク実行中に、`progress` シグナルを通じて進捗状況（通常 0-100 のパーセンテージ）を通知します。
- **キャンセル処理:** サービスからのキャンセル要求を受け付け、可能な範囲でタスクを安全に中断します。通常キャンセルは failure ではなく、ErrorLogViewer 用のエラーレコードには記録しません。キャンセル要求は `CancelReason` を持ち、UI は user requested / pipeline cancel / worker replacement / prefetch cleanup / progress dialog / shutdown を区別できます。
- **強制終了:** cancel wait timeout 後に `thread.terminate()` を使った場合、通常キャンセルとは扱いません。停止確認できた場合は `TERMINATED`、停止確認できない場合は `UNRESPONSIVE` として terminal event に記録します。

### 3.1 Terminal Contract

- `WorkerTerminalEvent` は `worker_id`, `worker_type`, `outcome`, `result`, `error`, `cancel_reason` を持ちます。
- `WorkerOutcome` は `SUCCEEDED`, `FAILED`, `CANCELED`, `CANCEL_TIMEOUT`, `TERMINATED`, `UNRESPONSIVE` を定義します。
- `CancelReason` は `USER_REQUESTED`, `PIPELINE_CANCEL`, `SEARCH_REPLACED`, `THUMBNAIL_REPLACED`, `PREFETCH_REPLACED`, `PROGRESS_DIALOG`, `SHUTDOWN`, `TIMEOUT_FALLBACK` を定義します。
- `WorkerManager` は worker ごとに terminal event を一度だけ確定します。cancel 要求後に queued `finished` / `error_occurred` が届いている場合は、その terminal を cancel fallback より優先します。
- thumbnail replacement / prefetch cancellation は検索結果を破棄しません。明示的な pipeline cancel は検索結果とサムネイル表示を破棄します。

### 3.2 Operation Event Migration Contract

- `WorkerTerminalEvent` は UI cleanup の所有者ではありません。worker の事実を `WorkerService` へ渡すための event です。
- `WorkerService` は `operation_id` / `request_id` / `generation` により current operation と superseded operation を区別します。
- `search_error(str)` / `thumbnail_error(str)` などの worker 種別別 signal は移行用 adapter です。新規 UI は operation event を購読します。
- compat signal から UI cleanup を直接増やしてはいけません。search/thumbnail pipeline cleanup は operation event 経路へ集約します。
- progress dialog close は terminal handling 側で一度だけ実行します。compat signal の購読者は progress close の所有者ではありません。

## 4. 実装ガイドライン

- **`execute()` の実装:**
    - 具体的な処理ロジックを実装します。
    - 正常完了時は結果オブジェクトを返します。
    - 処理中にエラーが発生した場合は、例外を送出します (`LoRAIroWorkerBase.run` で捕捉されます)。特定のビジネスロジックエラーは、`execute()` 内で捕捉し、エラーを示す特定のオブジェクトを返すことも可能です。
- **エラーハンドリング:**
    - `BaseWorker.run()` が一般的な `Exception` を捕捉し、`error_occurred` シグナルで通知します。
    - キャンセルは `CancellationError` またはキャンセルフラグで検出し、`WorkerStatus.CANCELED` と `canceled` シグナルで通知します。
    - `execute()` 内で、特定の予期される例外（例: `FileNotFoundError`, `ValueError`）を捕捉し、より具体的なエラー情報を含む結果を返すことも検討します。
- **状態管理:** ワーカーは自身の状態（実行中、キャンセル済みなど）を管理しますが、サービスやUIに直接依存しないようにします。状態の通知はシグナルを使用します。
- **リソース管理:** ワーカーがファイルハンドルやネットワーク接続などのリソースを使用する場合、`execute()` 内または `finally` ブロックで適切に解放するようにします。
- **UI非依存:** ワーカークラスはUIコンポーネントに直接アクセスしません。UIとのやり取りは、サービス層を経由してシグナル/スロットで行います。

## 5. 命名規則

- ワーカークラス名は、対応するサービス名に基づいて `[ServiceName]Worker` とします (例: `AnnotationWorker`, `ImageLoadingWorker`)。

## 6. 改訂履歴

- 2.1.0 (2026-05-24): `QThread` 実装に合わせて更新し、`WorkerTerminalEvent` / `WorkerOutcome` / `CancelReason` による終端 contract を追加
- 1.0.0 (2025-04-18): 初版作成
