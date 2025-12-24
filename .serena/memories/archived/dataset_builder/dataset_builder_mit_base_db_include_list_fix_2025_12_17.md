# 作業記録: MITビルド（CC0ベース差分追記）でCC0ソース混入を防ぐ

## 日付
2025-12-17

## 背景 / 問題
MIT版は「CC0版SQLiteをベースに差分追記」方式に変更したが、`out_db_mit/source_effects.tsv` に `TagDB_DataSource_CSV/danbooru_241016.csv`（CC0 Danbooruスナップショット）が `imported` として記録されるケースがあった。

## 原因
`license_builds/include_mit_sources.txt` に **CC0由来ソースが混入**していた。
- `TagDB_DataSource_CSV/danbooru_241016.csv`
- `TagDB_DataSource_CSV/TAG_FORMATS_202407081830.csv`
- `TagDB_DataSource_CSV/TAG_TYPES_202407081829.csv`
- `TagDB_DataSource_CSV/FORMAT_TAG_TYPES_202407081829.csv`
- `TagDB_DataSource_CSV/translation/Tags_zh_full.csv`

これにより、MITビルドでもホワイトリストに一致して取り込み対象になっていた。

## 対応
- `license_builds/include_mit_sources.txt` から上記CC0由来行を削除し、**MIT差分ソースのみ**列挙するように修正。

## 検証（MIT差分追記ビルド）
実行コマンド（例）:
```powershell
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\local_packages\genai-tag-db-dataset-builder\out_db_mit\genai-image-tag-db-mit.sqlite `
  --sources . `
  --report-dir .\local_packages\genai-tag-db-dataset-builder\out_db_mit `
  --include-sources .\local_packages\genai-tag-db-dataset-builder\license_builds\include_mit_sources.txt `
  --base-db .\local_packages\genai-tag-db-dataset-builder\out_db_cc0\genai-image-tag-db-cc0.sqlite `
  --skip-danbooru-snapshot-replace `
  --parquet-dir .\local_packages\genai-tag-db-dataset-builder\out_db_mit\parquet `
  --overwrite
```

確認結果:
- `out_db_mit/source_effects.tsv` で `danbooru_241016.csv` は `filtered` / `db_changes=0` になり、MIT差分としては混入しない。
- `usage_counts_replaced` もMIT側では発生しない（`--skip-danbooru-snapshot-replace` により回避）。

## 運用メモ
- MIT版READMEのライセンス列挙は `out_db_mit/source_effects.tsv` の `db_changes > 0` のソースに限定してよい。
- CC0由来ソースはCC0ビルド側（`include_cc0_sources.txt`）にのみ置く。