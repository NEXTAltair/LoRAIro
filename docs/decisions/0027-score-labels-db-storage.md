# ADR 0027: Score Labels DB Storage

- **日付**: 2026-05-17
- **ステータス**: Accepted

## Context

image-annotator-lib ADR 0002 (PR #67 / 実装 PR #68) で
`UnifiedAnnotationResult.score_labels: list[str] | None` field が新設され、
canonical scorer (`aesthetic_shadow_v1/v2`, `cafe_aesthetic`) が
`["very aesthetic"]` / `["aesthetic"]` / `["displeasing"]` / `["not_aesthetic"]`
を返すようになった。

しかし LoRAIro 側 `src/lorairo/services/annotation_save_service.py:_append_model_result`
は `scores` / `tags` / `captions` / `ratings` のみを `AnnotationsDict` に積み、
`score_labels` を **silent drop** していた。canonical scorer 出力の重要部分が
DB に永続化されない状態。

Issue #281 でこの経路欠落を解消するため、新規 DB 領域を設計する必要がある。

## Decision

新しい `score_labels` テーブル (SQLAlchemy model `ScoreLabel`) を新設する。
`Tag` / `Caption` / `Score` / `Rating` テーブルと parallel な構造で、
`(image_id, model_id, label, is_edited_manually, timestamps)` を持つ。

- `AnnotationsDict.score_labels: NotRequired[list[ScoreLabelAnnotationData]]` を追加
- `ImageRepository._save_score_labels()` は `_save_ratings` と同じ
  `model_id` キーの Upsert pattern を採る (1 image × 1 model = 1 label)
- `AnnotationSaveService._append_model_result` を拡張し `score_labels` を
  `result["score_labels"]` に積む

GUI 表示 / Export 経路は本 ADR の範囲外 — Issue #281 完了後に別 issue で追跡する。

## Rationale

### 候補比較

| 候補 | 採否 | 理由 |
|---|---|---|
| Option 1: `Score` テーブルに `label` 列を追加 | ✗ | AestheticShadow は `scores={"hq": x, "lq": 1-x}` で 2 Score 行 + 1 label を返す。両 row に同じ label を入れるか null を許容するか非自明、データセマンティクス歪み |
| **Option 2: 新 `score_labels` テーブル** | ✓ | `(image_id, model_id, label)` で 1 row、`Tag`/`Caption`/`Rating` テーブルと parallel pattern、ADR 0015 (Manual Rating Storage Unification) の先例に従う |
| Option 3: `ScoreAnnotationData` を nested dict に拡張 | ✗ | TypedDict 互換性 + 既存 `_save_scores` への破壊的変更が広範 |

### ADR 0015 との対称性

ADR 0015 で manual rating を `ratings` テーブルに統一する判断と同じ方針:
**「異なる意味を持つアノテーション系は独立テーブルに分離する」**。
score (数値) と label (categorical) は意味が異なる別 dimension のため分離。

この方針は「外部モデルごとの label scheme ごとに新テーブルを作る」という意味ではない。
ADR 0031 の model-native rating は、Danbooru / e621 / Sankaku / binary NSFW のように
scheme が異なっても rating という同一 dimension であり、既存 `ratings` テーブルに保存する。
LoRAIro canonical rating への変換は mapper の責務で、DB schema の追加では扱わない。

### iam-lib ADR 0002 との対称性

iam-lib ADR 0002 で `tags` field と `score_labels` field を独立に保つ判断と
LoRAIro 側 DB レイヤーが対称になる:
- `tags` テーブル = content tag (WDTagger 等)
- `score_labels` テーブル = score-derived categorical label (canonical scorer)

両者を field/テーブルレベルで分離することで、検索 / Export / GUI 表示で
content tag と score categorical label を区別可能にする。

### 整数 bin tag (`[CAFE]score_N`) を LoRAIro 側で再生成しない

iam-lib ADR 0002 で「整数 bin tag (`[CAFE]score_N` / `[IAP]score_N` /
`[WD]score_N`) は配布元保証外の arbitrary policy として lib 標準出力から排除」と
決定済み。LoRAIro 全コード (`src/` + `tests/`) を inventory した結果、これらの
リテラルを参照する consumer は **0 件** (Issue #281 調査時点)。

よって LoRAIro 側で再現する必要はなく、再導入が必要になった consumer は raw
`scores` から派生実装する。

## Consequences

### 良い点

- canonical scorer の `score_labels` が DB に永続化される (silent drop 解消)
- `tags` テーブルが content tag 専用に純化され、検索 / Export の意味が明確
- 既存 `Score` テーブル schema は変更なし — 後方互換性が保たれる
- `(image_id, model_id)` 単位の 1 label 設計で GUI 表示が単純 (max(created_at)
  等の集約が不要)

### 悪い点・トレードオフ

- 新テーブル追加に伴う Alembic migration が必要 (新規 user は影響なし、既存
  user は `alembic upgrade head` で空テーブル追加)
- GUI 表示 / Export 経路は別 issue で対応するまで silent stored (DB には積まれるが
  表示されない期間が発生)
- canonical scorer の `score_labels` 仕様 (現状 list[str] 単一要素) が将来複数要素
  になった場合、`_save_score_labels` の Upsert pattern を再検討する必要 (現状は
  最後の 1 つだけが残る既知挙動、`_save_scores` と同じ)

### 運用ルール

- `score_labels` テーブルへの書き込みは `_save_score_labels` のみ。手動 UPSERT は
  原則行わない (`is_edited_manually=True` で書きたい場合のみ手動経路を新設)
- migration `a7b8c9d0e1f2_add_score_labels_table` は冪等 (`upgrade` で
  `create_table`、`downgrade` で `drop_table` — 既存テーブル / column 触らず)
- GUI / Export 経路の追加は別 issue で扱う

## Related

- **Issue**: NEXTAltair/LoRAIro#281
- **iam-lib Issue (closed)**: NEXTAltair/image-annotator-lib#66
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **LoRAIro 先例 ADR**:
  - 0015 (Manual Rating Storage Unification) — 別テーブル化の先例
  - 0023 (PydanticAI/LiteLLM WebAPI Inference Boundary) — annotation result contract
  - 0031 (AI Rating Mapping to Canonical Rating) — model-native rating は既存 `ratings` テーブルに保存
- **LoRAIro 起源 issue**: #273 (closed/migrated to iam-lib #66)
- **submodule pin update PR (merged)**: #282
