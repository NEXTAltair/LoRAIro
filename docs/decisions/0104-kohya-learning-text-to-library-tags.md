---
type: ADR
title: Kohya データセットの学習テキストをライブラリの Tag へ写す (擬似モデル KOHYA_DATASET)
status: Accepted
timestamp: 2026-11-08
tags: [dataset, kohya, tags, provenance, manual-edit]
---

# ADR 0104: Kohya データセットの学習テキストをライブラリの Tag へ写す (擬似モデル KOHYA_DATASET)

## Context

Kohya 取り込みで入れた学習テキスト (手動で整理された精度の高いタグ) は `dataset_learning_texts`
(フォルダ × 画像) にだけあり、画像直下の `Tag` には入らない (ADR 0098)。そのため通常の検索・タグ編集・
通常の書き出しで使えない。ライブラリ側へ写す操作は ADR 0098 で後続とされ、#1397 でも
「現在のアノテーションへの反映は、履歴保存とは別の明示的な操作」とされている。

`Tag` には由来を表す列が無く、区別に使えるのは `model_id` / `existing` / `is_edited_manually` だけである。
`uq_tags_image_model_tag` (image_id, model_id, tag) が UNIQUE のため、`model_id` が違えば同じ表記の行が並んで存在できる。

## Decision

- 明示的な「ライブラリへ写す」操作として入れる。対象は 1 つの版と、その中から選んだフォルダ
  (指定が無ければ版の全フォルダ)。最初は CLI (`lorairo-cli dataset copy-tags`、`--dry-run` あり) だけとし、GUI は後続。
- 写した行は専用の擬似モデル `KOHYA_DATASET` (`provider="user"`、`litellm_model_id="__kohya_dataset__"`、
  `model_types` なし、`requires_api_key=False`) の `model_id` で持つ。手入力・共通タグ (`MANUAL_EDIT`) や
  AI の行とは別の行として共存させ、`model_id` で一括して取り消せるようにする。スキーマ変更はしない
  (`MANUAL_EDIT` と同じく、モデル行は初回に作る)。
- 同じ画像が選んだ複数のフォルダにあるときは、それらの学習テキストの要素の和集合を写す (選んでいない
  フォルダは使わない)。写すのは 1 つの拡張子の学習テキストだけで、既定は `.txt` (タグ) とする。
  `.caption` (文章のキャプション) はカンマ区切りの要素がタグにならないため、明示したときだけ写す。
- 表記は学習テキストの要素のまま写す (ADR 0098 と #1448 の共通タグと同じく `clean_format` もタグ DB での
  解決もしない。`tag_id` は空)。行は `existing=True`, `is_edited_manually=False` とする
  (取り込み元に既にあったタグであり、LoRAIro 上で手編集したものではない)。
- 写した後に学習テキストや版が変わっても、ライブラリ側は追従させない。写し直しは追加だけを行い、
  既に `KOHYA_DATASET` の同じ行 (soft-reject 済みを含む) がある画像には触れない。
  他のモデルの行は読みも書きもしない。
- `MANUAL_EDIT` と同じ除外は、モデル行の属性 (`model_types` なし、`requires_api_key=False`) で効く。
  推論の対象 (`ModelSelectionService` の annotation eligible 判定) と、WebAPI モデルの availability 調整
  (`reconcile_api_model_availability`) からは自然に外れるため、除外処理に名前で足す箇所は無い。
  名前で `MANUAL_EDIT` を見ている残りの箇所は、すべてレーティング (`Rating`) か手動タグの書き込み先であり、
  `Tag` だけを書く本操作には当てはまらない。

## Consequences

- 写したタグは通常の検索・タグ編集・通常の書き出しに出る。検索の「モデル」ファセットには
  `__kohya_dataset__` が他のモデルと同じく出るため、由来で絞り込める。
- 版・フォルダ・元の学習テキストまでは追えない。必要になったら `Tag` に由来の列を足す (#1454 の案 C)。
- 表記をそのまま写すため、ライブラリの表記 (例: アンダースコアと空白) と揃わないことがある。
- 取り消し (`KOHYA_DATASET` 行の一括削除) と GUI の入口は後続。

## Related

- Issue #1454, #1397, #1448, #1404
- ADR 0098 (データセットモデル), ADR 0023 (MANUAL_EDIT 行)
