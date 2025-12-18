# deepghs/site_tags: フィールド意味まとめ（曖昧点つぶし）

策定日: 2025-12-18

目的: `deepghs/site_tags` を既存のタグDBへ統合する前提として、**サイトごとの列の意味**と**既存スキーマへの落とし込み**を確定させる。

> 参照: `.serena/memories/deepghs_site_tags_sqlite_schema_matrix_2025_12_17.tsv` / `.serena/memories/deepghs_site_tags_non_sqlite_schema_matrix_2025_12_17.tsv`

---

## 共通方針（このプロジェクト側へのマッピング）

- `format`（ホスティングサイト）:
  - `TAG_FORMATS.format_name` は「サイト名」へ寄せる。
  - 原則: ドメインのドット前（例 `anime-pictures.net`→`anime-pictures`、`danbooru.donmai.us`→`danbooru`）
  - 例外:
  - `en.pixiv.net` は `pixiv` として扱う（`en` は採用しない）
  - `chan.sankakucomplex.com` は `sankaku` として扱う（`chan` は採用しない）

- `tag`（正規タグ） vs `source_tag`（ソースタグ）:
  - site_tags 側は基本 `name/tag` が「サイトのタグ文字列」なので **source_tag** 相当。
  - `TAGS.tag` は本プロジェクトの正規化後文字列（既存仕様）を入れる。

- `count`（使用回数）:
  - サイト側の `post_count` / `count` / `posts` / `total` / `num/num_pub` のいずれかを **TAG_USAGE_COUNTS.count** に入れる。
  - `num` と `num_pub` が両方ある場合は不整合が少数存在するため、暫定は `max(num, num_pub)` を採用（矛盾を吸収）。

- `count観測日時`:
  - サイト側の `updated_at` 等がある場合はそれを **“そのcount値の観測日時（ソース側の日時）”** として `TAG_USAGE_COUNTS.created_at/updated_at` に入れる。
  - サイト側日時が取れない場合は、まず **ベースDB（例: `genai-image-tag-db-cc0.sqlite`）に既に入っている日時を保持**する。
  - それも無い（新規作成した行など）場合のみ、ビルド時刻（挿入時刻）を入れる。

- `type/category`:
  - サイト固有のカテゴリコード/文字列（`category`, `type`, `tag_type`, `category_id`, boolean flags 等）を `TAG_TYPE_FORMAT_MAPPING` の入力として利用し、`TAG_STATUS.type_id` を決める。
  - 型の複数付与（1タグに複数type）は将来拡張候補だが優先度は低（現状は単一typeで運用）。

- `alias`:
  - site_tags 側の `tag_aliases` は、基本「別名→推奨名」の置換関係。
  - 本プロジェクトでは `TAG_STATUS(alias=true, preferred_tag_id != tag_id)` で表現する。

- `parent/child/related`:
  - サイトによって “タグ階層（親子）” や “関連タグ（共起）” が入っている。
  - 現行DBスキーマにそのまま入れる設計が無いため、導入するなら別テーブル追加（Phase7以降で検討）。

- `ambiguous`:
  - 「曖昧（曖昧語/汎用語で衝突しやすい等）」を示すフラグ。
  - 現行DB用途では必須ではない（優先度低、必要なら将来別途）。

- `description/wiki`:
  - 本プロジェクトの用途では優先度低（現状不要）。

---

## サイト別: スキーマと列意味

### danbooru.donmai.us / safebooru.donmai.us / booru.allthefallen.moe（Danbooru系）

- `tags`:
  - `id`: タグID（サイト内）
  - `name`: タグ名（source_tag）
  - `post_count`: 使用回数
  - `category`: タイプID（整数）
  - `created_at`, `updated_at`: サイト側の更新時刻
  - `is_deprecated`: 非推奨フラグ（aliasとは別軸）
  - `words`: 検索用語（サイト独自）
- `tag_aliases`:
  - `alias`: 別名
  - `tag`: 推奨名（置換先）

重要ポイント:
- Danbooruの `is_deprecated` は **必ずしも置換先（alias）を持たない**。
  - 実データ検証（`danbooru.donmai.us/tags.sqlite`）
    - `is_deprecated=1`: 3,510
    - deprecatedだが `tag_aliases.alias=tags.name` が無い: 3,221
- Danbooruの `tag_aliases` は基本的に tags と整合しているが、少数の例外がある（記号/エスケープ等）。
  - `tag_aliases` total: 52,496
  - `tag` が tags に存在しない: 10
  - `alias` が tags に存在しない: 42



### e621.net

- `tags`:
  - `id`, `name`, `post_count`, `category`, `created_at`, `updated_at`, `is_locked`
  - `related_tags`: 共起タグのキャッシュ文字列（後述）
  - `related_tags_updated_at`: 上記の更新時刻
- `tag_aliases`: `alias`, `tag`（別名→推奨名）

`related_tags` の形式:
- スペース区切りのペア列: `"tag count tag count ..."`
- 先頭に自分自身が入ることがある。

注意点:
- `tag_aliases` は tags 表に存在しない名前を参照することがある（履歴/削除/invalidの可能性）。
  - 実データ（e621.net/tags.sqlite）:
    - `tag_aliases` total: 70,547
    - `tag`（置換先）が tags に存在しない: 12,369
    - `alias`（別名）が tags に存在しない: 63,157
  - `tag='invalid_tag'` のような「無効タグ吸い込み先」が混在。
  - 取り込み時は「参照先が存在しないalias」は基本スキップし、別途レポートに回すのが安全。


### gelbooru.com

- `tags`（SQLiteでもCSVでも同様の情報）:
  - `name`: タグ名
  - `count`: 使用回数
  - `type`: 文字列カテゴリ（例: `general`, `copyright`）
  - `is_ambiguous`: 曖昧フラグ
- `tag_aliases`: `alias`, `to`（JSON/CSV側で確認できる）


### moebooru系（konachan.com / konachan.net / yande.re / rule34.xxx / xbooru.com / hypnohub.net）

- `tags`:
  - `id`（サイト内IDがある場合）
  - `name`: タグ名
  - `count`: 使用回数
  - `type`: 整数カテゴリ
  - `ambiguous`（or `is_ambiguous`）: 曖昧フラグ
- `tag_aliases`:
  - `alias` → `to`（または `tag`）

`ambiguous` の実データ例:
- yande.re: `buruma`, `bloomers` など（汎用語で曖昧）
- konachan.com: `no`, `art`, `big` など（短すぎ・一般語）


### chan.sankakucomplex.com（Sankaku系・多言語/階層あり）

- `tags`:
  - `id`, `name`
  - `type`: 整数カテゴリ
  - `post_count`: 使用回数
  - `pool_count`: poolに含まれる回数（タグが登場するpool数）
  - `series_count`: seriesに含まれる回数
  - `rating`: 文字列（例: `e`, `q` 等）
  - `version`: 数値（用途は不明瞭、現用途では不要）
  - `parent_ids`, `child_ids`, `related_ids`: TEXTだが中身は配列（例: `[542, 4067, ...]`）
  - `trans_*`: 多言語翻訳（`trans_ja`, `trans_zh-CN`, `trans_ko` 等）

- `parents` / `children`:
  - `parents(tag_id, parent_id)`
  - `children(tag_id, child_id)`
  - `tags.parent_ids/child_ids` のエッジを正規化したテーブル版（こちらの方が扱いやすい）

- `relations`:
  - テーブルはあるが、今回のスナップショットでは空。


### anime-pictures.net（AP系・num/num_pub/alias(parent)がID参照）

- `tags`:
  - `id`
  - `tag`（英語）
  - `tag_jp`, `tag_ru`（翻訳）
  - `num`, `num_pub`（count系）
  - `type`（整数カテゴリ）
  - `alias`（整数: 別名が参照する推奨タグIDの可能性）
  - `parent`（整数: 親IDの可能性）
  - `views`（閲覧回数）

`num` / `num_pub` の実データ観察:
- `num > num_pub` が圧倒的多数（例: `girl 705348 vs 685117`）
- ただし `num < num_pub` も少数存在（311/149065）→ データ品質の揺れがある。
- 暫定のcount採用は `max(num,num_pub)` が安全。

`type`（anime-pictures推定）:
- 4: artist（例: `sakimichan`, `tony taka`）
- 1: character（例: `hatsune miku`）
- 3: copyright/series（例: `fate (series)`）
- 0: meta/system（例: `tagme`, `private`）
- 2/7: general（記述語が多い）
- 5/6: 未確定（要追加調査）


### lolibooru.moe

- `tags`:
  - `id`, `name`, `post_count`
  - `tag_type`（整数カテゴリ）
  - `is_ambiguous`（曖昧フラグ）
  - `cached_related`: 関連タグキャッシュ（後述）
  - `cached_related_expires_on`: キャッシュ有効期限

`cached_related` の形式:
- カンマ区切りのペア列: `"tag,count,tag,count,..."`
- `cached_related_expires_on` を過ぎたら再計算される想定のキャッシュ。
- e621の `related_tags` と同系統（共起関係）だが、区切り/表現が違う。


### wallhaven.cc

- `tags`:
  - `id`, `name`
  - `category_id`, `category_name`
  - `posts`（使用回数）
  - `views`, `subscriptions`

補足:
- `category_id/category_name` は、`TAG_TYPE_FORMAT_MAPPING` に落とすのに使える。


### pixiv.net / en.pixiv.net

- `tags`:
  - `name`（タグ）
  - `posts`, `views`
  - `updated_at`
  - `wiki_url`
  - `is_anime/is_manga/...`（複数の boolean フラグ）
  - en版のみ `trans_ja`, `trans_ja_wiki_url` がある

補足:
- カテゴリが **単一IDではなくフラグ**（複数typeになり得る）。
- 現行DBでは単一type運用なので、導入は後回しでもよい。


### zerochan.net

- `tags`:
  - `tag`
  - `type`: 文字列カテゴリ（例: `mangaka`, `character`, `series`, `theme` など）
  - まれに `type` がカンマ区切りで複数（例: `game,theme`）
  - `total`: 使用回数
  - `parent`: カテゴリ名のような値（例: `Mangaka`, `Symbols and Shapes`, 作品名など）
  - `children_count`, `parent_count`
  - `strict`: 0/1/3など（意味は不明瞭、現用途では不要）

---

## 現時点で「取り込み不要」判定

- `ambiguous/is_ambiguous`
- `description_*` / `wiki_url` などの説明系
- `views` / `subscriptions`（用途が明確になったら）
- `pool_count` / `series_count` / `rating` / `version`（Sankaku固有、必要になったら）



---

## 追加観察（2025-12-18）

### anime-pictures.net: alias/parent の参照整合性

- `alias!=0`: 4,119 / 149,065
- `parent!=0`: 47,222 / 149,065
- 参照整合性:
  - `alias` が指す `id` は全て `tags.id` に存在（孤立参照 0）
  - `parent` が指す `id` も全て存在（孤立参照 0）

解釈:
- `alias` は **「このタグは別名（alias）で、推奨タグIDは alias列」** を意味する可能性が高い。
- `parent` は **「このタグの上位グループ（作品/大分類など）のタグID」** を意味する可能性が高い。

`type` 5/6 の追加推定（上位タグ観察）:
- type 5: 大規模フランチャイズ/ゲーム/作品群（例: `touhou`, `genshin impact`, `azur lane`）
- type 6: メタ的な大分類/制作会社/領域（例: `original`, `vocaloid`, `studio pierrot`, `hololive`）


### gelbooru.com: tag_aliases の品質

- `tag_aliases(alias, tag)` は **別名→推奨名** の形だが、以下の特徴がある。
  - `tag` 側が `tags.name` に存在しない行が多い（孤立参照が多い）
  - `alias` 側も `tags.name` に無い行が大半
  - `tag='bad_tag'` のような「無効タグの吸い込み先」っぽい値が存在

実データ（gelbooru.com/tags.sqlite）:
- `tag` が tags に存在しない: 12,014
- `alias` が tags に存在しない: 18,672

取り込み時の推奨:
- `tag='bad_tag'` は推奨名として扱わず、**invalidタグの除外/クリーンアップ用途**として別扱いする。
- `preferred(tag)` が存在しない alias 行は基本スキップ（必要なら別途レポート）。


### zerochan.net: strict

- `strict` は 0/1 ではなく、広い整数分布を取る（例: 0 が最多だが 300台なども存在）。
- 現状は意味が確定できないため、**現用途では取り込み不要（後回し）**。
