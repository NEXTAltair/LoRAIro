---
type: ADR
title: Unified Dataset Quality Tier
status: "Accepted (Revised 2: 2026-06-27 — tier ラベルの GUI 表示を廃止、スコア値による大まかな絞り込みは残す)"
timestamp: 2026-05-19
tags: []
---
# ADR 0029: Unified Dataset Quality Tier

## 改訂 2(2026-06-27): tier ラベルの GUI 表示を廃止

改訂 1 で tier を補助フィルタへ降格したが、さらに **GUI での tier ラベル表示(バッジ)を廃止する**。

- **廃止**: `品質: best quality (2 scorer)` や `品質: masterpiece (全 scorer 一致)` のような tier 語彙を GUI に表示する仕様(§Export / GUI 節のバッジ仕様)。
- **維持**: スコア値による大まかな絞り込み。検索フィルタの品質軸は tier 語彙ではなく、**数値スコア(`Score.score` 0–10)の範囲指定**として実装する。`QualityTierFilter.min_tier` のような tier 名指定ではなく、スライダーなどの数値入力をインターフェースとする。
- **内部ロジックは維持**: `domain/quality_tier.py` のマッピングと、`QualityIssueDetectionService` が参照する tier 判定は引き続き使用する。外部に見せる語彙(`masterpiece` 等)を UI から取り除くにとどめる。

---

## 改訂(2026-06-18): 品質尺度は数値スコアをベース、tier は派生サマリ

初版では離散 tier(`masterpiece` 〜 `worst quality`)を主インターフェースとし、連続数値スコアを #626 の追補(従)として位置づけていた。実運用で主従が逆であると判明したため、方針を反転する。

- **主(ベース)= 数値スコア**: `Score.score`(0.00–10.00、scorer 別生値、手動スコア)。連続値を品質の第一尺度とし、表示・並び替え・フィルタはまず数値スコアで行う。
- **従(派生サマリ)= `QualityTier` / `score_labels`**: 数値およびカテゴリ値から導く派生ビュー。「good quality 以上」のような大掴みの絞り込みやバッジとして併記する。

この反転に伴い、本文中の以下の記述は現方針では従位置に降格して読むこと。

- 「Search filter behavior」の「tier を主インターフェースにする」→ **数値スコアが主、tier は補助フィルタ**。
- 「Numeric aggregation を初期採用しない理由」→ **撤回**。数値スコアを主尺度とする。ただし、scorer 間で生値のスケールが異なるため**直接平均しない**点は維持し、表示用の 0–10 化は `domain/score_scaler.py` の単調・区分線形補間で行う(#626 の規約を本体へ昇格)。
- 「Continuous display score(#626 追補)」→ **追補ではなく本体**(品質のベース尺度)。

初版から維持する不変の原則は以下のとおりである。

- 生アノテーション(`scores` / `score_labels`)は書き換えない。tier も数値表示も派生値である。
- scorer 間の生値はスケールが異なるため、直接比較や単純平均はしない(0–10 化を経由する)。
- `no score` と `unknown` は実 tier に丸めない番兵値(sentinel)のまま維持する。

## Context

ADR 0027 で scorer 由来のカテゴリラベルを `score_labels` テーブルに保存し、ADR 0028 で `{model, label}` の生リストを GUI および JSON エクスポートへ出力する経路を追加した。

しかし、LoRA 学習用データセットの作成では、scorer ごとの生値を直接指定するフィルタは使いにくい。

- `aesthetic_shadow_v1/v2` は `very aesthetic` / `aesthetic` / `displeasing` / `very displeasing` を返す。
- `cafe_aesthetic` は `aesthetic` / `not_aesthetic` を返す。
- 手動スコアは DB 上 0.00–10.00 の浮動小数点数(UI 上は 0–1000)である。
- 回帰型 scorer(regression scorer)はモデルごとにスケールが異なる。

ユーザーがデータセットのエクスポートや検索で求めているのは、個別 scorer の細かな条件指定ではなく、「一定水準以上の画像」「低品質候補」「未採点画像」の抽出である。したがって、LoRAIro 側に検索・表示用の統一品質 tier が必要になる。

なお、NovelAI・Danbooru・現代のアニメ向け拡散モデル文化では、`masterpiece`・`best quality`・`good quality`・`normal quality`・`low quality`・`worst quality` という語彙が広く使われている。たとえば Anima は `masterpiece ... worst quality` を人間スコア由来の品質タグとし、別系統の `score_9 ... score_1` を審美モデル由来のタグとして併用している。NovelAI 公式も品質タグと審美タグを分離しているが、プロンプト実務では両者が品質表現として近接して使われる。

LoRAIro はこの馴染みのある語彙を UI およびフィルタ値に採用する。ただし、外部モデル共通の客観基準としてではなく、LoRAIro 独自の **データセット品質 tier(dataset quality tier)** として定義する。

## Decision

### 生アノテーションは変更しない

`scores` や `score_labels` に保存済みのモデル生出力は変更しない。統一品質 tier は生アノテーションの上に乗る派生ビューとする。

```text
raw scores / score_labels
  -> quality mapping
  -> dataset quality tier
  -> GUI badge / JSON export / search filter
```

マッピングを変更しても DB の生アノテーションは書き換えず、検索結果と表示のみを新しいマッピングに従って再計算する。

### Tier 語彙

検索 UI・API・JSON エクスポートの表示語彙として以下を採用する。

| tier | 用途 |
|---|---|
| `masterpiece` | 最上位。強い採用候補 |
| `best quality` | 高品質。採用候補 |
| `good quality` | 実用上採用可能 |
| `normal quality` | 中立。明確な高品質ではないが除外とも言い切れない |
| `low quality` | 低品質。除外候補 |
| `worst quality` | 最低品質。強い除外候補 |
| `no score` | スコア系アノテーションが存在しない |
| `unknown` | 生値は存在するがマッピング未定義 |

`no score` と `unknown` は分離する。未採点画像の抽出と、新モデルや未定義ラベルの検出は別のユースケースだからである。

### 初期マッピング

初期マッピングは、正規 scorer と手動スコアを対象とする。

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

`ImprovedAesthetic` や `WaifuAesthetic` などの回帰型 scorer は初期マッピングから除外する。これらはスケールと閾値の意味がモデル固有であり、ADR 0022 および iam-lib ADR 0002 でモデル横断比較不可と整理済みだからである。後続 ADR で閾値を決定した場合のみマッピングに追加する。

### 集約規約(Aggregation rule)

1 枚の画像に複数 scorer の `score_labels` と手動スコアがある場合、それぞれを **vote(票)** として扱い、統一 tier へ集約する。集約には **中央値(median)と全一致フラグ(`is_unanimous`)のハイブリッド方式** を採用する。

- `votes` を既知(マッピング定義済み)と未知(マッピング未定義)に分類する。
- 既知の票が 1 件以上ある場合:
  - `tier`: 既知の票の tier を順序尺度へ変換してソートした**中央値**とする。偶数件で同順位になった場合は上位寄り(`sorted_tiers[len // 2]`)で決定的に解決する。
  - `is_unanimous`: すべての既知の票が同一 tier であり、かつ未知の票が 0 件のときに `true` とする。
- 既知の票が 0 件で票自体は存在する場合: `tier = "unknown"` とする。
- 票が 1 件もない場合: `tier = "no score"`、`no_score = true` とする。

中央値を採用する理由は Rationale を参照すること。`is_unanimous` は、scorer 別ピル(ADR 0028)を見なくても scorer 間の合意有無を 1 フィールドで判定できるようにする補助シグナルである。

集約パターンの比較検討(中央値・最頻値・最小値・最大値・混在番兵値・票のみ)は #287 の計画フェーズで実施した。中央値は順序尺度として安定しておりフィルタの `min_tier` 比較と整合するうえ、`is_unanimous` によって不一致(UC-C)も表現できる。

### Search filter behavior

> 改訂(2026-06-18): 主従を反転済み。**フィルタは数値スコア(`Score.score` 0–10)を主**とし、下記の tier フィルタ(`min_tier` / `vote_mode` / `no_score_mode`)は**大掴みの補助フィルタ**として併設する。以下は補助 tier フィルタの仕様として読むこと。

データセットの検索・エクスポートフィルタでは、モデル固有の生値ではなく tier を主インターフェースとする。

```python
class QualityTierFilter(TypedDict):
    min_tier: str  # e.g. "good quality"
    vote_mode: str  # "any" | "majority" | "all"
    no_score_mode: str  # "exclude" | "include" | "only"
```

想定 UI は以下のとおりである。

```text
品質: good quality 以上
一致条件: 1件以上 / 過半数 / 全件
未採点: 除外 / 含める / 未採点のみ
```

`min_tier` の比較では、上位から下位への順序を以下で固定する。

```text
masterpiece > best quality > good quality > normal quality > low quality > worst quality
```

`unknown` は既定では条件一致に含めない。必要な場合は別の UI またはフィルタで抽出する。

### Export / GUI

JSON エクスポートでは生の `score_labels` を維持しつつ、追加で `quality_summary` を出力する。

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

`votes[]` の各要素は `source` で `"score_label"` と `"manual_score"` を識別し、`score_label` は `raw_label`、`manual_score` は `raw_score`(float)を保持する。未知の票には `quality_tier = "unknown"`(番兵値)を出力する。

GUI では ADR 0028 の scorer 別ピルを残し、統一 tier を別バッジとして `groupBoxScoreLabels` の最上段に単一 `QLabel` で併記する(例: `品質: best quality (2 scorer)`、`品質: masterpiece (3 scorer) (全 scorer 一致)`)。`tier="no score"` または `"unknown"` の場合は `known_count` を省き、`品質: no score` / `品質: unknown` と表示する。`quality_summary` が空辞書の場合はバッジを非表示とし、旧データとの互換性を保つ。

TXT エクスポートには出力しない(ADR 0028 と同じく、コンテンツタグ専用ファイルの汚染を避けるため)。

### マッピングの SSoT

マッピングの SSoT は**コードモジュール** `src/lorairo/domain/quality_tier.py` とする。

- `QualityTier`(順序尺度の `IntEnum`)、`(model, label) -> QualityTier` の辞書定数、手動スコアの範囲マッピング関数、`MAPPING_VERSION` 定数を持つ。
- `compute_quality_summary(score_labels, scores) -> dict` が派生ビューを計算する。
- `database`・`services`・`gui` 層は `domain` を一方向でインポートする(循環依存を作らない)。

TOML 設定(`src/lorairo/config/quality_tier_mapping.toml`)によるユーザー上書きは本 ADR のスコープ外とし、必要になった時点で別 ADR および `mapping_version` v2 で検討する。

マッピングはアプリ仕様でありユーザーアノテーションではない。DB に保存するとマイグレーション・シード・古い派生データの管理負担が大きくなるため、性能課題が出るまでは派生計算にとどめる。`get_image_annotations()` が戻り値辞書に `quality_summary` キーを派生計算で含める。

### Continuous display score(#626 — 改訂で本体・ベース尺度へ昇格)

> 改訂(2026-06-18): この連続スコアが**品質のベース尺度(主)**であり、tier は派生サマリ(従)である。下表の役割分担は主従が反転した前提で読むこと(display score が主、tier バッジが補助)。

tier バッジ(離散 6 段階)とは別に、AI 数値スコアを手動スライダーと同じ **0.0–10.0 の連続表示スコア(`score_value`)** として提供する。両者の役割分担は以下のとおりである。

| 観点 | tier バッジ(本 ADR 本体) | display score(#626) |
|---|---|---|
| 値域 | 離散 6 段階(`masterpiece` 〜 `worst quality`) | 連続 0.0–10.0 |
| 入力 | `score_labels`(カテゴリ値)+ 手動スコア | scorer の数値 `scores`(正方向キー)+ 手動スコア |
| SSoT | `domain/quality_tier.py` | `domain/score_scaler.py` |
| 用途 | フィルタ・多数決サマリバッジ | スライダー初期値・数値表示 |

`domain/score_scaler.py` の規約は以下のとおりである。

- 各 scorer の**正方向キー**(`higher_is_better=True`、例: shadow=`hq`、cafe=`aesthetic`)のみを表示尺度の入力とする。補数側(`lq` / `not_aesthetic`)は使わない。
- 生値から 0–10 への変換は**連続・単調・区分線形補間**で写像する(単純な `*10` でも 6 段階離散でもない)。節点(knot)はライブラリの `SCORE_THRESHOLDS`(Animagine 由来)と本 ADR の手動 tier 境界を根拠とする。
- `score_value` の導出(`ImageRepository._derive_display_score`)では、手動行があればその生値(既に 0–10)を最優先する。手動行がなければ各 scorer の連続 0–10 値の**平均**を採り、スコアがなければ 0.0 とする。
- AI scorer の数値スコアは、正方向キー 1 行のみを生値で保存する(`AnnotationSaveService`、変換は読み取り時に行う)。同一モデルで正方向と補数の 2 行が保存されて DB 上で正方向を判別できなくなる問題を防ぐためである。旧 2 行データは最新行の採用で近似する。

ライブラリ側の `ScoreScale`(range / `higher_is_better`)メタデータの安定化と、LoRAIro 側の `_AI_SCORE_SPEC` との乖離検出は iam-lib#144 で扱う(ピン反映後に乖離テストを有効化する)。

### 番兵 tier(`no score` / `unknown`)の扱い

`no score` と `unknown` は順序比較の対象外となる番兵値である。

- `no score`: スコア系アノテーション(`score_labels` / 手動スコア)が 1 件もない状態。
- `unknown`: 票は存在するがマッピングが未定義の状態(新 scorer、未登録ラベル、範囲外の手動スコアなど)。

両者を `low quality` などの実 tier に丸めると、未採点抽出とマッピング漏れ検出が区別できなくなる。GUI および JSON エクスポートでは番兵リテラルをそのまま出力し、フィルタ(スコープ外)では `no_score_mode` で別途扱う。

### 新しい scorer 追加時の運用

新しい scorer(例: `WaifuAesthetic`)を統一 tier に参加させる手順は以下のとおりである。

1. `_SCORE_LABEL_TO_TIER` に `(model_name, label) -> QualityTier` の行を追加する。
2. マッピングを変更した場合は `MAPPING_VERSION` を更新する(例: `quality-tier-v2`)。
3. `tests/unit/domain/test_quality_tier.py` に該当マッピングのテストを追加する。
4. マッピング未追加のままの新 scorer ラベルは `unknown` に落ちるため、暗黙の誤分類ではなく明示的に検出できる。

## Rationale

### 慣れた語彙を UI に使う理由

`masterpiece`・`best quality`・`low quality` はアニメ画像生成および LoRA 学習の文脈で広く共有された語彙であり、`EXCELLENT` や `PASS` といった抽象名より直感的に意味が伝わる。

ただし、NovelAI・Anima・NoobAI・Animagine などで付与基準は異なるため、本 ADR では外部標準ではなく LoRAIro のデータセット検索用エイリアスとして定義する。

### 生値と派生 tier を分ける理由

モデルの生出力は再現性の源泉である。マッピングを変更するたびに DB のアノテーションを書き換えると、過去のアノテーション結果が失われ、エクスポートや検索の再現性も損なわれる。

生値を保持し、tier を派生計算とすることで次の利点が得られる。

- マッピングを後から修正できる。
- 元の scorer 出力を監査できる。
- JSON エクスポートで生値と派生値の両方を出力できる。
- `unknown` を検出して新モデルやラベルの対応漏れを見つけられる。

### Numeric aggregation を初期採用しない理由

> 改訂(2026-06-18): **撤回**。数値スコアを品質のベース尺度として採用する(主従反転、冒頭「改訂」節を参照)。ただし、以下の「スケールが異なるため単純平均しない」点は維持し、表示用の 0–10 化は `domain/score_scaler.py` の単調・区分線形補間で行う。以下は単純平均を避ける根拠として読むこと。

`scores` はモデルごとにスケールが異なる。

- `aesthetic_shadow`: `hq` / `lq` の確率値
- `cafe_aesthetic`: `aesthetic` / `not_aesthetic` の確率値
- 手動スコア: 0.00–10.00
- `ImprovedAesthetic`: 1–10 の回帰値
- `WaifuAesthetic`: 0–1 の回帰値

単純平均や信頼度加重平均はスケールの意味を混同してしまう。初期実装では正規ラベルと手動スコアのルールベースマッピングに限定する。

### `no score` を tier として扱う理由

データセット作成では、未採点画像を探して追加で採点する操作が重要になる。`no score` を低品質と同一視すると、未判定と低品質が混ざってしまうため独立した tier として扱う。

## Consequences

### 良い点

- データセットのエクスポートや検索で「good quality 以上」のような自然な条件指定ができる。
- ユーザーが scorer ごとの生値を覚える必要がない。
- 生の DB アノテーションが不変であるため、マッピング変更に強い。
- `no score only` で未採点画像を抽出できる。
- `unknown` によりマッピング漏れを検出できる。

### 悪い点・トレードオフ

- `masterpiece` 等の語彙は外部モデルごとに意味が異なるため、LoRAIro 独自定義であることを UI・ADR・ドキュメントで明示する必要がある。
- 初期マッピングはルールベースであり、完全に客観的な美的尺度ではない。
- 回帰型 scorer は初期フィルタに含まれないため、利用するには後続 ADR が必要になる。
- tier フィルタを SQL で高速化する場合は、`score_labels` への追加インデックスや `(image_id, model_id)` の一意制約を検討する必要がある。

### 運用ルール

- `scores` や `score_labels` の生値を tier へ変換して DB を上書きしない。
- マッピング変更時は `mapping_version` を上げる。
- 未定義の生ラベルやモデルは `unknown` として扱い、近い tier へ暗黙に丸めない。
- `no score` はアノテーション不在として扱い、`unknown` と混同しない。
- 新しい scorer を統一 tier フィルタに参加させる場合は、マッピングとユニットテストを追加する。

## Related

- **Issue**: NEXTAltair/LoRAIro#287
- **Issue**: NEXTAltair/LoRAIro#626(連続 display score の追補)
- **関連 Issue**: NEXTAltair/image-annotator-lib#144(scorer `ScoreScale` メタデータ安定化・乖離検出)
- **親 ADR**: 0027(Score Labels DB Storage)
- **親 ADR**: 0028(Score Labels Usage and Display Strategy)
- **関連 ADR**: 0022(Aesthetic Score Predictor Model Survey)
- **iam-lib ADR**: `local_packages/image-annotator-lib/docs/decisions/0002-score-model-output-contract.md`
- **外部参照**:
  - NovelAI ドキュメント: quality tags および aesthetic tags
  - `circlestone-labs/Anima`: human score based quality tags および aesthetic model based score tags
  - Animagine / NoobAI モデルカード: モデル固有の品質タグ基準
