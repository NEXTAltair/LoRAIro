
CC4版（deepghs/site_tags）統合の実装: external_sources/site_tags/*/tags.sqlite を SiteTagsAdapter で読み、TAGS/TAG_STATUS/TAG_USAGE_COUNTS/TAG_TRANSLATIONS に追記する。
Sankaku の trans_zh-CN 等の列名に '-' が含まれるため、SELECT時は列名を必ず識別子クォートする。
master_data で format_id 4-18 を site_tags 用に予約し、TAG_TYPE_FORMAT_MAPPING はサイトの category/type 値をそのまま type_id として保持（不明は -1→後段レポート）。
TAG_STATUS に deprecated/deprecated_at/source_created_at を追加し、upsert は値が変わるときだけ更新する。
既存DBには migrations/2025_12_18_add_tag_status_deprecated_and_source_created_at.sql を一回適用して列追加が必要。
