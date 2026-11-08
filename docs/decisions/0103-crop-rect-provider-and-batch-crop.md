---
type: ADR
title: クロップ矩形の供給元を CropRectProvider で差し替え可能にし、外部 JSONL から一括作成する
status: Accepted
timestamp: 2026-11-08
tags: [cli, crop, batch, provider, object-detection]
---

# ADR 0103: クロップ矩形の供給元を CropRectProvider で差し替え可能にし、外部 JSONL から一括作成する

## Context

ADR 0092 でクロップ画像の親子関係 (`crop_relations`) と 1 件単位の作成サービス
(`crop_service.create_crop_image`) を整備し、CLI `images crop` で 1 画像 1 矩形を作れるようになった。
残る要求は「物体検出モデルで範囲を自動で決め、目視なしで学習素材を作る」ことで、これには
複数矩形の一括作成・部分失敗・再実行の契約と、検出器を差し込む境界が必要になる。

検討した案:

- A: 矩形の供給元を Protocol で切り離し、外部で用意した矩形 (JSONL) を一括で取り込む。検出モデルは入れない。
- B: アニメ向けの軽量 ONNX 検出器を image-annotator-lib に追加する。
- C: ゼロショット検出 (OWLv2 / Grounding DINO) を使う。
- D: マルチモーダル WebAPI に bbox を返させる。

B〜D はモデル選定・ライセンス・対象クラス・メタデータ保存の判断を伴い、CI で決定論的に検証しにくい。
一方、一括処理の入出力と部分失敗の契約はどの検出方式でも共通である。

## Decision

A → B の段階導入とし、本 ADR は Step 1 (案 A) を定める。

### 1. `CropRectProvider` Protocol を境界にする

`lorairo.domain.crop_rect_provider` に Qt / DB 非依存の Protocol を置く。

- `candidates_for(parent_image_id) -> Sequence[CropRectCandidate]`
- `CropRectCandidate` は `rect` (ADR 0092 §5 の表示向き座標)・`origin`・任意の `score`・任意の入力行番号 `line`。
- 画像ファイルが必要な実装 (検出器) は、パス解決手段をコンストラクタで受け取る。
- 矩形の妥当性検証は provider ではなく一括処理側が行う。

最初の実装は外部 JSONL を読む `JsonlCropRectProvider` とする。

### 2. 一括処理は 1 件の作成処理を再利用する

`crop_batch_service.run_crop_batch` は provider の候補ごとに `create_crop_image` を呼ぶ。
タグとレーティングは `images crop` の既定と同じく親からコピーする。契約は次のとおり。

- 1 矩形 = 1 結果 (`created` / `would_create` / `skipped` / `failed`)。失敗しても残りを続ける。
- 同じ親・矩形・`origin` の関係行が既にあれば `skipped (already_exists)`。再実行は冪等。
  切り出し結果が既存画像の pHash 重複なら `skipped (duplicate_image)`。
- 範囲外・幅高さ 0 以下は `failed (invalid_rect)`、未登録の親は `failed (parent_not_found)`。
- DB 例外は個別の失敗にせず伝播させる (継続しても全件失敗するため)。
- `dry_run` は書き込まずに範囲検証と重複判定だけを行う。

### 3. CLI `images crop-batch --rects FILE`

- 入力は 1 行 = 1 矩形の JSON object: `image_id` / `x` / `y` / `width` / `height` (整数、必須)、
  `origin` (空文字不可) と `score` (有限数) は任意。未知キーは誤記検出のため拒否する。空行は無視する。
- 構文エラー・型不一致などの不正な行は `failed (invalid_row)` として行番号付きで報告し、残りは続ける。
- 非空行が 500 行を超えたら、解釈も書き込みもせず `RESULT_SET_TOO_LARGE` (exit 2) で拒否する (ADR 0060 の作業集合上限)。
- `--origin` は `origin` を省略した行の既定値 (既定 `manual`)。`--dry-run` を持つ。
- 出力は ADR 0057 の JSONL。各行は item、最後に件数と `created_ids` / `failed_lines` を持つ result。
  `skipped` は成功扱いで、終了コードは全件成功 0・部分成功 3・全件失敗 1。

### 4. Step 1 ではスキーマを変更しない

検出メタデータ (モデル名・score・検出時刻) は保存しない。`score` は結果出力にだけ載せる。
由来は既存の `crop_relations.origin` に入れる。

## Alternatives and rationale

- **最初から検出器を入れる (B)**: 対象クラス・モデルのライセンス・メタデータの保存先を同時に決める必要があり、
  一括処理の契約と混ざって手戻りが大きい。Step 2 として切り出す。
- **JSONL の不正行で全体を中止する**: 外部ツールの出力に 1 行の誤りがあるだけで全件やり直しになる。
  行単位で失敗にし、`--dry-run` で事前確認できるようにした。
- **小さすぎる矩形を `--min-long-edge` で除外する**: 既定値の根拠 (GUI の警告しきい値 1024px は厳しすぎる可能性) が
  決まっていないため Step 1 には入れない。

## Consequences

- 外部の検出ツールで矩形を作れば、目視なしでクロップ画像を一括作成できる。
- Step 2 の検出器は `CropRectProvider` を実装するだけで同じ一括処理・出力契約に乗る。
- 検出メタデータを後から保存する場合は、ADR 0092 の方針どおり `crop_relations` には足さず、
  別テーブルで `crop_relations.id` を参照する (追加マイグレーションと新しい ADR が必要)。

## Related

- ADR 0057 (CLI 出力契約), ADR 0060 (count-first と 500 件上限), ADR 0092 (クロップの親子関係と座標系)
- Issue #1340
