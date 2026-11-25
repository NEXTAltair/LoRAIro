---
type: ADR
title: Jobs ステージ別 progress + サマリ帯 — 実データ表示契約と Qt-free 構築ロジック
status: Accepted
timestamp: 2026-06-27
tags: [jobs, annotation, worker, gui, progress]
---
# ADR 0079: Jobs ステージ別 progress + サマリ帯 — 実データ表示契約と Qt-free 構築ロジック

- **関連 Issue**: #805(Jobs フレームに実行中ステージ別進捗とサマリ帯を追加)
- **関連 ADR**: 0066(Unified Jobs Lifecycle View)、0034(Worker / Operation / Pipeline Lifecycle Boundary)、0075(アノテーションパイプライン構成ドメインモデル)

## Context

ADR 0066 では、Jobs フレームを「実行中・キュー・履歴」のライフサイクルビューとして定義した。しかし、DS の JobsScreen が要求する次の 2 要素が未実装だった。

1. **ステージ別進捗**: 実行中の TAGS、CAPTION、SCORE、RATING 各ステージにおける進捗(割合・完了状態)。
2. **サマリ帯(`SummaryStat`)**: 実行中、キュー待ち、過去 7 日間の完了件数、API 使用量の 4 指標。

既存の `JobEntry` は `job_id`、種別、状態、開始時刻、終了時刻、サマリーしか持たず、ステージごとの進捗や集計カウントを保持していなかった。

## Decision

### 1. ステージ別進捗の実態: 開始と完了の 2 点切り替え

`image-annotator-lib` の `execute_annotation(image_paths, litellm_model_ids)` は一括渡しのブロッキング呼び出しであり、推論途中の進捗を返さない。そのため、`stage_progress_updated` シグナルの送出は次の 2 回のみとする。

1. **実行開始直前**: `processed_count=0` を送り、全ステージを 0% とする(実行計画カードとして表示する)。
2. **`execute_annotation` の返却後**: `processed_count=total` を送り、各モデルの結果を成功(`ok`)または失敗(`err`)として表示する。

したがって、この表示は推論中にバーが動くリアルタイム進捗ではなく、**実行計画の可視化と完了・失敗通知**である。一括呼び出し失敗時の互換経路(モデル単位のフォールバック)ではモデルごとの `ok`・`err` を逐次送出するが、真のリアルタイム進捗への発展はライブラリ側が途中経過を返す設計になった場合に限る。

### 2. StageProgress 構築ロジックは Qt 非依存サービスに配置する

`StageProgress` の構築(選択モデルと対応機能から TAGS、CAPTION、SCORE、RATING ステージへ展開する処理)は `job_ledger_service.build_stage_progress()` に配置する。どのモデルがどの機能を持つかといったステージ展開の判定ロジックは、ワーカー側には記述しない。

### 3. 実データのみを表示する(値の捏造を禁止)

**API 使用量**は台帳側にデータソースが存在しないため、UI 上ではダッシュ記号「—」で正直に表示する。データが存在しない指標を「0」や推定値で埋めてはならない。

```python
# JobLedgerService.summary() — API 使用量は None を返す
SummaryStat(
    running=...,
    queued=...,
    completed_7d=...,
    api_usage=None,  # データソースなし → UI で「—」表示
)
```

### 4. WorkerService が台帳への反映を担う

`WorkerService._on_annotation_stage_progress` が `stage_progress_updated` シグナルを受信し、同期ジョブ台帳へ反映する。`SyncJobLedgerWidget` は台帳の変化を購読し、ステージごとの `QProgressBar` カードとして描画する(状態トーンに応じてバーの色を切り替える)。

### 5. サマリ帯の集計対象

`JobLedgerService.summary()` はメモリ上の台帳から次の 4 項目を集計する。

- `running`: 実行中のジョブ件数
- `queued`: キュー待ちのジョブ件数
- `completed_7d`: 過去 7 日以内に完了したジョブ件数
- `api_usage`: `None`(データソースなし)

失敗件数はサマリ帯には含めず、ジョブごとのステージ別表示(エラー状態トーン)で示す。

## Consequences

- ワーカーの責務が進捗の収集と送出のみに限定され、`StageProgress` 構築ロジックの変更がワーカーへ波及しない。
- API 使用量を「—」として正直に表示することで、画面表示の信頼性を維持できる。
- `SyncJobLedgerWidget` が台帳の購読を通じて動作するため、ワーカーとの直接結合を避けられる。
