# Provider Batch API 利用条件と運用ガイド

このガイドは、大量画像アノテーションを Provider Batch API で実行するかどうかを判断し、
LoRAIro で job 投入、確認、キャンセル、取得、import を運用する手順をまとめる。

対象は **OpenAI direct route** と **Anthropic direct route** のみ。Google Vertex AI / OpenRouter は
このガイドの Provider Batch API 対象外として扱う。

設計方針は [ADR 0038](decisions/0038-provider-batch-api-integration-strategy.md) を参照。
Provider の公式仕様は必要に応じて以下を確認する。

- OpenAI Batch API: https://platform.openai.com/docs/guides/batch
- Anthropic Message Batches API: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing

## 実装ステータス

ADR 0038 の段階導入計画と現状実装の対応関係。Provider Batch API は CLI / GUI / Service / DB 層は
provider 横断で実装済みである。image-annotator-lib 側 provider adapter は Anthropic Message Batches
と OpenAI Moderations Batch に対応している。OpenAI の通常 annotation 生成 batch
(`/v1/responses` / `/v1/chat/completions`) と Google は未実装である。

| Provider | LoRAIro 側 (CLI/GUI/Service/DB) | image-annotator-lib adapter | 現時点で実用できるか |
|---|---|---|---|
| Anthropic direct | 完全実装 | **完全実装** (Message Batches) | はい |
| OpenAI direct | rating preflight 実装 | **Moderations Batch のみ実装** (`/v1/moderations`) | はい。`task_type=rating_preflight` のみ |
| Google Vertex AI | submit を **拒否** (CLI/GUI) | 未実装 | いいえ (ADR 0038 Phase 3) |
| OpenRouter route | submit を **拒否** (CLI/GUI) | 対象外 | いいえ (ADR 0038 non-goal) |

関連 PR / Issue:

- LoRAIro #463 / PR #499: Provider Batch job 管理 CLI (`lorairo-cli batch ...`)
- LoRAIro #483 / PR #498: Provider Batch job 管理 GUI (`ProviderBatchJobWidget`、Provider Batch tab)
- LoRAIro PR #495: image-annotator-lib batch contract 整合
- LoRAIro #505: OpenAI Moderations Batch を `rating_preflight` として Provider Batch workflow に接続
- image-annotator-lib #102 / #103: Anthropic Message Batches adapter 移管・実装
- image-annotator-lib #116 / #117: WebAPI 配下への移管、compat test

## 使うべきケース

Provider Batch API は、今すぐ画面に結果を返す必要がない大量処理向けの非同期 job queue である。
同期 annotation の「開始して進捗バーを見ながら完了を待つ」処理とは別物として扱う。

使うべきケース:

- 数百から数万件の画像をまとめてアノテーションしたい
- 完了まで数十分から 24 時間程度待てる
- 通常の同期 API より cost discount と高い batch 用 rate limit を優先したい
- provider 側に request / result artifact が一定期間保存されることを許容できる
- **Anthropic direct route の API key を持っている**、または OpenAI Moderations Batch を
  rating preflight として使うための OpenAI API key を持っている

避けるべきケース:

- 少数画像を確認しながらすぐ結果を見たい
- GUI の progress dialog で逐次進捗を見たい
- OpenRouter 経由の provider routing / fallback だけを使っている
- Google Vertex AI の GCS / BigQuery / project / region / IAM 設定を使う batch inference を実行したい
- provider 側 retention / privacy policy により画像や prompt の一時保存を許容できない
- Zero Data Retention が必要 (Anthropic Message Batches は ZDR 対象外)

## 対象 provider

### Anthropic direct route

Anthropic Message Batches API は、`custom_id` 付き Messages requests を非同期処理し、batch status と
results stream を取得する方式である。Anthropic 公式 docs では、50% pricing、24h expiration、
batch results の 29 日 availability、Zero Data Retention 対象外であることが説明されている。

LoRAIro での setup checklist:

- [ ] Anthropic direct route の API key が `config/lorairo.toml` の `[api] claude_key` に設定されている
      (`ConfigurationService.get_api_keys()` は `[api]` セクションのみ参照する。`ANTHROPIC_API_KEY` 等の
      環境変数は Provider Batch submit には使われない)
- [ ] 対象 model が `lorairo-cli models list` で active 表示され、`discontinued_at` が null である
- [ ] image-annotator-lib の `list_batch_capable_models()` で Anthropic batch eligible として返る
- [ ] 24h expiration と results availability 期限 (29 日) 内に results を取得する運用になっている
- [ ] Zero Data Retention が必要な workflow ではない

Provider 制約 (Anthropic 公式):

- 1 batch あたり最大 **100,000** Message requests または **256 MB** body のいずれか先に到達した方
- 24 時間以内に処理されなかった item は **expired** として扱う
- results は 29 日間 provider 側で取得可能、その後は失われる
- Vision / tool use / system messages / multi-turn / beta features を batch 可能

LoRAIro 経由の追加制約 (image-annotator-lib の Anthropic adapter):

- **1 batch あたり最大 500 items** (lib 側 `_MAX_LIBRARY_ITEMS = 500` で enforce)
- `Batch contains N items; maximum is 500` で submit 拒否される
- 大量画像を投入する場合は LoRAIro 側で分割し、複数 job として submit する

### OpenAI direct route (Moderations rating preflight)

OpenAI direct route は、annotation API 投入前の safety / rating preflight 用に
`/v1/moderations` endpoint の Batch API を使う。LoRAIro は `provider_batch_items.task_type` に
`rating_preflight` を保存し、image-annotator-lib が Moderations response を
`RatingPrediction` / `UnifiedAnnotationResult.ratings` に正規化する。LoRAIro 側では OpenAI JSONL
artifact を直接 parse せず、既存 `ratings` table へ import する。

OpenAI Moderations Batch の setup checklist:

- [ ] OpenAI direct route の API key が `config/lorairo.toml` の `[api] openai_key` で設定されている
- [ ] `openai/omni-moderation-latest` などの rating model が `lorairo-cli models list` に存在する
- [ ] submit 時に `--task-type rating_preflight` を指定する
- [ ] endpoint は `/v1/moderations` を使う (override する場合も同 endpoint のみ)
- [ ] LoRAIro DB 上で対象 model が discontinued ではない
- [ ] job が 1 provider x 1 model x 1 endpoint x 1 prompt profile になるよう対象を分けている
- [ ] completed 後、OpenAI 側 retention 期限内に results を取得する運用になっている

Provider 制約 (公式仕様):

- Batch API の supported endpoint に `/v1/moderations` が含まれる
- input file は `purpose=batch` の JSONL。各行は `custom_id` / `method=POST` / `url=/v1/moderations` /
  `body` を持ち、`body.model` と `body.input` を指定する
- 1 batch あたり 50,000 requests / 200 MB JSONL file 以下
- 24h completion window、同期 API 比 50% discount
- `/v1/responses` / `/v1/chat/completions` 等の OpenAI annotation generation batch は LoRAIro では未対応
- streaming 非対応、画像入力は対応

### 対象外 provider

#### Google Vertex AI Gemini

Google Vertex AI Gemini batch inference は、Cloud Storage / BigQuery、Google Cloud project、region、
IAM / credential 設定を前提にするため、ADR 0038 Phase 3 として後回しになっている。
2026-05-27 時点で CLI / GUI / lib いずれも実装されていない。

`lorairo-cli batch submit --provider google` または model 解決で `google` が推定された場合、
CLI は中央エラー境界 (ADR 0057 §7) で構造化 `error` 行として abort する。`--json` 時は stdout に
`kind=error` の 1 行が出る (入力が不正なため `code=INVALID_INPUT` 相当、exit code 2)。message には
`Google Provider Batch submit is disabled until Phase 3.` 相当の内容が入る。

GUI 側では combo box の候補から silent excluded される (「not configured」表示は出ない)。

#### OpenRouter route

OpenRouter は同期 inference route として扱う。OpenRouter が内部で OpenAI / Anthropic / Google に
route できても、LoRAIro が provider-native batch job id、status、cancel、result artifact lifecycle、
discount、retention を直接管理できることとは別問題である。したがって OpenRouter 経由 model は
Provider Batch job 作成候補に表示しない。

`openrouter/...` prefix の litellm model ID で submit を試みると、CLI は中央エラー境界で構造化
`error` 行として abort する。`--json` 時は stdout に `kind=error` の 1 行が出る (入力が不正なため
`code=INVALID_INPUT` 相当、exit code 2)。message には
`Could not infer a direct Provider Batch provider for 'openrouter/...'. Use a direct openai/... or anthropic/... model.`
相当の内容が入る。

## LoRAIro と image-annotator-lib の責務境界

Provider Batch API は LoRAIro の同期 `AnnotationWorker` には統合しない。永続化された job queue として
扱い、アプリ再起動後も status refresh / results fetch / import を続けられる。

| 責務 | 担当 | 補足 |
|---|---|---|
| `custom_id = img-{image_id}` 生成 | LoRAIro | `ProviderBatchJobService.build_custom_id` で SSoT |
| DB job / item / artifact 永続化 | LoRAIro | `provider_batch_jobs` 等 3 テーブル |
| Stored image path の提供 | LoRAIro | `BatchSubmitItem.image_path` には `images.stored_image_path` (DB 上の保存画像、original) を渡す。MVP で resized 派生は使わない |
| MIME 判定 / base64 / data URL 化 | image-annotator-lib | provider 固有 image payload は lib 内 |
| provider 固有 request payload 構築 | image-annotator-lib | OpenAI/Anthropic 形式差を吸収 |
| HTTP submit / retrieve / cancel / fetch | image-annotator-lib | SDK 例外を `BatchJobError` に翻訳 |
| Response parse と normalized result 生成 | image-annotator-lib | `UnifiedAnnotationResult` で返す |
| Status 共通語彙への正規化 | LoRAIro Service | `ProviderBatchJobService.normalize_status` |
| Job lifecycle UI (queue / refresh / cancel / import) | LoRAIro | CLI + GUI |
| Normalized result → annotation save | LoRAIro | `AnnotationSaveService` 経由 |
| API key 受け渡し | LoRAIro → lib (引数渡し、`os.environ` 非汚染) | `BatchSubmitRequest.api_keys` |

LoRAIro は provider 生 payload / response を user workflow として扱わない。output / error file を
手動解析する運用も前提にしない。

ただし運用上の事実として、`provider_batch_jobs.raw_provider_payload` (job 単位) と
`provider_batch_items.raw_request` / `raw_response` (item 単位) の 3 カラムに provider 生 JSON が
保存される (privacy 注意点、§ Privacy / retention を参照)。

## CLI 運用

`lorairo-cli batch` は同期 annotation の `annotate run` とは別の top-level command group として
job lifecycle を操作する。subcommand 一覧:

| 操作 | 目的 |
|---|---|
| `submit` | 対象画像、provider、model、endpoint、prompt profile を指定して provider batch job を作成する |
| `list` | DB に永続化された provider batch jobs を一覧する |
| `status` | provider から最新 status と counts を取得し、DB job state を更新する (refresh 込み) |
| `cancel` | 実行中 job の cancel を provider に要求する |
| `fetch` | completed job の result artifacts / normalized results を取得する |
| `import` | fetch 済み normalized results を LoRAIro の annotation save path へ保存する |

注意: 既存 `lorairo-cli annotate import-batch` は **別経路の legacy/manual import** (§ Legacy/manual
OpenAI JSONL import との違い を参照)。

### batch submit — job 投入

**構文**:

```bash
lorairo-cli batch submit --project <name> --model <id_or_name> \
  --image-id <id> [--image-id <id> ...] \
  [--provider {openai,anthropic}] [--endpoint <path>] \
  [--prompt-profile <name>] [--description <text>]
```

**オプション**:

- `--project <name>` / `-p <name>`: 対象プロジェクト (必須)
- `--model <id>` / `-m <id>`: LiteLLM model ID (例: `anthropic/claude-3-5-sonnet-20240620`)
  または DB 上の一意な display name (必須)
- `--image-id <id>`: 投入する image ID (必須、複数指定可)
- `--provider`: provider 推定を override (`openai` または `anthropic`、optional)
- `--endpoint <path>`: provider endpoint を override (default: `openai`→`/v1/chat/completions`、
  `anthropic`→`/v1/messages`)
- `--prompt-profile <name>`: prompt profile 名 (default: `default`)
- `--description <text>`: provider job description (optional)

**例 (Anthropic、現在の実用パス)**:

```bash
uv run lorairo-cli batch submit \
  --project my_dataset \
  --model anthropic/claude-3-5-sonnet-20240620 \
  --image-id 101 --image-id 102 --image-id 103 \
  --prompt-profile default \
  --description "Test batch 2026-05-27"
```

**例 (OpenAI、lib adapter 完了まで失敗する)**:

```bash
uv run lorairo-cli batch submit \
  --project my_dataset \
  --model openai/gpt-4o-mini \
  --image-id 101 --image-id 102
# → 構造化 error 行で abort (message 例: Unsupported Provider Batch provider 'openai'.、現状の lib dispatch)
```

**出力例 (成功時)**:

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

**エラーケース** (ADR 0057 の中央エラー境界経由で構造化 `error` 行として出る。`--json` 時は stdout に
`kind=error` の 1 行、exit code は ADR 0057 §6 マップで決まる):

- API key 未設定 / 不正: submit 時に構造化 error 行 (`code=AUTH_ERROR`、`retryable=false` /
  `user_action_required=true`、exit code 1)。事前 gate は無いため、失敗してから初めて表示される
- 未知の model: model 解決は `click.UsageError` で reject されるため `code=INVALID_INPUT` (exit code 2)。
  message には `Unknown model '<id>'. Run \`lorairo-cli models list\`.` 相当が入る
- discontinued model (`models.discontinued_at IS NOT NULL`): **事前 gate されない**。`_resolve_model()`
  は `get_model_by_litellm_id()` を呼ぶだけで `discontinued_at` をチェックしないため、有効な
  LiteLLM ID であれば DB ヒットして submit 経路に進む。その後 lib / provider 境界で失敗する可能性が
  ある。ADR 0038 は eligibility gate を要求しているが CLI 側は現状未実装
- 同名 model が複数: 構造化 error 行 (入力不正のため `code=INVALID_INPUT` 相当)。message には
  `Ambiguous model '<id>': - <litellm_id> (provider: <p>) ...` 相当が入る
- Google: 構造化 error 行 (入力不正のため `code=INVALID_INPUT` 相当、exit code 2)。message は
  `Google Provider Batch submit is disabled until Phase 3.` 相当
- OpenRouter: 構造化 error 行 (入力不正のため `code=INVALID_INPUT` 相当、exit code 2)。message は
  `Could not infer a direct Provider Batch provider for ...` 相当
- 想定外例外: 構造化 error 行 (`code=INTERNAL_ERROR`、exit code 1) で `logs/lorairo.log` に stacktrace

### batch list — job 一覧

**構文**:

```bash
lorairo-cli batch list --project <name> [--provider <name>] [--status <name>] \
  [--limit N] [--offset N]
```

**オプション**:

- `--project <name>` / `-p <name>`: 対象プロジェクト (必須)
- `--provider <name>`: provider で絞り込み
- `--status <name>`: 共通 status で絞り込み (§ Status mapping と retry の 10 種から)
- `--limit N`: 最大行数 (1-1000、default 100)
- `--offset N`: スキップ数 (≥0、default 0)

**例**:

```bash
uv run lorairo-cli batch list --project my_dataset
uv run lorairo-cli batch list --project my_dataset --provider anthropic --status running
uv run lorairo-cli batch list --project my_dataset --limit 20 --offset 40
```

**出力**: Rich Table (5 列: ID / Provider / Status / Provider Status / Requests / Created)。

### batch status — 状態確認

**構文**:

```bash
lorairo-cli batch status <job_id> --project <name> [--refresh | --no-refresh]
```

**オプション**:

- `job_id`: 対象 job ID (必須、positional)
- `--project <name>` / `-p <name>`: 対象プロジェクト (必須)
- `--refresh` / `--no-refresh`: provider に最新 status を問い合わせるか (default: `--refresh`)

**例**:

```bash
# Provider に問い合わせて DB を更新してから表示
uv run lorairo-cli batch status 42 --project my_dataset

# DB の値のみを表示 (provider に問い合わせない)
uv run lorairo-cli batch status 42 --project my_dataset --no-refresh
```

**出力**: 17 行の縦型 Rich Table (id / provider / provider_job_id / status / provider_status /
endpoint / model_id / request_count / succeeded_count / failed_count / canceled_count /
expired_count / submitted_at / completed_at / canceled_at / expires_at / imported_at)。

### batch cancel — キャンセル

**構文**:

```bash
lorairo-cli batch cancel <job_id> --project <name>
```

**動作**:

- provider に cancel 要求を送る
- DB job status は `canceling` に遷移
- provider 完了確認後、後続の `status` / `refresh` で `canceled` に正規化される

### batch fetch — 結果取得

**構文**:

```bash
lorairo-cli batch fetch <job_id> --project <name> [--output-dir <path>]
```

**オプション**:

- `--output-dir <path>` / `-o <path>`: artifact 出力ディレクトリ (default は
  `config/lorairo.toml` の `[directories] batch_results_dir`、default `batch_results/`)

**動作**:

- normalized batch results と artifact を取得して DB の `provider_batch_items` を更新する
- ただし annotation save path には書き込まない (それは `import`)
- Anthropic は results を stream で返すため artifact file は生成されない (`destination_dir` 引数は
  Anthropic では無視される)

### batch import — annotation 保存

**構文**:

```bash
lorairo-cli batch import <job_id> --project <name> [--output-dir <path>]
```

**動作**:

- **常に provider に再リクエストして fetch を実行する** (CLI からは `fetch_result` 引数を渡せないため、
  `ProviderBatchWorkflowService.import_results` 内の `else self.fetch_results(...)` 分岐が必ず走る)
- 直前に `batch fetch` を実行していても、再度 provider にアクセスする
- そのため **provider retention 期限を過ぎた job は import できない**。Anthropic の場合 results 29 日、
  expiration 後は `batch import` も失敗する。fetch と import は短時間で連続実行する運用にする
- normalized result item を `custom_id = img-{image_id}` 基準で annotation save path に投入
- 全 item の保存が成功した場合のみ job status を `imported` に遷移し、`imported_at` を記録
- 既に `imported` または `imported_at IS NOT NULL` の job は **再 import 不可** (構造化 error 行で reject)。
  reject は `ProviderBatchError` (`RuntimeError` 派生) で raise され、`classify_exception` に専用マッピングが
  無いため現状は `code=INTERNAL_ERROR` (exit code 1、stderr に traceback) になる。message は
  `Provider batch job は import 済みです: job_id=<id>` 相当 (状態衝突を表す専用コード `CONFLICT` への割当ては未対応)

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

### Exit code

ADR 0057 §6 で exit code は中央エラー境界が error コードから機械的に導出する (旧 ADR 0038 draft では
「exit 2 = 想定外例外」だったが、ADR 0057 で **反転** した。現在 exit 2 は入力・検証エラー専用)。

| exit | 意味 | 該当エラーコード |
|---|---|---|
| `0` | 成功 | — |
| `2` | 入力・検証 | `INVALID_INPUT` / `VALIDATION_FAILED` / `RESULT_SET_TOO_LARGE` |
| `1` | 上記以外すべて (実行時) | `AUTH_ERROR` / `NOT_FOUND` / `CONFLICT` / `NETWORK_ERROR` / `INTERNAL_ERROR` 等 |

batch コマンドのエラーへの当てはめ:

- google submit reject / OpenRouter infer 失敗 / ambiguous model / unknown model は model 解決ロジックが
  `click.UsageError` で raise するため、中央境界で `INVALID_INPUT` → exit 2 に統一される
- API key 未設定 / 不正は `AUTH_ERROR` → exit 1
- 想定外例外 (`INTERNAL_ERROR`) は **exit 1** で `logs/lorairo.log` に stacktrace
  (旧 exit 2 から変更)
- `ProjectNotFoundError` (`--project` で存在しない project を指定) は対象不在のため `NOT_FOUND` 相当 →
  exit 1 (旧記述の exit 2 は ADR 0057 で無効になった)

旧実装の散在 `except ProviderBatchError → Exit(1)` / `except Exception → Exit(2)` は撤廃され、
全コマンドが中央境界 (`cli.main:main`) でエラーコード → exit code を導出する (ADR 0057 §7)。

## GUI 運用

`lorairo` GUI のメインウィンドウ上部 tab pane に **「Provider Batch」** tab (左から 3 つ目、index 2)
として `ProviderBatchJobWidget` が組み込まれる。同期 annotation の progress dialog とは独立した
job queue UI である。

### 基本手順

1. GUI を起動し、**「Provider Batch」** tab を選択する
2. **`Refresh Models`** ボタンで Model コンボボックスに batch eligible な direct provider model を読み込む
   - 読み込まれるのは `image-annotator-lib.list_batch_capable_models()` が返す model のうち、
     provider が `openai` または `anthropic` のもの (現時点では Anthropic のみ実装、OpenAI は lib adapter 完了後)
   - OpenRouter route と Google は silent excluded
3. 投入する model を選択する
4. **`Use Selected`** ボタンでワークスペースタブの選択画像 ID を `Image IDs` 欄に流し込む
   または `1, 2, 3` 形式で手入力する
5. **`Prompt`** (default `default`) と **`Description`** (optional) を入力する
6. **`Submit`** ボタンを押す
   - 成功すると Jobs テーブルに新規行が追加される
7. Jobs テーブルで対象行を選択すると Detail / Items 領域が自動更新される
8. **`Refresh Status`** で provider に問い合わせて status を更新、**`Cancel`** / **`Fetch`** / **`Import`**
   で各段階を進める
9. Items テーブル上の Status コンボボックスで `failed` / `expired` / `canceled` のみを抽出できる

### Submit 領域 (左カラム)

| ラベル | 種別 | 説明 |
|---|---|---|
| Model | QComboBox | `provider: litellm_model_id` 形式で表示 |
| Image IDs | QLineEdit | placeholder `1, 2, 3`、スペース/カンマ区切りで複数 ID |
| Prompt | QLineEdit | default `default` |
| Description | QLineEdit | 任意、空文字可 |
| Use Selected | QPushButton | ワークスペース選択画像 ID を流し込む |
| Refresh Models | QPushButton | batch eligible model を再取得 |
| Submit | QPushButton | job 投入 |

`endpoint` は UI に出さず、選択 model の provider に応じて固定 (`/v1/chat/completions` か
`/v1/messages`)。

### Jobs 領域 (右上)

5 列 Rich-like テーブル: **ID / Provider / Status / Provider Status / Requests**。

操作ボタン: **Refresh** (DB 一覧再取得) / **Refresh Status** (provider 問い合わせ) /
**Cancel** / **Fetch** / **Import**。

### Detail / Items 領域 (右下)

- **Detail**: read-only TextEdit に CLI と同じ 17 フィールド (id / provider / provider_job_id /
  status / provider_status / endpoint / model_id / request_count / succeeded_count / failed_count /
  canceled_count / expired_count / submitted_at / completed_at / canceled_at / expires_at /
  imported_at)
- **Items**: 5 列テーブル (Custom ID / Image ID / Status / Error Type / Error Message) と上部
  status filter combo box (`all` / `failed` / `expired` / `canceled`)

### 制限事項 (現状)

- 専用 Worker は無く、`submit` / `refresh` / `fetch` / `import` は GUI thread で同期実行される。
  数百件規模の job では submit / import 中に短時間 GUI がブロックする可能性がある
- Jobs テーブルには `submitted_at` / `completed_at` / `imported_at` を列として表示していない。
  これらは下の Detail 領域でのみ確認できる
- Google は GUI から silent excluded、「not configured」表示は出ない
- メニューバー / ツールバーからの専用エントリは無く、tab pane 経由でのみアクセスする

### 「Batch APIインポート」menu action との混同に注意

GUI のメニューに別途 **「Batch APIインポート」** という menu action があるが、これは legacy/manual
OpenAI JSONL import (§ Legacy/manual OpenAI JSONL import との違い 参照) のため、Provider Batch
job queue とは関係しない別機能である。

## Status mapping と retry

LoRAIro は provider 固有 status を共通 status に正規化して DB と UI に表示する。生 status は
`provider_status` カラムに raw 文字列で残るため、デバッグ時はそちらも参照する。

### 共通 status

| Status | 意味 | 主な対応 |
|---|---|---|
| `draft` | local job 作成中 | submit 前の状態として扱う |
| `submitted` | provider に投入済み | status refresh を待つ |
| `validating` | provider が request を検証中 | validation failure に備えて status を確認する |
| `running` | provider が処理中 | 完了、失敗、期限切れ、cancel を待つ |
| `completed` | provider results が取得可能 | retention 期限内に results を取得する |
| `failed` | provider job が失敗 | error を確認し、request 条件を修正して新しい job を作る |
| `canceling` | cancel 要求処理中 | refresh して canceled / completed / failed を確認する |
| `canceled` | cancel 済み | 未処理 item は必要に応じて新しい job で retry する |
| `expired` | 24h window 等で期限切れ | expired item を新しい job で retry する |
| `imported` | LoRAIro DB へ import 済み | 二重 import 不可 |

### Status transition

```
draft       → submitted, validating, running, completed, failed, canceling, canceled, expired
submitted   → validating, running, completed, failed, canceling, canceled, expired
validating  → running, completed, failed, canceling, canceled, expired
running     → completed, failed, canceling, canceled, expired
canceling   → completed, canceled, failed
completed   → imported
failed, canceled, expired, imported  → terminal (遷移不可)
```

### Item 単位の扱い

- **succeeded item**: `batch import` で annotation save path に保存される
- **failed item**: `error_type` / `error_message` を確認し、入力や model 条件を直して別 job で retry する
- **expired item**: provider が処理しなかった request として扱い、必要なら新しい job に入れる
- **canceled item**: cancel で送信されなかった request として扱い、必要なら新しい job に入れる

### Retry 方針

Provider Batch API の retry は **既存 job を変更しない**。LoRAIro は自動 retry を行わず、未解決
item を operator が選び直し、新しい job として submit する。legacy の `error_records.retry_count`
カラムは削除済み (migration `b4c5d6e7f8a9_drop_error_records_retry_count.py`)。

### 二重 import 防止

`ProviderBatchWorkflowService.import_results` は以下を pre-check する:

- `job.status == "imported"` → reject (`Provider batch job は import 済みです`)
- `job.imported_at IS NOT NULL` → reject

一度 import した job は再 import できない。修正したい場合は新しい job として submit し直す。

## Artifact 保存

`batch fetch` / `batch import` で取得した artifact は LoRAIro local に保存される。

### 保存先

- 設定キー: `[directories] batch_results_dir` (in `config/lorairo.toml`)
- default 値: `"batch_results"` (相対パス、cwd 基準で解決)
- CLI で `--output-dir <path>` を指定するとそちらが優先
- artifact path は `provider_batch_artifacts.local_path` に絶対 / 相対パスとして保存される

### artifact type

- `input`: provider に送った request artifact (OpenAI Batch では JSONL upload file。Anthropic は不要)
- `output`: provider から受信した result artifact (OpenAI Batch では output JSONL。Anthropic は stream で
  返すため artifact ファイルは生成されない)
- `error`: provider が報告した error artifact

各 artifact 行には `sha256` (整合性検証用) と `provider_file_id` (OpenAI uploaded file ID 等)
を保存する。

### 自動削除

LoRAIro 側に artifact 自動削除 / TTL の機構は **無い**。operator が定期的に
`[directories] batch_results_dir` 配下を手動 purge する責務になる。provider 側 retention は
provider のポリシーに従う (Anthropic は 29 日、OpenAI は公式 docs 参照)。

## Privacy / retention

Provider Batch API は provider 側に request / result artifact を保持する。LoRAIro の local DB や
artifact 保存方針だけでは retention を完結できない。

### 運用ルール

- OpenAI / Anthropic の最新 data retention policy を確認してから batch を使う
- Anthropic Message Batches は **Zero Data Retention 対象外** として扱う
- completed job は provider retention 期限内に results を取得する (Anthropic は 29 日)
- 取得済み artifacts は LoRAIro の local project data として扱い、通常の backup / purge policy に従う
- secret や公開できない画像を provider batch に投入しない

### Provider 生 JSON が DB に残ることへの注意

**重要**: 以下 3 つのカラムに provider 生 JSON が保存されるため、SQLite ファイル
(`lorairo_data/<project_dir>/image_database.db`) をバックアップ / 共有する際は内容を確認する必要がある。
project DB のファイル名は `image_database.db` 固定 (`ProjectManagementService.create_project()` および
`ServiceContainer.set_active_project()` が連携先として使用する)。

| カラム | スコープ | 内容 |
|---|---|---|
| `provider_batch_jobs.raw_provider_payload` | job 単位 | submit / status / fetch 各時点の provider raw JSON |
| `provider_batch_items.raw_request` | item 単位 | 各 request の serialize 済み payload (lib が返した値、apply 時に保存) |
| `provider_batch_items.raw_response` | item 単位 | 各 response の serialize 済み payload (`apply_result_items` で書き込まれる) |

`apply_result_items` (`ProviderBatchWorkflowService`) は fetch / import で得た各
`BatchResultItem.raw_response` を JSON-serialized 文字列として
`provider_batch_items.raw_response` に保存する。同様に `raw_request` も lib 側で生成された値が
保存される。したがって個別 image の prompt / response 内容が DB に残る。

ADR 0038 §6 Notes は当初「provider 生 payload / request / response JSON は LoRAIro DB の
stable schema には保存しない」と書いていたが、実装は debugging / re-processing 用途で保存している。
これは ADR と実装の差分 (§ ADR と実装の差分 参照)。

## Legacy/manual OpenAI JSONL import との違い

`lorairo-cli annotate import-batch` と GUI の **「Batch APIインポート」** menu action は、手動で
取得済みの OpenAI Batch API result JSONL を LoRAIro に取り込む legacy/manual import である。
新しい Provider Batch job queue (`lorairo-cli batch ...` / GUI Provider Batch tab) とは独立した
別経路として coexist する。

| 観点 | `lorairo-cli annotate import-batch` (legacy) | `lorairo-cli batch import` (新規) |
|---|---|---|
| 入力 | OpenAI Batch API output JSONL ファイル | DB に登録された `provider_batch_jobs` の job ID |
| job submit / status 管理 | しない | する |
| `provider_batch_*` テーブル書き込み | しない | する |
| `custom_id` matching | JSONL の `custom_id` を image stem や DB から逆引き | `img-{image_id}` を SSoT |
| provider response parse | LoRAIro 側 `BatchContentParser` | image-annotator-lib 側 |
| 使い分け | 既に手動 download した古い JSONL がある場合 | 新規の job 投入 / 管理 |

新規運用は Provider Batch job queue (`lorairo-cli batch` / GUI Provider Batch tab) を使う。

## ADR と実装の差分

ADR 0038 draft 時点と現在の実装には以下の差分がある。本ガイドは実装基準で書かれているが、ADR 0038
本体は historical decision として保持されている。差分の解消は将来の ADR amendment / 別 Issue で扱う。

| 項目 | ADR 0038 draft | 現状実装 |
|---|---|---|
| `provider_batch_jobs.description` | draft schema に存在 | カラム未追加 (引数のみで永続化されない) |
| `provider_batch_jobs.prompt_profile` | draft schema に存在 | カラム未追加 (引数のみで永続化されない) |
| `provider_batch_jobs.raw_provider_payload` | 「保存しない」(§6 Notes) | Text カラムで保存 |
| `provider_batch_items.task_type` | draft に無し | NOT NULL カラムあり |
| `provider_batch_items.raw_request` / `raw_response` | draft に無し | Text カラムあり |
| `BatchFetchResult.artifacts` フィールド | draft に存在 | lib 型に無し (LoRAIro 側のみ保持) |
| `fetch_batch_results(destination_dir)` 引数 | lib API として宣言 | Anthropic adapter は引数を無視 |
| `list_batch_capable_models()` の対象 | direct provider 全部 | Anthropic + OpenAI rating-capable model |
| OpenAI adapter (Phase 1 MVP) | 最初に実装 | Moderations Batch のみ対応。annotation generation batch は未対応 |

## 関連

- ADR: [docs/decisions/0038-provider-batch-api-integration-strategy.md](decisions/0038-provider-batch-api-integration-strategy.md)
- 同期 inference 境界: [docs/decisions/0023-pydanticai-litellm-webapi-inference-boundary.md](decisions/0023-pydanticai-litellm-webapi-inference-boundary.md)
- 同期 AnnotationWorker 契約: [docs/decisions/0033-annotation-worker-batch-execution-contract.md](decisions/0033-annotation-worker-batch-execution-contract.md)
- Service 一覧: [docs/services.md](services.md) (`ProviderBatchJobService` / `ProviderBatchWorkflowService` / `BatchImportService`)
- CLI 全体: [docs/cli.md](cli.md)
- AI 統合: [docs/integrations.md](integrations.md)
- 関連 Issue / PR: LoRAIro #395 / #458 / #463 / #466 / #483、PR #495 / #498 / #499、image-annotator-lib #102 / #103 / #116 / #117
