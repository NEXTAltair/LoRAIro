---
type: ADR
title: Provider Batch 失敗 image_id の CLI 復旧経路
status: Accepted
timestamp: 2026-09-07
tags: []
---
# ADR 0093: Provider Batch 失敗 image_id の CLI 復旧経路

- **関連 Issue**: #1337、#1358(フォローアップ: 汎用 DB メンテナンスコマンド、詳細設計は未着手)
- **関連 ADR**: 0038(Provider Batch Job Lifecycle)、0057(CLI 構造化エラー契約)、0062(`custom_id` と `image_id` の対応)、0063(`submit --image-ids`)

## Context

Provider Batch(OpenAI Batch API など)を 500 件規模で運用すると、ジョブ全体は `completed` であっても一部リクエストのみプロバイダー側で失敗する部分成功(実測: 498/500、447/500、289/500)が発生する。また、状態が `failed` かつ `request_count: 0`(プロバイダーが結果ファイルをすでに削除済み)となるケースもある。

しかし、いずれの場合も CLI から未保存・未処理の画像を `image_id` 単位で復元する経路がなかった(Issue #1337)。原因は以下の 2 点である。

1. `import_results` はプロバイダー項目の失敗を `failed_custom_ids`(`custom_id` 単位)として返すのみで、`custom_id` から `image_id` への変換を行っていなかった。対応情報自体は ADR 0062 により `ProviderBatchItem.image_id`(代表 `image_id`)と `raw_request.lorairo_image_ids`(重複排除の展開先となる fan-out 群)として DB に保存されているが、CLI 出力へ伝播していなかった。
2. 結果ファイル削除済みエラー(`ProviderBatchError`、`_batch_job_error_to_provider_error`)が `lorairo.cli._errors.classify_exception` で明示分類されておらず、未分類例外の最終フォールバック(`INTERNAL_ERROR`、`retryable=False`)へ落ちていた。これは「再送は Annotate から行ってください」という例外メッセージの意図と矛盾している。

その結果、運用者は DB スナップショットを手作業で集計し、未処理画像を推測して再投入するしかなかった。

## Decision

新規コマンドや新規テーブルは追加しない。既存の `raw_request.lorairo_image_ids`(ADR 0062)と構造化エラーの `details` 経路(ADR 0057)を活用し、以下の 2 箇所を拡張する。

### 1. `ProviderBatchImportResult.failed_image_ids` の追加

`_prepare_import_results` および `import_results` がすでに保持している `custom_id` と `ProviderBatchItem` の対応を利用する。`failed_custom_ids` と同じ集合を `image_id`(fan-out 込み)へ変換した `failed_image_ids: tuple[int, ...]` を追加し、`lorairo-cli batch import --json` の出力へそのまま載せる。

なお、`missing_custom_ids`(DB 項目自体が存在しない、または `image_id` が未設定のもの)は `image_id` を復元できないため対象外とし、従来どおり `custom_id` のまま返す。

### 2. 結果ファイル削除済みエラーの再分類

`ProviderBatchError` に任意の `details: Mapping[str, Any] | None` を持たせる。`_batch_job_error_to_provider_error` が「結果ファイル削除済み」と判定した場合、対象ジョブの未インポート項目から `image_id`(fan-out 込み)を集計し、`details = {"reason": "result_file_missing", "affected_image_ids": [...]}` を設定する。

さらに、`lorairo.cli._errors` に `ProviderBatchError` かつ `details.reason == "result_file_missing"` のケースを追加し、`retryable=True`、`user_action_required=True` と分類する。ADR 0057 の `_error_details` は例外の `details` 属性をそのまま構造化エラー出力へ転記する既存経路であるため、新しい出力契約は増やさない。

### 再投入の運用

復元した `image_id` の再投入は既存の `lorairo-cli batch submit --image-ids`(ADR 0063)へそのまま渡す運用とし、専用の再投入コマンドは新設しない。

## Rationale

以下の代替案を検討したが、いずれも却下した。

- **専用診断コマンド(`batch failures` など)を新設する案**: CLI のコマンド面数が増え、`status`、`fetch`、`import` と機能が重複する。今回必要な情報は既存コマンドの出力へ 1 フィールド追加するだけで得られるため過剰である。
- **ジョブごとの画像成否を記録する新規テーブルを作る案**: 同じ情報がすでに `raw_request.lorairo_image_ids` に存在するため、別テーブルへの複製は YAGNI 違反となり、データ不整合のリスクを増やす。

既存データと既存のエラー詳細経路を再利用することで、最小の実装コストで要件を満たせるため本案を採用した。DB とプロバイダー状態の突き合わせといった汎用的な診断ニーズは、Issue #1358 で別途検討する。

## Consequences

- `ProviderBatchImportResult` および CLI の `import` JSON 出力へのフィールド追加は後方互換である(既存フィールドは変更しない)。
- 今後 `ProviderBatchError` を独自の `details` 付きで送出する箇所が増える場合も、ADR 0057 の `_error_details` 経路をそのまま利用し、新しい例外プロトコルは作らない。
- `_errors.py` の分類テーブルに `ProviderBatchError` 用の分岐が増えたため、今後 Provider Batch 起因の新しい例外を追加する際はこの分類ルールも更新する。
- フォローアップとして Issue #1358(DB メンテナンス用コマンドの作成、設計未着手)を残す。
