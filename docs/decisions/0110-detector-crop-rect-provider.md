---
type: ADR
title: 物体検出器でクロップ矩形を決める images crop-detect を CropRectProvider として追加する
status: Accepted
timestamp: 2026-11-12
tags: [cli, crop, batch, provider, object-detection, license]
---

# ADR 0110: 物体検出器でクロップ矩形を決める images crop-detect を CropRectProvider として追加する

## Context

ADR 0103 で矩形の供給元を `CropRectProvider` Protocol として切り離し、外部 JSONL から一括作成する `images crop-batch` を導入した(段階導入のステップ 1)。ステップ 2 では物体検出モデルで範囲を自動決定し、目視なしでクロップ画像を作成する。

この実現には、次の設計判断が必要になる。

- どの検出モデルを採用するか(ライセンスを含む)
- 対象クラスをどのように指定するか
- 検出メタデータ(モデル名・`score`・検出時刻)を DB に保存するか
- 閾値・余白・NMS・既存クロップとの重複・小さすぎる矩形の既定値をどうするか
- 検出 0 件や閾値未満を、一括処理の契約(1 矩形につき 1 件の結果)の中でどう報告するか

検出器そのものは `image-annotator-lib` の型付き API(`detect_objects` / `list_detectors` / `release_detectors`、lib ADR 0014)として提供される。

## Decision

### 1. モデル選定: lib の 3 検出器を使い、`halfbody` は採用しない

| `--class` | 検出器(`origin` の値) | 既定 `min_score` | ライセンス |
|---|---|---|---|
| `person` | `person_detect_v1.3_s` | 0.324 | MIT |
| `face` | `face_detect_v1.4_s` | 0.307 | MIT |
| `head` | `head_detect_v2.0_s` | 0.413 | MIT |

- deepghs のアニメ向け YOLOv8 系 ONNX モデルを採用する。アニメ・イラストの学習素材を対象とする LoRAIro の用途に合致し、CPU のみでも実用的な速度で動作する。変種は `_n` より精度を優先した `_s` を選ぶ(選定根拠は lib ADR 0014)。
- ライセンスは各モデルカードのフロントマターにある `license: mit` を根拠とする(リポジトリに LICENSE ファイルは無い)。学習に使われた `ultralytics`(AGPL-3.0)の扱いは lib ADR 0014 を参照する。
- **`halfbody` は採用しない**: 配布元の表記が OpenRAIL 系であり、利用制限条項の本文を確認できていないためである。`--class halfbody` は選択肢に残し、指定された場合は理由を示して入力エラー(`exit 2`)を返す。条項を確認できた時点で改めて検討する。
- LoRAIro 側でクラスから検出器と既定閾値を引く対応表は、`crop_detect_provider.DETECTOR_CLASSES` の 1 箇所に置く。`--help` と `describe` が lib をインポートせずに選択肢と既定値を表示できるようにするためであり、lib のカタログとの一致はユニットテストで検証する。

### 2. 対象クラスはクラス名で指定し、ゼロショット検出は入れない

`--class person|face|head|halfbody` で 1 クラスを指定する。1 回の実行で使う検出器は 1 つ、`origin` も 1 種類とする。ゼロショット検出(OWLv2 / Grounding DINO)は需要が生じた段階で、同じ Protocol の別実装として追加する。

### 3. 検出メタデータは DB に保存しない

- `crop_relations` に列を追加せず、マイグレーションも行わない。`crop_relations.origin` には検出器名のみを記録し、`score` は結果出力(`item` の `score`)にだけ載せる。
- **理由**: 保存したメタデータを参照する機能が現時点では無いため(YAGNI)。どの検出器で作ったかは `origin` で判別でき、同じ検出器名とパラメータで再実行すれば同一の矩形を再現できる(同じ矩形・由来は `already_exists` になる)。
- 後から保存が必要になった場合は、ADR 0092 / ADR 0103 の方針どおり、`crop_relations.id` を参照する別テーブルを新しい ADR とマイグレーションで追加する。

### 4. パラメータの既定値と判定規則

| オプション | 既定値 | 理由 |
|---|---|---|
| `--min-score` | クラスごと(上表) | モデル提供元の推奨閾値をそのまま使う。 |
| `--padding` | 0.1 | 検出矩形は輪郭に密着するため、幅・高さそれぞれの 10% を左右・上下に足して髪や輪郭の切れを防ぐ。画像端でクランプする。 |
| `--nms-iou` | 0.5 | 同一画像内の重複検出を抑える一般的な値(lib の既定と同じ)。 |
| `--min-long-edge` | 256 | 余白適用後の長辺がこれ未満の矩形は学習素材として解像度が不足する(背景の小さな顔など)。GUI の警告しきい値 1024px は自動作成の足切りとしては厳しすぎるため、明らかに使えないものだけを落とす。 |
| `--existing-iou` | 0.7 | 同じ親の既存クロップとの IoU がこれ以上であれば、ほぼ同じ範囲の重複とみなして作成しない。余白だけを変えた再実行(例: 0.05 と 0.1 で IoU 約 0.84)も重複として扱える。 |

- **余白の丸め**: 検出矩形の幅・高さに比率を掛けた量を各辺に足し、左上は切り捨て、右下は切り上げで整数化する。
- **最小長辺の判定対象**: `--min-long-edge` は保存される矩形(余白適用後)に対して判定する。
- **既存クロップとの比較**: 同じ親に紐づくすべての子クロップ(由来を問わない)を対象とする。ただし、同じ矩形かつ同じ `origin` の既存行は IoU 判定から除外し、一括処理側の `already_exists`(再実行の冪等性、ADR 0103)に委ねる。
- **閾値未満の報告**: `--min-score` 未満の検出も報告するため、lib には `min_score x 0.5` を下限として渡し、下限以上かつ `min_score` 未満の候補を `below_min_score` として出力する。下限を設けなければ低スコアの誤検出が大量に並び出力が読めなくなる。NMS はスコアの高い順に残す矩形を決めるため、下限を下げても `min_score` 以上の矩形集合は変わらない。
- **件数上限**: 親画像は 1 回あたり 500 件までとする(ADR 0060)。超過した場合は検出を実行せず `RESULT_SET_TOO_LARGE`(`exit 2`)で拒否する。

### 5. `skipped` / `failed` の理由コードと Protocol の後方互換な拡張

一括処理の契約(1 矩形につき 1 件の結果、部分失敗は継続、`dry_run`、部分成功は `exit 3`)を維持したまま、プロバイダが「作成しない結果」を返せるように Protocol を拡張する。

- **`CropRectCandidate` の拡張**: 任意の `skip_reason` と `skip_message` を追加する。これらが設定された候補は、一括処理側が検証も作成も行わず `skipped` として報告する(`below_min_score` / `below_min_long_edge` / `overlaps_existing_crop`)。矩形と `score` は出力に載せる。
- **`CropRectNotice` の追加**: 矩形を伴わない親画像単位の結果(`status`・理由・詳細・由来)を表す型を追加する。
  - 検出 0 件: `skipped (no_detection)`
  - 親画像が未登録: `failed (parent_not_found)`
  - 開けない画像: `failed (io_error)`
  - モデルの取得・ロード失敗: `failed (detector_unavailable)`
  - 推論失敗・メモリ不足: `failed (detection_failed)`
  - これらでは `item` の座標は `null` になる。
- **後方互換性**: `candidates_for` の戻り値要素型を `CropRectCandidate | CropRectNotice` に広げる。候補のみを返す既存の JSONL プロバイダはそのまま Protocol を満たす。
- **障害時の再試行制御**: `detector_unavailable` は同一実行内の残り画像で再試行しない(ネットワーク障害で画像ごとに取得を繰り返すのを防ぐ)。一方、`detection_failed` は画像単位で扱い、残りの画像は処理を続ける。
- **エラー文言の保護**: 利用者向けメッセージに lib の例外文字列(内部パスを含み得る)を出さず、詳細はログにのみ残す。

### 6. CLI `images crop-detect`

- オプションは `--project`、`--class`、親画像の `--image-ids` / `--image-ids-file`、上記の閾値オプション、および `--dry-run` とする。
- 親画像は EXIF 適用後の表示向きで開いて検出する(ADR 0092 §5)。検出器セッションは lib がキャッシュし、実行終了時に `release_detectors()` で解放する(lib ADR 0014)。
- 出力形式は `images crop-batch` と同一とする(`item` の `line` は常に `null` で、理由コードの集合だけが広い)。`result` の型および終了コード(0 / 3 / 1 / 2)も同じ意味を持つ。
- 初回実行時は Hugging Face Hub から検出モデルを取得する(副作用 `network`)。
- `--help` と `describe` は lib(`onnxruntime`)をインポートしない。

## Alternatives and rationale

- **検出メタデータを別テーブルに保存する**: 参照機能が無い段階でスキーマと移行を増やすことになる。再現は検出器名とパラメータで足りるため見送った。
- **閾値未満を報告しない**: 受け入れ基準(閾値未満を理由コード付きで報告すること)を満たせず、「検出器は捉えていたが閾値で落ちた」事実が分からなくなる。
- **プロバイダが候補だけを返し、理由コードは一括処理側で判定する**: 閾値・最小長辺・既存クロップとの IoU は検出器プロバイダ固有のルールであり、JSONL 由来の一括処理へ持ち込むと契約が混ざる。
- **検出 0 件を例外で表す**: 検出 0 件は正常系であり、`skipped` として件数に数えたいため `CropRectNotice` とした。
- **クラスから検出器への対応を lib の `list_detectors()` から都度引く**: `--help` や `describe` のたびに lib をインポートすることになり、CLI の起動が重くなる。

## Consequences

- 目視なしで人物・顔・頭部のクロップ画像を一括作成できる。既存クロップと重複する範囲は作成されず、同一条件での再実行は冪等になる。
- プロバイダは `skipped` 理由付きの候補と `CropRectNotice` を返せるようになり、将来のゼロショット検出も同じ契約に乗せられる。
- 検出メタデータは DB に保存されない。`score` や検出時刻を後から参照する必要が出た場合は別テーブルを追加する。

## Related

- ADR 0057(CLI 出力契約)、ADR 0060(500 件上限)、ADR 0092(クロップの親子関係と座標系)、ADR 0103(`CropRectProvider` と `images crop-batch`)
- `image-annotator-lib` ADR 0014(物体検出 API)
- Issue #1340, Issue #1488
