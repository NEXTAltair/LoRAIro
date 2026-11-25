# タグ健全性レポート

`tags health` は既存プロジェクトの採用済みタグを読み取り、出現頻度・表記揺れ候補・明示した期待タグの欠落を報告します。

```bash
lorairo-cli --json tags health --project my_dataset
lorairo-cli --json --read-only tags health --project my_dataset \
  --expected-tag "1girl" --expected-tag "blue hair" --limit 100
```

## 動作の前提と読み取り専用保証

- `--read-only` の有無にかかわらず、常に読み取り専用で動作します。
- 現在のスキーマを持つ既存 DB が必要です。DB の初期化・マイグレーション・タグ DB の準備・モデル推論・タグ修正は一切実行しません。
- 未準備の DB に対して実行した場合は、既存の `PRECONDITION_FAILED` と復旧案内を返します。

## 集計と期待タグ

- **頻度の数え方**: 保存された同一タグが付いている**画像数**を集計します。同じ画像に複数モデルが同一タグを保存していても 1 件として数えます。大文字・小文字など保存値が異なるタグは、それぞれ個別に集計します。
- **対象外のタグ**: `rejected_at` が設定されたタグと、空白のみのタグは対象外です。なお、タグの付いていない画像もプロジェクト総数と欠落数に含めます。
- **期待タグの指定**: `--expected-tag` は「このタグを全画像に期待する」という明示条件です。複数指定する場合はオプションを繰り返します。省略時は期待タグを推測せず、欠落レコードも返しません。
- **期待タグの照合ルール**: 既存の `TagCleaner.clean_format` と `casefold` による比較で照合します(例:`Blue_Hair` と `blue hair` は一致します)。意味上の別名や翻訳の照合は行いません。重複する条件は最初の表記へまとめ、最大 500 条件まで指定できます。

## 表記揺れ候補の意味と範囲

- **`normalization`(正規化候補)**: 比較用表記が保存値と異なる場合に提示します。候補文字列が DB 内に存在するとは限りません。
- **`spelling`(スペル類似候補)**: 別の保存済みタグとの文字列類似候補を提示します。

どちらも誤りの断定や自動修正ではなく、内容を確認するための手掛かりとして扱ってください。

### スペル比較の対象と制限

- 対象は、正規化後の画像頻度順(同率は文字列順)で上位 500 語、かつ長さ 4〜128 文字のタグに限定します。短い語は誤検出を抑えるため比較対象外です。
- 標準ライブラリ `difflib.SequenceMatcher(autojunk=False)` の類似度比率が 0.85 以上の組を提示します。候補先は頻度順で先のタグです。
- この比率は意味の一致や正解確率を示すものではなく、表記が似た別概念を誤検出することがあります。
- 長すぎる語や 500 語上限によって比較対象が省略された場合は、`spelling_candidates_truncated=true` を返します。

## JSONL 出力と件数上限

各レコードは `kind=item` として出力され、`section` フィールドで種別を判別できます。

| `section` | フィールド |
| --- | --- |
| `frequency` | `tag`、`image_count` |
| `variant` | `tag`、`candidate`、`reason`、`similarity`(正規化候補では `null`) |
| `missing_expected` | `expected_tag`、`normalized_tag`、`missing_count`、`image_ids`、`image_ids_truncated` |

最後の `kind=result` 行では、`project`、`read_only=true`、`total_images`、`tagged_images`、`untagged_images`、`unique_tags`、`expected_tag_count` と、各セクションの件数および打ち切り情報を返します。期待タグが全画像に付与されている場合、そのタグの欠落レコードは出力しません。

### 出力件数・並び順・メモリ特性

- **上限指定**: `--limit` は既定 100(指定範囲 1〜500)で、各セクションの出力件数と各欠落レコードの画像 ID サンプル数を制限します。
- **並び順**: 頻度は画像数の降順(同率はタグ文字列順)、欠落条件は指定順、画像 ID は昇順です。表記揺れ候補は正規化候補のあとにスペル候補を返します。
- **全体件数と打ち切りフラグ**: `frequency_count`、`variant_count`、`missing_expected_count` は出力制限前の件数です。`frequencies_truncated`、`variants_truncated`、`missing_expected_truncated` は省略の有無を示します(`variant_count` は上記のスペル比較範囲内の候補数です)。
- **集計の正確性**: 集計画像数・各タグの画像数・期待タグの欠落数は、`--limit` やスペル比較上限に影響されないプロジェクト全体の値です。
- **メモリ消費**: 全画像 ID をメモリに保持せず、画像単位で読み取ります。タグの語彙集計では固有タグ数に比例するメモリを使用します。
