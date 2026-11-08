# DB メンテナンス点検

`maintenance check` は既存プロジェクトの DB とローカルファイルを読み取り、不整合を種類別に件数と ID で報告します (ADR 0099)。

```bash
lorairo-cli --json maintenance check --project my_dataset
lorairo-cli --json --read-only maintenance check --project my_dataset --scope batch --limit 50
```

`--read-only` の有無によらず読み取り専用です。現在のスキーマを持つ既存 DB が必要で、DB の初期化、マイグレーション、修復、プロバイダ API の呼び出しは行いません。未準備の DB は `PRECONDITION_FAILED` を返します。

## 点検の種類

`--scope` は繰り返して指定できます。省略すると全範囲を点検します。

| scope | check | id_type | 内容と対処の例 |
| --- | --- | --- | --- |
| `batch` | `batch_unknown_status` | `job_id` | job status が共通語彙の外。`batch status JOB_ID` で確認 |
| `batch` | `batch_import_marker_mismatch` | `job_id` | status `imported` と `imported_at` が一致しない |
| `batch` | `batch_active_past_expiry` | `job_id` | DB 上は進行中だが `expires_at` を過ぎた。`batch status JOB_ID` で最新化 |
| `batch` | `batch_unlinked_items` | `job_id` | 未取込みの item の画像が削除され、結果を保存できない |
| `files` | `image_file_missing` | `image_id` | 原本の保存ファイルが無い |
| `files` | `processed_file_missing` | `image_id` | 処理済み画像のファイルが 1 つ以上無い。`images process --image-ids` で再生成 |

プロバイダ側の状態との突き合わせは行いません。DB に記録された情報だけで判定します。

## JSONL と上限

点検ごとに `kind=item` を 1 行出します (件数 0 でも出します)。フィールドは `check`, `scope`, `id_type`, `count`, `ids`, `ids_truncated`, `description` です。

最後の `kind=result` は `project`, `read_only=true`, `status=success`, `scopes`, `limit`, `checked_batch_jobs`, `checked_images`, `checked_processed_images` (対象外の範囲は null), `provider_queried=false`, `repaired=false`, `checks_run`, `issue_count`, `issues_found`, `failing_checks` を返します。

`count` は常にプロジェクト全体の件数で、`ids` は昇順の先頭 `--limit` 件 (既定 100、1〜500) です。不整合が見つかっても exit 0 です。判定には `issues_found` を使ってください。`files` は全画像のファイル存在を確認するため、画像数に比例して時間がかかります。
