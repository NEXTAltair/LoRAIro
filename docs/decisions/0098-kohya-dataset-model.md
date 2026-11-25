---
type: ADR
title: Kohya-ss 学習データセットのデータモデルと取り込み・書き出し
status: Accepted
timestamp: 2026-11-25
tags: [dataset, kohya, import, export, training-config]
---

# ADR 0098: Kohya-ss 学習データセットのデータモデルと取り込み・書き出し

## Context

Kohya-ss 形式の学習データセット(`<繰り返し数>_<名前>/` フォルダ、画像、同名の `.txt` および `.caption`)とその学習設定を LoRAIro へ取り込み、同じ形式で書き出せるようにする必要がある。

主な要件は以下の 3 点である。

- 同じ画像が複数フォルダに所属し、フォルダごとに異なる学習テキストを持てること。
- データセットの版(履歴)を管理できること。
- 学習パラメーターを次の学習へ再利用できること。

詳細は設計書 `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`(§4、§9.5、§12)を参照する。

## Decision

### 1. データセットと版の単位

データセットの単位は、複数フォルダを含む学習プロジェクト全体とする。旧版と新版は別データセットに分けず、1 つのデータセットの版(履歴)として扱い、親の版への参照のみを記録する。

各版には全量のレコードを保持し、版同士の比較は表示時に計算する。

### 2. 学習テキストの原文保持と組み立て

取り込み時の学習テキスト原文は、版の記録として 1 回だけ保存する。確定済みの版(`dataset_versions.is_working=False`)は後から書き換えない。

- 編集せずに書き出す場合は、保存した原文をそのまま出力し、完全一致を保証する。
- 編集後はカンマ区切りの要素データから文字列を組み立てる。要素の中身・順序・表記は維持し、空白と末尾改行のみ変化を許容する。

### 3. 作業中の版による編集と確定

LoRAIro 内で版を編集する際は、指定した確定済みの版(省略時は最新の確定済みの版)からフォルダ・画像所属・学習テキストを全量コピーする。そのうえで `parent_version_id` に派生元を記録した「作業中の版」(`is_working=True`、1 データセットにつき同時に 1 つまで)を作成する(Issue #1486)。

- **確定済みの版の保護**: `is_working=False` の版に対する編集(`update_learning_text_elements`、画像の追加・差し替え・削除、トリガーワード変更)と破棄はすべて拒否する。
- **作業中の版の確定**: `commit_working_version` を実行すると `is_working=False` となり、以降は書き換え不可の新しい版として `parent_version_id` との差分(`DatasetVersionDiffService` および `dataset diff`)を計算できる。
- **作業中の版の破棄**: `discard_working_version` を実行すると、確定済みの版へ影響を与えずに作業中の版とその配下の行のみを削除する。
- **画像の差し替え**: `replace_image_in_working_folder` では、既定で旧画像の学習テキストを引き継ぐ(`inherit_texts=True`)。引き継がない指定(`inherit_texts=False`)の場合は、フォルダに `trigger_word` があれば `.txt` にそのトリガーワードだけを残し、なければ空にする。

### 4. タグの格納方針

取り込んだタグは、データセット内(フォルダと画像の組み合わせに紐づく学習テキスト)に版の記録として保持する。あわせて、取り込みの最後に画像直下の `Tag` へ擬似モデル `KOHYA_DATASET` の行として登録する(登録と同期の規則は ADR 0104)。

- 学習テキストはフォルダ別の原文と要素のまま保持し、書き出し(round trip)はこれだけを使う。`Tag` の内容は書き出しに影響しない。
- 通常タグ(`Tag`)に載せるのは、データセットごとの最新版の要素だけとする。古い版の要素は学習テキストにだけ残り、画像詳細の「学習に使ったデータセット」で確認する。
- タグ表記は書き換えず、分割はカンマと前後空白の除去のみを行う(`TagCleaner.clean_format` は使用しない)。
- タグは文字列のまま保持し、`tag_id` 参照にはしない。タグ DB は別 DB であり外部キー制約を張れないため、参照による版内容の変化を防ぐ。

改訂の経緯: 当初は「学習テキストにのみ保持し `Tag` には登録しない」としていた。しかし取り込んだ画像を選んでもタグ欄に何も出ず、手作業で整えたタグを次のデータセット作りに活かせなかった。別操作で写す方式(ADR 0104 の初版)も、学習テキストと通常タグの二重管理を利用者に意識させるだけだったため、取り込み時に常に登録する方式へ改めた。

### 5. トリガーワードの扱い

トリガーワードはフォルダの属性として管理する。取り込み時に先頭要素の共通性から候補を抽出し、ユーザーが確認して確定する。書き出し時には、学習テキストをトリガーワードで書き換えない。

- 作業中の版のフォルダへ画像を追加する際(`add_image_to_working_folder`)は、既定(`auto_prepend_trigger_word=True`)でフォルダの `trigger_word` が要素に含まれていなければ先頭へ自動付与する。
- トリガーワードが設定されたフォルダ内で `.txt` の要素にトリガーワードを含まない画像は、`find_images_missing_trigger_word` で検出できる。

### 6. 学習パラメーターの保存と変換

学習パラメーターは、元の内容と正規化した内容の両方を `training_configs` へ保存する。

- 秘密情報は取り込み時に除去し、保存も書き出しも行わない。
- 変換規則が未確認のキー、および `Standard` と `LyCORIS/LoCon` 以外の `LoRA_type` は変換せず、「未変換」の欄に残す。

### 7. sd-scripts TOML の書き出しと変換規則の根拠

書き出し形式は sd-scripts の TOML(`--dataset_config` と `--config_file`)とし、仕様は sd-scripts のソースコードを正とする。

- 空文字のキーは除外し、値の型は引数表に合わせる。
- `caption_extension` は常に明示する。
- 起動ツールの引数は含めず、フォルダのパスは書き出し先に合わせる。
- 変換規則の根拠は Kohya_ss の操作画面ソースと sd-scripts のソースとし、実際に動作した設定および `.bat` ファイルと突き合わせて検証する。

## Implementation

- **テーブル**: `datasets`、`dataset_versions`、`dataset_folders`、`dataset_folder_images`、`dataset_learning_texts`、`training_configs`(マイグレーション付き)。永続化は `DatasetRepository` が担う。
- **ビジネスロジック**: `learning_text`、`kohya_scanner`、`kohya_config_normalizer`、`sd_scripts_arg_table`、`sd_scripts_toml`、`DatasetImportService`、`KohyaDatasetExportService`(いずれも Qt 非依存)。
- **CLI**: `lorairo-cli dataset import`、`lorairo-cli dataset export`、`lorairo-cli dataset show`。

## Consequences

- 取り込んだ画像は `Image` として登録され、最新版の学習テキストの要素が `KOHYA_DATASET` のタグとして通常の検索・タグ編集に現れる(ADR 0104)。
- 版ごとに全量を保持するため容量は増えるが、テキストデータのみであるため許容する。
- 未変換のキーは TOML に出力されないため、利用する `LoRA_type` が増えた段階で変換規則を追加する。
- GUI の取り込み・編集ダイアログおよび差分取り込みは後続とし、本 ADR の範囲外とする。

## Related

- 設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`
- 計画: `docs/superpowers/plans/2026-11-05-kohya-dataset-core.md`
- Issue: #1410(親)、#1404(sd-scripts 調査)、#1409(共通タグ入力)、#1455(版の比較)、#1486(作業中の版の編集と確定)
- Issue: #1647(取り込み時に通常タグへ登録する改訂)
- ADR: 0035、0104(学習テキストをライブラリの `Tag` へ写す)
