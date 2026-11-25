---
type: ADR
title: アノテーションパイプライン構成 (選択モデル × アノテーション種類) のドメインモデル
status: Accepted
timestamp: 2026-06-23
tags: [gui, annotation, pipeline, domain-model]
---
# ADR 0075: アノテーションパイプライン構成 (選択モデル × アノテーション種類) のドメインモデル

- **一部改訂**: ADR 0076 — 「SSoT = 選択モデル集合」という定義は不変である。一方、SSoT の所在は `ModelSelectionWidget` のチェックボックス状態から `gui/state/` の選択状態マネージャへ移す(#884 での引き上げ)。

## Context

バッチアノテーションのモデル選択 UI は、ADR 0030 が規定した「環境 → タスク」の二段階フィルタから、ステージ単位のピッカー構成(`StageModelPickerDialog`、`PipelineStageTableWidget`、`PipelineCompositionService`)へ全面移行した(#741 / #839 / #845)。しかし、この刷新を記録した ADR が存在せず、ピッカー背後にあるドメインモデル(`src/lorairo/services/pipeline_composition.py`)の設計ルールは「デザインセッション 2026-06-11 / `docs/design/wireframes`」とソースコードにしか残っていなかった(#885 / #887)。

加えて、以下の 2 つの不整合も生じていた。

- ドメインモデルのソースコメントが、ADR 0023 と ADR 0031 を「固定スキーマと RATING 除外の根拠」として誤って引用していた(#888)。
- ステージ別ピッカーの実行環境セグメントは、ADR 0030 が文章で否定していた「環境未選択(`all`)状態」を既定値としている(#889)。

本 ADR はこのドメインモデルを正準として記録し、誤引用と実行環境の意味論における矛盾を是正する。

## Decision

### SSoT は「選択モデル集合」とする

バッチアノテーションの実行内容とコストを決定する唯一の正本(SSoT)は、選択されたモデルの集合(`ModelSelectionWidget` のチェック状態)である。

ステージへの割り当て(`PipelineCompositionService._assignments`)は SSoT ではない。`compose_from_models()` が選択モデル集合から毎回作り直す派生ビュー(呼び出しのたびにクリアして再構築)であり、「どのモデルをどのステージに配置したか」は出力にもコストにも影響しない。ステージ表示は、選択モデル集合を 4 つのアノテーション種類へ投影した見せ方にすぎない。

### アノテーション種類(出力の種類)

出力の種類は `tags`、`caption`、`score`、`rating` の 4 つとする。コード上では `PipelineStage` enum で表すが、本質は逐次工程ではなく「1 回の推論が並列に埋め得る出力の種類」である。

各モデルがどの種類を出力できるかは、モデルの能力(capabilities)に基づく `StageModelInfo.fill_stages()` で決まる。ピッカーやテーブル上での配置とは無関係に、モデルの能力のみで出力種類が定まる。

### マルチモーダルモデルの固定スキーマと RATING の出どころ

マルチモーダル WebAPI モデルの 1 回の推論は、`{tags, captions, score}` を固定で返す(`MULTIMODAL_FILL_STAGES`)。マルチモーダルモデルは `rating` を出力しない。

`rating` はマルチモーダルアノテーション経路ではなく、次の 2 経路から取得する。

- `rating` 対応モデルの出力
- 送信前モデレーションプリフライト(ADR 0070。Provider Batch では `task_type = "rating_preflight"`)

この固定スキーマと RATING 除外の規定は本 ADR を正準とする。ADR 0023(PydanticAI / LiteLLM 推論境界)と ADR 0031(rating から正規レーティングへのマッピング)はこの規定の根拠ではない。ソースコメントが両 ADR を引用していたのは誤りであるため、引用先を是正する(#888)。

### 派生出力(派生チップ `↝`)は読み取り専用とする

マルチモーダルモデルを 1 つのステージへ主割当すると、同一推論が埋める他のアノテーション種類には派生チップ(`DerivedChip`)が読み取り専用で表示される。構成時に個別に外す手段は提供しない(`remove` は主割当のみを対象とする)。

派生出力は既定で採用する。構成時のオプトアウトを設けないのは、推論が固定スキーマで全種類を返す以上、UI 上で隠してもデータは生成・保存されるためである(表示と実体の乖離を防ぐ)。

不要な派生出力を事後に除外する方法は、出力種類によって非対称である。

- **`tags` / `caption`**: Results 画面のソフト却下(ADR 0065、`rejected_at`)により行単位で除外できる。
- **`score`**: 現状では行単位の却下経路がない(ADR 0065 の `rejected_at` は `tags` と `caption` のみ対象であり、`Score` テーブルに却下列がない)。そのため派生 `score` は採用されたまま残る。除外が必要になった場合は `score` への却下経路追加が前提となる(本 ADR の範囲外、後続課題)。

### 推論回数 = ユニークモデル数 × ステージング枚数

推論回数(課金単位および推論アイテム数)は「ユニークモデル数 × ステージング枚数」で決まる。同一モデルを複数のアノテーション種類へ充当しても、`litellm_model_id` で重複排除されるためコストは増えない(`InferenceLedger`)。

なお、この「推論アイテム」は、ADR 0066 の Jobs ライフサイクルビューが数える「ジョブ(Pipeline / Operation 粒度)」とは別の粒度である(下記「用語」を参照)。

### 実行環境セグメントの意味論(ADR 0030 を上書き)

ステージ別ピッカーにおける実行環境は `すべて (all)`、`APIのみ (api)`、`ローカルのみ (local)` の 3 値とし、既定値は `all` とする。

これは ADR 0030 の「環境未選択状態を持たず、初期値は `api` または `local` とする」という規定を上書きする(#889)。ステージ別ピッカーはステージ単位で候補を提示するため、環境を絞らず全候補から選べる初期状態(`all`)のほうが自然である。環境は、種類やプロバイダと並ぶ絞り込みの 1 軸として扱う。

### 用語

| 用語 | 意味 |
|---|---|
| ジョブ(job) | Pipeline / Operation 粒度の実行単位(ADR 0034 / 0066)。Jobs ライフサイクルビューに表示される。Provider Batch は `provider_batch_jobs` |
| 推論アイテム / 推論回数 | 1 モデル × 1 画像の推論。INFERENCE LEDGER が数える単位であり、ジョブとは別粒度 |
| アノテーション種類 | 出力の種類(`tags` / `caption` / `score` / `rating`) |
| `task_type` | Provider Batch の処理モード(`annotation` / `rating_preflight`)。アノテーション種類とは別軸 |

用語の混同を防ぐため、次のルールを守る。

- `tags` / `caption` / `score` / `rating` を「タスク」と呼ばない(Provider Batch の `task_type` と衝突する)。
- 1 モデル × 1 画像の推論を「ジョブ」と呼ばない(ADR 0066 の Pipeline / Operation 粒度のジョブと衝突する)。「推論アイテム」または「推論回数」を使う。
- 既存 `InferenceLedgerWidget` の表示ラベル「推論ジョブ合計」は本定義と不整合であるため、「推論回数」系へ寄せる修正を後続課題とする。

## Rationale

ステージ別ピッカーの実態を整理すると、ステージへの割り当ては選択モデル集合からの派生にすぎず、出力もコストも「選んだモデル」と「各モデルの能力」だけで決まる。ドメインモデルを「割り当て状態」中心で説明すると、本質的でない中間データを正本と誤認させる恐れがある。そのため、SSoT を選択モデル集合に置き、ステージ表示を派生ビューと位置づける。

また、固定スキーマと RATING 除外を ADR 0023 / 0031 に帰していたのは根拠の取り違えであり、正準を本 ADR へ置くことで今後の引用が安定する。実行環境の意味論は ADR 0030 の二段階フィルタを前提とした規定であり、ステージ別ピッカーでは成立しないため上書きする。

## Consequences

- ADR 0030(Batch Annotation Model Selection UI)における「二段階フィルタ」および「実行環境は `api` / `local` のみ」という決定は本 ADR で置き換える。本 ADR の Accepted 化と同時に ADR 0030 を Superseded へ切り替えた(#885)。
- `pipeline_composition.py` における固定スキーマと RATING 除外の引用先を、ADR 0023 / 0031 から本 ADR および ADR 0070 へ差し替える(#888)。
- ドメインモデルの説明や docstring は、「選択モデル集合(SSoT)と各モデルのアノテーション種類、ステージ表示は派生ビュー」を基準とする。
- `conf-min` による推論後フィルタは前提が成立せず撤去済みである(#851 / PR #886)。本 ADR はタグ単位の信頼度(confidence)に基づく機能を含まない。
- 実行時にモデル単位のタグ閾値が必要になった場合は、ライブラリ側の `annotate()` 拡張が前提となる(将来課題 #851)。

## Related

- ADR 0030: Batch Annotation Model Selection UI(本 ADR により Superseded)
- ADR 0065: Tag/Caption Soft-Reject And Export Resolution(派生出力の事後却下)
- ADR 0066: Unified Jobs Lifecycle View(ジョブ = 実行単位)
- ADR 0070: OpenAI Moderation WebAPI Preflight(rating の出どころ)
- ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary(誤引用是正の対象)
- ADR 0031: AI Rating Mapping to Canonical Rating(誤引用是正の対象)
- LoRAIro #885(ADR 0030 二段階フィルタからステージ別ピッカーへのドリフト)
- LoRAIro #887(本 ADR によるドメインモデルの記録)
- LoRAIro #888(ADR 0023 / 0031 誤引用の是正)
- LoRAIro #889(実行環境意味論の上書き)
- LoRAIro #741 / #839 / #845(ステージ別ピッカー刷新)
- LoRAIro #851 / PR #886(`conf-min` 撤去)
