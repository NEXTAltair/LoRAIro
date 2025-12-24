# Dataset Builder - MIT版HuggingFaceアップロード完了

## 日付
2025年12月17日

## アップロード情報

### リポジトリ
- **URL**: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db-mit
- **ライセンス**: MIT
- **形式**: SQLite + Parquet

### ビルド構成

MIT版は CC0版をベースとした差分ビルド:
1. **ベース**: CC0版SQLite（tags_v4.db + CC0ソース）
2. **差分追加**: MITライセンスソースのみ追加取り込み
3. **レポート**: `source_effects.tsv` には MIT差分のみ記録

### 使用した機能

以下の実装機能を使用してビルド:

#### 1. MIT差分ビルド戦略
- `--base-db`: CC0版SQLiteをコピーしてベース使用
- `--skip-danbooru-snapshot-replace`: スナップショット置換スキップ
- Phase 0/1 自動スキップ（DB作成・tags_v4.db取り込み）

#### 2. 冪等なSQL UPSERT
- TAG_STATUS: 値が実際に変更された場合のみ更新
- TAG_USAGE_COUNTS: 新しいcountが既存より大きい場合のみ更新
- source_effects追跡精度向上

#### 3. 翻訳データクリーンアップ
- 言語値正規化（japanese→ja、zh-Hant→zh）
- ja翻訳の誤登録削除（中国語・英単語）
- 必須文字種チェック（ja/zh/ko）
- 全角記号正規化

#### 4. Parquetエクスポート
- HuggingFace Dataset Viewer 対応
- Danbooru形式カラム構成
- `--parquet-dir` で出力

### ビルドコマンド（推定）

```powershell
# CC0版ビルド
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\out_db_cc0\genai-image-tag-db-cc0.sqlite `
  --sources . `
  --report-dir .\out_db_cc0 `
  --include-sources .\license_builds\include_cc0_sources.txt `
  --parquet-dir .\out_db_cc0\parquet_danbooru `
  --overwrite

# MIT版ビルド（CC0版をベースに差分追記）
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\out_db_mit\genai-image-tag-db-mit.sqlite `
  --sources . `
  --report-dir .\out_db_mit `
  --include-sources .\license_builds\include_mit_sources.txt `
  --base-db .\out_db_cc0\genai-image-tag-db-cc0.sqlite `
  --skip-danbooru-snapshot-replace `
  --parquet-dir .\out_db_mit\parquet `
  --overwrite
```

### ライセンス表記

MIT版の README では `source_effects.tsv` の `db_changes > 0` のソースのみをライセンス表記対象として列挙可能:
- CC0由来ソース（danbooru_241016.csv 等）は MIT版レポートに混入しない
- 実際に影響したMITソースのみを記載

## 関連メモリ

- `dataset_builder_mit_build_strategy_update_2025_12_16.md`: MIT差分ビルド戦略
- `dataset_builder_source_effects_idempotent_upserts_2025_12_17.md`: 冪等UPSERT実装
- `dataset_builder_translation_cleanup_2025_12_17.md`: 翻訳クリーンアップ実装
- `dataset_builder_parquet_export_completion_2025_12_16.md`: Parquetエクスポート実装

## 今後の展開

CC0版も同様の手順で HuggingFace へアップロード可能:
- リポジトリ: NEXTAltair/genai-image-tag-db-cc0（推定）
- source_effects.tsv: CC0ソースのみ記録
