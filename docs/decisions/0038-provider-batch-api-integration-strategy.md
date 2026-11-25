---
type: ADR
title: Provider Batch API Integration Strategy
status: Accepted
timestamp: 2026-05-25
tags: []
---
# ADR 0038: Provider Batch API Integration Strategy

- **関連 Issue**: #395

## Context

LoRAIro は現在、`AnnotationWorker` から `image-annotator-lib` を同期的に呼び出す実行経路を持つ。ADR 0033 はこの同期ワーカー経路における進捗・部分失敗・保存の契約を定めたが、プロバイダが提供する Batch API はこれとは異なる概念である。

プロバイダの Batch API は即時応答ではなく、「ジョブ投入 → 後日の状態確認 → 結果ファイル取得」という非同期実行モデルを採る。各プロバイダの仕組みは次のとおりである。

- **OpenAI Batch API**:JSONL 形式のリクエストファイルを事前にアップロードし、バッチオブジェクトをポーリングして出力ファイルおよびエラーファイルを取得する。
- **Anthropic Message Batches API**:`custom_id` を付与した Messages リクエストを作成し、バッチ状態と結果ストリームを取得する。
- **Google Gemini Batch Inference**:Vertex AI の `BatchPredictionJob` として実行し、Cloud Storage または BigQuery を入出力に用いる。

既存コードには、OpenAI Batch API の出力 JSONL を取り込む `BatchImportService`、CLI、GUI のエントリーポイントが存在する。しかしこれらは**結果のインポート機能のみ**であり、ジョブ投入、状態管理、キャンセル、ポーリング、および DB でのジョブ管理は未実装である。

### 公式仕様確認

2026-05-25 時点で確認した主要制約を以下に示す。

| Provider | 方式 | 制約・特徴 |
|---|---|---|
| OpenAI | `/v1/batches` + アップロード済み JSONL ファイル | 24 時間の完了ウィンドウ、同期 API 比 50% 割引。`/v1/responses`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/completions`、`/v1/moderations` に対応。1 バッチあたり最大 50,000 リクエストまたは 200 MB。ストリーミング非対応、画像入力対応。 |
| Anthropic | Message Batches API | Messages リクエストを非同期処理する。多くは 1 時間未満で完了し、24 時間で期限切れとなる。同期 API 比 50% 割引。最大 100,000 リクエストまたは 256 MB。結果は 29 日間取得可能。Vision、tool use、system messages、multi-turn、beta features に対応。ZDR 対象外。 |
| Google | Vertex AI Gemini BatchPredictionJob | Cloud Storage の JSONL または BigQuery を入出力に使用する。50% 割引で、24 時間以内の完了を目指す。GCS または BigQuery、および Google Cloud の project と region が前提。Vertex AI 公式ドキュメントに Gemini Enterprise Agent Platform への移行に関する注意書きがある。 |
| OpenRouter | 対象外 | 公式ドキュメントおよび OpenAPI 仕様では `/api/v1/chat/completions` などの同期推論エンドポイントが中心であり、プロバイダのバッチジョブ用エンドポイントは公開されていない。OpenRouter はルーティングやフォールバック用の同期経路として扱い、Batch API はプロバイダ直接経路のみを対象とする。 |

参考資料:

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

### 0. Provider Batch API を採用し、対象はプロバイダ直接経路のみに限定する

LoRAIro は大量画像アノテーションのコスト削減およびレート制限対策として、Provider Batch API を採用する。ただし対象は、**プロバイダが公式にバッチジョブのライフサイクルを提供する直接経路(direct provider route)** に限定する。

採用対象:

- OpenAI 直接経路
- Anthropic 直接経路
- Google Vertex AI Gemini 直接経路

採用しない対象:

- OpenRouter 経路
- LiteLLM または PydanticAI 経由のバッチ抽象化
- 通常の同期 API に対して LoRAIro 独自に並列送信する仕組みを「Batch API」と呼ぶ設計

OpenRouter は LoRAIro の同期 WebAPI 経路としては維持するが、Provider Batch API パイプラインには含めない。OpenRouter 経由の `openrouter/openai/...` や `openrouter/anthropic/...` は、プロバイダ固有のバッチ割引、ジョブ状態、結果成果物のライフサイクルを LoRAIro 側で検証できないため、バッチ対象モデルの選択候補から除外する。

#### Batch 対象モデルの責務境界

LoRAIro の `models` テーブルは、アノテーション結果がどのモデル由来かを参照するためのローカル台帳であり、現在のモデル機能に関する SSoT ではない。ただし `discontinued_at` だけは例外的に、LoRAIro 側のローカル利用可否ゲートとして扱う。

- `models.discontinued_at IS NOT NULL` のモデルは、バッチ対応可否を `image-annotator-lib` に問い合わせず、バッチジョブ作成 UI にも表示しない。
- `discontinued_at` の上流仕様とローカル DB 間の不一致は、自動復活ロジックでは扱わない。必要な場合は運用者がローカル DB の `discontinued_at` を修正する。
- `discontinued_at IS NULL` のモデルだけを `image-annotator-lib` へ渡し、現在のタスクおよびプロバイダにおけるバッチ対応可否を都度問い合わせる。
- 送信直前にも、`image-annotator-lib` 側で同じモデル・タスク・プロバイダのバッチ対応可否を検証する。

バッチ対応可否は LoRAIro の DB に永続化しない。OpenAI 直接経路では、LiteLLM 同梱 DB に `input_cost_per_token_batches` または `output_cost_per_token_batches` が存在することを、Provider Batch API 対応の実用的な判定基準として扱う。`cache_read_input_token_cost_batches` は補助的な料金メタデータにとどめ、単独では対応判定に使用しない。

### 1. Provider Batch API は `AnnotationWorker` に統合しない

Provider Batch API は同期ワーカーの派生形態ではなく、独立した **Batch Job パイプライン** として設計する。

```
GUI / CLI
  -> ProviderBatchJobService
      -> image-annotator-lib batch API (openai / anthropic / google direct only)
      -> provider batch job submit / retrieve / cancel / fetch results
      -> normalized BatchFetchResult
      -> AnnotationSaveService
```

`AnnotationWorker` は ADR 0033 の同期即時実行専用のまま維持する。Provider Batch API は、`BatchSubmitWorker`、`BatchPollWorker`、`BatchImportWorker` のような専用ワーカー群で実行する。

分離する理由は次のとおりである。

- プロバイダバッチは完了まで最大 24 時間かかるため、プログレスバー中心の同期ワーカー UX と噛み合わない。
- 処理途中の状態がプロバイダ側に保持されるため、ローカル DB にジョブ状態を永続化する必要がある。
- キャンセル、再試行、結果インポートは、アノテーション実行ではなくジョブのライフサイクル管理の責務である。

### 2. 既存 Batch インポートはレガシー・手動インポートとして維持する

既存の `BatchImportService` は、OpenAI Batch API の出力 JSONL を手動で取り込むレガシー経路として維持する。新しい Provider Batch の送信・ポーリング経路では、プロバイダからの結果取得とレスポンス正規化を `image-annotator-lib` が担当し、LoRAIro は受け取った `BatchFetchResult` を既存のアノテーション保存経路へ渡す。

変更方針は次のとおりである。

- OpenAI の出力ファイルおよびエラーファイルはライブラリ側で取得・解析し、正規化した `BatchFetchResult` として LoRAIro に返す。
- Anthropic や Google との結果形式の差分もライブラリ側で吸収し、LoRAIro 側にはプロバイダ固有のパーサーを置かない。
- 手動取得済みの旧 OpenAI JSONL を取り込む GUI および CLI のエントリーポイントは、既存互換として残す。
- インポート済みのジョブには `imported_at` を記録し、二重インポートを防止する。

### 3. プロバイダ対応は段階的に導入する

#### Phase 1:OpenAI MVP

最初に OpenAI 直接経路を実装する。理由は以下の 3 点である。

- 既存のインポートサービスで OpenAI JSONL のレスポンス形式を検証済みであり、ライブラリ側のパーサーに知見を流用できる。
- API キーは既存の `ConfigurationService` が持つ `openai_key` をそのまま流用できる。
- ローカルファイルのアップロードと出力ファイルのダウンロードで完結するため、Google の GCS や BigQuery を前提とする構成より実装規模が小さい。

MVP の対象範囲は次のとおりとする。

- `/v1/responses` の画像アノテーション用リクエスト JSONL 生成
- バッチファイルのアップロード(`purpose=batch`)
- バッチの作成、状態取得、キャンセル
- 完了済みバッチの出力ファイルおよびエラーファイルのダウンロード
- 正規化済み `BatchFetchResult` と LoRAIro アノテーション保存経路との接続

#### Phase 2:Anthropic

Anthropic 直接経路は OpenAI MVP の完了後に追加する。理由は以下のとおりである。

- API 構造は比較的近いものの、OpenAI の JSONL ファイル形式とは異なり、`requests` 配列と結果ストリームを扱う必要がある。
- `custom_id` と LoRAIro の画像識別子の対応設計は OpenAI と共通化できる。
- ZDR 対象外であることや結果の保持期間が 29 日間であることなど、プライバシーと保持ポリシーが OpenAI と異なるため、ドキュメントで注意喚起を行う必要がある。

#### Phase 3:Google Vertex AI Gemini

Google Vertex AI Gemini 直接経路は最後に追加する。理由は以下のとおりである。

- Cloud Storage または BigQuery の入出力に加え、project、location、IAM、region の設定が必須であり、LoRAIro の現行ローカルファースト設定モデルより負担が大きい。
- `google_key` だけでは不足しており、サービスアカウントや ADC、GCS バケット、project id、region の設定が必要となる。
- Vertex AI 公式ドキュメントに Gemini Enterprise Agent Platform への移行に関する注意があり、仕様追従コストが高い。

#### Non-goal:OpenRouter 経路

OpenRouter は導入フェーズに含めない。将来、OpenRouter の公式 API にプロバイダのバッチジョブ用エンドポイントが追加され、送信・状態取得・キャンセル・結果成果物ダウンロード・プロバイダ固有割引・保持期間の仕様が公開された場合にのみ、別 ADR の改訂で再評価する。

### 4. `image-annotator-lib` との Batch API 契約はジョブ単位とする

プロバイダ固有のペイロード構築、送信、状態確認、結果取得、および結果の正規化は `image-annotator-lib` が担当する。LoRAIro 側はプロバイダの生レスポンスや成果物フォーマットを直接解析しない。

LoRAIro から見たライブラリ境界は以下のインターフェースとする。

```python
def list_batch_capable_models() -> list[BatchModelInfo]: ...

def submit_batch(request: BatchSubmitRequest) -> BatchSubmitResult: ...

def retrieve_batch(handle: BatchJobHandle) -> BatchStatusResult: ...

def cancel_batch(handle: BatchJobHandle) -> BatchStatusResult: ...

def fetch_batch_results(handle: BatchJobHandle, destination_dir: Path) -> BatchFetchResult: ...
```

`list_batch_capable_models()` は、現在バッチ実行可能な直接プロバイダモデルをすべて返す。LoRAIro は探索時の引数としてエンドポイントやプロンプトプロファイルを渡さず、返却された `litellm_model_id` とローカル DB の `discontinued_at IS NULL` レコードを突き合わせて UI に表示する。なお、`gpt-5.5-pro` family のようなコスト安全上の拒否リストは `image-annotator-lib` 側で除外し、送信時の検証でも拒否する。

`BatchSubmitRequest` では、LoRAIro が生成した `custom_id`、DB の画像 ID、送信用画像パス、およびジョブメタデータを渡す。

```python
class BatchSubmitRequest:
    provider: str
    endpoint: str
    litellm_model_id: str
    prompt_profile: str
    description: str | None
    api_keys: dict[str, str]
    items: list[BatchSubmitItem]

class BatchSubmitItem:
    custom_id: str  # img-{image_id}
    image_id: int
    image_path: Path
```

API キーは通常のアノテーションと同様に `api_keys` 辞書で渡す。`image_path` には LoRAIro が管理するリサイズ済み画像パスを渡す。OpenAI MVP では既存の長辺 512px リサイズ画像を使用し、`detail: high` などのプロバイダ固有の画像品質オプションは実装しない。バイナリ化、MIME や形式の判定、必要な形式変換、base64 や data URL への変換、およびプロバイダ固有の画像入力フィールド構築は `image-annotator-lib` が担当する。

```text
TODO: Consider provider image detail/fidelity options later. MVP uses existing resized image payloads.
```

送信後に LoRAIro が保存する安定契約の結果型は最小限にとどめる。

```python
class BatchSubmitResult:
    provider: str
    provider_job_id: str
    status: str
    request_count: int

class BatchJobHandle:
    provider: str
    provider_job_id: str
    api_keys: dict[str, str]

class BatchStatusResult:
    provider: str
    provider_job_id: str
    status: str
    request_count: int | None
    succeeded_count: int | None
    failed_count: int | None
    canceled_count: int | None
    expired_count: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
```

LoRAIro とライブラリ間の安定契約には、`raw_provider_payload` やプロバイダ固有ハンドルを含めない。OpenAI の `output_file_id` のようなプロバイダ固有の補助 ID はライブラリ内部で再取得するか、ライブラリ側の実装詳細として隠蔽する。LoRAIro は `provider` とプロバイダが返す `provider_job_id` だけを、状態確認・キャンセル・結果取得のための安定ハンドルとして扱う。

`BatchFetchResult` はジョブ単位で返却する。各要素の `annotation` は同期アノテーションと同じ結果契約へ正規化済みとし、LoRAIro 側でプロバイダ固有のレスポンス本文を解析しない。

```python
class BatchFetchResult:
    provider: str
    provider_job_id: str
    status: str
    items: list[BatchResultItem]
    artifacts: list[BatchArtifact] | None

class BatchResultItem:
    custom_id: str
    status: str  # succeeded / failed
    annotation: AnnotationResult | None
    error: BatchItemError | None
```

LoRAIro は `BatchFetchResult.items` を走査して `custom_id = img-{image_id}` から `image_id` を復元し、ジョブメタデータのモデル情報とあわせて既存のアノテーション保存経路へ渡す。プロバイダからの結果取得とローカルへの永続化は別フェーズとして扱い、ローカル保存で一部項目が失敗しても他項目の保存は継続する。

また、LoRAIro 内部ではプロバイダの生レスポンスを UI や DB に直接流さず、`BatchStatusResult` へ正規化する。

共通ステータスは以下の 10 種類とする。

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

プロバイダ固有のステータスは生 JSON と `provider_status` に保持し、共通ステータスへの変換はライブラリおよびサービス層の境界で行う。

### 5. `custom_id` は LoRAIro 側で生成し、結果照合の SSoT とする

バッチリクエストの `custom_id` は、以下の形式に統一する。

```
img-{image_id}
```

制約条件は次のとおりである。

- プロバイダ制約に合わせ、ASCII 英数字、ハイフン、アンダースコアのみを使用する。
- Anthropic の 64 文字制限を下限として、全プロバイダ共通で 64 文字以内とする。
- `image_id` には LoRAIro DB の `images.id` を用いる。
- `custom_id` には画像パス、ファイル名、モデル名、プロンプト名を含めない。
- ジョブが異なれば、`custom_id` の名前空間も独立したものとして扱う。

Provider Batch ジョブは、「1 ジョブ = 1 プロバイダ × 1 モデル × 1 エンドポイント × 1 プロンプトプロファイル」とする。同一ジョブ内に同じ `image_id` を重複投入しない。モデルやプロンプトプロファイルはジョブメタデータに保持し、結果インポート時はジョブコンテキストのモデルと `custom_id` から復元した `image_id` を用いて保存先を決定する。既存の OpenAI インポートで使われているファイル名(stem)照合はフォールバックとして残すが、新規の送信・ポーリング経路では `custom_id = img-{image_id}` を SSoT とする。

### 6. DB スキーマはジョブ・項目・成果物を分離する

マイグレーション草案は以下のとおりである。

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

補足事項:

- `provider_job_id` は、送信前の下書きジョブ(draft)において NULL を許容する。
- 項目ステータスは、プロバイダ由来のリクエスト単位ステータスを正規化して格納する。
- プロバイダ側の結果保持期間に依存しないよう、ダウンロード済みの成果物はローカルに保存する。
- プロバイダの生ペイロード、リクエスト JSON、レスポンス JSON は、LoRAIro DB の安定スキーマには保存しない。

### 7. UI は「実行中進捗」ではなく「ジョブキュー」中心にする

UI の要件を次のように定める。

- **バッチジョブ作成ダイアログ**
  - プロバイダ、モデル、エンドポイント、対象画像、プロンプトプロファイル、リクエスト件数を設定できること。
  - `discontinued_at IS NULL` のプロバイダ直接経路モデルだけを候補とし、バッチ対応可否は `image-annotator-lib` へ都度問い合わせること。
  - OpenRouter 経路および廃止済み(discontinued)モデルは表示せず、同期アノテーションまたは DB メタデータ修正へ誘導すること。
  - 任意の説明文(description、空文字可)を入力できること。
  - OpenAI はローカル JSONL アップロード方式であることを示すこと。
  - Google は project、location、GCS または BigQuery の設定が必要であることを明示すること。
- **バッチジョブ一覧**
  - プロバイダ、モデル、ステータス、件数、`submitted_at`、`completed_at`、`imported_at` を表示すること。
  - 更新、キャンセル、結果ダウンロード、結果インポートの操作を備えること。
- **バッチジョブ詳細**
  - `custom_id` 単位の項目テーブルを表示すること。
  - 失敗・期限切れ・キャンセル済み項目のフィルタリングができること。
  - プロバイダ固有の生ステータスを確認できること。

同期 `AnnotationWorker` 用のプログレスダイアログにプロバイダバッチを押し込んではならない。

なお MVP では、コスト・保持期間・完了予測を UI 要件に含めない。LoRAIro は送信前のコスト見積もり、完了後の使用量やコスト、保持期間のタイムライン、完了予定時刻を計算・表示しない。プロバイダが使用量(usage)を返しても MVP では無視してよい。UI は対象画像数、プロバイダ・モデル、プロンプトプロファイル、リクエスト件数、任意の説明文、ジョブ状態、結果インポート操作に集中する。

### 8. LiteLLM / PydanticAI との関係

ADR 0023 が定めた同期推論の境界は維持する。Provider Batch API は PydanticAI を経由させない。

理由は以下のとおりである。

- プロバイダバッチはリクエストファイル、ジョブオブジェクト、成果物ライフサイクルが中心であり、PydanticAI の同期エージェント実行抽象とは責務が異なる。
- LiteLLM にバッチ用ヘルパーが存在しても、プロバイダごとのアップロード、結果取得、キャンセル、保持期間、GCS 設定などの差分を完全には隠蔽できない。
- LoRAIro はプロバイダの成果物フォーマットではなく、ライブラリが返す正規化済みバッチ結果と `custom_id` を SSoT とする。

同期推論は `AnnotatorLibraryAdapter` と `image-annotator-lib` の同期経路、非同期プロバイダバッチは `image-annotator-lib` の Batch API として別境界に分ける。モデルのタスク対応能力とバッチ対応可否は `image-annotator-lib` が判定する。一方、LoRAIro は `models.discontinued_at` によるローカル制御、UI 表示、ジョブ永続化、既存アノテーション保存経路への投入を担う。

OpenRouter は LiteLLM 互換の同期エンドポイントとしては有用だが、Provider Batch API の SSoT にはしない。OpenRouter が内部で OpenAI、Anthropic、Google へルーティングできることと、各プロバイダのネイティブなバッチジョブのライフサイクルを LoRAIro が管理できることは別問題である。

## Rationale

### なぜ独立パイプラインにするのか

Provider Batch API では、ジョブの状態と成果物がプロバイダ側に存在する。ローカル処理の「今このワーカーが進んでいる」という状態とは異なり、アプリを終了してもジョブは進行する。したがって、DB に永続化されたジョブキューを UI の主軸にする必要がある。

### なぜ OpenAI を最初に実装するのか

LoRAIro はすでに OpenAI Batch API の結果 JSONL インポート機能を持っている。最初に OpenAI の送信・ポーリング・ダウンロードを追加すれば、既存のインポート経路を活かして最小の垂直スライスを構築できる。Anthropic や Google を同時に導入すると、結果形式・認証・ストレージの差分によって最初の PR が肥大化しすぎる。

### なぜ OpenRouter を対象外にするのか

OpenRouter は、ルーティング、フォールバック、および課金統合のための同期推論プロバイダとして位置づける。Provider Batch API は、プロバイダのジョブ ID、状態、キャンセル、結果ファイルやストリーム、保持期間、割引条件を LoRAIro が明示的に追跡できることが前提である。OpenRouter の公式ドキュメントおよび OpenAPI 仕様にはこのジョブライフサイクルが存在しないため、OpenRouter 経由で同一のバッチ API を使う設計は採用しない。

OpenRouter 経由で多数の同期リクエストを送信する仕組みは、レート制限緩和やキューイングの実装にはなり得る。しかしそれは本 ADR の Provider Batch API とは別機能であり、50% 割引や 24 時間の非同期完了を前提とする UX や DB スキーマには混在させない。

### なぜ Google を Phase 3 にするのか

Google Gemini のバッチ推論は、GCS または BigQuery、および Vertex AI の project、region、IAM が前提となる。LoRAIro の既存設定は API キーベースであり、Google Cloud リソース設定 UI と認証情報管理には別設計が求められる。OpenAI や Anthropic と同じフォームに押し込むと、UX と保守性が損なわれる。

### なぜ `custom_id` を `image_id` のみにするのか

バッチ結果はリクエストの送信順を保証しないため、プロバイダの公式ドキュメントでも意味のある `custom_id` による照合が推奨されている。ファイル名(stem)による推測だけでは、同名ファイル、再投入、リネームに弱い。一方で、データセット相対パスは長くなりやすく、ローカルのパス構造がプロバイダ側の成果物に残ってしまうため不向きである。バッチジョブを 1 モデル・1 プロンプトプロファイルに固定すれば、結果インポートに必要な識別子は `image_id` だけで足りる。モデル、エンドポイント、プロンプトプロファイルはジョブメタデータから取得すればよい。

## Consequences

### 良い点

- Provider Batch API が同期 `AnnotationWorker` と混ざらず、ADR 0033 の契約を壊さない。
- 既存の OpenAI JSONL インポート機能を再利用できる。
- ジョブ状態が DB に残るため、アプリ再起動後もポーリングやインポートを継続できる。
- `custom_id` を SSoT とすることで、結果インポート時の照合が安定する。
- Google の GCS や BigQuery 前提を MVP に無理に混ぜず、段階的に導入できる。
- OpenRouter 経路をバッチ対象外とすることで、存在しない割引や非同期ジョブ管理をユーザーへ誤認させない。

### 悪い点・トレードオフ

- DB マイグレーションとジョブキュー UI が必要となり、単純なワーカー追加より実装量が増える。
- プロバイダごとの結果パーサーおよびステータスマッパーを実装する必要がある。
- Batch API は各プロバイダの保持期間やプライバシーポリシーに依存するため、ドキュメントで差分を明記する必要がある。
- Google 対応は API キー設定だけでは完結せず、別途 GCP 設定用の UX が必要になる。
- `custom_id` は短く安定する反面、成果物単体からは人間が画像を特定しにくく、LoRAIro の DB または GUI 参照が必要になる。
- OpenRouter 経由でのみ利用しているモデルは、バッチジョブ作成 UI から選択できない。
- プロバイダ直接の API キーや認証情報を持たないユーザーは、プロバイダ固有のバッチ割引を利用できない。

### 実装方針(分解 Issue 草案)

1. **DB マイグレーション**:`provider_batch_jobs`、`provider_batch_items`、`provider_batch_artifacts` を追加する。
2. **Repository / Service**:プロバイダバッチジョブの CRUD、状態遷移、成果物登録を実装する。
3. **`image-annotator-lib` OpenAI Batch API**:`/v1/responses` リクエスト JSONL 生成、ファイルアップロード、バッチの作成・取得・キャンセル、出力・エラーファイル取得、正規化済み `BatchFetchResult` を実装する。
4. **LoRAIro バッチ送信ブリッジ**:`custom_id = img-{image_id}` とリサイズ済み画像パスを持つ `BatchSubmitRequest` を生成し、ライブラリの Batch API へ渡す。
5. **LoRAIro バッチインポートブリッジ**:`BatchFetchResult.items` を既存アノテーション保存経路へ接続し、項目ステータスを更新する。
6. **バッチモデル対応可否判定**:LoRAIro は `discontinued_at IS NULL` のプロバイダ直接経路モデルだけをライブラリへ渡し、ライブラリは LiteLLM のバッチ料金フィールドとタスク対応能力から対応可否を都度返す。
7. **GUI ジョブ一覧**:プロバイダバッチジョブの一覧表示、更新、キャンセル、ダウンロード、インポート操作を追加する。
8. **CLI**:`submit`、`list`、`status`、`cancel`、`download`、`import` の各サブコマンドを追加する。
9. **Anthropic アダプター**:Message Batches の作成・取得・キャンセル・結果ストリームおよびパーサーを追加する。
10. **Google 調査スパイク**:Vertex AI 認証情報、GCS、region 設定の UX とスキーマ追加要否を検証する。
11. **ドキュメント**:Provider Batch API の利用条件、プライバシー、同期アノテーションとの違いを記載する。

## Implementation Status (2026-05-27)

OpenAI MVP は以下の PR でマージ済みである。

| 対象 | 経路 | エンドポイント | 関連 PR |
|---|---|---|---|
| Rating preflight(Moderations Batch) | Batch | `/v1/moderations` | LoRAIro #509 / #510 / #515 / iam-lib #121 / #122 / #123 |
| 通常アノテーション(Chat Completions Batch) | Batch | `/v1/chat/completions` | LoRAIro #518(本実装) / iam-lib #126 |
| 同期 Moderations | 同期 | `/v1/moderations` | iam-lib #124 / #125(#517 関連) |

通常アノテーション Batch(Issue #518)の実装メモ:

- ADR 草案 §3 では `/v1/responses` を MVP 対象としていたが、実装では **`/v1/chat/completions`** を選択した。PydanticAI の同期経路と同じエンドポイントを共有することで、tool schema とレスポンス形状を完全一致させ、新 API(`/v1/responses`)のサンプル不足リスクを回避するためである。
- Pydantic の `AnnotationSchema` をスキーマの SSoT とし、Batch では `AnnotationSchema.model_json_schema()` から直接 OpenAI の function-tool スキーマを生成する(PydanticAI 抽象は経由しない)。
- 安全性拒否(`finish_reason=content_filter` または `message.refusal` が非 NULL)は `BatchItemError(code="provider_safety_refusal")` へ正規化し、同期側の `SafetyRefusalError` および `ContentPolicyRefusalError` 階層と等価に扱う。
- LoRAIro 側の `_TASK_TYPE_ENDPOINTS["annotation"]["openai"]` を `/v1/chat/completions` に設定し、CLI と `workflow_service` の双方でルーティングを完了した。

Phase 2(Anthropic Message Batches)および Phase 3(Google Vertex AI Gemini batch)は未着手である。

## Related

- #395:本 ADR の起票元
- #471 / ADR 0031 amendment:OpenAI Moderations Batch を既存レーティングパイプラインへ畳み込む事前判定(preflight)方針
- #384 / ADR 0033:`AnnotationWorker` 同期バッチ実行契約
- #396:`image-annotator-lib` の `model_name_list` 一括渡し最適化(本 ADR とは別件)
- #517:OpenAI Moderations の同期アノテーション経路(同期側、設計境界と整合)
- #518:OpenAI Batch `/v1/chat/completions` アノテーション(Phase 1 MVP 実装)
- ADR 0023:PydanticAI / LiteLLM WebAPI Inference Boundary
- ADR 0030:Batch Annotation Model Selection UI
- ADR 0037:`api/` Public Facade Wiring Policy
