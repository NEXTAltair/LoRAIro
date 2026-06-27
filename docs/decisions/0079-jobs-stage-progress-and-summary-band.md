---
type: ADR
title: Jobs ステージ別 progress + サマリ帯 — 実データ表示契約と Qt-free 構築ロジック
status: Accepted
timestamp: 2026-06-27
tags: [jobs, annotation, worker, gui, progress]
---
# ADR 0079: Jobs ステージ別 progress + サマリ帯 — 実データ表示契約と Qt-free 構築ロジック

- **関連 Issue**: #805 (Jobs frame に実行中ステージ別 progress + サマリ帯を追加)
- **関連 ADR**: 0066 (Unified Jobs Lifecycle View), 0034 (Worker / Operation / Pipeline Lifecycle Boundary), 0075 (アノテーションパイプライン構成ドメインモデル)

## Context

ADR 0066 で Jobs frame は「実行中 / キュー / 履歴」の lifecycle ビューとして定義されたが、DS JobsScreen が要求する 2 要素が未実装だった:

1. **ステージ別 progress**: 実行中の TAGS / CAPTION / SCORE / RATING ごとの進捗 (pct / done)
2. **サマリ帯 (SummaryStat)**: running / queued / 過去 7 日完了 / API 使用量の 4 stat

`JobEntry` は `job_id / 種別 / 状態 / 開始 / 終了 / サマリー` のみで per-stage 進捗と集計カウントを持たなかった。

## Decision

### 1. 「ステージ別進捗」の実態 — 開始/完了 2 点の状態切り替え

image-annotator-lib の `execute_annotation(image_paths, litellm_model_ids)` は**一括渡しのブロッキング呼び出し**であり、途中の推論状況を返さない。そのため `stage_progress_updated` の emit は 2 回のみ:

1. **実行開始直前**: `processed_count=0` → 全ステージ 0%（実行計画カードとして表示）
2. **`execute_annotation` 返却後**: `processed_count=total` → 各モデルを ok / err で表示

バーが推論中に動く「リアルタイム進捗」ではなく、**実行計画の可視化 + 完了/失敗通知**である。per-model fallback（一括呼び出し失敗時の互換経路）ではモデルごとの ok/err を逐次 emit するが、lib 側が途中経過を返す設計になった場合にのみ真の進捗表示に発展できる。

### 2. StageProgress 構築ロジックは Qt-free サービスに置く

`StageProgress` の構築（選択モデル × capability → TAGS/CAPTION/SCORE/RATING ステージへの展開）は `job_ledger_service.build_stage_progress()` に置く。ステージ展開の判定ロジック（どのモデルがどの capability を持つか）は worker に書かない。

### 2. 実データのみ表示する（捏造禁止）

**API 使用量** は台帳にデータソースがないため、「—」（ダッシュ）で正直に表示し、捏造しない。

```python
# JobLedgerService.summary() — API 使用量は None を返す
SummaryStat(
    running=...,
    queued=...,
    completed_7d=...,
    api_usage=None,  # データソースなし → UI で「—」表示
)
```

データがない stat を「0」や推定値で埋めない。

### 3. WorkerService が台帳反映を担う

`WorkerService._on_annotation_stage_progress` が `stage_progress_updated` シグナルを受け、同期ジョブ台帳へ反映する。`SyncJobLedgerWidget` は台帳の変化を購読して per-stage `QProgressBar` カードで表示する（tone で chunk 色切替）。

### 4. サマリ帯の集計対象

`JobLedgerService.summary()` は in-memory 台帳から以下を集計する:
- `running`: 実行中ジョブ件数
- `queued`: キュー待ちジョブ件数
- `completed_7d`: 過去 7 日以内に完了したジョブ件数
- `api_usage`: `None`（データソースなし）

失敗件数はサマリ帯には含めない（ステージ別 tone (err) で per-job に表示）。

## Consequences

- worker は progress 収集 / emit のみに責務が限定され、StageProgress 構築の変更が worker に波及しない
- API 使用量を「—」で正直表示することでデータ信頼性が維持される
- `SyncJobLedgerWidget` が台帳購読で動くため、worker との直接結合がない
