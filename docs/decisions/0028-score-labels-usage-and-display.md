---
type: ADR
title: Score Labels Usage and Display Strategy
status: Accepted
timestamp: 2026-05-18
tags: []
---
# ADR 0028: Score Labels Usage and Display Strategy

## Context

ADR 0027 (PR #283) で canonical scorer (`aesthetic_shadow_v1/v2`, `cafe_aesthetic`) の
`score_labels` を新規 `score_labels` テーブルに永続化する経路を追加した。しかし現状は
**silent stored** で、GUI 表示・Export のどちらにも反映されていない。

ADR 0027 は明示的に「GUI / Export は本 ADR の範囲外 — 別 issue で追跡」と記載しており、
本 ADR でその後続を扱う。

GUI / Export 経路を設計するためには、まず **score_labels の実用上のユースケース**を
確定する必要がある。Issue #284 の planning フェーズで user と相談し、想定ユースケースを
評価した結果、本 ADR で採用 / 不採用を決定する。

## Decision

### 採用ユースケース (SSoT)

| ID | ユースケース | 採否 |
|---|---|---|
| **UC-A** | Quality Export Filter (**多数決方式の majority vote** で高評価画像のみ絞り込み) | ✓ |
| **UC-C** | 複数 scorer の判定不一致発見 (GUI annotation review) | ✓ |
| **UC-E** | データセット品質統計レポート (label 別 distribution) | ✓ |
| UC-B | LoRA 学習 caption への label 混入 (kohya-ss 形式の trigger word) | ✗ |
| UC-D | 検索 / フィルタリング機能 (`ImageFilterCriteria` 拡張) | △ (本 Issue scope 外、interface 指針のみ) |

### データ形状

`score_labels` annotation は **常に model 名と組で保持** する。

```python
annotations["score_labels"] = [
    {"label": "very aesthetic", "model": "aesthetic_shadow_v1",
     "model_id": 1, "is_edited_manually": False},
    {"label": "aesthetic",      "model": "aesthetic_shadow_v2",
     "model_id": 2, "is_edited_manually": False},
    {"label": "very aesthetic", "model": "cafe_aesthetic",
     "model_id": 3, "is_edited_manually": False},
]
```

**Scalar shorthand (`score_label_value` 等の single-latest field) は採用しない**。
理由は Rationale 参照。

### 表示戦略 (GUI)

- 新 `groupBoxScoreLabels` を `groupBoxScores` の直後に追加
- 内部は compact pill コンテナ (`QHBoxLayout`) で各 scorer model 1 pill
- 各 pill のテキスト: `[<model_name>] <label>` 形式
  (例: `[aesthetic_shadow_v1] very aesthetic`)
- pill 数上限なし (canonical scorer は通常 2-4 model のため過剰描画は発生しない)
- `set_group_box_visibility(..., score_labels: bool = True)` で表示制御 (backward compatible)

### Export 戦略

| Format | score_labels の扱い |
|---|---|
| **JSON** | `metadata[path]["score_labels"] = [{"model": str, "label": str, ...}, ...]` で構造化 list を埋め込む |
| **TXT** | 出力なし (Caption file / Tags file への混入禁止、ADR 0027 の content tag 専用化原則と一致) |

### 将来拡張 (本 Issue scope 外、別 Issue で実装)

#### Filter 機能 (UC-A の核、別 Issue)

`ImageFilterCriteria` に以下の interface を追加することを **本 ADR で予約**:

```python
# 単一 label / model match
score_label_filter: list[ScoreLabelMatch] | None = None
# 多数決方式
score_label_majority_filter: ScoreLabelMajorityFilter | None = None
```

```python
class ScoreLabelMatch(TypedDict):
    label: str             # 例: "very aesthetic"
    model: NotRequired[str]  # 省略時は全 scorer model に match

class ScoreLabelMajorityFilter(TypedDict):
    target_labels: list[str]      # 例: ["very aesthetic", "aesthetic"]
    min_consensus_count: int      # 例: 2 (= 2 scorer 以上が target_labels の何れか)
```

#### Statistics Report (UC-E, 別 Issue)

データセット全体の label distribution を集計する viewer / CSV export 機能を別 Issue で
追跡。最低限の出力構造:

```text
| model              | label          | count |
|--------------------|----------------|-------|
| aesthetic_shadow_v1| very aesthetic | 1200  |
| aesthetic_shadow_v1| aesthetic      | 5000  |
| aesthetic_shadow_v1| displeasing    | 200   |
```

## Rationale

### なぜ「常に model 名と組で保持」か

UC-A の核である **多数決方式 majority vote** は「複数 scorer の判定を集約して
target labels に何件 match するか」を判定する。`{model, label}` ペアを失うと:

- 同じ model で複数 row が存在した場合 (= 再 annotation 履歴) の重複扱いが不可能
- 「scorer A は very aesthetic, scorer B は displeasing」のような不一致を検出不能
- UC-C の不一致発見が成立しない

よって model 名は **データ層 → GUI → Export の全経路で必ず保持** する。

### なぜ Scalar shorthand を採用しないか

既存 `score_value` / `rating_value` のような single-latest scalar は、numeric score / rating で
「最新の数値」を取得するのに有用 (1 model から 1 数値、time-series で latest が意味を持つ)。

しかし score_labels は **multi-scorer の categorical** で、latest 1 件のみ取り出すと:

- UC-A 多数決の入力にならない (集約計算の母集団が消える)
- UC-C 不一致発見の前提が崩れる (1 model 分の判定しか持たない)

よって `score_label_value` は明示的に **作らない**。GUI も Export も常に list 全体を消費する。

### なぜ TXT format に出力しないか

UC-B (LoRA caption への label 混入) を不採用としたため、TXT format への混入を行う
ユースケースが存在しない。さらに ADR 0027 で `Tag` テーブルを content tag 専用化する
方針 (`score_labels` を別テーブルに分離) と整合させるため、TXT (= tag / caption flat
file) には混入させない。

将来 UC-B 相当のニーズが発生した場合は別 ADR / 別 Issue で再評価する。

### なぜ UC-B を不採用としたか

ADR 0027 で「`Tag` テーブルは content tag 専用、`score_labels` テーブルは scorer 由来
categorical 専用」と分離を確立した。caption file (= 学習時 prompt source) に
score_labels を混入させると:

- content semantics と quality semantics が混在し、学習データ汚染リスク
- 整数 bin tag (`[CAFE]score_N`) を LoRAIro 側で再生成しない方針 (ADR 0027) と緊張

User 確認 (planning) でも本ユースケースの優先度は **不採用** とした。

### なぜ UC-D (Filter) を本 Issue scope 外としたか

UC-A の Filter 実装は `ImageFilterCriteria` への multi-field 拡張 + majority vote 計算 +
SQL クエリ最適化を含み、本 Issue (GUI 表示 + JSON export) と独立した実装規模。
責務分離のため別 Issue で扱い、本 ADR では interface 指針のみ予約する。

## Consequences

### 良い点

- canonical scorer の score_labels が GUI で全 scorer 並列表示され、UC-C (不一致発見) が成立
- JSON export に構造化 list で含まれ、後続の UC-A Filter / UC-E Statistics の入力として
  そのまま使える
- model 名と組で保持する設計が SSoT として ADR 0027 / iam-lib ADR 0002 と整合
- Scalar shorthand を作らないことで multi-scorer 集約の semantic を維持
- TXT format の content semantics が汚染されない

### 悪い点・トレードオフ

- GUI で多 scorer (5+ 個) を有効化した場合、pill が横長に並んで視認性が低下する可能性
  (回避: 通常運用で 2-4 scorer のため許容、将来は wrap policy 検討)
- JSON export の structured list を消費する側 (downstream tool) で `{model, label}` を
  unpack する処理が必要 (既存 consumer 0 件、本 Issue 完了で初の経路)
- Filter / Statistics の本実装が別 Issue 持ち越しのため、UC-A / UC-E の体験完成は
  follow-up Issue 完了まで待つ

### 運用ルール

- `score_labels` の GUI 表示は `_update_score_labels_display(list[dict])` のみ
- JSON export key は `"score_labels"` (plural snake_case)、構造は本 ADR で確定した形状
- 別 Issue で Filter 実装する際は本 ADR の `ScoreLabelMatch` / `ScoreLabelMajorityFilter`
  interface を採用 (変更時は本 ADR を update)

## Related

- **Issue**: NEXTAltair/LoRAIro#284
- **親 ADR**: 0027 (Score Labels DB Storage)
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **関連 ADR (先例)**:
  - 0015 (Manual Rating Storage Unification) — 別テーブル化先例
  - 0019 (Export Filter Required Design) — Export filter の必須化方針
  - 0023 (PydanticAI/LiteLLM WebAPI Inference Boundary) — annotation result contract
- **親 PR (merged)**: NEXTAltair/LoRAIro#283 (DB 保存経路 + ADR 0027)
- **本 ADR 実装 PR**: NEXTAltair/LoRAIro#284 (本 Issue で起票予定)
- **Follow-up Issues 候補**:
  - Filter 実装 (`ImageFilterCriteria.score_label_filter` + majority vote)
  - Statistics report (label distribution viewer / CSV export)