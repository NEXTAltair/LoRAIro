---
type: Guide
title: Provider Batch API 利用条件と運用ガイド
status: Accepted
timestamp: 2026-06-07
tags: [provider-batch, annotation, webapi]
depends_on: [openai-api, anthropic-api]
---

# Provider Batch API 利用条件と運用ガイド

このガイドでは、大量の画像アノテーションを Provider Batch API で実行すべきか判断するための基準と、LoRAIro でのジョブ投入、状態確認、キャンセル、結果取得、取り込み(import)の運用手順をまとめる。

対象となるのは **OpenAI 直接ルート(direct route)** と **Anthropic 直接ルート** のみである。Google Vertex AI および OpenRouter は対象外として扱う。

設計方針は [ADR 0038](decisions/0038-provider-batch-api-integration-strategy.md) を参照する。各プロバイダーの公式仕様は以下のドキュメントを確認する。

- OpenAI Batch API: https://platform.openai.com/docs/guides/batch
- Anthropic Message Batches API: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing

## 実装ステータス

ADR 0038 の段階導入計画に対する現状の実装状況を示す。LoRAIro 側の CLI、GUI、Service、DB 層はプロバイダー横断で実装済みである。`image-annotator-lib` 側のプロバイダーアダプターは Anthropic Message Batches と OpenAI Moderations Batch に対応している。一方、OpenAI の通常のアノテーション生成バッチ(`/v1/responses`、`/v1/chat/completions`)および Google は未実装である。

| プロバイダー | LoRAIro 側(CLI / GUI / Service / DB) | image-annotator-lib アダプター | 現時点で実用可能か |
|---|---|---|---|
| Anthropic 直接ルート | 完全実装 | **完全実装**(Message Batches) | はい |
| OpenAI 直接ルート | rating preflight を実装 | **Moderations Batch のみ実装**(`/v1/moderations`) | はい(`task_type=rating_preflight` のみ) |
| Google Vertex AI | submit を**拒否**(CLI / GUI) | 未実装 | いいえ(ADR 0038 Phase 3) |
| OpenRouter ルート | submit を**拒否**(CLI / GUI) | 対象外 | いいえ(ADR 0038 対象外) |

関連する PR と Issue は以下のとおりである。

- LoRAIro #463 / PR #499: Provider Batch ジョブ管理 CLI(`lorairo-cli batch ...`)
- LoRAIro #483 / PR #498: Provider Batch ジョブ管理 GUI(`ProviderBatchJobWidget`、Provider Batch タブ)
- LoRAIro PR #495: `image-annotator-lib` のバッチ契約との整合
- LoRAIro #505: OpenAI Moderations Batch を `rating_preflight` として Provider Batch ワークフローへ接続
- image-annotator-lib #102 / #103: Anthropic Message Batches アダプターの移管と実装
- image-annotator-lib #116 / #117: WebAPI 配下への移管および互換性テスト

## 使うべきケース

Provider Batch API は、結果を即座に画面へ返す必要がない大量処理向けの非同期ジョブキューである。同期アノテーションのように「開始して進捗バーを見ながら完了を待つ」処理とは別物として扱う。

### 使うべきケース

- 数百から数万件の画像をまとめてアノテーションしたい。
- 完了まで数十分から 24 時間程度待てる。
- 通常の同期 API よりも料金割引と高いバッチ用レート制限を優先したい。
- プロバイダー側にリクエストや結果の成果物(artifact)が一定期間保存されることを許容できる。
- **Anthropic 直接ルートの API キーを持っている**、または OpenAI Moderations Batch を rating preflight として使うための OpenAI API キーを持っている。

### 避けるべきケース

- 少数の画像を確認しながらすぐに結果を見たい。
- GUI の進捗ダイアログで逐次進捗を確認したい。
- OpenRouter 経由のプロバイダールーティングやフォールバックのみを利用している。
- Google Vertex AI の GCS、BigQuery、project、region、IAM 設定を伴うバッチ推論を実行したい。
- プロバイダー側の保持期間やプライバシーポリシー上、画像やプロンプトの一時保存を許容できない。
- Zero Data Retention(ZDR)が必要である(Anthropic Message Batches は ZDR 対象外)。

## 対象プロバイダー

### Anthropic 直接ルート

Anthropic Message Batches API は、`custom_id` を付与した Messages リクエストを非同期で処理し、バッチのステータスと結果ストリームを取得する方式である。Anthropic 公式ドキュメントでは、50% 割引、24 時間の有効期限、結果の 29 日間保持、および Zero Data Retention 対象外であることが明記されている。

#### LoRAIro でのセットアップチェックリスト

- [ ] Anthropic 直接ルートの API キーを `config/lorairo.toml` の `[api] claude_key` に設定している(`ConfigurationService.get_api_keys()` は `[api]` セクションのみを参照するため、`ANTHROPIC_API_KEY` などの環境変数は Provider Batch の投入に使われない)。
- [ ] 対象モデルが `lorairo-cli models list` で有効と表示され、`discontinued_at` が null である。
- [ ] `image-annotator-lib` の `list_batch_capable_models()` で Anthropic バッチ対象として返る。
- [ ] 24 時間の有効期限と 29 日間の結果取得期限内に結果を取り込む運用になっている。
- [ ] Zero Data Retention を必要とするワークフローではない。

#### プロバイダー制約(Anthropic 公式)

- 1 バッチあたり最大 **100,000** 件の Message リクエスト、または **256 MB** のリクエストボディのいずれか先に到達した方が上限となる。
- 24 時間以内に処理されなかった項目は **expired** として扱われる。
- 結果は 29 日間プロバイダー側で取得可能であり、その後は失われる。
- Vision、tool use、system messages、multi-turn、beta features がバッチ処理に対応する。

#### LoRAIro 経由の追加制約(image-annotator-lib の Anthropic アダプター)

- **1 バッチあたり最大 500 項目**に制限される(ライブラリ側の `_MAX_LIBRARY_ITEMS = 500` で強制)。
- 上限を超えると `Batch contains N items; maximum is 500` で投入が拒否される。
- 大量の画像を投入する場合は LoRAIro 側で分割し、複数ジョブとして投入する。

### OpenAI 直接ルート(Moderations rating preflight)

OpenAI 直接ルートは、アノテーション API 投入前の安全性・レーティング事前判定(rating preflight)として `/v1/moderations` エンドポイントの Batch API を使用する。LoRAIro は `provider_batch_items.task_type` に `rating_preflight` を保存し、`image-annotator-lib` が Moderations 応答を `RatingPrediction` および `UnifiedAnnotationResult.ratings` へ正規化する。LoRAIro 側では OpenAI の JSONL 成果物を直接パースせず、既存の `ratings` テーブルへ取り込む。

#### OpenAI Moderations Batch のセットアップチェックリスト

- [ ] OpenAI 直接ルートの API キーを `config/lorairo.toml` の `[api] openai_key` に設定している。
- [ ] `openai/omni-moderation-latest` などのレーティングモデルが `lorairo-cli models list` に存在する。
- [ ] 投入時に `--task-type rating_preflight` を指定している。
- [ ] エンドポイントに `/v1/moderations` を使用する(上書きする場合も同エンドポイントのみ)。
- [ ] LoRAIro DB 上で対象モデルが廃止(discontinued)になっていない。
- [ ] 1 ジョブが「1 プロバイダー × 1 モデル × 1 エンドポイント × 1 プロンプトプロファイル」になるよう対象を分けている。
- [ ] 完了後、OpenAI 側の保持期限内に結果を取得する運用になっている。

#### プロバイダー制約(公式仕様)

- Batch API の対応エンドポイントに `/v1/moderations` が含まれる。
- 入力ファイルは `purpose=batch` の JSONL 形式である。各行は `custom_id`、`method=POST`、`url=/v1/moderations`、`body` を持ち、`body.model` と `body.input` を指定する。
- 1 バッチあたり最大 50,000 リクエスト、かつ JSONL ファイルサイズ 200 MB 以下である。
- 完了ウィンドウは 24 時間、料金は同期 API 比で 50% 割引となる。
- `/v1/responses` や `/v1/chat/completions` といった OpenAI のアノテーション生成バッチは LoRAIro では未対応である。
- ストリーミングには非対応だが、画像入力には対応している。

### 対象外プロバイダー

#### Google Vertex AI Gemini

Google Vertex AI Gemini のバッチ推論は、Cloud Storage、BigQuery、Google Cloud プロジェクト、リージョン、IAM および認証情報の設定を前提とするため、ADR 0038 Phase 3 として後回しにしている。2026-05-27 時点で CLI、GUI、ライブラリのいずれも未実装である。

`lorairo-cli batch submit --provider google` を実行するか、モデル解決で `google` が推定された場合、CLI は中央エラー境界(ADR 0057 §7)で構造化 `error` 行を出力して中断する。`--json` 指定時は標準出力に `kind=error` の 1 行が出力され、入力不正として `code=INVALID_INPUT` 相当、終了コード 2 となる。メッセージには `Google Provider Batch submit is disabled until Phase 3.` 相当の内容が入る。

GUI 側ではコンボボックスの候補から黙って除外される(「未設定」などの表示は出ない)。

#### OpenRouter ルート

OpenRouter は同期推論ルートとして扱う。OpenRouter が内部で OpenAI、Anthropic、Google へルーティングできたとしても、LoRAIro がプロバイダー固有のバッチジョブ ID、ステータス、キャンセル、結果成果物のライフサイクル、割引、保持期間を直接管理できることとは別問題である。したがって、OpenRouter 経由のモデルは Provider Batch ジョブの作成候補に表示しない。

`openrouter/...` プレフィックスの LiteLLM モデル ID で投入を試みると、CLI は中央エラー境界で構造化 `error` 行を出力して中断する。`--json` 指定時は標準出力に `kind=error` の 1 行が出力され、入力不正として `code=INVALID_INPUT` 相当、終了コード 2 となる。メッセージには `Could not infer a direct Provider Batch provider for 'openrouter/...'. Use a direct openai/... or anthropic/... model.` 相当の内容が入る。

## LoRAIro と image-annotator-lib の責務境界

Provider Batch API は LoRAIro の同期 `AnnotationWorker` には統合せず、永続化されたジョブキューとして扱う。そのため、アプリを再起動しても状態更新、結果取得、取り込みを継続できる。

| 責務 | 担当 | 補足 |
|---|---|---|
| `custom_id = img-{image_id}` の生成 | LoRAIro | `ProviderBatchJobService.build_custom_id` を SSoT とする |
| DB のジョブ・項目・成果物の永続化 | LoRAIro | `provider_batch_jobs` ほか計 3 テーブル |
| 保存画像パスの提供 | LoRAIro | `BatchSubmitItem.image_path` には `images.stored_image_path`(DB 上の元画像)を渡す。MVP ではリサイズ派生を使わない |
| MIME 判定、base64・data URL 化 | image-annotator-lib | プロバイダー固有の画像ペイロード構築はライブラリ内で完結する |
| プロバイダー固有リクエストの構築 | image-annotator-lib | OpenAI と Anthropic の形式差を吸収する |
| HTTP による投入・取得・キャンセル | image-annotator-lib | SDK 例外を `BatchJobError` へ変換する |
| 応答パースと正規化結果の生成 | image-annotator-lib | `UnifiedAnnotationResult` として返す |
| 共通ステータス語彙への正規化 | LoRAIro Service | `ProviderBatchJobService.normalize_status` |
| ジョブライフサイクル UI(キュー管理・更新・キャンセル・取り込み) | LoRAIro | CLI および GUI |
| 正規化結果のアノテーション保存 | LoRAIro | `AnnotationSaveService` 経由 |
| API キーの受け渡し | LoRAIro からライブラリへ引数渡し(`os.environ` は汚染しない) | `BatchSubmitRequest.api_keys` |

LoRAIro はプロバイダーの生ペイロードや生レスポンスをユーザー操作の前提とせず、出力ファイルやエラーファイルの手動解析も想定していない。ただし実装上の事実として、`provider_batch_jobs.raw_provider_payload`(ジョブ単位)と `provider_batch_items.raw_request` / `raw_response`(項目単位)の 3 カラムにはプロバイダーの生 JSON が保存される(プライバシー上の注意点は「[プライバシーと保持期間](#プライバシーと保持期間)」を参照)。

## CLI 運用

`lorairo-cli batch` は、同期アノテーションの `annotate run` とは別のトップレベルコマンドグループとしてジョブのライフサイクルを操作する。

| 操作 | 目的 |
|---|---|
| `submit` | 対象画像、プロバイダー、モデル、エンドポイント、プロンプトプロファイルを指定してバッチジョブを作成する |
| `list` | DB に永続化されたバッチジョブを一覧表示する |
| `status` | プロバイダーから最新の状態と件数を取得し、DB のジョブ状態を更新して表示する |
| `cancel` | 実行中ジョブのキャンセルをプロバイダーへ要求する |
| `fetch` | 完了済みジョブの結果成果物および正規化結果を取得する |
| `import` | 取得済みの正規化結果を LoRAIro のアノテーション保存経路へ書き込む |

なお、既存の `lorairo-cli annotate import-batch` は**別経路のレガシー手動取り込み**である(詳細は「[レガシー手動 OpenAI JSONL 取り込みとの違い](#レガシー手動-openai-jsonl-取り込みとの違い)」を参照)。

### batch submit — ジョブ投入

**構文**:

```bash
lorairo-cli batch submit --project <name> --model <id_or_name> \
  --image-id <id> [--image-id <id> ...] \
  [--provider {openai,anthropic}] [--endpoint <path>] \
  [--prompt-profile <name>] [--description <text>]
```

**オプション**:

- `--project <name>` / `-p <name>`: 対象プロジェクト(必須)
- `--model <id>` / `-m <id>`: LiteLLM モデル ID(例: `anthropic/claude-3-5-sonnet-20240620`)または DB 上の一意な表示名(必須)
- `--image-id <id>`: 投入する画像 ID(必須、複数指定可能)
- `--provider`: 推定されるプロバイダーを上書きする(`openai` または `anthropic`、任意)
- `--endpoint <path>`: プロバイダーエンドポイントを上書きする(既定値は `openai` が `/v1/chat/completions`、`anthropic` が `/v1/messages`)
- `--prompt-profile <name>`: プロンプトプロファイル名(既定値は `default`)
- `--description <text>`: ジョブの説明文(任意)

**例(Anthropic、現在の実用パス)**:

```bash
uv run lorairo-cli batch submit \
  --project my_dataset \
  --model anthropic/claude-3-5-sonnet-20240620 \
  --image-id 101 --image-id 102 --image-id 103 \
  --prompt-profile default \
  --description "Test batch 2026-05-27"
```

**例(OpenAI、ライブラリのアダプター完了まで失敗する)**:

```bash
uv run lorairo-cli batch submit \
  --project my_dataset \
  --model openai/gpt-4o-mini \
  --image-id 101 --image-id 102
# → 構造化 error 行で中断(メッセージ例: Unsupported Provider Batch provider 'openai'.、現状のライブラリ側ディスパッチ)
```

**出力例(成功時)**:

```
Provider Batch job submitted: 42
                  Provider Batch Job 42
┌─────────────────────┬────────────────────────────────┐
│ Field               │ Value                          │
├─────────────────────┼────────────────────────────────┤
│ id                  │ 42                             │
│ provider            │ anthropic                      │
│ provider_job_id     │ msgbatch_01ABC...              │
│ status              │ submitted                      │
│ provider_status     │ in_progress                    │
│ endpoint            │ /v1/messages                   │
│ ...                 │                                │
└─────────────────────┴────────────────────────────────┘
```

**エラーケース**:

エラーは ADR 0057 の中央エラー境界を経由し、構造化 `error` 行として出力される。`--json` 指定時は標準出力に `kind=error` の 1 行が出力され、終了コードは ADR 0057 §6 の対応表で決まる。

- **API キー未設定または不正**: 投入時に構造化 `error` 行(`code=AUTH_ERROR`、`retryable=false`、`user_action_required=true`、終了コード 1)を返す。事前ゲートは存在しないため、失敗して初めて表示される。
- **未知のモデル**: モデル解決が `click.UsageError` で拒否されるため `code=INVALID_INPUT`(終了コード 2)となる。メッセージには `Unknown model '<id>'. Run \`lorairo-cli models list\`.` 相当の内容が入る。
- **廃止済みモデル(`models.discontinued_at IS NOT NULL`)**: **事前ゲートされない**。`_resolve_model()` は `get_model_by_litellm_id()` を呼ぶだけで `discontinued_at` を確認しないため、有効な LiteLLM ID であれば投入経路へ進み、その後ライブラリまたはプロバイダー境界で失敗する可能性がある。ADR 0038 は適格性ゲートを要求しているが、CLI 側は現状未実装である。
- **同名モデルが複数存在**: 入力不正として構造化 `error` 行(`code=INVALID_INPUT` 相当)を返す。メッセージには `Ambiguous model '<id>': - <litellm_id> (provider: <p>) ...` 相当の内容が入る。
- **Google 指定**: 入力不正として構造化 `error` 行(`code=INVALID_INPUT` 相当、終了コード 2)を返す。メッセージは `Google Provider Batch submit is disabled until Phase 3.` 相当である。
- **OpenRouter 指定**: 入力不正として構造化 `error` 行(`code=INVALID_INPUT` 相当、終了コード 2)を返す。メッセージは `Could not infer a direct Provider Batch provider for ...` 相当である。
- **想定外の例外**: 構造化 `error` 行(`code=INTERNAL_ERROR`、終了コード 1)を返し、`logs/lorairo.log` にスタックトレースを記録する。

### batch list — ジョブ一覧

**構文**:

```bash
lorairo-cli batch list --project <name> [--provider <name>] [--status <name>] \
  [--limit N] [--offset N]
```

**オプション**:

- `--project <name>` / `-p <name>`: 対象プロジェクト(必須)
- `--provider <name>`: プロバイダーで絞り込む
- `--status <name>`: 共通ステータスで絞り込む(「[ステータスマッピングと再実行方針](#ステータスマッピングと再実行方針)」の 10 種から指定)
- `--limit N`: 最大表示行数(1〜1000、既定値 100)
- `--offset N`: スキップする件数(0 以上、既定値 0)

**例**:

```bash
uv run lorairo-cli batch list --project my_dataset
uv run lorairo-cli batch list --project my_dataset --provider anthropic --status running
uv run lorairo-cli batch list --project my_dataset --limit 20 --offset 40
```

**出力**: Rich Table(ID、Provider、Status、Provider Status、Requests、Created の列を表示)。

### batch status — 状態確認

**構文**:

```bash
lorairo-cli batch status <job_id> --project <name> [--refresh | --no-refresh]
```

**オプション**:

- `job_id`: 対象ジョブ ID(必須、位置引数)
- `--project <name>` / `-p <name>`: 対象プロジェクト(必須)
- `--refresh` / `--no-refresh`: プロバイダーへ最新状態を問い合わせるかどうか(既定値は `--refresh`)

**例**:

```bash
# プロバイダーに問い合わせて DB を更新してから表示
uv run lorairo-cli batch status 42 --project my_dataset

# DB の値のみを表示(プロバイダーに問い合わせない)
uv run lorairo-cli batch status 42 --project my_dataset --no-refresh
```

**出力**: 17 行の縦型 Rich Table(`id`、`provider`、`provider_job_id`、`status`、`provider_status`、`endpoint`、`model_id`、`request_count`、`succeeded_count`、`failed_count`、`canceled_count`、`expired_count`、`submitted_at`、`completed_at`、`canceled_at`、`expires_at`、`imported_at`)。

### batch cancel — キャンセル

**構文**:

```bash
lorairo-cli batch cancel <job_id> --project <name>
```

**動作**:

- プロバイダーへキャンセル要求を送信する。
- DB 上のジョブステータスを `canceling` へ遷移させる。
- プロバイダー側の完了を確認した後、後続の `status` または `refresh` で `canceled` へ正規化される。

### batch fetch — 結果取得

**構文**:

```bash
lorairo-cli batch fetch <job_id> --project <name> [--output-dir <path>]
```

**オプション**:

- `--output-dir <path>` / `-o <path>`: 成果物の出力ディレクトリ(既定値は `config/lorairo.toml` の `[directories] batch_results_dir`、未設定時は `batch_results/`)

**動作**:

- 正規化済みのバッチ結果と成果物を取得し、DB の `provider_batch_items` を更新する。
- アノテーション保存経路への書き込みは行わない(書き込みは `import` が担う)。
- Anthropic は結果をストリームで返すため成果物ファイルは生成されない(`destination_dir` 引数は Anthropic では無視される)。

### batch import — アノテーション保存

**構文**:

```bash
lorairo-cli batch import <job_id> --project <name> [--output-dir <path>]
```

**動作**:

- **常にプロバイダーへ再リクエストして fetch を実行する**。CLI からは `fetch_result` 引数を渡せないため、`ProviderBatchWorkflowService.import_results` 内の `else self.fetch_results(...)` 分岐が必ず実行される。直前に `batch fetch` を実行していても再度プロバイダーへアクセスする。
- そのため、**プロバイダーの保持期限を過ぎたジョブは取り込めない**。Anthropic の場合、結果の保持期限(29 日)を過ぎると `batch import` も失敗する。`fetch` と `import` は短時間で連続実行する運用とする。
- 正規化済みの結果項目を `custom_id = img-{image_id}` 基準でアノテーション保存経路へ投入する。
- 全項目の保存が成功した場合のみ、ジョブステータスを `imported` へ遷移させ、`imported_at` を記録する。
- すでに `imported` であるか `imported_at IS NOT NULL` のジョブは**再取り込みできない**。拒否時は `ProviderBatchError`(`RuntimeError` 派生)が送出されるが、`classify_exception` に専用マッピングがないため現状は `code=INTERNAL_ERROR`(終了コード 1、標準エラー出力にトレースバック)となる。メッセージは `Provider batch job は import 済みです: job_id=<id>` 相当である(状態衝突を表す専用コード `CONFLICT` への割り当ては未対応)。

**出力例**:

```
       Provider Batch Import Summary
┌──────────────┬───────┐
│ Metric       │ Value │
├──────────────┼───────┤
│ Imported     │ 95    │
│ Skipped      │ 3     │
│ Errors       │ 2     │
│ Total        │ 100   │
│ Job Imported │ yes   │
└──────────────┴───────┘
```

### 終了コード

ADR 0057 §6 に基づき、終了コードは中央エラー境界がエラーコードから機械的に導出する。旧 ADR 0038 ドラフトでは「終了コード 2 = 想定外例外」だったが、ADR 0057 で反転され、現在は終了コード 2 が入力・検証エラー専用となっている。

| 終了コード | 意味 | 該当エラーコード |
|---|---|---|
| `0` | 成功 | — |
| `2` | 入力・検証エラー | `INVALID_INPUT`、`VALIDATION_FAILED`、`RESULT_SET_TOO_LARGE` |
| `1` | 上記以外すべて(実行時エラー) | `AUTH_ERROR`、`NOT_FOUND`、`CONFLICT`、`NETWORK_ERROR`、`INTERNAL_ERROR` 等 |

`batch` コマンドにおける具体的な割り当ては以下のとおりである。

- Google 投入拒否、OpenRouter 推定失敗、曖昧なモデル、未知のモデルは、モデル解決ロジックが `click.UsageError` を送出するため、中央境界で `INVALID_INPUT`(終了コード 2)に統一される。
- API キー未設定または不正は `AUTH_ERROR`(終了コード 1)となる。
- 想定外の例外(`INTERNAL_ERROR`)は終了コード 1 となり、`logs/lorairo.log` にスタックトレースを記録する(旧仕様の終了コード 2 から変更)。
- `ProjectNotFoundError`(`--project` に存在しないプロジェクトを指定)は対象不在のため `NOT_FOUND` 相当(終了コード 1)となる(旧記述の終了コード 2 は ADR 0057 で無効になった)。

旧実装に散在していた `except ProviderBatchError → Exit(1)` や `except Exception → Exit(2)` は撤廃され、全コマンドが中央境界(`cli.main:main`)でエラーコードから終了コードを導出する(ADR 0057 §7)。

## GUI 運用

「ジョブ」タブからの投入機能を撤去した(#884 epic、ADR 0076 §3)ため、投入の入口と監視画面は別タブに分かれている。

- **投入入口(作成)**: 「アノテ」タブ(`AnnotateTabWidget`)。ステージング集合とモデルピッカー(`batch_model_selection`)で対象画像とモデルを選び、実行バーの「詳細設定 ▸」から開く `RunSettingsDialog` で **送信方式(`dispatch_mode`)** を `sync`(同期実行)か `batch_api`(非同期 Provider Batch API へ送信)から選ぶ。`batch_api` ではバッチ対応モデルのみが許可され、非対応モデルが混在すると拒否される(部分送信は行わない、ADR 0076 §2)。実行ボタンで送信すると、モデル 1 台につき 1 件の `provider_batch_jobs` 行が作成される。
- **監視(専用)**: 「ジョブ」タブ(`JobsTabWidget`、メインウィンドウのタブペインに「ジョブ」として配置)。内部は `ProviderBatchJobWidget` で構成され、**作成入口(投入フォーム、モデルピッカー、ステージング)を持たない監視専用ビュー**である。タブを開くたびにジョブ一覧を自動で再読み込みする。

### ジョブタブの操作

1. 「ジョブ」タブを開くと、Jobs テーブルにジョブ一覧が自動で表示される。
2. Jobs テーブルで対象行を選択すると、Detail 領域と Items 領域が自動で更新される。
3. **`状態を確認`** ボタン(`buttonRefreshStatus`)でプロバイダーに問い合わせ、ステータスを更新する。
4. **`キャンセル`** ボタン(`buttonCancel`)で対象ジョブのキャンセルを要求する(キャンセル可能なステータスでのみ有効)。
5. Jobs テーブルの右クリックコンテキストメニューから **`結果を取得`** または **`結果を取り込み`** を実行する(ADR 0041 §7 の事故復旧系操作)。
6. Items テーブル上のステータスコンボボックスで、`all`、`failed`、`expired`、`canceled` の絞り込みができる。

### 画面構成

- **Jobs 領域**: ID、Provider、Status、Provider Status、Requests の 5 列テーブル。
- **Detail 領域**: 読み取り専用の TextEdit に、CLI と同じ 17 フィールド(`id`、`provider`、`provider_job_id`、`status`、`provider_status`、`endpoint`、`model_id`、`request_count`、`succeeded_count`、`failed_count`、`canceled_count`、`expired_count`、`submitted_at`、`completed_at`、`canceled_at`、`expires_at`、`imported_at`)を表示する。
- **Items 領域**: Custom ID、Image ID、Status、Error Type、Error Message の 5 列テーブルと、上部のステータスフィルタコンボボックス(`all`、`failed`、`expired`、`canceled`)。

### 現状の制限事項

- 専用のワーカーはなく、`refresh`、`cancel`、`fetch`、`import` は GUI スレッド上で同期実行される。数百件規模のジョブでは取り込み中に短時間 GUI がブロックする可能性がある。
- Jobs テーブルには `submitted_at`、`completed_at`、`imported_at` の列を表示していない。これらは下部の Detail 領域で確認する。
- Google は「アノテ」タブのモデルピッカーでバッチ対象から黙って除外される。

### 「Batch APIインポート」メニュー操作との混同に注意

GUI のメニューには別途 **「Batch APIインポート」** という項目がある。これはレガシー手動 OpenAI JSONL 取り込み(「[レガシー手動 OpenAI JSONL 取り込みとの違い](#レガシー手動-openai-jsonl-取り込みとの違い)」を参照)であり、Provider Batch ジョブキューとは別の機能である(`JobsTabWidget.start_batch_import()` スロット経由でジョブタブ内のインポートフローへ委譲される)。

## ステータスマッピングと再実行方針

LoRAIro はプロバイダー固有のステータスを共通ステータスへ正規化して DB と UI に表示する。生のステータス文字列も `provider_status` カラムにそのまま保持するため、デバッグ時はあわせて参照する。

### 共通ステータス

| ステータス | 意味 | 主な対応 |
|---|---|---|
| `draft` | ローカルジョブ作成中 | 投入前の状態として扱う |
| `submitted` | プロバイダーへ投入済み | 状態更新を待つ |
| `validating` | プロバイダーがリクエストを検証中 | 検証失敗に備えて状態を確認する |
| `running` | プロバイダーが処理中 | 完了、失敗、期限切れ、キャンセルを待つ |
| `completed` | 結果が取得可能 | 保持期限内に結果を取得する |
| `failed` | ジョブが失敗 | エラーを確認し、条件を修正して新しいジョブを作る |
| `canceling` | キャンセル要求を処理中 | 更新して `canceled` / `completed` / `failed` を確認する |
| `canceled` | キャンセル済み | 未処理項目は必要に応じて新しいジョブで再実行する |
| `expired` | 24 時間ウィンドウ等で期限切れ | 期限切れ項目を新しいジョブで再実行する |
| `imported` | LoRAIro DB へ取り込み済み | 二重取り込みは不可 |

### 状態遷移

```
draft       → submitted, validating, running, completed, failed, canceling, canceled, expired
submitted   → validating, running, completed, failed, canceling, canceled, expired
validating  → running, completed, failed, canceling, canceled, expired
running     → completed, failed, canceling, canceled, expired
canceling   → completed, canceled, failed
completed   → imported
failed, canceled, expired, imported  → terminal (遷移不可)
```

### 項目単位の扱い

- **succeeded**: `batch import` によってアノテーション保存経路へ保存される。
- **failed**: `error_type` と `error_message` を確認し、入力やモデル条件を修正して別ジョブで再実行する。
- **expired**: プロバイダーが処理しなかったリクエストとして扱い、必要なら新しいジョブに含める。
- **canceled**: キャンセルにより処理されなかったリクエストとして扱い、必要なら新しいジョブに含める。

### 再実行(retry)方針

Provider Batch API の再実行では**既存のジョブを変更しない**。LoRAIro は自動再実行を行わず、未解決の項目を運用者が選び直し、新しいジョブとして投入する。なお、レガシーの `error_records.retry_count` カラムは削除済みである(マイグレーション `b4c5d6e7f8a9_drop_error_records_retry_count.py`)。

### 二重取り込み防止

`ProviderBatchWorkflowService.import_results` は実行前に以下の条件を確認する。

- `job.status == "imported"` の場合は拒否する(`Provider batch job は import 済みです`)。
- `job.imported_at IS NOT NULL` の場合も拒否する。

一度取り込んだジョブは再取り込みできない。やり直したい場合は新しいジョブとして投入し直す。

## 成果物(Artifact)の保存

`batch fetch` および `batch import` で取得した成果物は LoRAIro のローカル環境へ保存される。

### 保存先

- 設定キー: `config/lorairo.toml` の `[directories] batch_results_dir`
- 既定値: `"batch_results"`(相対パスであり、カレントディレクトリ基準で解決される)
- CLI で `--output-dir <path>` を指定した場合はそちらが優先される。
- 成果物のパスは `provider_batch_artifacts.local_path` に絶対パスまたは相対パスとして保存される。

### 成果物の種別

- `input`: プロバイダーへ送信したリクエスト成果物(OpenAI Batch では JSONL アップロードファイル。Anthropic では不要)。
- `output`: プロバイダーから受信した結果成果物(OpenAI Batch では出力 JSONL。Anthropic はストリーム返却のためファイルは生成されない)。
- `error`: プロバイダーが報告したエラー成果物。

各成果物レコードには、整合性検証用の `sha256` と、OpenAI のアップロードファイル ID などを表す `provider_file_id` を保存する。

### 自動削除

LoRAIro 側には成果物の自動削除や TTL 管理の仕組みがない。運用者が定期的に `[directories] batch_results_dir` 配下を手動で削除する責務を持つ。プロバイダー側の保持期間は各社のポリシーに従う(Anthropic は 29 日、OpenAI は公式ドキュメントを参照)。

## プライバシーと保持期間

Provider Batch API ではリクエストと結果の成果物がプロバイダー側にも保持されるため、LoRAIro のローカル DB や成果物の保存方針だけではデータ保持管理を完結できない。

### 運用ルール

- 利用前に OpenAI および Anthropic の最新のデータ保持ポリシーを確認する。
- Anthropic Message Batches は **Zero Data Retention 対象外** として扱う。
- 完了したジョブはプロバイダーの保持期限内に結果を取得する(Anthropic は 29 日)。
- 取得済みの成果物は LoRAIro のローカルプロジェクトデータとして扱い、通常のバックアップおよび削除ポリシーに従う。
- 秘密情報や外部送信できない画像をバッチ投入しない。

### プロバイダーの生 JSON が DB に残る点への注意

**重要**: 以下の 3 カラムにはプロバイダーの生 JSON が保存される。SQLite ファイル(`lorairo_data/<project_dir>/image_database.db`)をバックアップまたは共有する際は、含まれる内容を確認する必要がある。プロジェクト DB のファイル名は `image_database.db` で固定されており、`ProjectManagementService.create_project()` および `ServiceContainer.set_active_project()` が連携先として使用する。

| カラム | スコープ | 内容 |
|---|---|---|
| `provider_batch_jobs.raw_provider_payload` | ジョブ単位 | submit、status、fetch 各時点のプロバイダー生 JSON |
| `provider_batch_items.raw_request` | 項目単位 | 各リクエストのシリアライズ済みペイロード(ライブラリが返した値を apply 時に保存) |
| `provider_batch_items.raw_response` | 項目単位 | 各レスポンスのシリアライズ済みペイロード(`apply_result_items` で書き込み) |

`ProviderBatchWorkflowService` の `apply_result_items` は、`fetch` や `import` で得た各 `BatchResultItem.raw_response` を JSON 文字列として `provider_batch_items.raw_response` に保存する。同様に `raw_request` もライブラリ側で生成された値が保存されるため、個別画像のプロンプトとレスポンス内容が DB に残る。

ADR 0038 §6 Notes では当初「プロバイダーの生ペイロード、リクエスト、レスポンス JSON は LoRAIro DB の安定スキーマには保存しない」としていたが、実装ではデバッグおよび再処理用途で保存している(詳細は「[ADR と実装の差分](#adr-と実装の差分)」を参照)。

## レガシー手動 OpenAI JSONL 取り込みとの違い

`lorairo-cli annotate import-batch` と GUI の **「Batch APIインポート」** メニューは、手動で取得済みの OpenAI Batch API 結果 JSONL を LoRAIro へ取り込むレガシー機能である。新しい Provider Batch ジョブキュー(`lorairo-cli batch ...` および GUI のジョブタブ)とは独立した別経路として共存している。

| 観点 | `lorairo-cli annotate import-batch`(レガシー) | `lorairo-cli batch import`(新規) |
|---|---|---|
| 入力 | OpenAI Batch API の出力 JSONL ファイル | DB に登録された `provider_batch_jobs` のジョブ ID |
| ジョブ投入・状態管理 | 行わない | 行う |
| `provider_batch_*` テーブル書き込み | 行わない | 行う |
| `custom_id` の照合 | JSONL の `custom_id` を画像 stem や DB から逆引き | `img-{image_id}` を SSoT として照合 |
| レスポンスのパース | LoRAIro 側の `BatchContentParser` | `image-annotator-lib` 側 |
| 使い分け | すでに手動ダウンロード済みの古い JSONL がある場合 | 新規のジョブ投入および管理 |

新規運用では Provider Batch ジョブキュー(`lorairo-cli batch` または GUI のジョブタブ)を使用する。

## ADR と実装の差分

ADR 0038 ドラフト時点と現在の実装には以下の差分がある。本ガイドは現在の実装を基準に記述しており、ADR 0038 本体は過去の意思決定記録として保持されている。差分の解消は将来の ADR 改訂または別 Issue で扱う。

| 項目 | ADR 0038 ドラフト | 現状の実装 |
|---|---|---|
| `provider_batch_jobs.description` | ドラフトスキーマに存在 | カラム未追加(引数のみで永続化されない) |
| `provider_batch_jobs.prompt_profile` | ドラフトスキーマに存在 | カラム未追加(引数のみで永続化されない) |
| `provider_batch_jobs.raw_provider_payload` | 保存しない(§6 Notes) | Text カラムで保存 |
| `provider_batch_items.task_type` | ドラフトに記載なし | NOT NULL カラムあり |
| `provider_batch_items.raw_request` / `raw_response` | ドラフトに記載なし | Text カラムあり |
| `BatchFetchResult.artifacts` フィールド | ドラフトに存在 | ライブラリ型に存在しない(LoRAIro 側のみ保持) |
| `fetch_batch_results(destination_dir)` 引数 | ライブラリ API として宣言 | Anthropic アダプターは引数を無視 |
| `list_batch_capable_models()` の対象 | 直接プロバイダー全般 | Anthropic と OpenAI のレーティング対応モデル |
| OpenAI アダプター(Phase 1 MVP) | 最初に実装予定 | Moderations Batch のみ対応。アノテーション生成バッチは未対応 |

## 関連ドキュメント

- ADR: [docs/decisions/0038-provider-batch-api-integration-strategy.md](decisions/0038-provider-batch-api-integration-strategy.md)
- 同期推論境界: [docs/decisions/0023-pydanticai-litellm-webapi-inference-boundary.md](decisions/0023-pydanticai-litellm-webapi-inference-boundary.md)
- 同期 AnnotationWorker 契約: [docs/decisions/0033-annotation-worker-batch-execution-contract.md](decisions/0033-annotation-worker-batch-execution-contract.md)
- Service 一覧: [docs/services.md](services.md)(`ProviderBatchJobService`、`ProviderBatchWorkflowService`、`BatchImportService`)
- CLI 全体: [docs/cli.md](cli.md)
- AI 統合: [docs/integrations.md](integrations.md)
- 関連 Issue / PR: LoRAIro #395 / #458 / #463 / #466 / #483、PR #495 / #498 / #499、image-annotator-lib #102 / #103 / #116 / #117
