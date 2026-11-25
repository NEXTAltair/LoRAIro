# DB メンテナンス点検

`maintenance check` は既存プロジェクトの DB とローカルファイルを読み取り、不整合を種類別の件数と ID で報告します(ADR 0099)。

```bash
lorairo-cli --json maintenance check --project my_dataset
lorairo-cli --json --read-only maintenance check --project my_dataset --scope batch --limit 50
lorairo-cli --json maintenance check --project my_dataset --scope provider
```

## 動作の前提と読み取り専用保証

- `--read-only` の有無にかかわらず、常に読み取り専用で動作します。
- 現在のスキーマを持つ既存 DB が必要です。DB の初期化・マイグレーション・修復は行いません。
- 未準備の DB に対して実行した場合は `PRECONDITION_FAILED` を返します。
- 既定(`--scope` 省略時)では `batch` と `files` のみを点検し、プロバイダ API は呼び出しません(`provider_queried=false`)。
- `--scope provider` を明示したときのみ、プロバイダ API を読み取り専用で照会します(`provider_queried=true`、`repaired=false`)。

## 点検の種類

`--scope` は複数回指定できます。省略するとローカル完結の `batch` と `files` を点検します(`provider` は明示指定時のみ実行します)。

| scope | check | id_type | 内容と対処の例 |
| --- | --- | --- | --- |
| `batch` | `batch_unknown_status` | `job_id` | ジョブの status が共通語彙の外にある。`batch status JOB_ID` で確認 |
| `batch` | `batch_import_marker_mismatch` | `job_id` | status の `imported` と `imported_at` が一致しない |
| `batch` | `batch_active_past_expiry` | `job_id` | DB 上は進行中だが `expires_at` を過ぎている。`batch status JOB_ID` で最新化 |
| `batch` | `batch_unlinked_items` | `job_id` | 未取込み item の画像が削除されており、結果を保存できない |
| `files` | `image_file_missing` | `image_id` | 原本の保存ファイルが存在しない |
| `files` | `processed_file_missing` | `image_id` | 処理済み画像のファイルが 1 つ以上欠けている。`images process --image-ids` で再生成 |
| `provider` | `provider_status_mismatch` | `job_id` | DB 状態がプロバイダ側の status と不一致(進行中のまま終端到達など)。`batch status JOB_ID` で最新化 |
| `provider` | `provider_job_missing` | `job_id` | DB の `provider_job_id` がプロバイダ側に存在しない(404) |
| `provider` | `provider_counts_mismatch` | `job_id` | DB とプロバイダ側の `succeeded_count` や `failed_count` が不一致。`batch status JOB_ID` で再同期 |

### `--scope provider` の上限とエラー終了コード

`--scope provider` では、外部 API の大量呼び出しを防ぐため上限とエラー分類を設けています。

- **対象件数超過**: DB 内の対象ジョブが 500 件を超える場合、API 呼び出し前に `RESULT_SET_TOO_LARGE`(exit 2)を返します。
- **認証エラー**: API キー未設定や認証エラーの場合は `AUTH_ERROR`(exit 1)を返します。
- **全件の通信失敗・レート制限**: `NETWORK_ERROR` または `RATE_LIMITED`(exit 1)を返します。
- **一部ジョブの通信失敗**: 複数ジョブの一部のみが通信エラーなどで失敗した場合は、`ok=false`・`status=partial_success`(exit 3)を返します。

## JSONL 出力と件数上限

点検項目ごとに `kind=item` を 1 行出力します(件数が 0 の場合も出力します)。各行には `check`、`scope`、`id_type`、`count`、`ids`、`ids_truncated`、`description` フィールドが含まれます。

最後の `kind=result` 行では、以下のフィールドを返します。

- `project`、`read_only=true`、`status`(`success` または `partial_success`)
- `scopes`、`limit`
- `checked_batch_jobs`、`checked_images`、`checked_processed_images`(対象外の範囲は `null`)
- `provider_queried`、`repaired=false`
- `checks_run`、`issue_count`、`issues_found`、`failing_checks`

### 上限と終了コードの注意点

- `count` は常にプロジェクト全体の件数を表します。
- `ids` には昇順で先頭 `--limit` 件(既定 100、指定範囲 1〜500)を格納します。
- 不整合が見つかっても終了コードは 0 です。不整合の有無は `issues_found` で判定してください。
- `files` スコープは全画像のファイル存在を確認するため、画像数に比例して実行時間がかかります。
