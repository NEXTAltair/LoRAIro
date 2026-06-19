---
type: ADR
title: Worker / Operation / Pipeline Lifecycle Boundary
status: Accepted
timestamp: 2026-05-24
tags: []
---
# ADR 0034: Worker / Operation / Pipeline Lifecycle Boundary

- **関連 Issue**: #434, #435

## Context

#430 / #433 で worker の cancel reason と abnormal terminal outcome を明示したが、GUI 層には
古い worker 種別別 signal (`search_error(str)`, `thumbnail_canceled(str)` など) が残っている。
これらは単一 worker の完了通知としては十分だったが、現在の search -> thumbnail pipeline では以下を
区別できない。

- 現在の user operation の失敗
- replacement された古い worker の失敗
- 明示キャンセル後の timeout / terminate
- prefetch cleanup など通常運用の cancel
- pipeline UI state の cleanup 対象かどうか

その結果、worker lifecycle、operation/request lifecycle、pipeline UI lifecycle が同じ signal 経路に
混在し、stale worker の terminal が現在の UI state を壊す、または cleanup が二重 dispatch される。

## Decision

### 1. Lifecycle を 3 層に分離する

| 層 | 所有者 | 表すもの | 購読者 |
|---|---|---|---|
| Worker lifecycle | `WorkerManager` | QThread / worker の事実 (`SUCCEEDED`, `FAILED`, `CANCELED`, `TERMINATED`, `UNRESPONSIVE`) | `WorkerService` |
| Operation lifecycle | `WorkerService` | user operation / request 単位の current / superseded / completed / failed / canceled | pipeline service, UI adapter |
| Pipeline lifecycle | `PipelineControlService` | search -> thumbnail -> display の画面状態と cleanup | widgets / MainWindow delegates |

`WorkerManager` は operation の current / stale 判定を行わない。`WorkerService` は worker fact を
operation event に変換し、`PipelineControlService` は operation event だけを authoritative input として
UI cleanup を行う。

### 2. Worker terminal event は事実イベントに限定する

`WorkerTerminalEvent` は worker ごとに一度だけ確定する事実イベントであり、UI cleanup の所有者ではない。

- `worker_id` と `worker_type` は worker の識別子であり、operation の新旧判定には使わない。
- `cancel_reason` は cancellation request の理由であり、operation current 判定の代替にしない。
- `UNRESPONSIVE` は「停止未確認」の事実なので、manager の active tracking を clean と見なさない。

### 3. Operation event を UI の authoritative input にする

`WorkerService` は `operation_id` / `request_id` / `generation` のいずれかで current operation を管理する。

- search は generation または operation_id で current / superseded を判定する。
- thumbnail は既存の `request_id` を operation context に取り込み、display / prefetch を区別する。
- superseded worker の `FAILED` / `TERMINATED` / `UNRESPONSIVE` は現在の operation state を変更しない。
- non-replacement failure は一度だけ operation failure として dispatch する。

### 4. compat signal は移行用 adapter とする

既存の `search_finished`, `search_error`, `search_canceled`, `thumbnail_*`, `batch_*`,
`enhanced_annotation_*` は当面残す。ただし新規 UI / service code は operation event を購読する。

compat signal の扱い:

- search / thumbnail は #434 で operation event 主導へ移行する。
- batch registration / batch import / enhanced annotation は #434 では棚卸し対象とし、即時移行しない。
- compat signal は operation event から派生する adapter であり、authoritative cleanup path ではない。

### 5. Progress close は terminal handling の責務にする

progress dialog は operation event や compat error signal の購読者ではなく、terminal handling 側で閉じる。

- success / failed / canceled / abnormal / superseded の代表経路で一度だけ close する。
- progress dialog を開始しない worker (thumbnail / prefetch など) は明示的に対象外にする。
- compat signal 側で progress close を再実行しない。

## Rationale

Qt signal を worker 種別別に分ける設計は単純な一回実行 worker では扱いやすい。しかし replacement や
prefetch を含む pipeline では、`search_error(str)` のような payload では stale 判定に必要な情報を
表現できない。

worker fact と user operation を分けることで、`WorkerManager` は QThread 管理に集中し、
`WorkerService` が request 単位の意味づけを担当できる。UI は operation event だけを見ればよく、
compat signal と terminal event の両方で cleanup する二重経路を避けられる。

## Consequences

- `WorkerService` に operation context と operation event 型を追加する必要がある。
- search / thumbnail UI は compat signal 直接購読から operation event 購読へ移行する。
- batch / annotation 系 signal は即時削除せず、残存範囲を docs / issue で管理する。
- テストは signal 名ではなく lifecycle 境界を守る観点で追加する。

## Prohibited Dependencies

- `WorkerManager` から `PipelineControlService` / widgets / current operation state を参照しない。
- `PipelineControlService` は raw worker terminal を authoritative cleanup input として扱わない。
- 新規 UI code は `search_error(str)` / `thumbnail_error(str)` に直接依存しない。
- `worker_id` prefix だけで current / stale 判定をしない。