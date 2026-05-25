# Provider Batch API 利用条件と運用ガイド

このガイドは、大量画像アノテーションを Provider Batch API で実行するかどうかを判断し、
LoRAIro 上で予定している job 投入、確認、キャンセル、取得、import の運用手順をまとめる。

対象は **OpenAI direct route** と **Anthropic direct route** のみ。Google Vertex AI / OpenRouter は
このガイドの Provider Batch API 対象外として扱う。

2026-05-25 時点の `main` では、Provider Batch API の DB / service boundary は存在するが、user が使う
CLI / GUI の job 管理画面と provider adapter wiring はまだ実装途中である。現時点で実行可能な CLI は
legacy/manual OpenAI JSONL import の `lorairo-cli annotate import-batch` のみで、新しい Provider Batch
job queue の submit / refresh / cancel / fetch / import workflow は #463 / #483 / 関連 issue の完了後に
利用可能になる。

設計方針は [ADR 0038](decisions/0038-provider-batch-api-integration-strategy.md) を参照。
Provider の公式仕様は必要に応じて以下を確認する。

- OpenAI Batch API: https://platform.openai.com/docs/guides/batch
- Anthropic Message Batches API: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing

## 使うべきケース

Provider Batch API は、今すぐ画面に結果を返す必要がない大量処理向けの非同期 job queue である。
同期 annotation の「開始して進捗バーを見ながら完了を待つ」処理とは別物として扱う。

使うべきケース:

- 数百から数万件の画像をまとめてアノテーションしたい
- 完了まで数十分から 24 時間程度待てる
- 通常の同期 API より cost discount と高い batch 用 rate limit を優先したい
- provider 側に request / result artifact が一定期間保存されることを許容できる
- OpenAI または Anthropic の direct API key を持っている

避けるべきケース:

- 少数画像を確認しながらすぐ結果を見たい
- GUI の progress dialog で逐次進捗を見たい
- OpenRouter 経由の provider routing / fallback だけを使っている
- Google Vertex AI の GCS / BigQuery / project / region / IAM 設定を使う batch inference を実行したい
- provider 側 retention / privacy policy により画像や prompt の一時保存を許容できない

## 対象 provider

### OpenAI direct route

OpenAI Batch API は request JSONL を upload し、batch job を作成して、後から status と output / error
file を取得する方式である。OpenAI 公式 docs では、同期 API 比の 50% discount、batch 用 rate limit、
24h completion window が説明されている。

Setup checklist:

- [ ] OpenAI direct route の API key が設定されている
- [ ] provider batch 対応 model が `image-annotator-lib` で eligible と判定される
- [ ] LoRAIro DB 上で対象 model が discontinued ではない
- [ ] job が 1 provider x 1 model x 1 endpoint x 1 prompt profile になるよう対象を分けている
- [ ] completed 後、OpenAI 側 retention 期限内に results を取得する運用になっている

注意:

- LoRAIro は OpenAI の provider-native request JSONL / output JSONL を user に手動編集させない
- provider-native file download と parser は `image-annotator-lib` の責務
- LoRAIro は library から返る normalized result を DB に保存する設計である
- 既存の `lorairo-cli annotate import-batch` は、手動取得済み OpenAI JSONL の legacy/manual import 用であり、
  新しい Provider Batch job queue とは別経路である

### Anthropic direct route

Anthropic Message Batches API は、`custom_id` 付き Messages requests を非同期処理し、batch status と
results stream を取得する方式である。Anthropic 公式 docs では、50% pricing、24h expiration、
batch results の 29 日 availability、Zero Data Retention 対象外であることが説明されている。

Setup checklist:

- [ ] Anthropic direct route の API key が設定されている
- [ ] 対象 model が active で、Provider Batch eligibility に通る
- [ ] vision request として `image-annotator-lib` が normalized result へ変換できる
- [ ] 24h expiration と results availability 期限内に results を取得する運用になっている
- [ ] Zero Data Retention が必要な workflow ではない

注意:

- 24h 以内に処理されなかった item は expired として扱う
- results は provider retention 期限内に取得する
- ZDR が必要な workflow では Anthropic Message Batches を使わない

### 対象外 provider

Google Vertex AI Gemini batch inference は、Cloud Storage / BigQuery、Google Cloud project、region、
IAM / credential 設定を前提にするため、この OpenAI / Anthropic direct route guide には含めない。

OpenRouter は同期 inference route として扱う。OpenRouter が内部で OpenAI / Anthropic / Google に
route できても、LoRAIro が provider-native batch job id、status、cancel、result artifact lifecycle、
discount、retention を直接管理できることとは別問題である。したがって OpenRouter 経由 model は
Provider Batch job 作成候補に表示しない。

## LoRAIro の責務境界

Provider Batch API は LoRAIro の同期 `AnnotationWorker` には統合しない。永続化された job queue として
扱い、アプリ再起動後も status refresh / results fetch / import を続けられるようにする。

責務分担:

- `image-annotator-lib`: provider-specific payload 作成、submit、retrieve、cancel、result fetch、
  provider response parse、normalized result 生成を担当する予定
- LoRAIro: job / item / artifact の DB 永続化、`custom_id` mapping、status 表示、normalized result import
  を担当する予定
- user: direct provider API key 設定、job の投入と監視、retention 期限内の results 取得判断

LoRAIro は provider 生 payload / response を stable user workflow として扱わない。output / error file を
手動解析する運用も前提にしない。

## CLI 運用

Provider Batch job 管理 CLI は、同期 annotation の `annotate run` とは別の job lifecycle 操作として扱う。
ただし、2026-05-25 時点の `main` ではこの CLI はまだ利用できない。以下は #463 で追加される想定の
operation model であり、実際の command name / option は実装後の `lorairo-cli --help` を正とする。

| 操作 | 目的 |
|---|---|
| submit | 対象画像、provider、model、endpoint、prompt profile を指定して provider batch job を作成する |
| list | DB に永続化された provider batch jobs を一覧する |
| status / refresh | provider から最新 status と counts を取得し、DB job state を更新する |
| cancel | 実行中 job の cancel を provider に要求する |
| fetch | completed job の result artifacts / normalized results を library 経由で取得する |
| import | fetch 済み normalized results を LoRAIro の annotation save path へ保存する予定 |

実装後の基本手順:

1. `models list` などで OpenAI / Anthropic direct route の対象 model を確認する。
2. Provider Batch job を submit する。対象は同一 provider、同一 model、同一 endpoint、同一 prompt profile に揃える。
3. `list` または `status / refresh` で status と counts を確認する。
4. `completed` になったら `fetch` で results を取得する。
5. `import` で normalized annotation results を LoRAIro DB に保存する。
6. `failed` / `expired` / `canceled` item があれば、対象画像を絞って新しい job として retry する。

運用上の注意:

- `submit` 済み job は provider 側で進むため、LoRAIro を終了しても job 自体は止まらない
- `cancel` は即時完了とは限らず、`canceling` を経て `canceled` になる
- `imported` の job は、import 実装後に二重 import しない
- provider retention 期限を過ぎると results を取得できなくなる可能性があるため、completed job は早めに取得する

## GUI 運用

GUI では、Provider Batch job を同期 annotation の progress dialog ではなく job queue として操作する。
ただし、2026-05-25 時点の `main` ではこの GUI はまだ利用できない。以下は #483 で追加される想定の
画面構成であり、実際の label / action は実装後の GUI を正とする。

実装後の基本手順:

1. Batch job 作成 dialog を開く。
2. provider、model、endpoint、対象画像、prompt profile、request count、任意 description を確認する。
3. OpenRouter route と discontinued model が候補に出ていないことを確認する。
4. job を submit する。
5. Batch job list view で provider、model、status、counts、submitted_at、completed_at、imported_at を確認する。
6. 必要に応じて refresh、cancel、fetch results、import を実行する。
7. Batch job detail view で `custom_id` ごとの item status を確認し、failed / expired / canceled item を絞り込む。

GUI でも provider-native payload / result JSONL を直接編集・解析する必要はない。fetch / import は
実装後に `image-annotator-lib` の normalized result contract を通して実行する。

## Status と retry

LoRAIro は provider 固有 status を共通 status に正規化して表示する。

| Status | 意味 | 主な対応 |
|---|---|---|
| draft | local job 作成中 | submit 前の状態として扱う |
| submitted | provider に投入済み | status refresh を待つ |
| validating | provider が request を検証中 | validation failure に備えて status を確認する |
| running | provider が処理中 | 完了、失敗、期限切れ、cancel を待つ |
| completed | provider results が取得可能 | retention 期限内に results を取得する |
| failed | provider job が失敗 | error を確認し、request 条件を修正して新しい job を作る |
| canceling | cancel 要求処理中 | refresh して canceled / completed / failed を確認する |
| canceled | cancel 済み | 未処理 item は必要に応じて新しい job で retry する |
| expired | 24h window 等で期限切れ | expired item を新しい job で retry する |
| imported | LoRAIro DB へ import 済み | import 実装後は二重 import しない |

Item 単位の扱い:

- succeeded item は import 実装後の保存対象になる
- failed item は error type / message を確認し、入力や model 条件を直して retry する
- expired item は provider が処理しなかった request として扱い、必要なら新しい job に入れる
- canceled item は cancel で送信されなかった request として扱い、必要なら新しい job に入れる

Provider Batch API の retry は既存 job を変更する操作ではない。未解決 item を選び直し、新しい job として
submit する。

## Privacy / retention

Provider Batch API は provider 側に request / result artifact を保持する。LoRAIro の local DB や
artifact 保存方針だけでは retention を完結できない。

運用ルール:

- OpenAI / Anthropic の最新 data retention policy を確認してから batch を使う
- Anthropic Message Batches は Zero Data Retention 対象外として扱う
- completed job は provider retention 期限内に results を取得する
- 取得済み artifacts は LoRAIro の local project data として扱い、通常の backup / purge policy に従う
- secret や公開できない画像を provider batch に投入しない

## Legacy/manual OpenAI JSONL import との違い

`lorairo-cli annotate import-batch` と既存 GUI import は、手動で取得済みの OpenAI Batch API result JSONL を
LoRAIro に取り込む legacy/manual import である。

新しい Provider Batch job queue との違い:

- legacy/manual import は provider job submit / status / cancel / fetch を管理しない
- legacy/manual import は OpenAI JSONL result file を入力にする
- Provider Batch job queue は `provider_batch_jobs` / `provider_batch_items` / `provider_batch_artifacts`
  に job state を保存する設計である
- Provider Batch job queue は `custom_id = img-{image_id}` を result 照合の SSoT とする設計である
- Provider Batch job queue は OpenAI / Anthropic の provider 差分を `image-annotator-lib` 側で吸収する設計である

新規 workflow は、Provider Batch job queue の CLI / GUI / adapter wiring 実装後に使う。現時点で既に
取得済みの OpenAI JSONL を後から取り込む場合だけ、legacy/manual import を使う。
