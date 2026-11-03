# タグ健全性レポート

`tags health` は既存プロジェクトの採用済みタグを読み取り、頻度、表記揺れ候補、明示した期待タグの欠落を報告します。

```bash
lorairo-cli --json tags health --project my_dataset
lorairo-cli --json --read-only tags health --project my_dataset \
  --expected-tag "1girl" --expected-tag "blue hair" --limit 100
```

`--read-only` の有無によらず読み取り専用です。現在のスキーマを持つ既存 DB が必要で、DB の初期化、マイグレーション、タグ DB の準備、モデル推論、タグ修正は実行しません。未準備の DB は既存の `PRECONDITION_FAILED` と復旧案内を返します。

## 集計と期待タグ

- 頻度は、保存された同一タグが付いた**画像数**です。同じ画像に複数モデルが同じタグを保存していても 1 件として数えます。大文字・小文字など保存値が異なるタグの頻度は個別に返します。
- `rejected_at` が設定されたタグ、空白のみのタグは対象外です。タグのない画像もプロジェクト総数と欠落数に含めます。
- `--expected-tag` は「このタグを全画像に期待する」という明示条件です。複数条件はオプションを繰り返します。省略時は期待タグを推測せず、欠落レコードも返しません。
- 期待タグは既存 `TagCleaner.clean_format` と `casefold` による比較で照合します。たとえば `Blue_Hair` と `blue hair` は一致します。意味上の別名や翻訳の照合はしません。重複条件は最初の表記へまとめ、最大 500 条件です。

## 候補の意味と範囲

`normalization` は上記の比較用表記が保存値と異なる場合の候補です。候補文字列が DB に存在するとは限りません。`spelling` は別の保存済みタグとの文字列類似候補です。どちらも誤りの断定や自動修正ではなく、内容を確認するための手掛かりです。

スペル比較は正規化後の画像頻度順（同率は文字列順）の最大 500 語、長さ 4～128 文字に限定します。標準ライブラリ `difflib.SequenceMatcher(autojunk=False)` の比率が 0.85 以上の組を提示します。候補先は頻度順で先のタグです。この比率は意味の一致や正解確率ではなく、似た別概念の誤検出もあります。長すぎる語や 500 語上限で対象が省略された場合は `spelling_candidates_truncated=true` を返します。短い語は誤検出を抑えるため比較対象外です。

## JSONL と上限

`kind=item` は `section` で識別できます。

| section | フィールド |
| --- | --- |
| `frequency` | `tag`, `image_count` |
| `variant` | `tag`, `candidate`, `reason`, `similarity`（正規化候補では null） |
| `missing_expected` | `expected_tag`, `normalized_tag`, `missing_count`, `image_ids`, `image_ids_truncated` |

最後の `kind=result` は `project`, `read_only=true`, `total_images`, `tagged_images`, `untagged_images`, `unique_tags`, `expected_tag_count` と各セクションの件数・打ち切り情報を返します。期待タグが全画像にある場合、そのタグの欠落レコードは返しません。

`--limit` は既定 100、1～500。各セクションの出力件数と各欠落レコードの画像 ID サンプル数を制限します。頻度は画像数降順・タグ文字列順、欠落条件は指定順、ID は昇順です。候補は正規化候補の後にスペル候補を返します。

`frequency_count`, `variant_count`, `missing_expected_count` は出力を制限する前の件数、`frequencies_truncated`, `variants_truncated`, `missing_expected_truncated` はレコードの省略有無です。`variant_count` は上述のスペル比較範囲内の候補数です。集計画像数、各タグの画像数、期待タグの欠落数は、`--limit` やスペル比較上限によらずプロジェクト全体の値です。全画像 ID をメモリに保持せず、画像単位で読み取ります。タグの語彙集計は固有タグ数に比例するメモリを使います。
