---
type: ADR
title: model_id が空のタグ行に出所を持たせる (擬似モデル SIDECAR_IMPORT / IMAGE_PROCESSING)
status: Accepted
timestamp: 2026-11-19
tags: [tags, provenance, manual-edit, migration, sidecar]
---

# ADR 0111: model_id が空のタグ行に出所を持たせる (擬似モデル SIDECAR_IMPORT / IMAGE_PROCESSING)

## Context

`Tag` には出所を表す列が無く、区別に使えるのは `model_id` / `existing` / `is_edited_manually` だけである
(ADR 0104 / 0107 と同じ事情)。`model_id` が空 (NULL) の行は、次の別々の出所が混ざっていた。

- 画像に添えた `.txt` (関連ファイル) からの取り込み
- CLI での手入力 (`images` / `tags` のタグ追加、一括置換の置換先)、クロップで新たに与えたタグ
- アップスケール時に自動で付く `upscaled`

GUI の手動編集は既に `MANUAL_EDIT` の `model_id` で保存しており、同じ「手入力」が経路によって
NULL と `MANUAL_EDIT` に分かれていた。また読み取り側には次の不整合があった。

- 増分書き出しの「前回以降に変わった画像」の判定が「`model_id` あり = AI 実行」とみなしており、
  擬似モデル (`KOHYA_DATASET` / `GENERATION_METADATA` 等) の行も AI 実行として拾っていた (既存バグ)。
- 検索の「最近使ったモデル」に擬似モデルが出ていた。
- 表示で、出所の分からない行は `Unknown` / 手動扱いになり、取り込みと手入力を区別できなかった。

## Decision

- **擬似モデルを 2 つ追加する**。既存の擬似モデルと同じく `provider="user"`、`model_types` なし、
  `requires_api_key=False` で、実行時に初回だけ作る (スキーマ変更なし)。
  - `SIDECAR_IMPORT` (`litellm_model_id="__sidecar_import__"`): 関連ファイル (`.txt`) から取り込んだタグ。
  - `IMAGE_PROCESSING` (`litellm_model_id="__image_processing__"`): 画像処理が自動で付けたタグ (`upscaled`)。
- **書き込みで NULL を作らない**。
  - `.txt` 取り込み → `SIDECAR_IMPORT` (キャプションは対象外)。
  - CLI の手動追加 (dry-run の見積りを含む)・一括置換の置換先・クロップで新たに与えたタグ → `MANUAL_EDIT`。
  - クロップで親から引き継ぐタグ → 親の行の `model_id` のまま。
  - `upscaled` → `IMAGE_PROCESSING`。
  - 手動追加で同じ表記の soft-reject 済み行を復活させる判定は、`MANUAL_EDIT` の行を対象にする
    (`uq_tags_image_model_tag` に反する重複行を作らない)。dry-run の見積りはモデル行を作らない。
- **既存データを Alembic のデータ移行で振り分ける** (set-based UPDATE、`updated_at` は変えない)。
  1. NULL かつ `tag='upscaled'` かつ `existing=False` → `IMAGE_PROCESSING`
  2. NULL かつ `is_edited_manually=True` → `MANUAL_EDIT`
  3. それ以外の NULL かつ `existing=True` → `SIDECAR_IMPORT`
  4. 残りは NULL のまま
  擬似モデル行が無ければ移行内で作る。移行先に同じ (image_id, model_id, tag) の行が既にある NULL 行は
  UNIQUE を守るため移さない。`model_id` の NOT NULL 化はしない。
- **「擬似モデルか」の判定は 1 つにまとめる**。`schema.py` の擬似モデル sentinel の定数から
  `PSEUDO_MODEL_LITELLM_IDS` を導き、AI かどうかを判定する箇所はすべてこれを使う。
  - 「前回以降に変わった画像」の AI 実行判定から擬似モデルの行を除く (既存バグの修正)。
    手動編集は従来どおり `is_edited_manually` で拾う。
  - 「最近使ったモデル」から擬似モデルを除く。
  - 表示では `SIDECAR_IMPORT` を「取り込み」(`source="Import"`)、`IMAGE_PROCESSING` を「画像処理」
    (`source="Processing"`)、`MANUAL_EDIT` を「手動」として出し、AI とは出さない。

## Constraints

- 2024 年ごろの旧タガーがプロンプト欄から書き出したタグは、`.txt` の取り込みと区別できる情報が
  DB に残っていないため、移行で `SIDECAR_IMPORT` に入る。
- 移行の downgrade は `SIDECAR_IMPORT` / `IMAGE_PROCESSING` の行を NULL に戻す。`MANUAL_EDIT` へ
  移した行は、移行前から `MANUAL_EDIT` だった行 (GUI の手動編集) と区別できないため戻さない
  (旧版も `MANUAL_EDIT` の行をそのまま扱える)。

## Consequences

- タグ行の出所が `model_id` だけで分かり、出所ごとの一括取り消しや絞り込みができる。
- 手入力は経路によらず `MANUAL_EDIT` の 1 行にまとまり、soft-reject からの復活も同じ行で効く。
- 増分書き出しは、取り込みや自動付与だけがあった画像を「変わった」とみなさなくなる。
- 検索の「最近使ったモデル」に擬似モデル (`__generation_metadata__` を含む) が出なくなる。
  ADR 0107 の「ファセットに `__generation_metadata__` が出る」はこの点で置き換わる。
- `GENERATION_METADATA` / `KOHYA_DATASET` の行の表示ラベルは本 ADR では変えない。

## Related

- Issue #1616
- ADR 0023 (MANUAL_EDIT 行), ADR 0104 (擬似モデル KOHYA_DATASET), ADR 0107 (擬似モデル GENERATION_METADATA)
