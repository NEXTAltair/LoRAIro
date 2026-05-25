# ADR 0038: Provider Batch API Integration Strategy

- **日付**: 2026-05-25
- **ステータス**: Accepted
- **関連 Issue**: #395

## Context

LoRAIro は現在、`AnnotationWorker` から `image-annotator-lib` を同期呼び出しする実行経路を持つ。
ADR 0033 はこの同期 Worker 経路の進捗・部分失敗・保存契約を定めたが、プロバイダ提供の
Batch API は別概念である。

プロバイダ Batch API は「即時応答」ではなく「ジョブ投入、後で状態確認、結果ファイル取得」の
非同期実行モデルを取る。OpenAI Batch API は JSONL request file を事前 upload し、batch object
を polling して output/error file を取得する。Anthropic Message Batches API は `custom_id` 付きの
Messages requests を作成し、batch status と results stream を取得する。Google Gemini batch
inference は Vertex AI BatchPredictionJob として Cloud Storage / BigQuery input-output を使う。

既存コードには OpenAI Batch API 結果 JSONL を取り込む `BatchImportService` / CLI / GUI entrypoint
がある。ただしこれは **結果 import** だけで、ジョブ投入・状態管理・キャンセル・polling・DB job
管理は未実装である。

### 公式仕様確認

2026-05-25 時点で確認した主要制約:

| Provider | 方式 | 制約・特徴 |
|---|---|---|
| OpenAI | `/v1/batches` + uploaded JSONL file | 24h completion window、同期 API 比 50% discount、`/v1/responses` / `/v1/chat/completions` / `/v1/embeddings` / `/v1/completions` / `/v1/moderations` 対応。1 batch は 50,000 requests / 200 MB file limit。streaming 非対応、画像入力対応。 |
| Anthropic | Message Batches API | Messages requests を非同期処理。多くは 1h 未満、24h で expire、50% discount。100,000 requests または 256 MB limit。results は 29 日取得可能。Vision / tool use / system messages / multi-turn / beta features を batch 可能。ZDR 対象外。 |
| Google | Vertex AI Gemini BatchPredictionJob | Cloud Storage / BigQuery の JSONL or BigQuery input-output。50% discount、24h turnaround を目指す。GCS/BQ と Google Cloud project/region が前提。Vertex AI docs は Gemini Enterprise Agent Platform への移行注意がある。 |
| OpenRouter | 対象外 | 公式 docs / OpenAPI spec では `/api/v1/chat/completions` などの同期 inference endpoint が中心で、provider batch job endpoint は公開されていない。OpenRouter は provider routing / fallback の同期 route として扱い、Batch API は direct provider route のみを対象にする。 |

参考:
- OpenAI Batch API guide: https://platform.openai.com/docs/guides/batch
- OpenAI Batch API reference: https://platform.openai.com/docs/api-reference/batch
- OpenAI Batch API FAQ: https://help.openai.com/en/articles/9197833-batch-api-faq
- Anthropic Batch processing: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing
- Anthropic Message Batches API reference: https://docs.anthropic.com/en/api/messages-batches
- Google Gemini batch inference: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/batch-prediction-gemini
- Google Gemini batch prediction API: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/batch-prediction-api
- OpenRouter quickstart: https://openrouter.ai/docs/quickstart
- OpenRouter API reference / OpenAPI spec: https://openrouter.ai/docs/api/reference/overview

## Decision

### 0. LoRAIro は Provider Batch API を採用するが、direct provider route のみに限定する

LoRAIro は大量画像アノテーションの cost / rate-limit 対策として Provider Batch API を採用する。
ただし対象は **provider が公式に batch job lifecycle を提供する direct route** に限定する。

採用対象:
- OpenAI direct route
- Anthropic direct route
- Google Vertex AI Gemini direct route

採用しない対象:
- OpenRouter route
- LiteLLM / PydanticAI 経由の batch abstraction
- 通常同期 API に対する LoRAIro 独自の並列 submit を「Batch API」と呼ぶ設計

OpenRouter は LoRAIro の同期 WebAPI route としては維持するが、Provider Batch API pipeline には
入れない。OpenRouter 経由の `openrouter/openai/...` や `openrouter/anthropic/...` は provider
native batch discount / job status / result artifact lifecycle を LoRAIro が検証できないため、
batch 対象 model selection から除外する。

#### Batch 対象モデルの責務境界

LoRAIro の `models` table は annotation result が「どのモデル由来か」を参照するための
local ledger であり、現在の model capability の SSoT ではない。`discontinued_at` は例外的に
LoRAIro 側の local availability gate として扱う。

- `models.discontinued_at IS NOT NULL` のモデルは batch eligibility を image-annotator-lib に
  問い合わせず、batch job 作成 UI にも表示しない
- `discontinued_at` の upstream / local DB 不一致は自動復活ロジックでは扱わない。必要なら operator
  が local DB の `discontinued_at` を修正する
- `discontinued_at IS NULL` のモデルだけを image-annotator-lib へ渡し、現在の task / provider batch
  eligibility を都度問い合わせる
- submit 直前にも image-annotator-lib 側で同じ model / task / provider batch eligibility を
  validation する

Batch eligibility は LoRAIro DB に永続化しない。OpenAI direct route では、LiteLLM 同梱 DB に
`input_cost_per_token_batches` または `output_cost_per_token_batches` が存在することを
Provider Batch API 対応の実用シグナルとして扱う。`cache_read_input_token_cost_batches` は補助的な
料金 metadata とし、単独では対応判定に使わない。

### 1. Provider Batch API は `AnnotationWorker` に統合しない

Provider Batch API は同期 Worker の variant ではなく、独立した **Batch Job pipeline** として扱う。

```
GUI / CLI
  -> ProviderBatchJobService
      -> image-annotator-lib batch API (openai / anthropic / google direct only)
      -> provider batch job submit / retrieve / cancel / fetch results
      -> normalized BatchFetchResult
      -> AnnotationSaveService
```

`AnnotationWorker` は ADR 0033 の同期 immediate execution 専用のまま維持する。Provider Batch API
は `BatchSubmitWorker` / `BatchPollWorker` / `BatchImportWorker` のような別 Worker 群で実行する。

理由:
- provider batch は「完了まで最大 24h」の UI であり、progress bar 中心の同期 Worker UX と合わない
- 途中結果が provider 側に保持されるため、ローカル DB に job state を永続化する必要がある
- cancel / retry / result import は annotation execution ではなく job lifecycle の責務

### 2. 既存 Batch import は legacy/manual import として維持する

既存 `BatchImportService` は OpenAI Batch API output JSONL の legacy/manual import として維持する。
新しい Provider Batch submit/poll path では、provider result retrieval と response normalization は
image-annotator-lib が担当し、LoRAIro は `BatchFetchResult` を既存 annotation save path に渡す。

変更方針:
- OpenAI output/error file は library が取得・parse し、normalized `BatchFetchResult` として LoRAIro に返す
- Anthropic / Google の result shape 差分も library が吸収し、LoRAIro 側には provider-specific parser を置かない
- 手動で取得済みの旧 OpenAI JSONL を取り込む GUI / CLI entrypoint は既存互換として残す
- import 済み job は `imported_at` を記録し、二重 import を防ぐ

### 3. Provider support は段階導入する

#### Phase 1: OpenAI MVP

OpenAI direct route を最初に実装する。理由:
- 既存 import サービスで OpenAI JSONL response shape の扱いを検証済みで、library 側 parser に知見を流用できる
- API key は既存 `ConfigurationService` の `openai_key` を流用できる
- local file upload + output file download のモデルで、Google の GCS/BQ 前提より小さい

MVP の対象:
- `/v1/responses` の画像アノテーション用 request JSONL 生成
- batch file upload (`purpose=batch`)
- batch create / retrieve / cancel
- completed batch output/error file download
- normalized `BatchFetchResult` と LoRAIro annotation save path への接続

#### Phase 2: Anthropic

Anthropic direct route は OpenAI MVP 後に追加する。理由:
- API shape は比較的近いが、OpenAI の JSONL endpoint file とは異なり `requests` array と results stream
  を扱う
- `custom_id` と LoRAIro image identity の対応設計は OpenAI と共通化できる
- ZDR 対象外、results 29 日保持など privacy / retention policy が OpenAI と異なるため、docs で注意する

#### Phase 3: Google Vertex AI Gemini

Google Vertex AI Gemini direct route は最後に追加する。理由:
- Cloud Storage / BigQuery input-output、project / location / IAM / region が必須で、
  LoRAIro の現行 local-first 設定モデルより重い
- `google_key` だけでは不十分で、service account / ADC / GCS bucket / project id / region 設定が必要
- Vertex AI docs 自体に Gemini Enterprise Agent Platform への移行注意があり、仕様追従コストが高い

#### Non-goal: OpenRouter route

OpenRouter は Phase には含めない。OpenRouter の公式 API surface に provider batch job endpoint が
追加され、request submit / status retrieve / cancel / result artifact download / provider-native
discount / retention の仕様が公開された場合だけ、別 ADR amendment で再評価する。

### 4. image-annotator-lib との Batch API contract は job 単位にする

Provider 固有の payload 構築、submit / status / result fetch、result 正規化は
image-annotator-lib が担当する。LoRAIro は provider 生 response / artifact format を直接 parse しない。

LoRAIro から見る library boundary は以下の形にする。

```python
def list_batch_capable_models() -> list[BatchModelInfo]: ...

def submit_batch(request: BatchSubmitRequest) -> BatchSubmitResult: ...

def retrieve_batch(handle: BatchJobHandle) -> BatchStatusResult: ...

def cancel_batch(handle: BatchJobHandle) -> BatchStatusResult: ...

def fetch_batch_results(handle: BatchJobHandle, destination_dir: Path) -> BatchFetchResult: ...
```

`list_batch_capable_models()` は現在 batch 実行可能な direct-provider model をすべて返す。LoRAIro は
endpoint / prompt profile を discovery 引数として渡さず、返された `litellm_model_id` と local DB の
`discontinued_at IS NULL` model records を突き合わせて UI に表示する。`gpt-5.5-pro` family のような
cost-safety denylist は image-annotator-lib 側で除外し、submit validation でも拒否する。

`BatchSubmitRequest` は LoRAIro が生成した `custom_id`、DB image identity、送信用画像 path、job metadata
を渡す。

```python
class BatchSubmitRequest:
    provider: str
    endpoint: str
    litellm_model_id: str
    prompt_profile: str
    description: str | None
    items: list[BatchSubmitItem]

class BatchSubmitItem:
    custom_id: str  # img-{image_id}
    image_id: int
    image_path: Path
```

`image_path` は LoRAIro が管理する resized image path を渡す。OpenAI MVP では既存の長辺 512px resized
image を使い、`detail: high` 等の provider image fidelity option は実装しない。

```text
TODO: Consider provider image detail/fidelity options later. MVP uses existing resized image payloads.
```

`BatchFetchResult` は job 単位で返す。各 item の `annotation` は同期 annotation と同じ
annotation result contract に正規化済みで、LoRAIro は provider-native batch response body を parse
しない。

```python
class BatchFetchResult:
    provider: str
    provider_job_id: str
    status: str
    items: list[BatchResultItem]
    artifacts: list[BatchArtifact]

class BatchResultItem:
    custom_id: str
    status: str  # succeeded / failed
    annotation: AnnotationResult | None
    error: BatchItemError | None
```

LoRAIro は `BatchFetchResult.items` を走査し、`custom_id = img-{image_id}` から image_id を復元し、
job metadata の model と合わせて既存 annotation save path に渡す。provider result retrieval と
local annotation persistence は別 phase とし、local 保存で一部 item が失敗しても他 item の保存は
継続する。

LoRAIro 内部では provider 生 response を UI/DB に直接流さず、`BatchStatusResult` に正規化する。

共通 status:
- `draft`
- `submitted`
- `validating`
- `running`
- `completed`
- `failed`
- `canceling`
- `canceled`
- `expired`
- `imported`

Provider 固有 status は raw JSON と `provider_status` に保持し、共通 status は library/service 境界で
map する。

### 5. `custom_id` は LoRAIro 側で生成し、結果照合の SSoT とする

Batch request の `custom_id` は次の規約にする。

```
img-{image_id}
```

制約:
- provider 制約に合わせて ASCII alphanumeric / hyphen / underscore のみ
- Anthropic の 64 文字制限を下限として全 provider 共通で 64 文字以内
- `image_id` は LoRAIro DB の `images.id`
- `custom_id` には image path / filename / model name / prompt name は含めない
- job が異なれば `custom_id` 名前空間も別として扱う

Provider Batch job は 1 job = 1 provider × 1 model × 1 endpoint × 1 prompt profile とする。
同一 job 内で同じ `image_id` を複数回投入しない。モデルや prompt profile は job metadata に保持し、
result import は job context の model と `custom_id` から復元した image_id で保存先を決定する。
既存 OpenAI import の file stem matching は fallback として残すが、新規 submit/poll path では
`custom_id = img-{image_id}` を SSoT にする。

### 6. DB スキーマは job / item / artifact を分ける

Migration draft:

```sql
CREATE TABLE provider_batch_jobs (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_job_id TEXT,
    status TEXT NOT NULL,
    provider_status TEXT,
    endpoint TEXT,
    model_id INTEGER,
    prompt_profile TEXT,
    description TEXT,
    request_count INTEGER NOT NULL DEFAULT 0,
    succeeded_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    canceled_count INTEGER NOT NULL DEFAULT 0,
    expired_count INTEGER NOT NULL DEFAULT 0,
    submitted_at DATETIME,
    completed_at DATETIME,
    canceled_at DATETIME,
    imported_at DATETIME,
    expires_at DATETIME,
    input_artifact_path TEXT,
    output_artifact_path TEXT,
    error_artifact_path TEXT,
    raw_provider_payload TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE UNIQUE INDEX uq_provider_batch_jobs_provider_job
ON provider_batch_jobs(provider, provider_job_id)
WHERE provider_job_id IS NOT NULL;

CREATE TABLE provider_batch_items (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES provider_batch_jobs(id) ON DELETE CASCADE,
    custom_id TEXT NOT NULL,
    image_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    raw_request TEXT,
    raw_response TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE(job_id, custom_id)
);

CREATE TABLE provider_batch_artifacts (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES provider_batch_jobs(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    local_path TEXT NOT NULL,
    provider_file_id TEXT,
    sha256 TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(job_id, artifact_type, local_path)
);
```

Notes:
- `raw_provider_payload`, `raw_request`, `raw_response` は JSON text とする。SQLite 互換を優先し、
  JSON 型にはしない
- `provider_job_id` は submit 前の draft job では null を許容する
- item status は provider 由来の per-request status を正規化する
- provider result retention に依存しないよう、download 済み artifacts はローカルに保存する

### 7. UI は「実行中 progress」ではなく「job queue」中心にする

UI 要件:
- Batch job 作成ダイアログ
  - provider / model / endpoint / 対象画像 / prompt profile / request count
  - `discontinued_at IS NULL` の direct provider route model だけを候補にし、Batch eligibility は
    image-annotator-lib へ都度問い合わせる
  - OpenRouter route と discontinued model は表示せず、同期 annotation または DB metadata 修正へ誘導
  - optional description (空文字可)
  - OpenAI: local JSONL upload 方式
  - Google: project / location / GCS or BigQuery 設定が必要なことを明示
- Batch job list
  - provider, model, status, counts, submitted_at, completed_at, imported_at
  - refresh / cancel / download results / import results
- Batch job detail
  - item table by custom_id
  - failed/expired/canceled item filtering
  - raw provider status inspection

同期 `AnnotationWorker` の progress dialog に provider batch を押し込まない。

MVP では cost / retention / completion prediction は UI 要件にしない。LoRAIro は pre-submit cost
estimate、post-completion usage/cost、retention timeline、expected completion timestamp を計算・表示しない。
provider が usage を返しても MVP では無視してよい。UI は対象画像数、provider/model、prompt profile、
request count、optional description、job status、result import 操作に集中する。

### 8. LiteLLM / PydanticAI との関係

ADR 0023 の同期推論境界は維持する。Provider Batch API は PydanticAI 経由にしない。

理由:
- provider batch は request file / job object / artifact lifecycle が中心で、PydanticAI の sync
  agent execution 抽象とは責務が異なる
- LiteLLM の batch helper が存在しても provider ごとの upload / results / cancel / retention / GCS
  差分を完全には隠せない
- LoRAIro は provider artifact format ではなく、library が返す normalized batch result と
  `custom_id` を SSoT にする

同期 inference は `AnnotatorLibraryAdapter` / `image-annotator-lib`、非同期 provider batch は
image-annotator-lib の batch API として別境界にする。モデルの task capability と provider batch
eligibility は image-annotator-lib が判定し、LoRAIro は `models.discontinued_at` による local gate、
UI 表示、job persistence、既存 annotation save path への投入を担当する。

OpenRouter は LiteLLM-compatible な同期 endpoint としては有用だが、Provider Batch API の
SSoT にはしない。OpenRouter が内部で OpenAI / Anthropic / Google provider に route できることと、
その provider の native batch job lifecycle を LoRAIro が管理できることは別問題である。

## Rationale

### なぜ separate pipeline か

Provider Batch API は provider 側に job state と artifact が存在する。ローカル処理の「今この Worker
が進んでいる」状態とは異なり、アプリを閉じても job は進む。したがって DB 永続化された job queue
を UI の主軸にする必要がある。

### なぜ OpenAI first か

LoRAIro は既に OpenAI Batch API の result JSONL import を持つ。最初に OpenAI submit/poll/download
を追加すれば、既存 import path を活かして最小の垂直 slice を作れる。Anthropic と Google を同時に
入れると、result shape / auth / storage の差分で最初の PR が大きくなりすぎる。

### なぜ OpenRouter を対象外にするか

OpenRouter は routing / fallback / unified billing のための同期 inference provider として扱う。
Provider Batch API は provider job id、provider status、cancel、result file / stream、retention、
discount 条件を LoRAIro が明示的に追跡できることが前提である。OpenRouter 公式 docs / OpenAPI spec
にはこの job lifecycle がないため、OpenRouter 経由で「同じ batch API」を使う設計は採用しない。

OpenRouter 経由で多数の同期 request を投げる実装は、rate limit mitigation や queueing の実装には
なり得るが、本 ADR の Provider Batch API とは別機能であり、50% discount や 24h async turnaround
を前提にした UX / DB schema に混ぜない。

### なぜ Google を Phase 3 にするか

Google Gemini batch inference は GCS/BQ と Vertex AI project/region/IAM が前提になる。LoRAIro の
既存設定は API key ベースであり、Google Cloud resource 設定 UI と credential handling が別設計を
要求する。OpenAI / Anthropic と同じ form に押し込むと UX と保守性が悪くなる。

### なぜ `custom_id` を image_id のみにするか

Batch result は request order を保証しない。provider docs でも meaningful `custom_id` による照合が
推奨される。file stem や filename 推測だけでは、同名ファイル・再投入・リネームに弱い。一方で、
dataset-relative path は長く、local path 構造を provider artifact に残すため `custom_id` には向かない。
Batch job を 1 model / 1 prompt profile に固定すれば、result import に必要な request identity は
image_id だけで足りる。model / endpoint / prompt profile は job metadata から取得する。

## Consequences

### 良い点

- Provider Batch API が同期 AnnotationWorker と混ざらず、ADR 0033 の契約を壊さない
- 既存 OpenAI JSONL import を再利用できる
- job state が DB に残るため、アプリ再起動後も polling / import を継続できる
- `custom_id` SSoT により result import の照合が安定する
- Google の GCS/BQ 前提を無理に MVP に混ぜず、段階的に導入できる
- OpenRouter route を batch 対象外にすることで、ユーザーに存在しない discount / async job 管理を
  暗示しない

### 悪い点・トレードオフ

- DB migration と job queue UI が必要になり、単純な Worker 追加より実装量が多い
- Provider ごとの result parser / status mapper が必要
- Batch API は provider retention / privacy policy に依存するため、docs で provider policy 差分に注意する
- Google support は API key 設定だけでは完結せず、別途 GCP 設定 UX が必要
- `custom_id` は短く安定するが、artifact 単体では人間が画像を特定しづらく、LoRAIro DB/GUI 参照が必要
- OpenRouter 経由でしか使っていない model は batch job 作成 UI では選べない
- direct provider API key / credential を持たないユーザーは provider-native batch discount を使えない

### 実装方針 (分解 Issue 草案)

1. **DB migration**: `provider_batch_jobs` / `provider_batch_items` / `provider_batch_artifacts` を追加
2. **Repository / Service**: provider batch job CRUD、status transition、artifact registration を実装
3. **image-annotator-lib OpenAI batch API**: `/v1/responses` request JSONL build、file upload、
   batch create/retrieve/cancel、output/error file fetch、normalized `BatchFetchResult` を実装
4. **LoRAIro batch submit bridge**: `custom_id = img-{image_id}` と resized image path を持つ
   `BatchSubmitRequest` を生成し、library batch API に渡す
5. **LoRAIro batch import bridge**: `BatchFetchResult.items` を既存 annotation save path に接続し、
   item status を更新
6. **Batch model eligibility**: LoRAIro は `discontinued_at IS NULL` の direct provider route model だけを
   lib に渡し、lib は LiteLLM batch pricing fields と task capability から eligibility を都度返す
7. **GUI job list**: provider batch job 一覧、refresh、cancel、download、import 操作を追加
8. **CLI**: submit/list/status/cancel/download/import subcommands を追加
9. **Anthropic adapter**: Message Batches create/retrieve/cancel/results stream と parser を追加
10. **Google investigation spike**: Vertex AI credential / GCS / region 設定 UX と schema 追加要否を検証
11. **Docs**: Provider Batch API の利用条件、privacy、同期 annotation との違いを記載

## Related

- #395: 本 ADR の起票元
- #384 / ADR 0033: AnnotationWorker 同期 batch execution contract
- #396: image-annotator-lib `model_name_list` 一括渡し最適化 (本 ADR とは別)
- ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary
- ADR 0030: Batch Annotation Model Selection UI
- ADR 0037: api/ Public Facade Wiring Policy
