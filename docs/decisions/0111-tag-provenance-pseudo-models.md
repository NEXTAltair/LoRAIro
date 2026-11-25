---
type: ADR
title: model_id が空のタグ行に出所を持たせる (擬似モデル SIDECAR_IMPORT / IMAGE_PROCESSING)
status: Accepted
timestamp: 2026-11-19
tags: [tags, provenance, manual-edit, migration, sidecar]
---

# ADR 0111: model_id が空のタグ行に出所を持たせる(擬似モデル SIDECAR_IMPORT / IMAGE_PROCESSING)

## Context

`Tag` テーブルには出所を表す専用列が無く、区別に使える列は `model_id`・`existing`・`is_edited_manually` のみである(ADR 0104 / ADR 0107 と同じ事情)。従来、`model_id` が空(NULL)の行には、次の異なる出所が混在していた。

- 画像に添えた `.txt`(関連ファイル)からの取り込み
- CLI での手入力(`images` / `tags` のタグ追加、一括置換の置換先)、およびクロップで新たに与えたタグ
- アップスケール時に自動付与される `upscaled`

GUI の手動編集は既に `MANUAL_EDIT` の `model_id` で保存されていたため、同じ「手入力」でも経路によって NULL と `MANUAL_EDIT` に分裂していた。さらに、読み取り側には次の不整合も生じていた。

- 増分書き出しにおける「前回以降に変わった画像」の判定が、`model_id` の有無だけで AI 実行とみなしていたため、擬似モデル(`KOHYA_DATASET` / `GENERATION_METADATA` 等)の行まで AI 実行として拾っていた(既存バグ)。
- 検索の「最近使ったモデル」に擬似モデルが表示されていた。
- 画面表示では出所不明の行が `Unknown` または手動扱いになり、取り込みと手入力を区別できなかった。

## Decision

### 1. 擬似モデルを 2 つ追加する

既存の擬似モデルと同じく、`provider="user"`、`model_types` なし、`requires_api_key=False` の属性で 2 つの擬似モデルを追加する。スキーマ変更は行わず、実行時の初回利用時にモデル行を作成する。

- `SIDECAR_IMPORT`(`litellm_model_id="__sidecar_import__"`): 関連ファイル(`.txt`)から取り込んだタグ
- `IMAGE_PROCESSING`(`litellm_model_id="__image_processing__"`): 画像処理が自動付与したタグ(`upscaled`)

### 2. 書き込み時に NULL を作らない

新規書き込み時の `model_id` 割り当てを次のとおり統一する。

| 書き込み経路 | 割り当てる `model_id` |
|---|---|
| `.txt` からの取り込み(キャプションは対象外) | `SIDECAR_IMPORT` |
| CLI の手動追加(ドライランの見積もりを含む)、一括置換の置換先、クロップで新たに与えたタグ | `MANUAL_EDIT` |
| クロップで親画像から引き継ぐタグ | 親の行の `model_id` を維持 |
| アップスケール時の `upscaled` | `IMAGE_PROCESSING` |

- 手動追加で同じ表記のソフトリジェクト(soft-reject)済み行を復活させる判定は、`MANUAL_EDIT` の行を対象とする(`uq_tags_image_model_tag` に反する重複行を作らない)。
- ドライラン(dry-run)の見積もりではモデル行を作成しない。

### 3. 既存データを Alembic のデータ移行で振り分ける

集合ベースの `UPDATE` により、`updated_at` を変えずに既存の NULL 行を次の優先順で振り分ける。

1. `model_id` が NULL かつ `tag='upscaled'` かつ `existing=False` の行は `IMAGE_PROCESSING` へ移す。
2. `model_id` が NULL かつ `is_edited_manually=True` の行は `MANUAL_EDIT` へ移す。
3. それ以外の `model_id` が NULL かつ `existing=True` の行は `SIDECAR_IMPORT` へ移す。
4. 上記に該当しない残りの行は NULL のまま残す。

擬似モデル行が未作成であれば移行内で作成する。移行先に同じ `(image_id, model_id, tag)` の行が既に存在する NULL 行は、UNIQUE 制約を守るため移行せず残す。また、`model_id` の NOT NULL 制約化は行わない。

### 4. 擬似モデルの判定を 1 箇所に集約する

`schema.py` に定義された擬似モデルの番兵(sentinel)定数から `PSEUDO_MODEL_LITELLM_IDS` を導出し、AI モデルかどうかを判定するすべての箇所でこれを参照する。

- 「前回以降に変わった画像」の AI 実行判定から擬似モデルの行を除外する(既存バグの修正)。手動編集は従来どおり `is_edited_manually` で判定する。
- 検索の「最近使ったモデル」から擬似モデルを除外する。
- 表示では `SIDECAR_IMPORT` を「取り込み」(`source="Import"`)、`IMAGE_PROCESSING` を「画像処理」(`source="Processing"`)、`MANUAL_EDIT` を「手動」として出力し、AI とは表示しない。

## Constraints

- 2024 年ごろの旧タガーがプロンプト欄から書き出したタグは、`.txt` 取り込みと区別できる情報が DB に残っていないため、移行によって `SIDECAR_IMPORT` に分類される。
- 移行のダウングレード(downgrade)では、`SIDECAR_IMPORT` と `IMAGE_PROCESSING` の行を NULL へ戻す。一方で、`MANUAL_EDIT` へ移した行は移行前から存在した GUI 手動編集の行と区別できないため戻さない(旧版でも `MANUAL_EDIT` の行はそのまま扱える)。

## Consequences

- タグ行の出所が `model_id` だけで判別できるようになり、出所ごとの一括取り消しや絞り込みが可能になる。
- 手入力は経路によらず `MANUAL_EDIT` の 1 行に統一され、ソフトリジェクトからの復活も一貫して機能する。
- 増分書き出しは、取り込みや自動付与だけが行われた画像を「変更あり」と誤判定しなくなる。
- 検索の「最近使ったモデル」に擬似モデル(`__generation_metadata__` を含む)が表示されなくなる。ADR 0107 の「ファセットに `__generation_metadata__` が出る」という記述はこの点で置き換わる。
- `GENERATION_METADATA` と `KOHYA_DATASET` の表示ラベルは本 ADR では変更しない。

## Related

- Issue #1616
- ADR 0023(`MANUAL_EDIT` 行)、ADR 0104(擬似モデル `KOHYA_DATASET`)、ADR 0107(擬似モデル `GENERATION_METADATA`)
