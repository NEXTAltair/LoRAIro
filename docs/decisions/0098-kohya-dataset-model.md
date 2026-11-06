---
type: ADR
title: Kohya-ss 学習データセットのデータモデルと取り込み・書き出し
status: Proposed
timestamp: 2026-11-06
tags: [dataset, kohya, import, export, training-config]
---

# ADR 0098: Kohya-ss 学習データセットのデータモデルと取り込み・書き出し

## Context

Kohya-ss 形式の学習データセット (`<繰り返し数>_<名前>/` フォルダ、画像、同名の `.txt` / `.caption`) と
その学習設定を、LoRAIro に取り込み、同じ形で書き出せるようにする。
同じ画像が複数フォルダに入り、フォルダごとに学習テキストが異なること、版 (履歴) を持つこと、
学習パラメーターを次の学習へ再利用できることが要件になる。
詳細は設計書 `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md` (§4, §9.5, §12)。

## Decision

- データセットの単位は複数フォルダを持つ学習プロジェクト全体とする。旧版・新版は別データセットではなく
  1 つのデータセットの版 (履歴) とし、親の版への参照だけを記録する。版ごとに全量のレコードを持ち、
  版の比較は表示時に計算する。
- 取り込み時の学習テキスト原文を版の記録として 1 回だけ保存し、版は後から書き換えない。
  編集せずに書き出すときは原文を出す (完全一致)。編集後は要素 (カンマ区切り) のデータから組み立て、
  要素の中身・順序・表記は保つ (空白と末尾改行は変わってよい)。
- 取り込んだタグはデータセット内 (フォルダ × 画像の学習テキスト) にだけ持ち、画像直下の `Tag` には入れない。
  タグ表記は書き換えず、分割はカンマと前後空白の除去のみ (`TagCleaner.clean_format` は使わない)。
  タグは文字列のまま持ち、`tag_id` 参照にしない (タグ DB は別 DB で外部キーが無く、版の中身が変わるのを防ぐ)。
- トリガーワードはフォルダの属性とする。取り込み時に先頭要素の共通性から候補を出し、ユーザーが確認して確定する。
  書き出しでは学習テキストをトリガーワードで書き換えない。
- 学習パラメーターは元の中身と正規化したものの両方を `training_configs` に保存する。
  秘密の値は取り込み時に取り除き、保存も書き出しもしない。
  変換規則が未確認のキーと、`Standard` / `LyCORIS/LoCon` 以外の `LoRA_type` は変換せず「未変換」の欄に残す。
- 書き出しは sd-scripts の TOML (`--dataset_config` と `--config_file`) とし、仕様は sd-scripts のソースを正とする。
  空文字のキーは除き、値の型は引数表に合わせ、`caption_extension` は常に明示し、
  起動ツールの引数は入れず、フォルダの場所は書き出し先に合わせる。
- 変換規則の出どころは Kohya_ss の操作画面のソースと sd-scripts のソースとし、実際に動いた設定と `.bat` と突き合わせて確かめる。

## Implementation

- テーブル: `datasets`, `dataset_versions`, `dataset_folders`, `dataset_folder_images`,
  `dataset_learning_texts`, `training_configs` (migration 付き)。永続化は `DatasetRepository`。
- Business Logic: `learning_text`, `kohya_scanner`, `kohya_config_normalizer`, `sd_scripts_arg_table`,
  `sd_scripts_toml`, `DatasetImportService`, `KohyaDatasetExportService` (いずれも Qt-free)。
- CLI: `lorairo-cli dataset import / export / show`。

## Consequences

- 取り込んだ画像は `Image` として登録されるが、タグ付きでは通常の検索・タグ編集に出ない。
  ライブラリ側へタグを写す機能は後続。
- 版ごとに全量を持つため容量は増えるが、テキストのみで許容する。
- 未変換のキーは TOML に入らないため、使う `LoRA_type` が増えたら変換規則を足す。
- 後続 (本 ADR の範囲外): GUI の取り込みダイアログ、トリガーワードの自動付与、差分取り込み、
  既存ライブラリ画像のデータセットへの追加。

## Related

- 設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`
- 計画: `docs/superpowers/plans/2026-11-05-kohya-dataset-core.md`
- Issue #1410 (親), #1404 (sd-scripts 調査), #1409 (共通タグ入力)
- ADR 0035
