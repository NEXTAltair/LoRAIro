# deepghs/site_tags: SQLite schema summary

- site root: `C:\LoRAIro\external_sources\site_tags`
- sqlite dbs found: 18
- unique schema signatures: 12
- matrix: `C:\LoRAIro\.serena\memories\deepghs_site_tags_sqlite_schema_matrix_2025_12_17.tsv`

## Signature groups

### 21db0d966809397f8cddd86e352c26f3be00e997 (3 sites)
- example: `hypnohub.net`
- sites:
  - `hypnohub.net`
  - `rule34.xxx`
  - `xbooru.com`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, type, count, name, ambiguous, id

### 4f167646818c0e5589fb47027e794c2203632a8d (3 sites)
- example: `booru.allthefallen.moe`
- sites:
  - `booru.allthefallen.moe`
  - `danbooru.donmai.us`
  - `safebooru.donmai.us`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, id, name, post_count, category, created_at, updated_at, is_deprecated, words

### f808a8725d94c7dd0c00ba0f5cbacc94c8351449 (3 sites)
- example: `konachan.com`
- sites:
  - `konachan.com`
  - `konachan.net`
  - `yande.re`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, id, name, count, type, ambiguous

### 064e075251ad8b333851f0b2b2c57b31011a813c (1 sites)
- example: `anime-pictures.net`
- sites:
  - `anime-pictures.net`

Tables:
- `tags`: index, id, tag, tag_ru, tag_jp, num, num_pub, type, description_en, description_ru, description_jp, alias, parent, views

### 4540c355d3bfe7b1c16cc5c0f5efd060c326ebcf (1 sites)
- example: `chan.sankakucomplex.com`
- sites:
  - `chan.sankakucomplex.com`

Tables:
- `children`: index, tag_id, child_id
- `parents`: index, tag_id, parent_id
- `relations`: index, tag_id, related_id
- `tags`: index, id, name, type, post_count, pool_count, series_count, rating, version, parent_ids, child_ids, related_ids, trans_en, trans_ja, trans_ru, trans_pt, trans_zh-CN, trans_fr, trans_it, trans_ko, trans_vi, trans_zh-HK, trans_de, trans_es, trans_th

### 599cd6a444596297c2dcbfd4b6f1b6b7b1154150 (1 sites)
- example: `en.pixiv.net`
- sites:
  - `en.pixiv.net`

Tables:
- `tags`: index, name, wiki_url, updated_at, views, posts, checklists, is_anime, is_manga, is_novel, is_game, is_figure, is_music, is_art, is_design, is_general, is_person, is_character, is_quote, is_event, is_doujin, trans_ja, trans_ja_wiki_url

### 61dbb638a52fe63ad3038a840015ea944c2fa63f (1 sites)
- example: `wallhaven.cc`
- sites:
  - `wallhaven.cc`

Tables:
- `tags`: index, name, id, category_name, category_id, posts, views, subscriptions

### 6abcb1f22df2e9a4035928393edd3cddf6e47d28 (1 sites)
- example: `zerochan.net`
- sites:
  - `zerochan.net`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, tag, type, parent, total, strict, children_count, parent_count

### 8ce58f355c9b986fe3de47ff1015f85bb9cc811d (1 sites)
- example: `lolibooru.moe`
- sites:
  - `lolibooru.moe`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, id, name, post_count, cached_related, cached_related_expires_on, tag_type, is_ambiguous

### 8cef464b452615fe63357def496db0a08dbcc07b (1 sites)
- example: `gelbooru.com`
- sites:
  - `gelbooru.com`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, name, count, type, is_ambiguous

### b02dbd059f3bd06495e3ce80c63de05dc13d10e7 (1 sites)
- example: `e621.net`
- sites:
  - `e621.net`

Tables:
- `tag_aliases`: index, alias, tag
- `tags`: index, id, name, post_count, related_tags, related_tags_updated_at, category, is_locked, created_at, updated_at

### ea96b914699b1992297598429079e6bed2070667 (1 sites)
- example: `pixiv.net`
- sites:
  - `pixiv.net`

Tables:
- `tags`: index, name, wiki_url, updated_at, views, posts, checklists, is_anime, is_manga, is_novel, is_game, is_figure, is_music, is_art, is_design, is_general, is_person, is_character, is_quote, is_event, is_doujin
