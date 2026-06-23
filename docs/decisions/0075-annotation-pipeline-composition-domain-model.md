---
type: ADR
title: アノテーションパイプライン構成 (選択モデル × アノテーション種類) のドメインモデル
status: Proposed
timestamp: 2026-06-23
tags: [gui, annotation, pipeline, domain-model]
---
# ADR 0075: アノテーションパイプライン構成 (選択モデル × アノテーション種類) のドメインモデル

## Context

バッチアノテーションのモデル選択 UI は、ADR 0030 が規定した「環境 → タスク」の
**二段階フィルタ** から、per-stage ピッカー (`StageModelPickerDialog` +
`PipelineStageTableWidget` + `PipelineCompositionService`) へ全面移行した
(#741 / #839 / #845)。しかしこの刷新を記録した ADR が存在せず、ピッカー背後の
ドメインモデル (`src/lorairo/services/pipeline_composition.py`) の設計ルールは
「デザインセッション 2026-06-11 / docs/design/wireframes-v11」とコードにしか
無い (#885 / #887)。

加えて、ドメインモデルのソースコメントが ADR 0023 / 0031 を「固定スキーマと
RATING 除外の根拠」として誤引用していた (#888)。また per-stage ピッカーの実行環境
セグメントは ADR 0030 が文章で否定した「環境未選択 (`all`) 状態」を既定にしている
(#889)。

本 ADR はこのドメインモデルを正準として記録し、誤引用と env 意味論の矛盾を是正する。

## Decision

### SSoT は「選択モデル集合」

バッチアノテーションで実行とコストを決める唯一の正本は **選択されたモデルの集合**
(`ModelSelectionWidget` のチェック状態) である。

ステージへの割り当て (`PipelineCompositionService._assignments`) は SSoT ではない。
`compose_from_models()` が選択モデル集合から **毎回作り直す派生ビュー** であり
(呼ぶたびにクリアして再構築)、「どのモデルをどのステージに置いたか」は出力にも
コストにも影響しない。ステージ表示は選択集合を 4 つのアノテーション種類に投影した
見せ方にすぎない。

### アノテーション種類 (出力の種類)

出力の種類は `tags / caption / score / rating` の 4 つ。コード上は `PipelineStage`
enum で表すが、本質は逐次工程ではなく **1 推論が並列に埋めうる出力の種類** である。

各モデルがどの種類を出せるかは `StageModelInfo.fill_stages()` (capabilities 由来) で
決まる。ピッカーやテーブルへの配置と無関係に、モデルの能力だけで出力種類が決まる。

### multimodal の固定スキーマと RATING の出どころ

multimodal WebAPI モデルの 1 推論は `{tags, captions, score}` を固定で返す
(`MULTIMODAL_FILL_STAGES`)。**multimodal は rating を出さない。**

`rating` は次の経路から得る (multimodal annotation 経路ではない):

- rating 対応モデルの出力
- 送信前 moderation プリフライト (ADR 0070、provider batch では `task_type = "rating_preflight"`)

この固定スキーマと RATING 除外は本 ADR が正準とする。ADR 0023 (PydanticAI /
LiteLLM 推論境界) と ADR 0031 (rating→canonical mapping) は **この規定の根拠では
ない**。ソースコメントが両 ADR を引いていたのは誤りで、引用先を是正する (#888)。

### 派生出力 (派生チップ `↝`) は read-only

multimodal を 1 ステージに主割当すると、同一推論が埋める他のアノテーション種類には
**派生チップ (`DerivedChip`)** が read-only で表示される。compose 時に外す手段は
持たない (`remove` は主割当のみ対象)。

派生出力は **既定で採用** され、間違ったものだけ Results の soft-reject (ADR 0065)
で任意に外す。compose で opt-out させない理由は、推論が固定スキーマで全種類を返す
以上、UI で隠してもデータは生成・保存されるため (表示と実体の乖離を避ける)。

### 推論回数 = ユニークモデル数 × ステージング枚数

推論回数 (= 課金単位 = ジョブ数) は **ユニークモデル数 × ステージング枚数**。同一
モデルを複数のアノテーション種類に充当しても `litellm_model_id` で dedupe され、
コストは増えない (`InferenceLedger`)。

### 実行環境セグメントの意味論 (ADR 0030 から上書き)

per-stage ピッカーの実行環境は `すべて (all) / APIのみ (api) / ローカルのみ (local)`
の 3 値で、既定は `all`。

これは ADR 0030 の「環境未選択状態を持たない。初期値は `api` または `local`」を
**上書きする** (#889)。per-stage ピッカーはステージ単位で候補を出すため、環境を絞らず
全候補から選ぶ初期状態 (`all`) が自然であり、環境は絞り込みの 1 軸 (種類・provider と
並ぶ) として扱う。

### 用語

| 用語 | 意味 |
|---|---|
| ジョブ (job) | 実行単位。1 モデル × 1 画像の推論、または provider batch の 1 送信。lifecycle 管理対象 (ADR 0066) |
| アノテーション種類 | 出力の種類 = `tags / caption / score / rating` |
| `task_type` | provider batch の処理モード = `annotation` / `rating_preflight`。アノテーション種類とは別軸 |

`tags/caption/score/rating` を「タスク」と呼ばない (provider batch の `task_type` と
衝突するため)。

## Rationale

per-stage ピッカーの実態を追うと、ステージへの割り当ては選択モデル集合からの派生で
あり、出力もコストも「選んだモデル」と「各モデルの能力」だけで決まる。ドメインモデルを
「割り当て状態」中心に説明すると load-bearing でない中間データを正本のように誤認させる
ため、SSoT を選択モデル集合に置き、ステージ表示を派生ビューと位置づける。

固定スキーマ / RATING 除外を ADR 0023 / 0031 に帰していたのは出どころの取り違えで、
正準を本 ADR に置けば以後の引用が安定する。env 意味論は ADR 0030 の二段階フィルタ前提
の規定であり、per-stage ピッカーでは成立しないため上書きする。

## Consequences

- ADR 0030 (Batch Annotation Model Selection UI) の「二段階フィルタ」「env =
  `api`/`local` のみ」の決定は本 ADR が **superseded** する。ADR 0030 は status を
  Superseded に更新する (#885)。
- `pipeline_composition.py` の固定スキーマ / RATING 除外の引用を ADR 0023/0031 から
  本 ADR + ADR 0070 へ差し替える (#888)。
- ドメインモデルの説明・docstring は「選択モデル集合 (SSoT) + 各モデルのアノテーション
  種類、ステージ表示は派生ビュー」を基準にする。
- conf-min による推論後フィルタは前提が成立せず撤去済み (#851 / PR #886)。本 ADR は
  per-tag confidence ベースの機能を含まない。
- 実行時 per-model のタグ閾値が必要になった場合は lib `annotate()` 拡張が前提
  (someday #851)。

## Related

- ADR 0030: Batch Annotation Model Selection UI (本 ADR が superseded)
- ADR 0065: Tag/Caption Soft-Reject And Export Resolution (派生出力の事後却下)
- ADR 0066: Unified Jobs Lifecycle View (ジョブ = 実行単位)
- ADR 0070: OpenAI Moderation WebAPI Preflight (rating の出どころ)
- ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary (誤引用是正の対象)
- ADR 0031: AI Rating Mapping to Canonical Rating (誤引用是正の対象)
- LoRAIro #885 (ADR 0030 二段階フィルタ → per-stage ドリフト)
- LoRAIro #887 (本 ADR でドメインモデルを記録)
- LoRAIro #888 (ADR 0023/0031 誤引用の是正)
- LoRAIro #889 (env 意味論の上書き)
- LoRAIro #741 / #839 / #845 (per-stage 刷新)
- LoRAIro #851 / PR #886 (conf-min 撤去)
