---
type: ADR
title: Score Labels DB Storage
status: Accepted
timestamp: 2026-05-17
tags: []
---
# ADR 0027: Score Labels DB Storage

## Context

image-annotator-lib ADR 0002(PR #67、実装 PR #68)により、`UnifiedAnnotationResult.score_labels: list[str] | None` フィールドが新設された。これに伴い、正規 scorer(`aesthetic_shadow_v1/v2`、`cafe_aesthetic`)が `["very aesthetic"]`・`["aesthetic"]`・`["displeasing"]`・`["not_aesthetic"]` などのラベルを返すようになった。

しかし、LoRAIro 側の `src/lorairo/services/annotation_save_service.py:_append_model_result` は、`scores`・`tags`・`captions`・`ratings` のみを `AnnotationsDict` に格納しており、`score_labels` を暗黙に破棄(silent drop)していた。正規 scorer 出力の重要な情報が DB に永続化されない状態であった。

Issue #281 でこの経路欠落を解消するため、新規 DB 領域を設計する必要がある。

## Decision

新しい `score_labels` テーブル(SQLAlchemy モデル `ScoreLabel`)を新設する。`Tag`・`Caption`・`Score`・`Rating` テーブルと並列な構造とし、`(image_id, model_id, label, is_edited_manually, timestamps)` を保持する。

- `AnnotationsDict.score_labels: NotRequired[list[ScoreLabelAnnotationData]]` を追加する。
- `ImageRepository._save_score_labels()` は `_save_ratings` と同じく `model_id` をキーとした Upsert パターンを採用する(1 画像 × 1 モデルにつき 1 ラベル)。
- `AnnotationSaveService._append_model_result` を拡張し、`score_labels` を `result["score_labels"]` に格納する。

GUI 表示およびエクスポート経路は本 ADR の範囲外とし、Issue #281 完了後に別 Issue で追跡する。

## Rationale

### 候補比較

| 候補 | 採否 | 理由 |
|---|---|---|
| Option 1: `Score` テーブルに `label` 列を追加する | ✗ | AestheticShadow は `scores={"hq": x, "lq": 1-x}` として 2 件の Score 行と 1 つのラベルを返す。両行に同じラベルを入れるか NULL を許容するかが非自明であり、データの意味論が歪む。 |
| **Option 2: 新しい `score_labels` テーブルを作る** | ✓ | `(image_id, model_id, label)` で 1 行に収まり、`Tag` / `Caption` / `Rating` テーブルと並列な構造になる。ADR 0015(Manual Rating Storage Unification)の先例にも従う。 |
| Option 3: `ScoreAnnotationData` をネスト辞書へ拡張する | ✗ | `TypedDict` の互換性や既存 `_save_scores` への破壊的変更が広範に及ぶ。 |

### ADR 0015 との対称性

ADR 0015 で手動レーティングを `ratings` テーブルへ統一した判断と同じく、**「異なる意味を持つアノテーション系統は独立テーブルに分離する」**という方針を採る。スコア(数値)とラベル(カテゴリ値)は意味が異なる別次元であるため、テーブルを分離する。

なお、この方針は「外部モデルのラベル体系ごとに新テーブルを作る」という意味ではない。ADR 0031 のモデル固有レーティングは、Danbooru・e621・Sankaku・binary NSFW のように体系が異なっても「レーティング」という同一の次元であるため、既存の `ratings` テーブルに保存する。LoRAIro の正規レーティングへの変換はマッパーの責務とし、DB スキーマの追加では扱わない。

### image-annotator-lib ADR 0002 との対称性

image-annotator-lib ADR 0002 で `tags` フィールドと `score_labels` フィールドを独立させた判断と、LoRAIro 側の DB 層が対称になる。

- `tags` テーブル: コンテンツタグ(WDTagger 等)
- `score_labels` テーブル: スコア由来のカテゴリラベル(正規 scorer)

両者をフィールドおよびテーブル単位で分離することで、検索・エクスポート・GUI 表示においてコンテンツタグとスコア由来ラベルを明確に区別できる。

### 整数ビンタグ(`[CAFE]score_N`)を LoRAIro 側で再生成しない理由

image-annotator-lib ADR 0002 では、整数ビンタグ(`[CAFE]score_N` / `[IAP]score_N` / `[WD]score_N`)について「配布元保証外の独自ポリシーであるためライブラリ標準出力から排除する」と決定している。Issue #281 の調査時点で LoRAIro 全コード(`src/` および `tests/`)を棚卸しした結果、これらのリテラルを参照する箇所は 0 件であった。

したがって、LoRAIro 側でこれらを再生成する必要はない。将来必要になった利用箇所があれば、生の `scores` から派生実装する。

## Consequences

### 良い点

- 正規 scorer の `score_labels` が DB に永続化され、暗黙破棄が解消される。
- `tags` テーブルがコンテンツタグ専用に純化され、検索およびエクスポートの意味が明確になる。
- 既存の `Score` テーブルスキーマは変更しないため、後方互換性が保たれる。
- `(image_id, model_id)` 単位で 1 ラベルとする設計により、`max(created_at)` などの集約が不要になり GUI 表示が単純になる。

### 悪い点・トレードオフ

- 新テーブル追加に伴い Alembic マイグレーションが必要になる。新規ユーザーには影響しないが、既存ユーザーは `alembic upgrade head` で空テーブルを追加する必要がある。
- GUI 表示とエクスポート経路が別 Issue で対応されるまで、DB には保存されるが表示されない期間(silent stored)が生じる。
- 正規 scorer の `score_labels` 仕様(現状は単一要素の `list[str]`)が将来複数要素になった場合、`_save_score_labels` の Upsert パターンを再検討する必要がある。現状は最後の 1 件のみが残る既知の挙動であり、`_save_scores` と同じである。

### 運用ルール

- `score_labels` テーブルへの書き込みは `_save_score_labels` のみで行う。手動 UPSERT は原則行わず、`is_edited_manually=True` で書き込みたい場合のみ手動経路を新設する。
- マイグレーション `a7b8c9d0e1f2_add_score_labels_table` は冪等とする(`upgrade` で `create_table`、`downgrade` で `drop_table` を行い、既存テーブルやカラムには触れない)。
- GUI 表示およびエクスポート経路の追加は別 Issue で扱う。

## Related

- **Issue**: NEXTAltair/LoRAIro#281
- **iam-lib Issue(クローズ済み)**: NEXTAltair/image-annotator-lib#66
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **LoRAIro 先例 ADR**:
  - 0015(Manual Rating Storage Unification)— 別テーブル化の先例
  - 0023(PydanticAI / LiteLLM WebAPI Inference Boundary)— アノテーション結果契約
  - 0031(AI Rating Mapping to Canonical Rating)— モデル固有レーティングは既存 `ratings` テーブルに保存
- **LoRAIro 起源 Issue**: #273(クローズ・iam-lib #66 へ移管)
- **サブモジュールピン更新 PR(マージ済み)**: #282
