# ADR 0029: Unified Dataset Quality Tier

- **日付**: 2026-05-19
- **ステータス**: Accepted

## Context

ADR 0027 で scorer 由来の categorical label を `score_labels` テーブルに保存し、
ADR 0028 で `{model, label}` の raw list を GUI / JSON export に表示する経路を追加した。

しかし LoRA 学習用データセット作成では、scorer ごとの raw value を直接指定する filter は
使いにくい。

- `aesthetic_shadow_v1/v2` は `very aesthetic` / `aesthetic` /
  `displeasing` / `very displeasing` を返す
- `cafe_aesthetic` は `aesthetic` / `not_aesthetic` を返す
- 手動 score は 0.00-10.00 の DB float (UI は 0-1000)
- regression scorer は model ごとに scale が異なる

ユーザーが dataset export/search で求めている操作は、個別 scorer の詳細条件ではなく
「一定水準以上の画像」「低品質候補」「未採点画像」の抽出である。したがって LoRAIro 側に
検索・表示用の統一品質 tier が必要。

なお、NovelAI / Danbooru / 現代 anime diffusion model 文化では
`masterpiece`, `best quality`, `good quality`, `normal quality`, `low quality`,
`worst quality` が広く使われている。例として Anima は
`masterpiece ... worst quality` を human score based quality tags とし、別系統の
`score_9 ... score_1` を aesthetic model based tags として併用している。NovelAI 公式も
quality tags と aesthetic tags を分離しているが、prompt 実務では両者が品質表現として
近接して使われる。

LoRAIro はこの慣れた語彙を UI / filter value に採用する。ただし外部モデル共通の客観基準
としてではなく、LoRAIro 独自の **dataset quality tier** として定義する。

## Decision

### Raw annotation は変更しない

`scores` / `score_labels` に保存済みの model raw output は変更しない。
統一品質 tier は raw annotation の上に乗る derived view とする。

```text
raw scores / score_labels
  -> quality mapping
  -> dataset quality tier
  -> GUI badge / JSON export / search filter
```

mapping を変更しても DB の raw annotation は書き換えない。検索結果と表示だけが新 mapping に
従って再計算される。

### Tier vocabulary

検索 UI / API / JSON export の表示語彙は以下を採用する。

| tier | 用途 |
|---|---|
| `masterpiece` | 最上位。強い採用候補 |
| `best quality` | 高品質。採用候補 |
| `good quality` | 実用上採用可能 |
| `normal quality` | 中立。明確な高品質ではないが除外とも言い切れない |
| `low quality` | 低品質。除外候補 |
| `worst quality` | 最低品質。強い除外候補 |
| `no score` | score 系 annotation が存在しない |
| `unknown` | raw value は存在するが mapping 未定義 |

`no score` と `unknown` は分離する。未採点画像の抽出と、新 model / 未定義 label の検出は
別ユースケースだからである。

### Initial mapping

初期 mapping は canonical scorer と manual score を対象にする。

```text
aesthetic_shadow_v1 / aesthetic_shadow_v2:
  very aesthetic     -> masterpiece
  aesthetic          -> best quality
  displeasing        -> low quality
  very displeasing   -> worst quality

cafe_aesthetic:
  aesthetic          -> good quality
  not_aesthetic      -> low quality

manual score (0.00-10.00):
  9.00-10.00         -> masterpiece
  8.00-8.99          -> best quality
  6.00-7.99          -> good quality
  5.00-5.99          -> normal quality
  3.00-4.99          -> low quality
  0.00-2.99          -> worst quality
```

`ImprovedAesthetic` / `WaifuAesthetic` などの regression scorer は初期 mapping から外す。
これらは scale と閾値の意味が model-specific であり、ADR 0022 / iam-lib ADR 0002 で
model 横断比較不可と整理済みである。後続 ADR で閾値を決めた場合のみ mapping に追加する。

### Aggregation rule (集約規約)

1 image に複数 scorer の `score_labels` と manual score がある場合、それぞれを
**vote** として扱い、統一 tier に集約する。集約は **median + is_unanimous hybrid**
方式を採用する。

- `votes` を known (mapping 定義済) / unknown (mapping 未定義) に分類する。
- known votes が 1 件以上ある場合:
  - `tier` = known votes の tier を順序尺度に変換しソートした **中央値**。
    偶数件の tie は higher 寄り (`sorted_tiers[len // 2]`) で決定的に解決する。
  - `is_unanimous` = 全 known votes が同一 tier かつ unknown vote が 0 件のとき `true`。
- known votes が 0 件で vote 自体は存在する場合 → `tier = "unknown"`。
- vote が 1 件も無い場合 → `tier = "no score"`、`no_score = true`。

median を採用する理由は Rationale 参照。`is_unanimous` は per-scorer pill
(ADR 0028) を見なくても scorer 合意の有無を 1 field で判定できるようにするための
補助 signal である。

集約パターンの比較検討 (median / most common / lowest / highest / mixed sentinel /
votes-only) は #287 の planning フェーズで実施した。median は順序尺度として安定で
filter の `min_tier` 比較と整合し、`is_unanimous` で不一致 (UC-C) も表現できる。

### Search filter behavior

dataset search/export filter は model-specific raw value ではなく tier を主 interface にする。

```python
class QualityTierFilter(TypedDict):
    min_tier: str  # e.g. "good quality"
    vote_mode: str  # "any" | "majority" | "all"
    no_score_mode: str  # "exclude" | "include" | "only"
```

想定 UI:

```text
品質: good quality 以上
一致条件: 1件以上 / 過半数 / 全件
未採点: 除外 / 含める / 未採点のみ
```

`min_tier` 比較では、上位から下位の順序を以下で固定する。

```text
masterpiece > best quality > good quality > normal quality > low quality > worst quality
```

`unknown` は既定では条件一致に含めない。必要な場合は別 UI / filter で抽出する。

### Export / GUI

JSON export では raw `score_labels` を維持し、追加で `quality_summary` を出力する。

```json
{
  "score_labels": [
    {"model": "aesthetic_shadow_v2", "label": "aesthetic"}
  ],
  "quality_summary": {
    "mapping_version": "quality-tier-v1",
    "tier": "best quality",
    "is_unanimous": true,
    "known_count": 1,
    "unknown_count": 0,
    "no_score": false,
    "votes": [
      {
        "model": "aesthetic_shadow_v2",
        "source": "score_label",
        "raw_label": "aesthetic",
        "quality_tier": "best quality"
      }
    ]
  }
}
```

`votes[]` 要素は `source` で `"score_label"` / `"manual_score"` を識別し、
score_label は `raw_label`、manual_score は `raw_score` (float) を持つ。
unknown vote は `quality_tier = "unknown"` (sentinel) を出力する。

GUI は ADR 0028 の per-scorer pill を残し、統一 tier は別 badge として `groupBoxScoreLabels`
内の最上段に単一 QLabel で併記する (例: `品質: best quality (2 scorer)` / `品質: masterpiece
(3 scorer) (全 scorer 一致)`)。`tier="no score"` / `"unknown"` のときは known_count 抜きで
`品質: no score` / `品質: unknown` を表示する。`quality_summary` が空 dict のときは
badge を hide する (旧データ互換、graceful fallback)。

TXT export には出力しない (ADR 0028 と同じ理由: content tag 専用 file 汚染を避ける)。

### Mapping SSoT

mapping SSoT は **code module** `src/lorairo/domain/quality_tier.py` とする。

- `QualityTier` (IntEnum、順序尺度) と `(model, label) -> QualityTier` の dict 定数、
  manual score の range mapping 関数、`MAPPING_VERSION` 定数を持つ。
- `compute_quality_summary(score_labels, scores) -> dict` が derived view を計算する。
- `database` / `services` / `gui` 層は `domain` を一方向 import する (循環なし)。

TOML config (`src/lorairo/config/quality_tier_mapping.toml`) によるユーザー override は
本 ADR の scope 外とし、必要になった時点で別 ADR / `mapping_version` v2 で検討する。

mapping はアプリ仕様であり user annotation ではない。DB に保存すると migration / seed /
stale derived data の負担が大きいため、性能課題が出るまで derived calculation に留める。
`get_image_annotations()` が戻り値 dict に `quality_summary` キーを derived 計算で含める。

### Continuous display score (#626 追補)

tier badge (離散 6 段階) とは **別に**、AI 数値スコアを手動スライダーと同じ
**0.0-10.0 の連続表示スコア** (`score_value`) として提供する。両者は役割分担する:

| 観点 | tier badge (本 ADR 本体) | display score (#626) |
|---|---|---|
| 値域 | 離散 6 段階 (`masterpiece` ... `worst quality`) | 連続 0.0-10.0 |
| 入力 | `score_labels` (categorical) + manual score | scorer の数値 `scores` (positive key) + manual score |
| SSoT | `domain/quality_tier.py` | `domain/score_scaler.py` |
| 用途 | フィルタ / 多数決サマリー badge | スライダー初期値 / 数値表示 |

`domain/score_scaler.py` の規約:

- 各 scorer の **positive key** (`higher_is_better=True`、例: shadow=`hq`, cafe=`aesthetic`)
  だけを表示尺度の入力とする。complement (lq / not_aesthetic) は使わない。
- 生値 → 0-10 は **連続・単調・区分線形補間** で写像する (線形 `*10` でも 6 段階離散でもない)。
  knot は lib の `SCORE_THRESHOLDS` (Animagine 由来) と本 ADR の manual tier 境界を根拠にする。
- `score_value` 導出 (`ImageRepository._derive_display_score`): 手動行があれば最優先で
  その生値 (既に 0-10)、無ければ各 scorer の連続 0-10 値の **平均**、スコア無しは 0.0。
- AI scorer の数値スコアは positive key 1 行だけを生値で保存する
  (`AnnotationSaveService`、変換は読み取り時)。同一 model で positive/complement の 2 行が
  保存され DB で positive 判別不能になる問題を防ぐ。legacy 2 行データは最新行採用で近似する。

lib 側の `ScoreScale` (range / higher_is_better) メタデータ安定化と、LoRAIro 自前
`_AI_SCORE_SPEC` との drift-guard は iam-lib#144 で扱う (pin 反映後に drift テストを有効化)。

### Sentinel tier (`no score` / `unknown`) の扱い

`no score` と `unknown` は ordinal 比較の対象外の sentinel である。

- `no score`: score 系 annotation (score_labels / manual score) が 1 件も無い。
- `unknown`: vote は存在するが mapping 未定義 (新 scorer / 未登録 label / 範囲外 manual score)。

両者を `low quality` 等の実 tier に丸めると、未採点抽出と mapping 漏れ検出が
区別できなくなる。GUI / JSON export では sentinel literal をそのまま出力し、
filter (out-of-scope) では `no_score_mode` で別途扱う。

### New scorer 追加時の運用

新 scorer (例: `WaifuAesthetic`) を unified tier に参加させる手順:

1. `_SCORE_LABEL_TO_TIER` に `(model_name, label) -> QualityTier` の行を追加する。
2. mapping を変更した場合は `MAPPING_VERSION` を bump する (例: `quality-tier-v2`)。
3. `tests/unit/domain/test_quality_tier.py` に該当 mapping の test を追加する。
4. mapping 未追加のままの新 scorer label は `unknown` に落ちる (silent misclassification
   ではなく明示的に検出可能)。

## Rationale

### 慣れた語彙を UI に使う理由

`masterpiece` / `best quality` / `low quality` は anime image generation / LoRA 文脈で
広く共有された語彙であり、`EXCELLENT` / `PASS` などの抽象名より一見して意味が伝わる。

ただし NovelAI、Anima、NoobAI、Animagine などで付与基準は異なるため、本 ADR では
外部標準ではなく LoRAIro の dataset search 用 alias として定義する。

### Raw value と derived tier を分ける理由

model raw output は再現性の源泉である。mapping を変えるたびに DB annotation を書き換えると、
過去の annotation 結果が失われ、export / search の再現性も曖昧になる。

raw value を保存し、tier を派生計算にすることで:

- mapping を後から修正できる
- 元の scorer 出力を監査できる
- JSON export で raw と derived を両方出せる
- `unknown` を検出して新 model / label 対応漏れを見つけられる

### Numeric aggregation を初期採用しない理由

`scores` は model ごとに scale が異なる。

- `aesthetic_shadow`: `hq` / `lq` probability
- `cafe_aesthetic`: `aesthetic` / `not_aesthetic` probability
- manual score: 0.00-10.00
- `ImprovedAesthetic`: 1-10 regression
- `WaifuAesthetic`: 0-1 regression

単純平均や confidence-weighted aggregation は、scale の意味を混同する。初期実装では
canonical label と manual score の rule-based mapping に限定する。

### `no score` を tier として扱う理由

データセット作成では、未採点画像を探して追加 scoring する操作が重要である。
`no score` を低品質と同一視すると、未判定と低品質が混ざってしまう。

## Consequences

### 良い点

- dataset export/search で「good quality 以上」のような自然な条件指定ができる
- scorer ごとの raw value をユーザーが覚えなくてよい
- raw DB annotation は不変で、mapping 変更に強い
- `no score only` で未採点画像を抽出できる
- `unknown` で mapping 漏れを検出できる

### 悪い点・トレードオフ

- `masterpiece` 等の語彙は外部モデルごとに意味が異なるため、LoRAIro 独自定義であることを
  UI / ADR / docs で明示する必要がある
- 初期 mapping は rule-based であり、完全に客観的な美的尺度ではない
- regression scorer は初期 filter に含まれないため、利用するには後続 ADR が必要
- tier filter を SQL で高速化する場合、`score_labels` の追加 index や
  `(image_id, model_id)` unique constraint を検討する必要がある

### 運用ルール

- `scores` / `score_labels` raw value を tier に変換して DB 上書きしない
- mapping 変更時は `mapping_version` を上げる
- 未定義 raw label / model は `unknown` として扱い、黙って近い tier に丸めない
- `no score` は annotation absence として扱い、`unknown` と混同しない
- new scorer を unified tier filter に参加させる場合は mapping と unit test を追加する

## Related

- **Issue**: NEXTAltair/LoRAIro#287
- **Issue**: NEXTAltair/LoRAIro#626 (連続 display score の追補)
- **Related Issue**: NEXTAltair/image-annotator-lib#144 (scorer `ScoreScale` メタデータ安定化 / drift-guard)
- **Parent ADR**: 0027 (Score Labels DB Storage)
- **Parent ADR**: 0028 (Score Labels Usage and Display Strategy)
- **Related ADR**: 0022 (Aesthetic Score Predictor Model Survey)
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **External reference**:
  - NovelAI docs: quality tags and aesthetic tags
  - `circlestone-labs/Anima`: human score based quality tags and aesthetic model based score tags
  - Animagine / NoobAI model cards: model-specific quality tag criteria
