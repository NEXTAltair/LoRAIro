# Dataset Builder - MIT版ビルド戦略の更新

## 更新日
2025年12月16日

## 背景

MIT版ビルドの戦略を以下のように変更します：

**旧戦略**:
- tags_v4.dbをスキップ（`--skip-tags-v4`）
- MITライセンスのCSVのみを取り込み

**新戦略**:
- tags_v4.dbを含むCC0基盤でCC0版SQLiteを生成
- その上でMITライセンスのCSVを追加取り込みしてMIT版SQLiteを生成
- 可能なら1回のコマンドでCC0+MITを同時生成（デュアルビルド）

**新戦略（更新）**:
- MIT版は **CC0版SQLiteをベースに差分追記**する。
  - 目的: MIT版の `source_effects.tsv` にCC0由来（例: `danbooru_241016.csv` の `usage_counts_replaced`）が混ざらないようにする。
  - 目的: READMEのライセンス表記対象を「MIT差分で実際に影響したソース」に絞れるようにする。

## MIT版ビルド手順（更新）

1. CC0版をビルドして `genai-image-tag-db-cc0.sqlite` を生成（SQLite+Parquet）。
2. MIT版は CC0版SQLiteをコピーして `genai-image-tag-db-mit.sqlite` を作成。
3. builderは **MITソースのみ**を追記で取り込む（CC0ソースは再取り込みしない）。
   - `include_mit_sources.txt` にはMIT由来ソースのみを列挙する（例: `danbooru_241016.csv` や `TAG_FORMATS_202407081830.csv`、`Tags_zh_full.csv` などCC0由来のものは含めない）。
   - MIT版の `source_effects.tsv` ではCC0由来ソースが `filtered` として出ることはあり得るが、`imported` や `db_changes>0` で混入しないことを確認する。
4. MIT版のParquetも生成。
5. MIT版 `report-dir` に `source_effects.tsv` を出力し、`db_changes>0` のMITソースのみをREADMEに記載。

## 実装完了（2025年12月17日）

以下の機能を `builder.py` に実装しました：

### 新規パラメータ
- `base_db_path`: ベースとなる既存SQLiteファイルを指定（MIT版ビルド等で使用）
- `skip_danbooru_snapshot_replace`: Danbooruスナップショット置換をスキップ（MIT版で使用）

### 実装内容

#### 1. Phase 0/1のスキップ機能
`base_db_path` が指定された場合：
- Phase 0（DB作成・マスターデータ登録）をスキップ
- Phase 1（tags_v4.db取り込み）をスキップ
- 代わりに `base_db_path` からSQLiteファイルをコピー
- 既存DBから `tags_mapping`, `existing_tags`, `next_tag_id` を読み取り

#### 2. Danbooruスナップショット置換のスキップ機能
`skip_danbooru_snapshot_replace=True` の場合：
- Phase 2でDanbooruスナップショット検出をスキップ
- `_select_latest_count_snapshot()` を呼び出さない
- `has_authoritative_danbooru_counts = False` となり、通常のmax マージが適用される

#### 3. CLI引数の追加
- `--base-db`: ベースDBパスを指定
- `--skip-danbooru-snapshot-replace`: スナップショット置換をスキップ

### MIT版ビルドコマンド例

```powershell
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

### テスト結果
- 全119ユニットテスト: PASS
- カバレッジ: 60.38%（要求55%を上回る）
- 構文チェック: PASS（行長エラーのみ修正済み）

### 変更ファイル
1. `src/genai_tag_db_dataset_builder/builder.py`: 主要実装（+150行程度）
2. `license_builds/README.md`: MIT版ビルド手順の更新

### 効果
- MIT版の `source_effects.tsv` にはMIT差分のみが記録される
- READMEのライセンス表記を「実際に影響したMITソース」に絞れる
- CC0由来のデータ（例: `danbooru_241016.csv`）がMIT版レポートに混入しない

## コミット記録

### Submodule (genai-tag-db-dataset-builder)
- Commit: cce30a7
- Message: "feat: Implement MIT differential build strategy with idempotent SQL upserts"
- Files: builder.py, license_builds/README.md, test_idempotent_upserts.py, test_builder_smoke.py

### Main Repository
- Commit: 904f57b
- Message: "feat: Update dataset builder with MIT differential build strategy"
- Files: submodule reference, memory files (mit_build_strategy, source_effects_idempotent_upserts)
