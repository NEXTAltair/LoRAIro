---
type: ADR
title: 物体検出器でクロップ矩形を決める images crop-detect を CropRectProvider として追加する
status: Accepted
timestamp: 2026-11-12
tags: [cli, crop, batch, provider, object-detection, license]
---

# ADR 0110: 物体検出器でクロップ矩形を決める images crop-detect を CropRectProvider として追加する

## Context

ADR 0103 で矩形の供給元を `CropRectProvider` Protocol で切り離し、外部 JSONL から一括作成する
`images crop-batch` を入れた (段階導入の Step 1)。Step 2 では検出モデルで範囲を自動で決め、
目視なしでクロップ画像を作る。これには次の判断が必要になる。

- どの検出モデルを使うか (ライセンスを含む)
- 対象クラスをどう指定するか
- 検出メタデータ (モデル名・score・検出時刻) を保存するか
- 閾値・余白・NMS・既存クロップとの重複・小さすぎる矩形の既定値
- 検出 0 件や閾値未満を、一括処理の契約 (1 矩形 = 1 結果) の中でどう報告するか

検出器そのものは image-annotator-lib の型付き API (`detect_objects` / `list_detectors` /
`release_detectors`、lib ADR 0014) として提供される。

## Decision

### 1. モデル: lib の 3 検出器を使い、halfbody は採用しない

| `--class` | 検出器 (= `origin`) | 既定 `min_score` | ライセンス |
|---|---|---|---|
| `person` | `person_detect_v1.3_s` | 0.324 | MIT |
| `face` | `face_detect_v1.4_s` | 0.307 | MIT |
| `head` | `head_detect_v2.0_s` | 0.413 | MIT |

- deepghs のアニメ向け YOLOv8 系 ONNX。アニメ・イラストの学習素材を対象とする LoRAIro の
  用途に合い、CPU だけで実用速度で動く。`_n` より精度を優先した `_s` 変種 (選定は lib ADR 0014)。
- ライセンスは各モデルカードの front matter の `license: mit` を根拠とする (リポジトリに
  LICENSE ファイルは無い)。学習に使われた ultralytics (AGPL-3.0) の扱いは lib ADR 0014 を参照する。
- **halfbody は採用しない。** 配布元の表記が OpenRAIL 系で、利用制限条項の本文を確認できていない。
  `--class halfbody` は選択肢に残し、指定されたら理由を示して入力エラー (exit 2) にする。
  条項を確認できた時点で別途検討する。
- LoRAIro 側のクラス → 検出器・既定閾値の対応表は `crop_detect_provider.DETECTOR_CLASSES` の
  1 箇所に置く。`--help` / `describe` が lib を import せずに選択肢と既定値を示すためで、
  lib のカタログと一致することはユニットテストで検証する。

### 2. 対象クラスはクラス名で指定し、ゼロショット検出は入れない

`--class person|face|head|halfbody` で 1 クラスを選ぶ。1 回の実行は 1 検出器で、`origin` も
1 種類になる。ゼロショット検出 (OWLv2 / Grounding DINO) は需要が出てから同じ Protocol の
別実装として追加する。

### 3. 検出メタデータは保存しない

- `crop_relations` に列を足さず、追加マイグレーションもしない。`crop_relations.origin` に
  検出器名を入れるだけにする。score は結果出力 (item の `score`) にだけ載せる。
- 理由: 保存したメタデータを読む機能が今は無い (YAGNI)。どの検出器で作ったかは `origin` で分かり、
  同じ検出器名とパラメータで再実行すれば同じ矩形を再現できる (同じ矩形・由来は `already_exists`)。
- 保存が必要になったら、ADR 0092 / 0103 の方針どおり `crop_relations.id` を参照する別テーブルを
  新しい ADR とマイグレーションで追加する。

### 4. 既定値

| オプション | 既定値 | 理由 |
|---|---|---|
| `--min-score` | クラスごと (上表) | モデル提供元の推奨閾値をそのまま使う。 |
| `--padding` | 0.1 | 検出矩形は輪郭に密着するため、幅・高さそれぞれの 10% を左右・上下に足して髪や輪郭の切れを防ぐ。画像端でクランプする。 |
| `--nms-iou` | 0.5 | 同一画像内の重複検出を抑える一般的な値 (lib の既定と同じ)。 |
| `--min-long-edge` | 256 | 余白適用後の長辺がこれ未満の矩形は学習素材として解像度が足りない (背景の小さな顔など)。GUI の警告しきい値 1024px は自動作成の足切りとしては厳しすぎるため、明らかに使えないものだけを落とす。 |
| `--existing-iou` | 0.7 | 同じ親の既存クロップとの IoU がこれ以上なら、ほぼ同じ範囲の重複として作らない。余白だけ変えた再実行 (例 0.05 と 0.1 で IoU 約 0.84) も重複として扱える。 |

- 余白は検出矩形の幅・高さに比率を掛けた量を各辺に足し、左上は切り捨て・右下は切り上げで整数化する。
- `--min-long-edge` は保存される矩形 (余白適用後) に対して判定する。
- 既存クロップとの比較は、同じ親の全ての子 (由来を問わない) を対象にする。ただし同じ矩形・同じ
  `origin` の既存行は IoU 判定から外し、一括処理の `already_exists` (再実行の冪等性、ADR 0103) に任せる。
- `--min-score` 未満の検出も報告するため、lib には `min_score x 0.5` を下限として渡し、
  下限以上・`min_score` 未満を `below_min_score` として出す。下限を設けないと低 score の誤検出が
  大量に並び、出力が読めなくなる。NMS は score の高い順に残す矩形を決めるため、下限を下げても
  `min_score` 以上の矩形の集合は変わらない。
- 親画像は 1 回 500 件まで (ADR 0060)。超えたら検出せず `RESULT_SET_TOO_LARGE` (exit 2)。

### 5. skipped / failed の理由コードと Protocol の後方互換な拡張

一括処理の契約 (1 矩形 = 1 結果、部分失敗は継続、dry-run、部分成功は exit 3) は変えずに、
provider が「作成しない結果」を返せるよう Protocol を広げる。

- `CropRectCandidate` に任意の `skip_reason` / `skip_message` を足す。設定された候補は一括処理が
  検証も作成もせず `skipped` として報告する (`below_min_score` / `below_min_long_edge` /
  `overlaps_existing_crop`)。矩形と score は出力に載る。
- 矩形を伴わない親画像単位の結果として `CropRectNotice` (status・理由・詳細・由来) を足す。
  検出 0 件は `skipped (no_detection)`、親画像が未登録は `failed (parent_not_found)`、
  開けない画像は `failed (io_error)`、モデルの取得・ロード失敗は `failed (detector_unavailable)`、
  推論失敗・メモリ不足は `failed (detection_failed)`。item の座標は null になる。
- `candidates_for` の戻り値の要素型を `CropRectCandidate | CropRectNotice` に広げる。
  候補だけを返す既存の JSONL provider はそのまま Protocol を満たす。
- `detector_unavailable` は同じ実行の残りの画像で再試行しない (ネットワーク障害で画像ごとに
  取得を繰り返さない)。`detection_failed` は画像ごとに扱い、残りの画像は続ける。
- 利用者向けメッセージに lib の例外文字列 (内部パスを含み得る) を出さず、詳細はログにだけ残す。

### 6. CLI `images crop-detect`

- `--project`、`--class`、親画像の `--image-ids` / `--image-ids-file`、上記の閾値オプション、`--dry-run`。
- 親画像は EXIF 適用後の表示向きで開いて検出する (ADR 0092 §5)。検出器セッションは lib が
  キャッシュし、実行の終わりに `release_detectors()` で解放する (lib ADR 0014)。
- item は `images crop-batch` と同じ項目 (`line` は常に null、理由コードの集合だけが広い)、
  result は `images crop-batch` と同じ型。終了コードは 0 / 3 / 1 / 2 で同じ意味。
- 初回実行時は Hugging Face Hub から検出モデルを取得する (side effect `network`)。
- `--help` と `describe` は lib (onnxruntime) を import しない。

## Alternatives and rationale

- **検出メタデータを別テーブルに保存する**: 読む機能が無いうちにスキーマと移行を増やすことになる。
  再現は検出器名とパラメータで足りるため見送った。
- **閾値未満を報告しない**: 受け入れ基準 (閾値未満を理由コード付きで報告) を満たせず、
  「検出器は見えていたが閾値で落ちた」ことが分からない。
- **provider が候補だけを返し、理由コードは一括処理側で判定する**: 閾値・最小長辺・既存クロップとの
  IoU は検出器 provider 固有のルールで、JSONL 由来の一括処理に持ち込むと契約が混ざる。
- **検出 0 件を例外で表す**: 正常系であり、`skipped` として件数に数えたいので notice にした。
- **クラス → 検出器を lib の `list_detectors()` から都度引く**: `--help` / `describe` で lib を
  import することになり、CLI 起動が重くなる。

## Consequences

- 目視なしで人物・顔・頭部のクロップ画像を一括作成できる。作成済みのクロップと重なる範囲は
  作られず、同じ条件の再実行は冪等になる。
- provider は skipped 理由付きの候補と notice を返せる。将来のゼロショット検出も同じ契約に乗る。
- 検出メタデータは保存されない。score や検出時刻を後から参照する必要が出たら別テーブルを追加する。

## Related

- ADR 0057 (CLI 出力契約), ADR 0060 (500 件上限), ADR 0092 (クロップの親子関係と座標系),
  ADR 0103 (CropRectProvider と images crop-batch)
- image-annotator-lib ADR 0014 (物体検出 API)
- Issue #1340, Issue #1488
