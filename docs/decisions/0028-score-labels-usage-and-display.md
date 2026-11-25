---
type: ADR
title: Score Labels Usage and Display Strategy
status: Accepted
timestamp: 2026-05-18
tags: []
---
# ADR 0028: Score Labels Usage and Display Strategy

## Context

ADR 0027(PR #283)により、正規 scorer(`aesthetic_shadow_v1/v2`、`cafe_aesthetic`)の `score_labels` を新規 `score_labels` テーブルへ永続化する経路を追加した。しかし現状は DB に保存されるだけで、GUI 表示にもエクスポートにも反映されていない(silent stored)。

ADR 0027 では「GUI 表示とエクスポートは本 ADR の範囲外とし、別 Issue で追跡する」と明記している。本 ADR はその後続として、表示およびエクスポート方針を定める。

GUI とエクスポートの経路を設計するには、まず `score_labels` の実用上のユースケースを確定する必要がある。Issue #284 の計画フェーズでユーザーと相談し、想定ユースケースを評価したうえで、本 ADR で採否を決定する。

## Decision

### 採用ユースケース(SSoT)

| ID | ユースケース | 採否 |
|---|---|---|
| **UC-A** | 品質エクスポートフィルタ(**多数決方式**で高評価画像のみを絞り込む) | ✓ |
| **UC-C** | 複数 scorer 間の判定不一致の発見(GUI アノテーションレビュー) | ✓ |
| **UC-E** | データセット品質統計レポート(ラベル別分布) | ✓ |
| UC-B | LoRA 学習キャプションへのラベル混入(kohya-ss 形式のトリガーワード) | ✗ |
| UC-D | 検索・フィルタリング機能(`ImageFilterCriteria` 拡張) | △(本 Issue スコープ外、インターフェース指針のみ) |

### データ形状

`score_labels` アノテーションは、**常にモデル名と組で保持する**。

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

**スカラー短縮形(`score_label_value` 等の最新 1 件フィールド)は採用しない。** 理由は Rationale を参照すること。

### GUI の表示戦略

- 新しい `groupBoxScoreLabels` を `groupBoxScores` の直後に追加する。
- 内部はコンパクトなピルコンテナ(`QHBoxLayout`)とし、各 scorer モデルにつき 1 ピルを表示する。
- 各ピルのテキストは `[<model_name>] <label>` 形式とする(例: `[aesthetic_shadow_v1] very aesthetic`)。
- ピル数に上限は設けない。正規 scorer は通常 2〜4 モデルであるため、過剰な描画は発生しない。
- `set_group_box_visibility(..., score_labels: bool = True)` で表示を制御し、後方互換性を維持する。

### エクスポート戦略

| 形式 | `score_labels` の扱い |
|---|---|
| **JSON** | `metadata[path]["score_labels"] = [{"model": str, "label": str, ...}, ...]` として構造化リストを埋め込む |
| **TXT** | 出力しない(キャプションファイル・タグファイルへの混入を禁止し、ADR 0027 のコンテンツタグ専用化原則と一致させる) |

### 将来拡張(本 Issue スコープ外、別 Issue で実装)

#### フィルタ機能(UC-A の中核、別 Issue)

`ImageFilterCriteria` に以下のインターフェースを追加することを、**本 ADR で予約する**。

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

#### 統計レポート(UC-E、別 Issue)

データセット全体のラベル分布を集計するビューアおよび CSV エクスポート機能を別 Issue で追跡する。最低限の出力構造は以下のとおりである。

```text
| model              | label          | count |
|--------------------|----------------|-------|
| aesthetic_shadow_v1| very aesthetic | 1200  |
| aesthetic_shadow_v1| aesthetic      | 5000  |
| aesthetic_shadow_v1| displeasing    | 200   |
```

## Rationale

### なぜ常にモデル名と組で保持するか

UC-A の中核である**多数決方式(majority vote)**では、複数 scorer の判定を集約し、`target_labels` に何件一致するかを判定する。`{model, label}` の組を失うと、次の問題が起きる。

- 同一モデルで複数行が存在した場合(再アノテーション履歴など)の重複処理ができない。
- 「scorer A は `very aesthetic`、scorer B は `displeasing`」のような不一致を検出できない。
- UC-C の不一致発見が成立しない。

したがって、モデル名はデータ層から GUI、エクスポートまでの全経路で必ず保持する。

### なぜスカラー短縮形を採用しないか

既存の `score_value` や `rating_value` のような最新 1 件スカラーは、数値スコアやレーティングにおいて最新の値を取得するのに有用である。1 モデルから 1 数値が返り、時系列での最新値に意味があるためである。

しかし、`score_labels` は複数 scorer によるカテゴリ値である。最新 1 件だけを取り出すと、次の欠陥が生じる。

- UC-A の多数決計算に必要な母集団が失われる。
- 1 モデル分の判定しか残らないため、UC-C の不一致発見が成り立たない。

そのため、`score_label_value` は明示的に作成しない。GUI もエクスポートも常にリスト全体を消費する。

### なぜ TXT 形式に出力しないか

UC-B(LoRA キャプションへのラベル混入)を不採用としたため、TXT 形式へ混入するユースケースが存在しない。さらに、ADR 0027 で `Tag` テーブルをコンテンツタグ専用とし、`score_labels` を別テーブルへ分離した方針とも整合させるため、TXT(タグ・キャプションのフラットファイル)には出力しない。

将来 UC-B 相当の需要が生じた場合は、別 ADR または別 Issue で再評価する。

### なぜ UC-B を不採用としたか

ADR 0027 では、`Tag` テーブルをコンテンツタグ専用、`score_labels` テーブルを scorer 由来カテゴリ専用として分離を確立した。キャプションファイル(学習時のプロンプト元)に `score_labels` を混入させると、次の問題が生じる。

- コンテンツの意味情報と品質の意味情報が混在し、学習データが汚染されるリスクがある。
- 整数ビンタグ(`[CAFE]score_N`)を LoRAIro 側で再生成しない方針(ADR 0027)と矛盾する。

計画フェーズでのユーザー確認でも、本ユースケースは不採用と確定した。

### なぜ UC-D(フィルタ)を本 Issue のスコープ外としたか

UC-A のフィルタ実装には、`ImageFilterCriteria` の複数フィールド拡張、多数決計算、SQL クエリ最適化が含まれる。本 Issue(GUI 表示と JSON エクスポート)とは独立した実装規模になるため、責務分離の観点から別 Issue で扱い、本 ADR ではインターフェース指針の予約にとどめる。

## Consequences

### 良い点

- 正規 scorer の `score_labels` が GUI で全 scorer 並列表示され、UC-C(不一致発見)が成立する。
- JSON エクスポートに構造化リストとして含まれるため、後続の UC-A フィルタや UC-E 統計の入力としてそのまま利用できる。
- モデル名と組で保持する設計が SSoT として ADR 0027 および iam-lib ADR 0002 と整合する。
- スカラー短縮形を作らないことで、複数 scorer 集約の意味論を維持できる。
- TXT 形式のコンテンツ意味論が汚染されない。

### 悪い点・トレードオフ

- GUI で多数の scorer(5 個以上)を有効化すると、ピルが横長に並んで視認性が低下する可能性がある。通常運用は 2〜4 scorer のため許容し、必要になれば将来折り返し方針を検討する。
- JSON エクスポートの構造化リストを消費する下流ツールでは、`{model, label}` を展開する処理が必要になる(既存利用箇所は 0 件であり、本 Issue 完了が初の経路となる)。
- フィルタと統計の本実装を別 Issue に持ち越すため、UC-A と UC-E の体験完成は後続 Issue の完了を待つ必要がある。

### 運用ルール

- `score_labels` の GUI 表示は `_update_score_labels_display(list[dict])` のみで行う。
- JSON エクスポートのキーは `"score_labels"`(複数形 snake_case)とし、構造は本 ADR で確定した形状に従う。
- 別 Issue でフィルタを実装する際は、本 ADR の `ScoreLabelMatch` および `ScoreLabelMajorityFilter` インターフェースを採用する(変更時は本 ADR を更新する)。

## Related

- **Issue**: NEXTAltair/LoRAIro#284
- **親 ADR**: 0027(Score Labels DB Storage)
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **関連 ADR(先例)**:
  - 0015(Manual Rating Storage Unification)— 別テーブル化の先例
  - 0019(Export Filter Required Design)— エクスポートフィルタの必須化方針
  - 0023(PydanticAI / LiteLLM WebAPI Inference Boundary)— アノテーション結果契約
- **親 PR(マージ済み)**: NEXTAltair/LoRAIro#283(DB 保存経路および ADR 0027)
- **本 ADR 実装 PR**: NEXTAltair/LoRAIro#284(本 Issue で起票予定)
- **後続 Issue 候補**:
  - フィルタ実装(`ImageFilterCriteria.score_label_filter` および多数決方式)
  - 統計レポート(ラベル分布ビューアおよび CSV エクスポート)
