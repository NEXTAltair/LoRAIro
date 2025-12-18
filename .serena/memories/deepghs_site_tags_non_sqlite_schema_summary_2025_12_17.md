# deepghs/site_tags: Non-SQLite format schema summary

- site root: `C:\LoRAIro\external_sources\site_tags`
- sites scanned: 19
- output matrix: `C:\LoRAIro\.serena\memories\deepghs_site_tags_non_sqlite_schema_matrix_2025_12_17.tsv`

## File counts
- tags.csv: 18
- tags.json: 18
- tags.parquet: 14

## Unique schema counts
- csv unique headers: 12
- json unique keysets: 10
- parquet unique schemas: 9

## CSV headers (top groups)

### 3 sites
- `konachan.com`
- `konachan.net`
- `yande.re`

Schema:
`id|name|count|type|ambiguous`

### 3 sites
- `booru.allthefallen.moe`
- `danbooru.donmai.us`
- `safebooru.donmai.us`

Schema:
`id|name|post_count|category|created_at|updated_at|is_deprecated|words`

### 3 sites
- `hypnohub.net`
- `rule34.xxx`
- `xbooru.com`

Schema:
`type|count|name|ambiguous|id`

### 1 sites
- `lolibooru.moe`

Schema:
`id|name|post_count|cached_related|cached_related_expires_on|tag_type|is_ambiguous`

### 1 sites
- `e621.net`

Schema:
`id|name|post_count|related_tags|related_tags_updated_at|category|is_locked|created_at|updated_at`

### 1 sites
- `chan.sankakucomplex.com`

Schema:
`id|name|type|post_count|pool_count|series_count|rating|version|parent_ids|child_ids|related_ids|trans_en|trans_ja|trans_ru|trans_pt|trans_zh-CN|trans_fr|trans_it|trans_ko|trans_vi|trans_zh-HK|trans_de|trans_es|trans_th`

### 1 sites
- `anime-pictures.net`

Schema:
`id|tag|tag_ru|tag_jp|num|num_pub|type|description_en|description_ru|description_jp|alias|parent|views`

### 1 sites
- `gelbooru.com`

Schema:
`name|count|type|is_ambiguous`

### 1 sites
- `wallhaven.cc`

Schema:
`name|id|category_name|category_id|posts|views|subscriptions`

## JSON keysets (top groups)

### 6 sites
- `hypnohub.net`
- `konachan.com`
- `konachan.net`
- `rule34.xxx`
- `xbooru.com`
- `yande.re`

Schema:
`ambiguous|count|id|name|type`

### 3 sites
- `booru.allthefallen.moe`
- `danbooru.donmai.us`
- `safebooru.donmai.us`

Schema:
`category|created_at|id|is_deprecated|name|post_count|updated_at|words`

### 2 sites
- `en.pixiv.net`
- `pixiv.net`

Schema:
`checklists|is_anime|is_art|is_character|is_design|is_doujin|is_event|is_figure|is_game|is_general|is_manga|is_music|is_novel|is_person|is_quote|name|posts|updated_at|views|wiki_url`

### 1 sites
- `anime-pictures.net`

Schema:
`alias|description_en|description_jp|description_ru|id|num|num_pub|parent|tag|tag_jp|tag_ru|type|views`

### 1 sites
- `lolibooru.moe`

Schema:
`cached_related|cached_related_expires_on|id|is_ambiguous|name|post_count|tag_type`

### 1 sites
- `wallhaven.cc`

Schema:
`category_id|category_name|id|name|posts|subscriptions|views`

### 1 sites
- `e621.net`

Schema:
`category|created_at|id|is_locked|name|post_count|related_tags|related_tags_updated_at|updated_at`

### 1 sites
- `chan.sankakucomplex.com`

Schema:
`child_ids|id|name|parent_ids|pool_count|post_count|rating|related_ids|series_count|trans_en|trans_ja|type|version`

### 1 sites
- `zerochan.net`

Schema:
`children_count|parent|parent_count|strict|tag|total|type`

## Parquet schemas (top groups)

### 3 sites
- `konachan.com`
- `konachan.net`
- `yande.re`

Schema:
`id:int64|name:string|count:int64|type:int64|ambiguous:bool`

### 3 sites
- `hypnohub.net`
- `rule34.xxx`
- `xbooru.com`

Schema:
`type:int64|count:int64|name:string|ambiguous:bool|id:int64`

### 2 sites
- `danbooru.donmai.us`
- `safebooru.donmai.us`

Schema:
`id:int64|name:string|post_count:int64|category:int64|created_at:timestamp[us, tz=-05:00]|updated_at:timestamp[us, tz=-04:00]|is_deprecated:bool|words:string`

### 1 sites
- `e621.net`

Schema:
`id:int64|name:string|post_count:int64|related_tags:string|related_tags_updated_at:string|category:int64|is_locked:bool|created_at:timestamp[us, tz=-05:00]|updated_at:timestamp[us, tz=-04:00]`

### 1 sites
- `anime-pictures.net`

Schema:
`id:int64|tag:string|tag_ru:string|tag_jp:string|num:int64|num_pub:int64|type:int64|description_en:string|description_ru:string|description_jp:string|alias:int64|parent:int64|views:int64`

### 1 sites
- `gelbooru.com`

Schema:
`name:string|count:int64|type:string|is_ambiguous:bool`

### 1 sites
- `wallhaven.cc`

Schema:
`name:string|id:int64|category_name:string|category_id:int64|posts:int64|views:int64|subscriptions:int64`

### 1 sites
- `pixiv.net`

Schema:
`name:string|wiki_url:string|updated_at:timestamp[ns]|views:int64|posts:int64|checklists:int64|is_anime:bool|is_manga:bool|is_novel:bool|is_game:bool|is_figure:bool|is_music:bool|is_art:bool|is_design:bool|is_general:bool|is_person:bool|is_character:bool|is_quote:bool|is_event:bool|is_doujin:bool`

### 1 sites
- `en.pixiv.net`

Schema:
`name:string|wiki_url:string|updated_at:timestamp[ns]|views:int64|posts:int64|checklists:int64|is_anime:bool|is_manga:bool|is_novel:bool|is_game:bool|is_figure:bool|is_music:bool|is_art:bool|is_design:bool|is_general:bool|is_person:bool|is_character:bool|is_quote:bool|is_event:bool|is_doujin:bool|trans_ja:string|trans_ja_wiki_url:string`
