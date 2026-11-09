---
type: ADR
title: 読み取り専用の DB メンテナンス点検コマンド
status: Accepted
timestamp: 2026-11-08
tags: [cli, maintenance, provider-batch, read-only, filesystem]
---

# ADR 0099: 読み取り専用の DB メンテナンス点検コマンド

## Context

ADR 0093 で Provider Batch の失敗画像は既存の `batch status/fetch/import` 出力で特定する方針とし、
DB と他の状態 (プロバイダ・実ファイル) を突き合わせて不整合を見つける汎用的な仕組みは別に検討することにした。
不整合が起こり得る領域は多い (画像 ↔ 実ファイル、Provider Batch の job/item、crop、データセット、SQLite 自体)。
修復まで含めると削除・NULL 化・再リンクなど種類ごとに価値判断が必要で、事故の影響も大きい。

検討した案:

- A: 読み取り専用の点検コマンドだけを新設し、修復は既存コマンドに任せる。
- B: A に加え、dry-run を既定とする修復コマンドを持つ。
- C: 汎用コマンドを作らず、各ドメインのグループ (`batch` / `images` / `project`) に個別に足す。
- D: SQLite レベル (`integrity_check` 等) の点検だけにする。

## Decision

- 案 A を採用し、`lorairo-cli maintenance check` を新設する。常に読み取り専用で、修復はしない。
  出力した ID は既存コマンド (`batch status` / `batch submit --image-ids` / `images process` 等) に渡して対処する。
- 既定 (`--scope` 省略時) の点検はローカル完結の 2 範囲 (`batch` / `files`) とし、外部プロバイダ API は呼ばない (`provider_queried=false`)。
  - `batch`: job status が共通語彙 (ADR 0038) の外、`imported` と `imported_at` の不一致、
    DB 上は進行中なのに記録済みの `expires_at` を過ぎた job、画像参照を失った未取込み item を持つ job。
  - `files`: 原本 (`images.stored_image_path`) の実ファイル欠損、処理済み画像の実ファイル欠損 (画像 ID 単位)。
- `--scope provider` を明示指定したときのみ、Provider Batch API を read-only で照会して DB と突合する (#1476, `provider_queried=true`, `repaired=false`):
  - `provider_status_mismatch`: DB が進行中なのに provider 側が終端 (`completed` / `failed` / `canceled` / `expired`)、または DB が終端状態なのに provider 側 status と不一致 (`imported` は provider 側 `completed` と対応)。
  - `provider_job_missing`: DB の `provider_job_id` が provider 側に存在しない (404 / not found)。
  - `provider_counts_mismatch`: DB と provider 側の双方に件数があるとき `succeeded_count` または `failed_count` が不一致。
  - 外部 API 大量呼び出しを防ぐため、`--scope provider` では DB 内の対象 job 件数が 500 件 (`MAX_PROVIDER_CHECK_JOBS`) を超える場合、API 呼び出し前に `RESULT_SET_TOO_LARGE` (`exit 2`) で拒否する。
  - API キー未設定や認証失敗は `AUTH_ERROR` (`exit 1`)、全件の通信失敗・レート制限は `NETWORK_ERROR` / `RATE_LIMITED` (`exit 1`)、複数 job の一部のみが通信失敗・レート制限となった場合は `ok=false`・`status=partial_success` (`exit 3`) を返す。
- 出力は count-first (ADR 0056/0060): 件数は常にプロジェクト全体、ID は点検ごとに昇順で `--limit` (1〜500、既定 100) 件まで。
  ローカル scope (`batch` / `files`) の走査は件数で打ち切らず全件を見るため、`RESULT_SET_TOO_LARGE` は返さない。
- 点検で不整合が見つかってもコマンドとしては成功 (exit 0、`status=success`)。判定は結果の `issues_found` / `issue_count` で行う。
  `tags health` と同じく、見つかった不整合は失敗ではなくデータとして扱う。
- DB は既存の互換 DB を読み取り専用で開く (ADR 0059)。初期化・マイグレーションは行わず、既定 scope では外部通信も行わない。
  DB 読み取りは Repository 経由で、chunk ごとの短いセッションで走査する。

## Implementation

- CLI: `src/lorairo/cli/commands/maintenance.py`、introspection の `maintenance check`。
- public API: `lorairo.public_api.maintenance.check_database`。
- Business Logic: `DbMaintenanceCheckService` (Qt-free)、`ProviderBatchJobService.fetch_remote_status_readonly`、`ProviderBatchWorkflowService.fetch_remote_status_readonly`。
- Repository: `ImageRepository.iter_stored_image_paths` / `iter_processed_image_paths`、
  `ProviderBatchRepository.list_job_states` / `list_job_ids_with_unlinked_items`。

## Consequences

- 修復手順は利用者・エージェントが既存コマンドで組み立てる。定型修復が必要になったら、
  dry-run 既定・`--apply` 必須・事前バックアップ・exact-set guard を条件に種類ごとに追加する (案 B)。
- `files` は全画像のファイル存在確認をするため、画像数とファイルシステムの速度に比例して時間がかかる。
- 点検の種類を増やすときは `--scope` を増やし、同じ item/result 形式に載せる。

## Related

- Issue #1358, #1337, #1476
- ADR 0038, 0056, 0057, 0059, 0060, 0093
