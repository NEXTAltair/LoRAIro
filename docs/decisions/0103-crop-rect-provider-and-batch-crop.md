---
type: ADR
title: クロップ矩形の供給元を CropRectProvider で差し替え可能にし、外部 JSONL から一括作成する
status: Accepted
timestamp: 2026-11-08
tags: [cli, crop, batch, provider, object-detection]
---

# ADR 0103: クロップ矩形の供給元を CropRectProvider で差し替え可能にし、外部 JSONL から一括作成する

## Context

ADR 0092 でクロップ画像の親子関係(`crop_relations`)と 1 件単位の作成サービス(`crop_service.create_crop_image`)を整備し、CLI の `images crop` で 1 画像につき 1 矩形を作成できるようになった。

残る要求は、「物体検出モデルで範囲を自動で決め、目視なしで学習素材を作成する」ことである。これを実現するには、複数矩形の一括作成・部分失敗・再実行に関する契約と、検出器を差し込む境界が必要になる。

検討した選択肢は次の 4 案である。

- **案 A**: 矩形の供給元を Protocol で切り離し、外部で用意した矩形(JSONL)を一括で取り込む。検出モデルは含めない。
- **案 B**: アニメ向けの軽量 ONNX 検出器を `image-annotator-lib` に追加する。
- **案 C**: ゼロショット検出(OWLv2 / Grounding DINO)を利用する。
- **案 D**: マルチモーダル WebAPI にバウンディングボックス(bbox)を返させる。

案 B〜D は、モデル選定・ライセンス・対象クラス・メタデータ保存の判断を伴い、CI で決定論的に検証しにくい。一方で、一括処理の入出力や部分失敗の契約は、どの検出方式を採る場合でも共通である。

## Decision

案 A から案 B への段階導入とし、本 ADR ではステップ 1(案 A)の設計を定める。

### 1. `CropRectProvider` Protocol を境界にする

`lorairo.domain.crop_rect_provider` に、Qt と DB の双方に依存しない Protocol を配置する。

- `candidates_for(parent_image_id) -> Sequence[CropRectCandidate]` をインターフェースとする。
- `CropRectCandidate` は、`rect`(ADR 0092 §5 の表示向き座標)、`origin`、任意の `score`、任意の入力行番号 `line` を持つ。
- 検出器のように画像ファイルを必要とする実装は、パス解決手段をコンストラクタで受け取る。
- 矩形の妥当性検証はプロバイダ側ではなく、一括処理側で行う。

最初の実装は、外部 JSONL を読み込む `JsonlCropRectProvider` とする。

### 2. 一括処理は 1 件の作成処理を再利用する

`crop_batch_service.run_crop_batch` は、プロバイダが返す候補ごとに既存の `create_crop_image` を呼び出す。タグとレーティングは `images crop` の既定と同じく親画像からコピーする。処理の契約は次のとおりとする。

- 1 矩形につき 1 件の結果(`created` / `would_create` / `skipped` / `failed`)を返す。個別の矩形が失敗しても残りの処理を継続する。
- 同じ親・矩形・`origin` の関係行が既に存在する場合は `skipped (already_exists)` とし、再実行の冪等性を保つ。
- 切り出し結果が既存画像と pHash で重複する場合は `skipped (duplicate_image)` とする。
- 範囲外または幅・高さが 0 以下の矩形は `failed (invalid_rect)`、未登録の親画像は `failed (parent_not_found)` とする。
- DB 例外は個別の失敗として握りつぶさず伝播させる(継続しても全件失敗するため)。
- `dry_run` では DB とファイル保存先へ書き込まず、範囲検証・関係行の重複・切り出し結果の pHash 重複(一時ファイルで判定)を本番実行と同じ結果になるよう判定する。

### 3. CLI `images crop-batch --rects FILE`

- 入力は 1 行につき 1 矩形を表す JSON オブジェクトとする。`image_id`・`x`・`y`・`width`・`height`(整数)を必須とし、`origin`(空文字不可)と `score`(有限数)を任意とする。未知のキーは誤記検出のため拒否し、空行は無視する。
- 構文エラーや型不一致などの不正な行は、行番号付きの `failed (invalid_row)` として報告し、残りの行の処理を続ける。
- 非空行が 500 行を超える場合は、解釈も書き込みも行わず `RESULT_SET_TOO_LARGE`(`exit 2`)で拒否する(ADR 0060 の作業集合上限)。
- `--origin` で `origin` 省略行の既定値を指定できる(既定値は `manual`)。また、`--dry-run` オプションを提供する。
- 出力は ADR 0057 の JSONL 形式とする。各行に `item` を出力し、末尾に件数と `created_ids` / `failed_lines` を含む `result` を出力する。`skipped` は成功扱いとし、終了コードは全件成功を 0、部分成功を 3、全件失敗を 1 とする。

### 4. ステップ 1 ではスキーマを変更しない

検出メタデータ(モデル名・`score`・検出時刻)は DB に保存せず、`score` は結果出力にのみ載せる。由来は既存の `crop_relations.origin` に記録する。

## Alternatives and rationale

- **最初から検出器を組み込む(案 B)**: 対象クラス・モデルライセンス・メタデータ保存先を同時に決める必要があり、一括処理の契約設計と混ざって手戻りが大きくなるため、ステップ 2 として切り出した。
- **JSONL の不正行で全体を中止する**: 外部ツールの出力に 1 行の誤りがあるだけで全件やり直しになるのを避けるため、行単位の失敗とし、`--dry-run` で事前確認できる設計にした。
- **小さすぎる矩形を `--min-long-edge` で除外する**: 既定値の根拠(GUI の警告しきい値 1024px は厳しすぎる可能性がある)が未確定のため、ステップ 1 には含めない。

## Consequences

- 外部の検出ツールで矩形 JSONL を生成すれば、目視なしでクロップ画像を一括作成できる。
- ステップ 2 で検出器を導入する際は、`CropRectProvider` を実装するだけで同じ一括処理と出力契約に乗せられる。
- 検出メタデータを後から保存する場合は、ADR 0092 の方針どおり `crop_relations` へ列を足さず、`crop_relations.id` を参照する別テーブルを設ける(追加マイグレーションと新しい ADR が必要)。

## Related

- ADR 0057(CLI 出力契約)、ADR 0060(count-first と 500 件上限)、ADR 0092(クロップの親子関係と座標系)
- Issue #1340
