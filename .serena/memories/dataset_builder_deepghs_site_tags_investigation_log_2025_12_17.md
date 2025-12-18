# deepghs/site_tags 調査ログ（Phase7前）

## 目的
- `deepghs/site_tags` を既存タグDBへ統合するための前提情報（列の意味、サイト数、alias/parent/type/countの意味と分布）を整理する。

## 決定事項（このログの前提）
- **TAG_FORMATS.format_name の例外:
- `en.pixiv.net` → `pixiv`
- `chan.sankakucomplex.com` → `sankaku`

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


### 2025-12-18 追加調査（曖昧点の確定）

- フィールド意味の確定版まとめを作成:
  - `.serena/memories/dataset_builder_deepghs_site_tags_field_semantics_2025_12_18.md`

#### `ambiguous` / `is_ambiguous` の実データ確認
- yande.re（moebooru系）: `ambiguous=1` は 37/132,180
  - 例: `buruma`, `bloomers`
- konachan.com: `ambiguous=1` は 190/93,713
  - 例: `no`, `art`, `big`
- hypnohub.net: `ambiguous=1` は 36/58,633
  - 例: `cat_girl`, `story`, `progress_indicator`

暫定結論:
- いずれも「曖昧語/一般語で衝突しやすい」系のフラグとして妥当。
- 本タグDB用途では必須ではないので優先度低（必要になったら導入）。

#### `cached_related` / `cached_related_expires_on` の意味（lolibooru.moe）
- `cached_related` は `tag,count,tag,count,...` の形式で、共起/関連タグのキャッシュ。
- `cached_related_expires_on` はそのキャッシュ有効期限。
- e621の `related_tags` と同系統だが表現が異なる（空間区切り vs カンマ区切り）。

#### Sankaku（chan.sankakucomplex.com）列の意味
- `pool_count` / `series_count` が存在。
- `parent_ids` / `child_ids` は TEXTだが内容は配列（例: `[542, 4067, ...]`）。
- `parents(tag_id,parent_id)` / `children(tag_id,child_id)` テーブルがあり、配列を正規化した形。
- `relations` テーブルは存在するが、このスナップショットでは空。

#### anime-pictures.net の `num` / `num_pub`
- 149,065行中:
  - `num > num_pub`: 21,827
  - `num < num_pub`: 311（少数の不整合）
  - `num = num_pub`: 126,927
暫定:
- count採用は `max(num,num_pub)` が安全。

#### wallhaven.cc カテゴリ
- `category_id/category_name` の組み合わせが多く、`TAG_TYPE_FORMAT_MAPPING` の入力に使える。



#### anime-pictures.net: alias/parent の参照
- `alias!=0`: 4,119 / 149,065
- `parent!=0`: 47,222 / 149,065
- `alias`/`parent` が指すIDは全て `tags.id` に存在（孤立参照0）

#### gelbooru.com: tag_aliases の注意点
- `tag_aliases(alias, tag)` は存在するが、`tag='bad_tag'` のような無効タグ吸い込みが混在。
- 孤立参照が非常に多い（alias/targetの多くが tags.name に存在しない）。
  - `tag` が tags に存在しない: 12,014
  - `alias` が tags に存在しない: 18,672

#### zerochan.net: strict
- `strict` は 0/1 ではなく広い整数分布を取る（意味は未確定）。
- 現用途では取り込み不要として後回し。


#### e621.net: tag_aliases の注意点（数値）
- `tag_aliases` total: 70,547
- `tag`（置換先）が tags に存在しない: 12,369
- `alias`（別名）が tags に存在しない: 63,157
- `invalid_tag` のような無効タグ吸い込み先が混在する。


### 2025-12-18: type/category 対応表を追加
- `.serena/memories/dataset_builder_deepghs_site_tags_type_category_mappings_2025_12_18.md`
  - サイト別のtype/categoryコード表 + 公式URL（あるもの） + 実データ根拠（上位タグ例）
  - invalid_tag/bad_tag/orphan alias の運用方針案も併記

### 2025-12-18: danbooru.donmai.us の tag_aliases ダブルチェック
- `tag_aliases(alias TEXT, tag TEXT)` は `alias -> tag`（別名 -> 推奨/正規タグ）の対応
- `tag_aliases` total: 52,496
  - `tag` が `tags.name` に存在しない: 10
  - `alias` が `tags.name` に存在しない: 42（alias文字列が tags テーブルに居ないのは通常挙動）
- `bad_tag` / `invalid_tag` のような吸い込み先は、少なくとも `tag_aliases.tag` には見当たらない
