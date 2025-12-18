# deepghs/site_tags 調査ログ（Phase7前）

## 目的
- `deepghs/site_tags` を既存タグDBへ統合するための前提情報（列の意味、サイト数、alias/parent/type/countの意味と分布）を整理する。

## 決定事項（このログの前提）
- **TAG_FORMATS.format_name はドメインのドット前まで**を採用する。
  - 例: `anime-pictures.net` → `anime-pictures`
  - 例: `danbooru.donmai.us` → `danbooru`
  - 例: `e621.net` → `e621`
- 例外:
  - `en.pixiv.net` → `pixiv`（`en` ではなく `pixiv` に寄せる）
- `site_tags` はサイト別フォルダに分割されており、統合DB（サイト横断の関係）は別途ETLで構築する。

## 取得済み状況
- Clone先: `C:\LoRAIro\external_sources\site_tags`
- 取得サイズ: 約 4.86GiB
- Git LFS関連警告（実害小）:
  - `lolibooru.moe/tag_aliases.csv`（約94KB）
  - `lolibooru.moe/tag_aliases.json`（約161KB）

## 調査チェックリスト（逐次追記）

### 1) サイト一覧と形式
- サイトフォルダ数（= format候補数）
- 各サイトが持つ形式（`tags.sqlite/tags.csv/tags.json/tags.parquet` 等）
  - SQLiteの全体スキーマ（サイト横断）をまず把握する（差分のあるサイトを見つける）

### 2) SQLiteスキーマ（代表サイト複数）
代表サイト（例: `danbooru`, `e621`, `lolibooru`, `anime-pictures`）で差分を記録する。
- テーブル一覧
- `tags` テーブルの列一覧
- `alias/parent/type/num/num_pub/views` の意味
- `alias/parent` が `id` 参照か（孤立参照の有無）

### 3) 列の意味の確定（最重要）
- `type` の数値コードの意味（サイトごとに異なる可能性）
- `alias` の方向（別名→推奨 なのか、推奨→別名 なのか）
- `parent` の意味（階層/グルーピング）
- `num` と `num_pub` の違い

### 4) 既存DBへのマッピング案（暫定）
- `tags.tag` → `TAGS.tag`（正規化後）
- サイト固有情報（type/alias/preferred/parent）→ `TAG_STATUS`
- count相当（`num`/`views`等）→ `TAG_USAGE_COUNTS`（採用列を決める）
- 翻訳（`tag_jp/tag_ru` 等）→ `TAG_TRANSLATIONS`

---

## 調査メモ（逐次追記）

### 2025-12-17
- clone 完了。巨大ファイル上位に各サイトの `tags.sqlite` が存在。
- 例（あるサイトの `tags.sqlite`）: `tags` 単一テーブルで以下の列を確認
  - `index, id, tag, tag_ru, tag_jp, num, num_pub, type, description_en, description_ru, description_jp, alias, parent, views`
- Danbooru（`danbooru.donmai.us/tags.sqlite`）のスキーマ確認:
  - テーブル: `tags`, `tag_aliases`
  - `tags` 列:
    - `id, name, post_count, category, created_at, updated_at, is_deprecated, words`（他に `index`）
  - `tag_aliases` 列:
    - `alias TEXT, tag TEXT`（他に `index`）
    - 文字列→文字列の置換（alias→推奨名）に見える

#### Danbooru: deprecated と alias の対応関係（実データ検証）
（`danbooru.donmai.us/tags.sqlite` に対しローカルでクエリ実行）

- `tags_total`: 1,593,780
- `tags_deprecated`（`is_deprecated=1`）: 3,510
- `aliases_total`（`tag_aliases` 行数）: 52,496
- `deprecated_without_replacement`（deprecatedだが `tag_aliases.alias = tags.name` が無い）: **3,221**
  - deprecatedタグの多くが「alias置換先を必ず持つ」わけではない（少なくともこのスナップショットではそうなっている）

サンプル（deprecated だが置換先が見つからない例）:
- `looking_away`, `eyebrows`, `uniform`, `light_blue_hair`, `striped`, `plaid` など

一方で `tag_aliases` 側には、deprecatedフラグと独立に見える alias 置換が存在する（`alias_but_not_deprecated_exists` が真）:
- 例: `!!! -> !!`, `!!!! -> !!`, `.3. -> o3o` など（この alias が deprecated と一致しない／または tags 側に無い可能性）

暫定結論:
- Danbooruの `is_deprecated` は `alias` とは別軸の状態フラグとして扱う必要がある。
- 「deprecatedなら必ず置換先がある」を前提に統合ロジックを書くのは危険（例外が多い）。

#### site_tags 全体: SQLiteスキーマ差分の集計
（`C:\LoRAIro\external_sources\site_tags` 配下の `**/tags.sqlite` を走査）

- SQLite DB数: 18
- スキーマ署名（列構造のハッシュ）ユニーク数: 12
- 生成物:
  - 行列（サイト→署名）: `.serena/memories/deepghs_site_tags_sqlite_schema_matrix_2025_12_17.tsv`
  - 署名グループ要約: `.serena/memories/deepghs_site_tags_sqlite_schema_summary_2025_12_17.md`

#### site_tags 全体: SQLite以外（CSV/JSON/Parquet）の構造差分
（`tags.csv` / `tags.json` / `tags.parquet` のヘッダ/キー/スキーマを走査）

- 生成物:
  - 行列（サイト→CSV/JSON/Parquetの構造）: `.serena/memories/deepghs_site_tags_non_sqlite_schema_matrix_2025_12_17.tsv`
  - 要約（形式ごとのユニーク構造数など）: `.serena/memories/deepghs_site_tags_non_sqlite_schema_summary_2025_12_17.md`
