---
type: ADR
title: Unified Jobs Lifecycle View
status: Accepted (2026-06-12)
timestamp: 2026-06-12
tags: []
---
# ADR 0066: Unified Jobs Lifecycle View

- **関連**: ADR 0034 (Worker / Operation / Pipeline Lifecycle Boundary), ADR 0038 (Provider Batch API Integration), ADR 0041 (Provider Batch 実行 UI 統一), ADR 0044 (Provider Batch Submit Threading)

## Context

実行状況の表示が分断されている: 同期実行 (AnnotationWorker 等) は進捗ポップアップ（廃止予定の暫定実装）、Provider Batch はジョブタブ (`ProviderBatchJobWidget`)。Wireframes v11 Frame 3 と Epic #731 で「B 案: 独立 Jobs タブ」が確定済みであり、本 ADR は統一 Jobs lifecycle ビューの設計を形式化する。

## Decision

### 1. Jobs タブを統一 lifecycle ビューにする

「実行中 / キュー / 履歴」の 3 状態で同期ジョブと Provider Batch を 1 つのビューに統合する。空状態でも履歴テーブルの枠は消さない（Jobs の半分は台帳 — Frame 3）。

### 2. 同期ジョブの履歴はセッションスコープ (in-memory) — DB 永続化しない

同期ジョブの履歴に新規テーブルは作らない。永続化は重いだけで利点がなく、元来「個別実行をログに残さない」運用である（2026-06-12 ユーザー判断）。診断には loguru ログが既に存在する。

- 同期ジョブ: in-memory 台帳（アプリ再起動で消える）
- Provider Batch: 既存 `provider_batch_jobs` テーブルのまま。**非同期で再起動を跨ぐ必然がある**ため永続が正当化される非対称を意図的に許容する

### 3. ジョブ粒度 = Pipeline / Operation レベル (ADR 0034)

Jobs に載せるのは: アノテーションパイプライン実行・Provider Batch（rating preflight 含む。preflight は親 Operation の子として表示）・DB 登録バッチ・model install（枠のみ、§5）。
**載せない**: 検索 / サムネイル等の UI 応答系 Worker（ジョブではなく操作の一部。載せると firehose 化する）。

### 4. 進捗ポップアップは Phase 7 で廃止

- 並存期間は置かない（暫定実装の役目を終える）
- 実行開始時に Jobs タブへの自動遷移は**しない**（statusbar 通知のみ。完了時は既存の Results 自動着地 — Frame 5）
- キャンセル操作は Jobs 行のアクションへ移設する

### 5. Model installer は job_type の枠のみ定義

「暗黙 HuggingFace DL の明示 install ジョブ化」(Epic 確定済み判断) は iam-lib 側のバックエンド新規を伴うため、本 ADR では Jobs ビューに installer 用 job_type を予約するに留め、DL の job 化実装は別 Phase に分離する。

### 6. キューは実セマンティクスを持つ

表示上の状態だけでなく実行制御を導入する:

- **ローカル GPU 推論ジョブ: 同時 1 件**（直列キュー。VRAM 競合を構造的に防ぐ）
- API 系ジョブ: 並列許容（プロバイダ rate limit は lib 側 retry で吸収、ADR 0023 Phase 1.8）

## Consequences

### 良い点

- 実行状況の確認場所が 1 箇所になり、ポップアップの暫定実装を返却できる
- スキーマ変更ゼロ（同期履歴 in-memory + 既存 provider_batch_jobs）で導入が軽い
- GPU 直列化で VRAM 競合由来の失敗が構造的に消える

### トレードオフ

- 同期ジョブ履歴は再起動で消える（意図的。台帳の永続性が必要なのは Provider Batch のみ）
- 「直近の実行サマリ」表示はセッション内に限定される

## 実装メモ (Phase 7)

- 既存 `ProviderBatchJobWidget` を拡張するか統一ビューへ置換するかは実装時に判断
- in-memory 台帳は Qt-free サービス（`JobLedgerService` 等）として実装し、WorkerService のライフサイクルイベント (ADR 0034) を購読する