---
type: ADR
title: Provider Batch 失敗 image_id の CLI 復旧経路
status: Accepted
timestamp: 2026-09-07
tags: []
---
# ADR 0093: Provider Batch 失敗 image_id の CLI 復旧経路

- **関連 Issue**: #1337, #1358 (フォローアップ: 汎用 DB メンテナンスコマンド、詳細設計は未着手)
- **関連 ADR**: 0038 (Provider Batch Job Lifecycle), 0057 (CLI 構造化エラー契約), 0062 (custom_id ⇔ image_id 対応), 0063 (submit --image-ids)

## Context

Provider Batch (OpenAI Batch API 等) を 500 件規模で運用すると、ジョブ全体は
`completed` でも一部リクエストだけ provider 側で失敗する部分成功 (実測: 498/500,
447/500, 289/500) が発生する。また `failed` かつ `request_count: 0` (provider が
結果ファイルを既に削除済み) というケースもある。

いずれの場合も、CLI から「どの画像が未保存/未処理か」を image_id 単位で復元する経路が
なかった (#1337)。理由は 2 つ:

1. `import_results` は provider item の失敗を `failed_custom_ids` (custom_id 単位)
   としてのみ返しており、custom_id → image_id の変換は行っていなかった。この変換自体は
   ADR 0062 で `ProviderBatchItem.image_id` (代表 image_id) と `raw_request.lorairo_image_ids`
   (dedupe fan-out 群) として DB に保存されているが、CLI 出力までは伝播していなかった。
2. 結果ファイル削除済みエラー (`ProviderBatchError`, `_batch_job_error_to_provider_error`)
   は `lorairo.cli._errors.classify_exception` で明示分類されておらず、未分類例外の
   最終フォールバック (`INTERNAL_ERROR, retryable=False`) に落ちていた。これは
   「再送は Annotate から行ってください」という例外メッセージの意図と矛盾する。

結果として、運用者は DB スナップショットを手作業で集計し、未処理画像を推測して
再投入するしかなかった。

## Decision

新規コマンド・新規テーブルは追加しない。既存の `raw_request.lorairo_image_ids`
(ADR 0062) と既存の構造化エラー `details` 経路 (ADR 0057) を使い、2 箇所を拡張する。

1. **`ProviderBatchImportResult.failed_image_ids`**: `_prepare_import_results` /
   `import_results` が既に保持している custom_id ⇔ `ProviderBatchItem` の対応を使い、
   `failed_custom_ids` と同じ集合を image_id (fan-out 込み) へ変換した
   `failed_image_ids: tuple[int, ...]` を追加する。`lorairo-cli batch import --json`
   の出力にそのまま載る。missing_custom_ids (DB item 自体が無い/image_id 未設定) は
   image_id を復元できないため対象外とし、従来通り custom_id のまま返す。

2. **結果ファイル削除済みエラーの再分類**: `ProviderBatchError` に任意の
   `details: Mapping[str, Any] | None` を持たせ、`_batch_job_error_to_provider_error`
   が「結果ファイル削除済み」と判定した場合、対象 job の未 import item から
   image_id (fan-out 込み) を集めて `details = {"reason": "result_file_missing",
   "affected_image_ids": [...]}` を設定する。`lorairo.cli._errors` に
   `ProviderBatchError` + `details.reason == "result_file_missing"` を
   `retryable=True, user_action_required=True` と判定する分類を追加する。
   ADR 0057 の `_error_details` は例外の `details` 属性をそのまま構造化エラー出力に
   転記する既存経路であり、新しい出力契約は増やさない。

再投入は既存の `lorairo-cli batch submit --image-ids` (ADR 0063) にそのまま渡せる
運用とし、専用の再投入コマンドは作らない。

## Rationale

検討した代替案:

- **専用診断コマンド (`batch failures` 等) を新設**: CLI の面数が増え、`status`/
  `fetch`/`import` と機能が重複する。今回欲しい情報は既存コマンドの出力に 1
  フィールド足すだけで得られるため過剰。
- **ジョブ×画像の成否を記録する新規テーブル**: 同じ情報が既に
  `raw_request.lorairo_image_ids` に存在するため、別テーブルへの複製は YAGNI 違反
  でありデータ不整合リスクを増やす。

既存データ・既存エラー詳細経路の再利用が最小の実装コストでニーズを満たすため、
これを採用した。より汎用的な「DB とプロバイダ状態の突き合わせ」ニーズ (診断コマンド
等) は #1358 で別途検討する。

## Consequences

- `ProviderBatchImportResult` / CLI `import` JSON 出力のフィールド追加は後方互換
  (既存フィールドは変更しない)。
- `ProviderBatchError` を独自の `details` 付きで raise する既存箇所が増える場合、
  ADR 0057 の `_error_details` 経路をそのまま使う (新しい例外プロトコルを作らない)。
- `_errors.py` の分類テーブルに `ProviderBatchError` 用のケースが増えたため、
  今後 Provider Batch 起因の新しい例外を追加する際はこの分類ルールを更新すること。
- フォローアップ: #1358 (DB メンテナンス用コマンドの作成、設計未着手)。
