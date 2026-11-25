---
type: ADR
title: 読み取り専用の DB メンテナンス点検コマンド
status: Accepted
timestamp: 2026-11-08
tags: [cli, maintenance, provider-batch, read-only, filesystem]
---

# ADR 0099: 読み取り専用の DB メンテナンス点検コマンド

## Context

ADR 0093 では、Provider Batch の失敗画像を既存の `batch status`・`batch fetch`・`batch import` の出力で特定する方針を採った。一方で、DB と他の状態(外部プロバイダや実ファイル)を突き合わせて不整合を検出する汎用的な仕組みは、別課題として検討を保留していた。

不整合が発生し得る領域は、画像と実ファイルの対応、Provider Batch のジョブやアイテム、クロップ、データセット、SQLite 自体など多岐にわたる。これらを自動修復しようとすると、削除・NULL 化・再リンクといった種類ごとの価値判断が必要になり、誤操作による影響も大きくなる。

検討した選択肢は次の 4 案である。

- **案 A**: 読み取り専用の点検コマンドだけを新設し、修復は既存コマンドに委ねる。
- **案 B**: 案 A に加え、ドライランを既定とする修復コマンドも設ける。
- **案 C**: 汎用コマンドは作らず、各ドメインのグループ(`batch` / `images` / `project`)に個別の点検コマンドを追加する。
- **案 D**: SQLite レベル(`integrity_check` 等)の点検のみに限定する。

## Decision

案 A を採用し、`lorairo-cli maintenance check` を新設する。本コマンドは常に読み取り専用とし、修復処理は行わない。検出した ID を既存コマンド(`batch status`、`batch submit --image-ids`、`images process` 等)へ渡して対処する運用とする。

### 点検スコープ

既定(`--scope` 省略時)の点検対象は、ローカルで完結する次の 2 スコープとする。外部プロバイダ API は呼び出さない(`provider_queried=false`)。

- `batch`: 次の不整合を検出する。
  - ジョブのステータスが共通語彙(ADR 0038)の範囲外である。
  - `imported` と `imported_at` の状態が一致しない。
  - DB 上は進行中であるにもかかわらず、記録済みの `expires_at` を過ぎている。
  - 画像参照を失った未取込みアイテムを持つジョブが存在する。
- `files`: 原本(`images.stored_image_path`)または処理済み画像の実ファイル欠損を画像 ID 単位で検出する。

`--scope provider` を明示指定した場合のみ、Provider Batch API を読み取り専用で照会し、DB と突合する(#1476、`provider_queried=true`、`repaired=false`)。

- `provider_status_mismatch`: DB が進行中なのにプロバイダ側が終端状態(`completed` / `failed` / `canceled` / `expired`)である場合、または DB が終端状態なのにプロバイダ側のステータスと一致しない場合を検出する(`imported` はプロバイダ側の `completed` に対応する)。
- `provider_job_missing`: DB の `provider_job_id` がプロバイダ側に存在しない(404 / not found)場合を検出する。
- `provider_counts_mismatch`: DB とプロバイダ側の双方に件数があるとき、`succeeded_count` または `failed_count` が一致しない場合を検出する。

### 外部 API 呼び出しの安全制御とエラー扱い

`--scope provider` では、外部 API の大量呼び出しを防ぐための制限とエラー分類を設ける。

- DB 内の対象ジョブ件数が 500 件(`MAX_PROVIDER_CHECK_JOBS`)を超える場合、API を呼び出す前に `RESULT_SET_TOO_LARGE`(`exit 2`)で拒否する。
- API キー未設定や認証失敗は `AUTH_ERROR`(`exit 1`)を返す。
- 全件の通信失敗やレート制限は `NETWORK_ERROR` または `RATE_LIMITED`(`exit 1`)を返す。
- 複数ジョブの一部のみが通信失敗やレート制限となった場合は、`ok=false`・`status=partial_success`(`exit 3`)を返す。

### 出力形式・終了コード・DB アクセス

- **count-first 出力(ADR 0056 / ADR 0060)**: 件数は常にプロジェクト全体を集計し、ID は点検種別ごとに昇順で `--limit`(1〜500、既定 100)件まで出力する。ローカルスコープ(`batch` / `files`)の走査は件数で打ち切らず全件を確認するため、`RESULT_SET_TOO_LARGE` は返さない。
- **終了コード**: 点検で不整合が見つかっても、コマンド自体は成功(`exit 0`、`status=success`)とする。不整合の有無は結果の `issues_found` と `issue_count` で判定する。`tags health` と同じく、見つかった不整合は失敗ではなく点検データとして扱う。
- **読み取り専用の DB アクセス**: 既存の互換 DB を読み取り専用で開く(ADR 0059)。初期化やマイグレーションは行わず、既定スコープでは外部通信も行わない。DB の読み取りは Repository 経由で、チャンクごとの短いセッションにより走査する。

## Implementation

- **CLI**: `src/lorairo/cli/commands/maintenance.py`、イントロスペクションの `maintenance check`
- **公開 API**: `lorairo.public_api.maintenance.check_database`
- **ビジネスロジック**: `DbMaintenanceCheckService`(Qt 非依存)、`ProviderBatchJobService.fetch_remote_status_readonly`、`ProviderBatchWorkflowService.fetch_remote_status_readonly`
- **Repository**: `ImageRepository.iter_stored_image_paths` / `iter_processed_image_paths`、`ProviderBatchRepository.list_job_states` / `list_job_ids_with_unlinked_items`

## Consequences

- 修復手順は利用者やエージェントが既存コマンドを組み合わせて実行する。定型的な修復が必要になった場合は、ドライラン既定・`--apply` 必須・事前バックアップ・exact-set guard を条件として、種類ごとに追加する(案 B)。
- `files` スコープは全画像の実ファイル存在確認を行うため、画像数とファイルシステムの速度に比例して処理時間が延びる。
- 点検の種類を追加する際は `--scope` の選択肢を増やし、既存のアイテム・結果形式に乗せて拡張できる。

## Related

- Issue #1358, #1337, #1476
- ADR 0038, 0056, 0057, 0059, 0060, 0093
